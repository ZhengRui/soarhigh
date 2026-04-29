import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ...agents.router.classifier import classify_turn
from ...agents.router.store import decision_store
from ...agents.runtime.contracts import AgentKind, RouteKind, RouterDecision
from ...agents.runtime.store import AgentTurnRecord, agent_turn_store
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


def _parse_sse_event(raw: bytes) -> tuple[str | None, dict]:
    event_name: str | None = None
    data_lines: list[str] = []
    for line in raw.decode("utf-8").splitlines():
        if line.startswith("event: "):
            event_name = line[len("event: ") :]
        elif line.startswith("data: "):
            data_lines.append(line[len("data: ") :])
    if not data_lines:
        return event_name, {}
    return event_name, json.loads("\n".join(data_lines))


class _UnifiedTurnCollector:
    def __init__(
        self,
        *,
        seq: int,
        decision: RouterDecision,
        user_message: str,
        agenda_before: dict | None = None,
    ) -> None:
        self.seq = seq
        self.decision = decision
        self.user_message = user_message
        self.agenda_before = agenda_before
        self.assistant_chunks: list[str] = []
        self.tool_trace: list[dict] = []
        self._tool_calls: dict[str, dict] = {}
        self._buffer = b""
        self.done_data: dict | None = None
        self.error_data: dict | None = None
        self.agenda_after: dict | None = None

    def observe_chunk(self, chunk: bytes) -> None:
        self._buffer += chunk
        while b"\n\n" in self._buffer:
            raw, self._buffer = self._buffer.split(b"\n\n", 1)
            event_name, data = _parse_sse_event(raw)
            self.observe_event(event_name, data)

    def observe_event(self, event_name: str | None, data: dict) -> None:
        if event_name == "assistant_text":
            chunk = data.get("chunk")
            if isinstance(chunk, str):
                self.assistant_chunks.append(chunk)
        elif event_name == "tool_call_start":
            call_id = data.get("id")
            if isinstance(call_id, str):
                self._tool_calls[call_id] = {
                    "id": call_id,
                    "name": data.get("name", ""),
                    "args": data.get("args") or {},
                }
        elif event_name == "tool_call_end":
            call_id = data.get("id")
            call = self._tool_calls.get(call_id, {}) if isinstance(call_id, str) else {}
            self.tool_trace.append(
                {
                    "id": call_id,
                    "name": call.get("name", ""),
                    "args": call.get("args", {}),
                    "status": data.get("status", "ok"),
                    "result": data.get("result"),
                }
            )
            agenda_after = data.get("agenda_after")
            if isinstance(agenda_after, dict):
                self.agenda_after = agenda_after
        elif event_name == "done":
            self.done_data = data
            final_agenda = data.get("final_agenda")
            if isinstance(final_agenda, dict):
                self.agenda_after = final_agenda
        elif event_name == "error":
            self.error_data = data

    @property
    def is_terminal(self) -> bool:
        return self.done_data is not None or self.error_data is not None

    def to_record(self) -> AgentTurnRecord:
        done = self.done_data or {}
        error = self.error_data or {}
        agent_kind = (
            self.decision.agent_kind
            if self.decision.route == RouteKind.SPECIALIST and self.decision.agent_kind is not None
            else AgentKind.ROUTER
        )
        specialist_seq = None if done.get("router_only") else done.get("seq")
        assistant_text = "".join(self.assistant_chunks) or done.get("final_text") or error.get("message") or ""
        domain_payload: dict = {}
        if self.done_data is not None:
            domain_payload["done"] = self.done_data
        if self.error_data is not None:
            domain_payload["error"] = self.error_data

        return AgentTurnRecord(
            seq=self.seq,
            agent_kind=agent_kind,
            route=self.decision.route,
            user_message=self.user_message,
            assistant_text=assistant_text,
            tool_trace=self.tool_trace,
            router_decision=self.decision.model_dump(mode="json"),
            specialist_seq=specialist_seq if isinstance(specialist_seq, int) else None,
            agenda_before=self.agenda_before,
            agenda_after=self.agenda_after,
            domain_payload=domain_payload,
        )


