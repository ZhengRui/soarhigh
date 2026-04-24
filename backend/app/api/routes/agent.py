import asyncio
import copy
import json
import logging
from typing import AsyncIterator

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

from ...agent.agent import USAGE_LIMITS, agent
from ...agent.history import truncate_to_last_turns
from ...agent.models import AgendaDeps
from ...agent.prompts import SNAPSHOT_TEMPLATE
from ...agent.store import session_store
from ...models.agent import AgentTurnRequest
from .auth import get_current_user

log = logging.getLogger(__name__)
agent_router = r = APIRouter(prefix="/agent")


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


@r.post("/turn")
async def agent_turn(req: AgentTurnRequest, user=Depends(get_current_user)):
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
                                        yield _sse("assistant_text", {"chunk": part.content})
                                    elif isinstance(part, ThinkingPart) and part.content:
                                        yield _sse("thinking", {"chunk": part.content})
                                elif isinstance(event, PartDeltaEvent):
                                    delta = event.delta
                                    if isinstance(delta, TextPartDelta) and delta.content_delta:
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
                                    yield _sse(
                                        "tool_call_end",
                                        {
                                            "id": tool_event.tool_call_id,
                                            "status": "retry" if is_retry else "ok",
                                            "result": result_part.content,
                                            "agenda_after": deps.agenda.model_dump(),
                                        },
                                    )

            final_result = run.result
            final_text = final_result.output if final_result else ""
            final_msgs = ModelMessagesTypeAdapter.dump_python(final_result.all_messages()) if final_result else []
            await session_store.save(req.session_id, tail_seq=next_seq, history=final_msgs)
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
            log.exception("agent turn failed for session %s", req.session_id)
            yield _sse(
                "error",
                {"reason": "agent_error", "recoverable": True, "message": str(e)},
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")
