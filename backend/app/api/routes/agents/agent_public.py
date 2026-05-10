"""AgentPublic SSE endpoint.

Public, read-only counterpart to the member /agent/turn route. This route does
not run the router and does not touch member Agent persistence.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request, Response
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

from ....agents.general.agent_public import (
    USAGE_LIMITS_PUBLIC,
    agent_public,
    compose_system_prompt_public,
    skill_registry_public,
)
from ....agents.general.models_public import GeneralPublicDeps
from ....agents.general.prompts_public import SNAPSHOT_PUBLIC_TEMPLATE
from ....agents.runtime.history import (
    replace_system_prompt,
    strip_skill_bodies_from_dumped_history,
    strip_snapshots_from_dumped_history,
    truncate_to_last_turns,
)
from ....agents.runtime.store_public import AgentTurnPublicRecord, agent_turn_store_public
from ....models.agents.public import AgentTurnPublicRequest
from ..auth import get_optional_extended_user
from ._shared import _detect_user_language, _extract_error_info, _session_unavailable_response, _sse
from .identity_public import AgentIdentityPublic, ensure_visitor_cookie_public, resolve_identity_public
from .rate_limit_public import PublicRateLimitIdentity, rate_limiter_public

log = logging.getLogger(__name__)
agent_public_router = r = APIRouter(prefix="/agent-public")

_ALLOWED_PUBLIC_TOOLS = {"view_skill_public", "lookup_meeting_public"}


def _current_skill_sources(tool_trace: list[dict]) -> list[str]:
    sources: list[str] = []
    for trace in tool_trace:
        if trace.get("name") != "view_skill_public" or trace.get("status") != "ok":
            continue
        result = trace.get("result")
        skill = result.get("skill") if isinstance(result, dict) else None
        if not isinstance(skill, str):
            args = trace.get("args")
            skill = args.get("name") if isinstance(args, dict) else None
        if isinstance(skill, str) and skill not in sources:
            sources.append(skill)
    return sources


def _current_meeting_lookup_summaries(tool_trace: list[dict]) -> list[dict]:
    summaries: list[dict] = []
    for trace in tool_trace:
        if trace.get("name") != "lookup_meeting_public" or trace.get("status") != "ok":
            continue
        result = trace.get("result")
        if not isinstance(result, dict):
            continue
        summaries.append(
            {
                "filters": trace.get("args") or {},
                "total_matches": result.get("total_matches", 0),
                "limit_clamped": bool(result.get("limit_clamped")),
            }
        )
    return summaries


def _public_domain_payload(tool_trace: list[dict]) -> dict:
    payload: dict = {}
    skill_sources = _current_skill_sources(tool_trace)
    if skill_sources:
        payload["skill_sources"] = skill_sources
    lookups = _current_meeting_lookup_summaries(tool_trace)
    if lookups:
        payload["meeting_lookup"] = lookups
    return payload


@r.post("/visitor")
async def visitor_public(request: Request, response: Response):
    visitor_id = ensure_visitor_cookie_public(request, response)
    return {"visitor_id": visitor_id}


@r.post("/turn")
async def agent_turn_public(
    req: AgentTurnPublicRequest,
    request: Request,
    user=Depends(get_optional_extended_user),
):
    identity = resolve_identity_public(request, user)

    if not await agent_turn_store_public.verify_session_access(
        req.session_id,
        channel=identity.channel,
        visitor_key=identity.visitor_key,
    ):
        return _session_unavailable_response()

    try:
        await rate_limiter_public.check(
            PublicRateLimitIdentity(channel=identity.channel, visitor_key=identity.visitor_key),
            session_id=req.session_id,
        )
    except Exception:
        # HTTPException(429) should propagate with the correct status. Other
        # rate-limit storage failures should not run the model.
        raise

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            async for chunk in _agent_turn_public_stream(req, identity):
                yield chunk
        except asyncio.CancelledError:
            log.info("AgentPublic turn cancelled by client: %s", req.session_id)
            raise
        except Exception as e:
            message, recoverable = _extract_error_info(e)
            try:
                from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded

                known = isinstance(e, (ModelHTTPError, UsageLimitExceeded))
            except ImportError:
                known = False
            if known:
                log.warning("AgentPublic turn failed for session %s: %s", req.session_id, message)
            else:
                log.exception("AgentPublic turn failed for session %s", req.session_id)
            yield _sse("error", {"reason": "agent_error", "recoverable": recoverable, "message": message})
        finally:
            await rate_limiter_public.release(session_id=req.session_id)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _agent_turn_public_stream(
    req: AgentTurnPublicRequest,
    identity: AgentIdentityPublic,
) -> AsyncIterator[bytes]:
    tail_seq, history_json = await agent_turn_store_public.load(
        req.session_id,
        channel=identity.channel,
        visitor_key=identity.visitor_key,
    )
    next_seq = tail_seq + 1

    composed_system_prompt = compose_system_prompt_public()
    if history_json:
        prior = ModelMessagesTypeAdapter.validate_python(history_json)
        prior = replace_system_prompt(prior, composed_system_prompt)
        history = truncate_to_last_turns(prior)
        storage_prior = history
    else:
        history = []
        storage_prior = []

    language_hint = f"[Reply language] {_detect_user_language(req.user_message)}\n"
    today_iso = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    deps = GeneralPublicDeps(
        session_id=req.session_id,
        current_user_message=req.user_message,
        today=today_iso,
        skill_registry=skill_registry_public,
    )
    prompt = SNAPSHOT_PUBLIC_TEMPLATE.format(
        next_seq=next_seq,
        tail_seq=tail_seq,
        user_message=req.user_message,
        language_hint=language_hint,
        today=today_iso,
    )

    tool_call_args: dict[str, dict] = {}
    assistant_text_chunks: list[str] = []
    tool_trace: list[dict] = []

    async with agent_public.iter(
        prompt,
        deps=deps,
        message_history=history,
        usage_limits=USAGE_LIMITS_PUBLIC,
    ) as run:
        async for node in run:
            if agent_public.is_model_request_node(node):
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
            elif agent_public.is_call_tools_node(node):
                async with node.stream(run.ctx) as tool_stream:
                    async for tool_event in tool_stream:
                        if isinstance(tool_event, FunctionToolCallEvent):
                            call_part: ToolCallPart = tool_event.part
                            if call_part.tool_name not in _ALLOWED_PUBLIC_TOOLS:
                                registered = {t.name for t in agent_public._function_toolset.tools.values()}
                                if call_part.tool_name in registered:
                                    raise RuntimeError(
                                        f"AgentPublic registered unauthorized tool {call_part.tool_name!r}"
                                    )
                                log.warning("AgentPublic hallucinated tool %r", call_part.tool_name)
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
                            if call_ctx.get("name") == "view_skill_public" and not is_retry:
                                body_len = len(result_part.content) if isinstance(result_part.content, str) else 0
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
                            yield _sse(
                                "tool_call_end",
                                {
                                    "id": tool_event.tool_call_id,
                                    "status": status,
                                    "result": traced_result,
                                },
                            )

    final_result = run.result
    final_text = final_result.output if final_result else ""
    new_msgs = list(final_result.new_messages()) if final_result else []
    final_msgs = ModelMessagesTypeAdapter.dump_python(list(storage_prior) + new_msgs, mode="json")
    final_msgs = strip_snapshots_from_dumped_history(final_msgs)
    final_msgs = strip_skill_bodies_from_dumped_history(final_msgs)
    assistant_text = "".join(assistant_text_chunks) or final_text
    domain_payload = _public_domain_payload(tool_trace)

    await agent_turn_store_public.save_turn(
        req.session_id,
        channel=identity.channel,
        visitor_key=identity.visitor_key,
        turn=AgentTurnPublicRecord(
            seq=next_seq,
            agent_kind="general",
            user_message=req.user_message,
            assistant_text=assistant_text,
            tool_trace=tool_trace,
            history_cursor=final_msgs,
            domain_payload=domain_payload,
        ),
    )
    yield _sse(
        "done",
        {
            "seq": next_seq,
            "final_text": final_text,
            "sources": domain_payload.get("skill_sources", []),
        },
    )
