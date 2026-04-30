import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from pydantic_ai.messages import ModelMessagesTypeAdapter

from ....agents.meeting.history import append_router_exchange, truncate_to_last_turns
from ....agents.router.classifier import classify_turn
from ....agents.runtime.contracts import AgentKind, RouteKind, RouterDecision
from ....agents.runtime.store import AgentTurnRecord, agent_turn_store
from ....models.agents.meeting import MeetingAgentTurnRequest
from ....models.agents.statistics import StatisticsAgentTurnRequest
from ....models.agents.unified import AgentTurnRequest
from ..auth import get_current_user
from .meeting import agent_turn as meeting_agent_turn
from .statistics import stats_agent_turn

log = logging.getLogger(__name__)
agent_router = r = APIRouter(prefix="/agent")


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


def _as_bytes(chunk: str | bytes | memoryview) -> bytes:
    if isinstance(chunk, bytes):
        return chunk
    if isinstance(chunk, memoryview):
        return chunk.tobytes()
    return chunk.encode("utf-8")


def _detect_user_language(text: str) -> str:
    if not text:
        return "en"
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if cjk == 0 and latin == 0:
        return "en"
    return "zh" if cjk > latin else "en"


def _router_decision_payload(seq: int, decision: RouterDecision) -> dict:
    return {"seq": seq, "decision": decision.model_dump(mode="json")}


async def _save_router_turn(
    *,
    session_id: str,
    user_id: str | None,
    seq: int,
    decision: RouterDecision,
    user_message: str,
    assistant_text: str,
    prior_history: list[dict] | None = None,
) -> None:
    history_cursor = append_router_exchange(
        prior_history or [],
        user_message=user_message,
        assistant_text=assistant_text,
    )
    record = AgentTurnRecord(
        seq=seq,
        agent_kind=AgentKind.ROUTER,
        route=decision.route,
        user_message=user_message,
        assistant_text=assistant_text,
        router_decision=decision.model_dump(mode="json"),
        history_cursor=history_cursor,
    )
    try:
        await agent_turn_store.save_turn(session_id, user_id=user_id, turn=record)
    except Exception:
        log.exception("failed to persist router turn for session %s", session_id)


def _router_pre_dispatch_error_message(e: Exception, *, language: str) -> str:
    """Short user-readable message for failures BEFORE the router can
    return a stream — i.e. the unified history load or the router LLM
    call itself. Mirrors the shape of `_extract_error_info` in the
    specialist routes but stays inline since the unified route only
    needs the message string.
    """
    try:
        from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
    except ImportError:
        return str(e)
    if isinstance(e, ModelHTTPError):
        body = e.body if isinstance(e.body, dict) else {}
        err = body.get("error") if isinstance(body, dict) else None
        msg = err.get("message") if isinstance(err, dict) else None
        if msg:
            return f"[{e.status_code}] {msg}"
        return f"Model HTTP error {e.status_code}"
    if isinstance(e, UsageLimitExceeded):
        return str(e)
    name = type(e).__name__
    detail = str(e) or "(no message)"
    if language == "zh":
        return f"路由失败 ({name}): {detail}"
    return f"Router failure ({name}): {detail}"


async def _error_only_stream(*, reason: str, recoverable: bool, message: str) -> AsyncIterator[bytes]:
    """Single-event SSE stream used when the router can't even reach
    the dispatch point (history load / classify fails). Same shape the
    specialists emit on agent_error so the frontend's onEvent handler
    renders the banner the same way."""
    yield _sse(
        "error",
        {"reason": reason, "recoverable": recoverable, "message": message},
    )


def _router_terminal_text(decision: RouterDecision, *, language: str) -> str:
    if decision.route == RouteKind.DIRECT_ANSWER:
        return decision.direct_response or ""
    if decision.route == RouteKind.CLARIFY:
        question = decision.clarification_question or "Please clarify which agent should handle this request."
        if language == "zh" and decision.intent == "meeting_edit_without_agenda_snapshot":
            return "我需要当前议程快照才能修改会议。请从会议草稿页面重新发送。"
        if language == "zh" and decision.intent == "ambiguous_agent_target":
            return "你想让我修改当前会议草稿, 还是回答历史统计问题?"
        return question
    if language == "zh":
        return decision.reason or "这个请求当前无法处理。"
    return decision.reason or "This request is not supported yet."


async def _prepend_router_event(
    seq: int,
    decision: RouterDecision,
    specialist_response: StreamingResponse,
) -> AsyncIterator[bytes]:
    """Specialist dispatch: emit router_decision SSE, then forward bytes
    verbatim. The specialist owns its agent_turns row write."""
    yield _sse("router_decision", _router_decision_payload(seq, decision))
    async for chunk in specialist_response.body_iterator:
        yield _as_bytes(chunk)


