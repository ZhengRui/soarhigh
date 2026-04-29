import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ...agents.router.classifier import classify_turn
from ...agents.router.store import decision_store
from ...agents.runtime.contracts import AgentKind, RouteKind, RouterDecision
from ...models.agent import AgentTurnRequest
from ...models.meeting_agent import MeetingAgentTurnRequest
from ...models.statistics_agent import StatisticsAgentTurnRequest
from .auth import get_current_user
from .meeting_agent import agent_turn as meeting_agent_turn
from .statistics_agent import stats_agent_turn

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
    return {
        "seq": seq,
        "decision": decision.model_dump(mode="json"),
    }


def _router_terminal_text(decision: RouterDecision, *, language: str) -> str:
    if decision.route == RouteKind.CLARIFY:
        question = decision.clarification_question or "Please clarify which agent should handle this request."
        if language == "zh" and decision.intent == "meeting_edit_without_agenda_snapshot":
            return "我需要当前议程快照才能修改会议。请从会议草稿页面重新发送。"
        if language == "zh" and decision.intent == "ambiguous_agent_target":
            return "你想让我修改当前会议草稿, 还是回答历史统计问题?"
        return question
    if decision.route == RouteKind.HANDOFF:
        if language == "zh":
            return (
                "这个请求需要先查历史统计, 再把结果交给会议编辑 agent 执行。"
                "后端已经识别为跨 agent handoff, 但执行编排还没启用; 请先分两步操作。"
            )
        return (
            "This request needs a statistics-to-meeting handoff. The router recognizes it, "
            "but executable handoff orchestration is not enabled yet; please do it in two steps for now."
        )
    if language == "zh":
        return decision.reason or "这个请求当前无法处理。"
    return decision.reason or "This request is not supported yet."


async def _prepend_router_event(
    *,
    seq: int,
    decision: RouterDecision,
    specialist_response: StreamingResponse,
) -> AsyncIterator[bytes]:
    yield _sse("router_decision", _router_decision_payload(seq, decision))
    async for chunk in specialist_response.body_iterator:
        yield _as_bytes(chunk)


async def _terminal_stream(seq: int, decision: RouterDecision, text: str) -> AsyncIterator[bytes]:
    yield _sse("router_decision", _router_decision_payload(seq, decision))
    yield _sse("assistant_text", {"chunk": text})
    yield _sse(
        "done",
        {
            "seq": seq,
            "final_text": text,
            "router_only": True,
        },
    )


@r.post("/turn")
async def unified_agent_turn(req: AgentTurnRequest, user=Depends(get_current_user)):
    decision = classify_turn(req)
    record = await decision_store.save_decision(
        req.session_id,
        user_id=getattr(user, "uid", None),
        user_message=req.user_message,
        decision=decision,
    )
    language = _detect_user_language(req.user_message)

    if decision.route != RouteKind.SPECIALIST:
        text = _router_terminal_text(decision, language=language)
        return StreamingResponse(_terminal_stream(record.seq, decision, text), media_type="text/event-stream")

    if decision.agent_kind == AgentKind.STATISTICS:
        specialist_response = await stats_agent_turn(
            StatisticsAgentTurnRequest(session_id=req.session_id, user_message=req.user_message),
            user=user,
        )
        return StreamingResponse(
            _prepend_router_event(seq=record.seq, decision=decision, specialist_response=specialist_response),
            media_type="text/event-stream",
        )

    if decision.agent_kind == AgentKind.MEETING and req.agenda_snapshot is not None:
        specialist_response = await meeting_agent_turn(
            payload=MeetingAgentTurnRequest(
                session_id=req.session_id,
                user_message=req.user_message,
                agenda_snapshot=req.agenda_snapshot,
            ).model_dump_json(),
            image=None,
            user=user,
        )
        return StreamingResponse(
            _prepend_router_event(seq=record.seq, decision=decision, specialist_response=specialist_response),
            media_type="text/event-stream",
        )

    log.warning("router produced unsupported specialist decision: %s", decision.model_dump(mode="json"))
    fallback = RouterDecision(
        route=RouteKind.CLARIFY,
        intent="unsupported_router_decision",
        reason="Router selected a specialist without the required request payload.",
        clarification_question="Please retry with the current meeting draft context.",
    )
    text = _router_terminal_text(fallback, language=language)
    return StreamingResponse(_terminal_stream(record.seq, fallback, text), media_type="text/event-stream")
