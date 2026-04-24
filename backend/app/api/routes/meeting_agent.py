import asyncio
import copy
import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
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

from ...meeting_agent.agent import USAGE_LIMITS, agent
from ...meeting_agent.history import strip_snapshots_from_dumped_history, truncate_to_last_turns
from ...meeting_agent.models import AgendaDeps
from ...meeting_agent.prompts import SNAPSHOT_TEMPLATE
from ...meeting_agent.store import TurnRecord, session_store
from ...models.meeting_agent import MeetingAgentRevertRequest, MeetingAgentTurnRequest
from .auth import get_current_user

log = logging.getLogger(__name__)
meeting_agent_router = r = APIRouter(prefix="/meeting-agent")


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


def _extract_error_info(e: Exception) -> tuple[str, bool]:
    """Pull a user-readable message + recoverability hint out of an agent
    exception. The raw `str(e)` on Pydantic AI errors is a huge dump of the
    provider's JSON response; the UI banner needs a single clean sentence."""
    try:
        from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
    except ImportError:
        return (str(e), True)

    if isinstance(e, UsageLimitExceeded):
        # Same request will hit the same limit; no point offering Retry.
        return (str(e), False)

    if isinstance(e, ModelHTTPError):
        body = e.body if isinstance(e.body, dict) else {}
        # Gemini/OpenAI convention: {"error": {"message": "..."}}
        err = body.get("error") if isinstance(body, dict) else None
        msg = err.get("message") if isinstance(err, dict) else None
        if msg:
            return (f"[{e.status_code}] {msg}", True)
        return (f"Model HTTP error {e.status_code}", True)

    return (str(e), True)


@r.post("/turn")
async def agent_turn(req: MeetingAgentTurnRequest, user=Depends(get_current_user)):
    async def event_stream() -> AsyncIterator[bytes]:
        try:
            tail_seq, history_json = await session_store.load(req.session_id)
            next_seq = tail_seq + 1

            full_history = ModelMessagesTypeAdapter.validate_python(history_json) if history_json else []
            # Cap context window at the last N user turns. Older turns drop off
            # here; they remain in session_store (so the UI can still show the
            # full conversation), only the portion fed to the LLM is trimmed.
            history = truncate_to_last_turns(full_history)
            deps = AgendaDeps(
                agenda=copy.deepcopy(req.agenda_snapshot),
                session_id=req.session_id,
            )

            prompt = SNAPSHOT_TEMPLATE.format(
                snapshot_json=json.dumps(req.agenda_snapshot.model_dump(), ensure_ascii=False, indent=2),
                next_seq=next_seq,
                tail_seq=tail_seq,
                user_message=req.user_message,
            )

            tool_call_args: dict[str, dict] = {}
            # Accumulate per-turn trace for persistence. tool_trace preserves
            # the order and outcome of every tool invocation this turn; the UI
            # uses it to replay the turn on session resume.
            assistant_text_chunks: list[str] = []
            tool_trace: list[dict] = []
            agenda_before = req.agenda_snapshot.model_dump()

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
                                    # tool_event.result is ToolReturnPart on success or
                                    # RetryPromptPart when the tool raised ModelRetry (soft
                                    # refusal). Surface which via `status` so the UI can
                                    # render a warning badge vs a success badge.
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
                                            "agenda_after": deps.agenda.model_dump(),
                                        },
                                    )

            final_result = run.result
            final_text = final_result.output if final_result else ""
            # mode="json" serializes datetimes (Pydantic AI ModelMessage.timestamp)
            # to ISO strings so the result is valid JSONB input for supabase-py,
            # which json.dumps the payload internally.
            final_msgs = (
                ModelMessagesTypeAdapter.dump_python(final_result.all_messages(), mode="json") if final_result else []
            )
            # Strip SNAPSHOT_TEMPLATE wrappers from past UserPromptParts before
            # persisting. Past snapshots are stale by construction; leaving
            # them in history_cursor confuses the LLM on subsequent turns
            # (multiple JSON blobs → attention drift → hallucinated answers
            # about current state). The current turn's snapshot is injected
            # fresh via SNAPSHOT_TEMPLATE on the NEXT call, so nothing is lost.
            final_msgs = strip_snapshots_from_dumped_history(final_msgs)
            # Prefer the streamed chunks for assistant_text (covers cases where
            # run.result.output is None because of an early exit), but fall back
            # to final_text if no chunks were streamed.
            assistant_text = "".join(assistant_text_chunks) or final_text
            await session_store.save_turn(
                req.session_id,
                user_id=getattr(user, "uid", None),
                turn=TurnRecord(
                    seq=next_seq,
                    user_message=req.user_message,
                    assistant_text=assistant_text,
                    tool_trace=tool_trace,
                    agenda_before=agenda_before,
                    agenda_after=deps.agenda.model_dump(),
                    history_cursor=final_msgs,
                ),
            )
            yield _sse(
                "done",
                {
                    "seq": next_seq,
                    "final_agenda": deps.agenda.model_dump(),
                    "final_text": final_text,
                },
            )
        except asyncio.CancelledError:
            log.info("agent turn cancelled by client: %s", req.session_id)
            raise
        except Exception as e:
            message, recoverable = _extract_error_info(e)
            # Known failure modes (provider errors, usage limits) don't need
            # a stack trace — the message is self-explanatory. Reserve the
            # full traceback for unexpected exceptions so production logs
            # stay readable.
            try:
                from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded

                known = isinstance(e, (ModelHTTPError, UsageLimitExceeded))
            except ImportError:
                known = False
            if known:
                log.warning("agent turn failed for session %s: %s", req.session_id, message)
            else:
                log.exception("agent turn failed for session %s", req.session_id)
            yield _sse(
                "error",
                {"reason": "agent_error", "recoverable": recoverable, "message": message},
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@r.post("/revert")
async def agent_revert(req: MeetingAgentRevertRequest, user=Depends(get_current_user)):
    """Rewind a session to the state just BEFORE turn `target_seq` ran.

    Returns the agenda_before of target_seq and the new tail_seq (target_seq-1).
    Side effect: turns >= target_seq are deleted from the store.
    """
    if req.target_seq < 1:
        raise HTTPException(status_code=400, detail="target_seq must be >= 1")

    turn = await session_store.load_turn(req.session_id, req.target_seq)
    if turn is None:
        raise HTTPException(status_code=404, detail=f"turn {req.target_seq} not found")

    await session_store.delete_turns_at_or_after(req.session_id, req.target_seq)
    return {
        "agenda": turn.agenda_before,
        "new_tail_seq": req.target_seq - 1,
    }