async def _save_unified_turn(
    *,
    session_id: str,
    user_id: str | None,
    collector: _UnifiedTurnCollector,
) -> None:
    try:
        await agent_turn_store.save_turn(session_id, user_id=user_id, turn=collector.to_record())
    except Exception:
        log.exception("failed to persist unified agent turn for session %s", session_id)


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
    session_id: str,
    user_id: str | None,
    user_message: str,
    agenda_before: dict | None = None,
) -> AsyncIterator[bytes]:
    collector = _UnifiedTurnCollector(
        seq=seq,
        decision=decision,
        user_message=user_message,
        agenda_before=agenda_before,
    )
    saved = False
    router_chunk = _sse("router_decision", _router_decision_payload(seq, decision))
    collector.observe_chunk(router_chunk)
    yield router_chunk
    async for chunk in specialist_response.body_iterator:
        chunk_bytes = _as_bytes(chunk)
        collector.observe_chunk(chunk_bytes)
        if collector.is_terminal and not saved:
            await _save_unified_turn(session_id=session_id, user_id=user_id, collector=collector)
            saved = True
        yield chunk_bytes


async def _terminal_stream(
    seq: int,
    decision: RouterDecision,
    text: str,
    *,
    session_id: str,
    user_id: str | None,
    user_message: str,
) -> AsyncIterator[bytes]:
    collector = _UnifiedTurnCollector(seq=seq, decision=decision, user_message=user_message)
    chunks = [
        _sse("router_decision", _router_decision_payload(seq, decision)),
        _sse("assistant_text", {"chunk": text}),
        _sse(
            "done",
            {
                "seq": seq,
                "final_text": text,
                "router_only": True,
            },
        ),
    ]
    saved = False
    for chunk in chunks:
        collector.observe_chunk(chunk)
        if collector.is_terminal and not saved:
            await _save_unified_turn(session_id=session_id, user_id=user_id, collector=collector)
            saved = True
        yield chunk


@r.post("/turn")
async def unified_agent_turn(req: AgentTurnRequest, user=Depends(get_current_user)):
    user_id = getattr(user, "uid", None)
    decision = classify_turn(req)
    record = await decision_store.save_decision(
        req.session_id,
        user_id=user_id,
        user_message=req.user_message,
        decision=decision,
    )
    language = _detect_user_language(req.user_message)

    if decision.route != RouteKind.SPECIALIST:
        text = _router_terminal_text(decision, language=language)
        return StreamingResponse(
            _terminal_stream(
                record.seq,
                decision,
                text,
                session_id=req.session_id,
                user_id=user_id,
                user_message=req.user_message,
            ),
            media_type="text/event-stream",
        )

    if decision.agent_kind == AgentKind.STATISTICS:
        specialist_response = await stats_agent_turn(
            StatisticsAgentTurnRequest(session_id=req.session_id, user_message=req.user_message),
            user=user,
        )
        return StreamingResponse(
            _prepend_router_event(
                seq=record.seq,
                decision=decision,
                specialist_response=specialist_response,
                session_id=req.session_id,
                user_id=user_id,
                user_message=req.user_message,
            ),
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
            _prepend_router_event(
                seq=record.seq,
                decision=decision,
                specialist_response=specialist_response,
                session_id=req.session_id,
                user_id=user_id,
                user_message=req.user_message,
                agenda_before=req.agenda_snapshot.model_dump(mode="json"),
            ),
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
    return StreamingResponse(
        _terminal_stream(
            record.seq,
            fallback,
            text,
            session_id=req.session_id,
            user_id=user_id,
            user_message=req.user_message,
        ),
        media_type="text/event-stream",
    )