async def _terminal_stream(
    *,
    seq: int,
    decision: RouterDecision,
    text: str,
    session_id: str,
    user_id: str | None,
    user_message: str,
    prior_history: list[dict],
) -> AsyncIterator[bytes]:
    """Router-only paths (clarify / refuse / direct_answer). Emit the
    router envelope, then persist a single agent_turns row with
    agent_kind=router."""
    yield _sse("router_decision", _router_decision_payload(seq, decision))
    yield _sse("assistant_text", {"chunk": text})
    yield _sse("done", {"seq": seq, "final_text": text, "router_only": True})
    await _save_router_turn(
        session_id=session_id,
        user_id=user_id,
        seq=seq,
        decision=decision,
        user_message=user_message,
        assistant_text=text,
        prior_history=prior_history,
    )


@r.post("/turn")
async def unified_agent_turn(
    payload: str = Form(...),
    image: UploadFile | None = File(None),
    user=Depends(get_current_user),
):
    try:
        req = AgentTurnRequest.model_validate_json(payload)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e

    user_id = getattr(user, "uid", None)
    language = _detect_user_language(req.user_message)

    # Wrap pre-stream work (history load + router LLM call) in try/except.
    # Any failure here would otherwise propagate as a 500 with no SSE body,
    # leaving the frontend to silently swallow the error and the user staring
    # at a stuck "…" bubble. We return a tiny error-only stream so the
    # existing onEvent handler renders the banner with Retry like any other
    # agent_error.
    try:
        _tail_seq, prior_history = await agent_turn_store.load(req.session_id)
        full_history = ModelMessagesTypeAdapter.validate_python(prior_history) if prior_history else []
        # classify_turn handles its own SystemPromptPart normalization
        # (Pydantic AI only injects _sys_parts when message_history is
        # empty, so the router replaces any persisted system prompt
        # internally with its own).
        router_history = truncate_to_last_turns(full_history)
        decision = await classify_turn(req, message_history=router_history)

        # The router decision is persisted on the unified `agent_turns`
        # row (router_decision JSONB) when the router-only path saves,
        # or carried into the specialist's row via router_decision on
        # the dispatch request. seq advances off the unified store's
        # tail so router and specialist turns share one sequence.
        seq = _tail_seq + 1
    except Exception as e:
        log.exception("router pre-dispatch failed for session %s", req.session_id)
        return StreamingResponse(
            _error_only_stream(
                reason="router_failure",
                recoverable=True,
                message=_router_pre_dispatch_error_message(e, language=language),
            ),
            media_type="text/event-stream",
        )

    # CLARIFY / REFUSE / DIRECT_ANSWER: router-only.
    if decision.route != RouteKind.SPECIALIST:
        return StreamingResponse(
            _terminal_stream(
                seq=seq,
                decision=decision,
                text=_router_terminal_text(decision, language=language),
                session_id=req.session_id,
                user_id=user_id,
                user_message=req.user_message,
                prior_history=prior_history,
            ),
            media_type="text/event-stream",
        )

    # SPECIALIST: dispatch and pass router_decision through so the specialist's
    # agent_turns row carries the routing context. The specialist owns the write.
    # Multi-turn cross-agent flows (e.g. "find someone for X" → stats, then
    # "选 Leta Li" → meeting) are handled naturally: each turn classifies on
    # its own merits, both specialists load the same session_id history, and
    # the meeting agent on the follow-up turn reads the stats agent's prior
    # tool calls + reply text from history. No special handoff machinery.
    decision_payload = decision.model_dump(mode="json")

    if decision.agent_kind == AgentKind.STATISTICS:
        specialist_response = await stats_agent_turn(
            StatisticsAgentTurnRequest(
                session_id=req.session_id,
                user_message=req.user_message,
                router_decision=decision_payload,
            ),
            user=user,
        )
        return StreamingResponse(
            _prepend_router_event(seq, decision, specialist_response),
            media_type="text/event-stream",
        )

    if decision.agent_kind == AgentKind.MEETING and req.agenda_snapshot is not None:
        specialist_response = await meeting_agent_turn(
            payload=MeetingAgentTurnRequest(
                session_id=req.session_id,
                user_message=req.user_message,
                agenda_snapshot=req.agenda_snapshot,
                router_decision=decision_payload,
            ).model_dump_json(),
            image=image,
            user=user,
        )
        return StreamingResponse(
            _prepend_router_event(seq, decision, specialist_response),
            media_type="text/event-stream",
        )

    log.warning("router produced unsupported specialist decision: %s", decision.model_dump(mode="json"))
    fallback = RouterDecision(
        route=RouteKind.CLARIFY,
        intent="unsupported_router_decision",
        reason="Router selected a specialist without the required request payload.",
        clarification_question="Please retry with the current meeting draft context.",
    )
    return StreamingResponse(
        _terminal_stream(
            seq=seq,
            decision=fallback,
            text=_router_terminal_text(fallback, language=language),
            session_id=req.session_id,
            user_id=user_id,
            user_message=req.user_message,
            prior_history=prior_history,
        ),
        media_type="text/event-stream",
    )
