"""Statistics agent SSE endpoint.

Read-only counterpart to /meeting-agent/turn. Same wire format (SSE
events: assistant_text, thinking, tool_call_start, tool_call_end, done,
error) so the frontend can reuse the existing chat-panel plumbing
behind a mode toggle.

Differences from the meeting agent route:
  - No image upload (stats agent doesn't accept attachments).
  - No agenda_snapshot in the request payload (stats is read-only).
  - No agenda_after / show_current addenda — there's no draft to
    render. Historical previews still get folded meta / intro / agenda
    blocks, shared with the meeting agent.
"""

import asyncio
import json
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

from ....agents.meeting.history import (
    replace_system_prompt,
    strip_snapshots_from_dumped_history,
    truncate_to_last_turns,
)
from ....agents.runtime.contracts import AgentKind, RouteKind
from ....agents.runtime.policy import require_tool_allowed
from ....agents.runtime.store import AgentTurnRecord, agent_turn_store
from ....agents.statistics.agent import USAGE_LIMITS, agent
from ....agents.statistics.models import StatsDeps
from ....agents.statistics.prompts import SNAPSHOT_TEMPLATE, STATS_SYSTEM_PROMPT
from ....models.agents.statistics import StatisticsAgentTurnRequest
from ....services.meeting_preview_markdown import render_preview_addendum
from ..auth import get_current_user

log = logging.getLogger(__name__)
statistics_agent_router = r = APIRouter(prefix="/statistics-agent")
_PREVIEW_TOOL_NAMES = {"preview_meeting"}


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


def _extract_error_info(e: Exception) -> tuple[str, bool]:
    try:
        from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
    except ImportError:
        return (str(e), True)
    if isinstance(e, UsageLimitExceeded):
        return (str(e), False)
    if isinstance(e, ModelHTTPError):
        body = e.body if isinstance(e.body, dict) else {}
        err = body.get("error") if isinstance(body, dict) else None
        msg = err.get("message") if isinstance(err, dict) else None
        if msg:
            return (f"[{e.status_code}] {msg}", True)
        return (f"Model HTTP error {e.status_code}", True)
    return (str(e), True)


def _detect_user_language(text: str) -> str:
    """Same heuristic the meeting agent uses — CJK majority → 'zh',
    otherwise 'en'. Per-turn detection so the model's reply language
    follows the user's current message regardless of session history."""
    if not text:
        return "en"
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if cjk == 0 and latin == 0:
        return "en"
    return "zh" if cjk > latin else "en"


def _all_preview_payloads(tool_trace: list[dict]) -> list[dict]:
    payloads: list[dict] = []
    for trace in tool_trace:
        if trace.get("name") not in _PREVIEW_TOOL_NAMES or trace.get("status") != "ok":
            continue
        result = trace.get("result")
        if isinstance(result, dict):
            payloads.append(result)
    return payloads


def _build_stats_addendum(tool_trace: list[dict]) -> str:
    previews = _all_preview_payloads(tool_trace)
    return render_preview_addendum(previews) if previews else ""


@r.post("/turn")
async def stats_agent_turn(
    req: StatisticsAgentTurnRequest,
    user=Depends(get_current_user),
):
    # Request validation is done by FastAPI on the typed `req` parameter
    # — no manual model_validate_json needed (the meeting agent does it
    # only because it parses a multipart `payload` field as a string).

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            tail_seq, history_json = await agent_turn_store.load(req.session_id)
            next_seq = tail_seq + 1

            full_history = ModelMessagesTypeAdapter.validate_python(history_json) if history_json else []
            # Pydantic AI only injects this agent's `_sys_parts` when
            # message_history is empty — and a prior turn (specialist
            # or router) may have persisted a SystemPromptPart with a
            # different agent's prompt. Replace it with this agent's
            # prompt so we always run with the correct identity.
            full_history = replace_system_prompt(full_history, STATS_SYSTEM_PROMPT)
            history = truncate_to_last_turns(full_history)
            language_hint = f"[Reply language] {_detect_user_language(req.user_message)}\n"
            today_iso = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
            deps = StatsDeps(
                session_id=req.session_id,
                current_user_message=req.user_message,
                today=today_iso,
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
                                    require_tool_allowed(AgentKind.STATISTICS, call_part.tool_name)
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
                                    tool_trace.append(
                                        {
                                            "id": tool_event.tool_call_id,
                                            "name": call_ctx.get("name", ""),
                                            "args": call_ctx.get("args", {}),
                                            "status": status,
                                            "result": result_part.content,
                                        }
                                    )
                                    yield _sse(
                                        "tool_call_end",
                                        {
                                            "id": tool_event.tool_call_id,
                                            "status": status,
                                            "result": result_part.content,
                                        },
                                    )

            final_result = run.result
            final_text = final_result.output if final_result else ""
            assistant_text_so_far = "".join(assistant_text_chunks)
            stats_addendum = _build_stats_addendum(tool_trace)
            if stats_addendum:
                assistant_text_chunks.append(stats_addendum)
                final_text = f"{final_text or ''}{stats_addendum}"
                yield _sse("assistant_text", {"chunk": stats_addendum})
            final_msgs = (
                ModelMessagesTypeAdapter.dump_python(final_result.all_messages(), mode="json") if final_result else []
            )
            final_msgs = strip_snapshots_from_dumped_history(final_msgs)
            assistant_text = "".join(assistant_text_chunks) or assistant_text_so_far or final_text
            await agent_turn_store.save_turn(
                req.session_id,
                user_id=getattr(user, "uid", None),
                turn=AgentTurnRecord(
                    seq=next_seq,
                    agent_kind=AgentKind.STATISTICS,
                    route=RouteKind.SPECIALIST,
                    user_message=req.user_message,
                    assistant_text=assistant_text,
                    tool_trace=tool_trace,
                    router_decision=req.router_decision or {},
                    history_cursor=final_msgs,
                ),
            )
            yield _sse(
                "done",
                {
                    "seq": next_seq,
                    "final_text": final_text,
                },
            )
        except asyncio.CancelledError:
            log.info("stats agent turn cancelled by client: %s", req.session_id)
            raise
        except Exception as e:
            message, recoverable = _extract_error_info(e)
            try:
                from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded

                known = isinstance(e, (ModelHTTPError, UsageLimitExceeded))
            except ImportError:
                known = False
            if known:
                log.warning("stats agent turn failed for session %s: %s", req.session_id, message)
            else:
                log.exception("stats agent turn failed for session %s", req.session_id)
            yield _sse(
                "error",
                {"reason": "agent_error", "recoverable": recoverable, "message": message},
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")
