"""General Q&A agent SSE endpoint.

Read-only counterpart to /meeting-agent/turn and /statistics-agent/turn.
Same wire format (SSE events: assistant_text, thinking, tool_call_start,
tool_call_end, done, error) so the frontend reuses the existing
chat-panel plumbing.

Differences from the statistics route:
  - No image upload, no agenda_snapshot (knowledge Q&A only).
  - Composes the system prompt with skill-registry manifest + always-loaded
    bodies + load-skill instruction before `replace_system_prompt`.
  - Runs both `strip_snapshots_from_dumped_history` (defensive — no
    snapshot wrapper is produced here, but composition with the unified
    history makes it cheap insurance) and the new
    `strip_skill_bodies_from_dumped_history` to keep view_skill bodies
    out of the persisted history_cursor.
"""

import asyncio
import logging
from datetime import datetime
from typing import AsyncIterator
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessagesTypeAdapter,
    PartDeltaEvent,
    PartStartEvent,
    RetryPromptPart,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
)

from ....agents.general.agent import USAGE_LIMITS, agent, skill_registry
from ....agents.general.models import GeneralDeps
from ....agents.general.prompts import GENERAL_SYSTEM_PROMPT, LOAD_SKILL_INSTRUCTION, SNAPSHOT_TEMPLATE
from ....agents.runtime.contracts import AgentKind, RouteKind
from ....agents.runtime.history import (
    prepare_history_for_agent,
    strip_skill_bodies_from_dumped_history,
    strip_snapshots_from_dumped_history,
)
from ....agents.runtime.policy import AgentPolicyError, require_tool_allowed
from ....agents.runtime.store import AgentTurnRecord, agent_turn_store
from ....models.agents.general import GeneralAgentTurnRequest
from ..auth import get_current_extended_user
from ._shared import (
    _detect_user_language,
    _extract_error_info,
    _session_unavailable_response,
    _sse,
    require_member,
)

log = logging.getLogger(__name__)
general_agent_router = r = APIRouter(prefix="/general-agent")


def _compose_system_prompt() -> str:
    """Build the per-turn system prompt = base + always-loaded skills +
    skill manifest + load-skill instruction.

    All four parts are static-per-process: skill registry is built at
    module load. Composition is just string concat, but kept in a helper
    so tests can swap the registry.
    """
    parts = [GENERAL_SYSTEM_PROMPT]
    always = skill_registry.render_always_loaded()
    if always:
        parts.append(always)
    manifest = skill_registry.render_manifest()
    if manifest:
        parts.append(manifest)
        parts.append(LOAD_SKILL_INSTRUCTION)
    return "\n\n".join(parts)


def _current_skill_sources(tool_trace: list[dict]) -> list[str]:
    """Return successful view_skill names from the current turn only."""
    sources: list[str] = []
    for trace in tool_trace:
        if trace.get("name") != "view_skill" or trace.get("status") != "ok":
            continue
        result = trace.get("result")
        skill = result.get("skill") if isinstance(result, dict) else None
        if not isinstance(skill, str):
            args = trace.get("args")
            skill = args.get("name") if isinstance(args, dict) else None
        if isinstance(skill, str) and skill not in sources:
            sources.append(skill)
    return sources


@r.post("/turn")
async def general_agent_turn(
    req: GeneralAgentTurnRequest,
    user=Depends(get_current_extended_user),
):
    member = require_member(user)
    user_id = member.uid
    if not await agent_turn_store.verify_session_access(req.session_id, user_id=user_id):
        return _session_unavailable_response()

    composed_system_prompt = _compose_system_prompt()

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            tail_seq, history_json = await agent_turn_store.load(req.session_id, user_id=user_id)
            next_seq = tail_seq + 1

            history, storage_prior = prepare_history_for_agent(
                history_json or [],
                current_agent=AgentKind.GENERAL,
                system_prompt=composed_system_prompt,
            )
            language_hint = f"[Reply language] {_detect_user_language(req.user_message)}\n"
            today_iso = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
            deps = GeneralDeps(
                session_id=req.session_id,
                current_user_message=req.user_message,
                today=today_iso,
                skill_registry=skill_registry,
            )
            prompt = SNAPSHOT_TEMPLATE.format(
                next_seq=next_seq,
                tail_seq=tail_seq,
                user_message=req.user_message,
                language_hint=language_hint,
                today=today_iso,
            )

            tool_call_args: dict[str, dict] = {}
            assistant_text_chunks: list[str] = []
            tool_trace: list[dict] = []

            async with agent.iter(
                prompt,
                deps=deps,
                message_history=history,
                usage_limits=USAGE_LIMITS,
            ) as run:
                async for node in run:
                    if agent.is_model_request_node(node):
                        async with node.stream(run.ctx) as stream:
                            async for event in stream:
                                if isinstance(event, PartStartEvent):
                                    part = event.part
                                    if isinstance(part, TextPart) and part.content:
                                        assistant_text_chunks.append(part.content)
                                        yield _sse("assistant_text", {"chunk": part.content})
                                    elif isinstance(part, ThinkingPart) and part.content:
                                        yield _sse("thinking", {"chunk": part.content})
                                elif isinstance(event, PartDeltaEvent):
                                    delta = event.delta
                                    if isinstance(delta, TextPartDelta) and delta.content_delta:
                                        assistant_text_chunks.append(delta.content_delta)
                                        yield _sse("assistant_text", {"chunk": delta.content_delta})
                                    elif isinstance(delta, ThinkingPartDelta) and getattr(delta, "content_delta", None):
                                        yield _sse("thinking", {"chunk": delta.content_delta})
                    elif agent.is_call_tools_node(node):
                        async with node.stream(run.ctx) as tool_stream:
                            async for tool_event in tool_stream:
                                if isinstance(tool_event, FunctionToolCallEvent):
                                    call_part: ToolCallPart = tool_event.part
                                    # Same two-tier policy check as meeting/statistics:
                                    # registered-but-unauthorized fails closed (config bug);
                                    # names not registered at all fall through to Pydantic AI's
                                    # unknown-tool retry path (model hallucination).
                                    try:
                                        require_tool_allowed(AgentKind.GENERAL, call_part.tool_name)
                                    except AgentPolicyError as policy_err:
                                        registered = {t.name for t in agent._function_toolset.tools.values()}
                                        if call_part.tool_name in registered:
                                            raise
                                        log.warning(
                                            "general agent policy rejected unregistered tool %r "
                                            "(likely model hallucination): %s",
                                            call_part.tool_name,
                                            policy_err,
                                        )
                                    args = call_part.args_as_dict()
                                    tool_call_args[call_part.tool_call_id] = {
                                        "name": call_part.tool_name,
                                        "args": args,
                                    }
                                    yield _sse(
                                        "tool_call_start",
                                        {
                                            "id": call_part.tool_call_id,
                                            "name": call_part.tool_name,
                                            "args": args,
                                        },
                                    )
                                elif isinstance(tool_event, FunctionToolResultEvent):
                                    result_part = tool_event.result
                                    is_retry = isinstance(result_part, RetryPromptPart)
                                    call_ctx = tool_call_args.get(tool_event.tool_call_id, {})
                                    status = "retry" if is_retry else "ok"
                                    # tool_trace is persisted to agent_turns.tool_trace; for
                                    # view_skill the result body can be many KB. Store length
                                    # only — the body is reproducible from disk via the
                                    # registry, so persistence buys nothing.
                                    if call_ctx.get("name") == "view_skill" and not is_retry:
                                        body_len = (
                                            len(result_part.content) if isinstance(result_part.content, str) else 0
                                        )
                                        traced_result: object = {
                                            "skill": call_ctx.get("args", {}).get("name"),
                                            "body_length": body_len,
                                        }
                                    else:
                                        traced_result = result_part.content
                                    tool_trace.append(
                                        {
                                            "id": tool_event.tool_call_id,
                                            "name": call_ctx.get("name", ""),
                                            "args": call_ctx.get("args", {}),
                                            "status": status,
                                            "result": traced_result,
                                        }
                                    )
                                    # SSE to frontend: same compaction. Users don't read
                                    # raw markdown bodies in the chat; they read the
                                    # assistant's reply that synthesized them.
                                    sse_result = traced_result
                                    yield _sse(
                                        "tool_call_end",
                                        {
                                            "id": tool_event.tool_call_id,
                                            "status": status,
                                            "result": sse_result,
                                        },
                                    )

            final_result = run.result
            final_text = final_result.output if final_result else ""
            assistant_text_so_far = "".join(assistant_text_chunks)
            # Build saved cursor from the UNFILTERED prior + this turn's
            # new_messages, NOT from `final_result.all_messages()`. The
            # latter is built on top of the filtered model_view, so saving
            # it would permanently scrub other agents' tool-call audit out
            # of the shared `history_cursor`. Using new_messages() preserves
            # the full cross-agent history for future turns to load.
            new_msgs = list(final_result.new_messages()) if final_result else []
            final_msgs = ModelMessagesTypeAdapter.dump_python(list(storage_prior) + new_msgs, mode="json")
            final_msgs = strip_snapshots_from_dumped_history(final_msgs)
            final_msgs = strip_skill_bodies_from_dumped_history(final_msgs)
            assistant_text = "".join(assistant_text_chunks) or assistant_text_so_far or final_text
            skill_sources = _current_skill_sources(tool_trace)
            await agent_turn_store.save_turn(
                req.session_id,
                user_id=user_id,
                turn=AgentTurnRecord(
                    seq=next_seq,
                    agent_kind=AgentKind.GENERAL,
                    route=RouteKind.SPECIALIST,
                    user_message=req.user_message,
                    assistant_text=assistant_text,
                    tool_trace=tool_trace,
                    router_decision=req.router_decision or {},
                    history_cursor=final_msgs,
                    domain_payload={"skill_sources": skill_sources},
                ),
            )
            yield _sse(
                "done",
                {
                    "seq": next_seq,
                    "final_text": final_text,
                    "sources": skill_sources,
                },
            )
        except asyncio.CancelledError:
            log.info("general agent turn cancelled by client: %s", req.session_id)
            raise
        except Exception as e:
            message, recoverable = _extract_error_info(e)
            try:
                from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded

                known = isinstance(e, (ModelHTTPError, UsageLimitExceeded))
            except ImportError:
                known = False
            if known:
                log.warning("general agent turn failed for session %s: %s", req.session_id, message)
            else:
                log.exception("general agent turn failed for session %s", req.session_id)
            yield _sse(
                "error",
                {"reason": "agent_error", "recoverable": recoverable, "message": message},
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")
