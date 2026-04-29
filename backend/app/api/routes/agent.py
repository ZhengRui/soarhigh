import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ...agents.router.classifier import classify_turn
from ...agents.router.store import decision_store
from ...agents.runtime.contracts import AgentKind, RouteKind, RouterDecision
from ...agents.runtime.policy import validate_handoff_policy
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


async def _iter_sse_frames(body_iterator) -> AsyncIterator[tuple[bytes, str | None, dict]]:
    buffer = b""
    async for chunk in body_iterator:
        buffer += _as_bytes(chunk)
        while b"\n\n" in buffer:
            raw, buffer = buffer.split(b"\n\n", 1)
            frame = raw + b"\n\n"
            event_name, data = _parse_sse_event(raw)
            yield frame, event_name, data


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
        self.handoff_proposal: dict | None = None

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
        elif event_name == "handoff_proposal":
            self.handoff_proposal = data

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
        if self.handoff_proposal is not None:
            domain_payload["handoff_proposal"] = self.handoff_proposal

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


def _handoff_stats_message(user_message: str, *, language: str) -> str:
    if language == "zh":
        return (
            "[跨 agent handoff: 只做历史事实收集]\n"
            "用户的原始请求还包含当前会议修改意图。你是只读统计 agent: "
            "请忽略修改/安排/分配动作, 只回答执行该请求前需要查清楚的历史统计事实。"
            "如果现有统计工具不能完整回答, 请明确说明限制。\n\n"
            f"[原始请求]\n{user_message}"
        )
    return (
        "[Cross-agent handoff: historical fact gathering only]\n"
        "The original user request also contains a current-meeting mutation intent. "
        "You are the read-only statistics agent: ignore the edit/assign/apply action "
        "and answer only the historical facts needed before that request can be acted on. "
        "If the current statistics tools cannot answer it completely, state the limitation.\n\n"
        f"[Original request]\n{user_message}"
    )


def _extract_handoff_facts(tool_trace: list[dict], *, limit: int = 5) -> tuple[list[dict], list[dict]]:
    facts: list[dict] = []
    references: list[dict] = []
    for call in tool_trace:
        result = call.get("result")
        if not isinstance(result, dict):
            continue
        value = result.get("value")
        if isinstance(value, dict):
            groups = value.get("groups")
            if isinstance(groups, list):
                facts.extend(group for group in groups if isinstance(group, dict))
            value_refs = value.get("references")
            if isinstance(value_refs, list):
                references.extend(ref for ref in value_refs if isinstance(ref, dict))
        top_refs = result.get("references")
        if isinstance(top_refs, list):
            references.extend(ref for ref in top_refs if isinstance(ref, dict))
    return facts[:limit], references[:limit]


def _handoff_confirmation_text(*, language: str) -> str:
    if language == "zh":
        return (
            "\n\n我已经先查完历史数据。这个请求如果要继续修改当前议程, 需要你明确确认: "
            "请回复要把哪位候选人安排到哪个当前议程角色, 例如“确认把 Joyce Feng 安排为 Timer”。"
        )
    return (
        "\n\nI gathered the historical facts first. To continue with a current-agenda edit, "
        'please confirm the exact candidate and role, for example: "Confirm Joyce Feng as Timer."'
    )


def _build_handoff_proposal(
    *,
    decision: RouterDecision,
    stats_done: dict,
    tool_trace: list[dict],
    language: str,
) -> dict:
    handoff = validate_handoff_policy(decision.handoff) if decision.handoff is not None else None
    facts, references = _extract_handoff_facts(tool_trace)
    return {
        "source_agent": handoff.source_agent if handoff else AgentKind.STATISTICS,
        "target_agent": handoff.target_agent if handoff else AgentKind.MEETING,
        "intent": handoff.intent if handoff else decision.intent,
        "requires_confirmation": True,
        "facts": facts,
        "references": references,
        "constraints": handoff.constraints if handoff else {},
        "statistics": {
            "seq": stats_done.get("seq"),
            "final_text": stats_done.get("final_text", ""),
            "tool_call_count": len(tool_trace),
        },
        "confirmation": {
            "required": True,
            "next_step": _handoff_confirmation_text(language=language).strip(),
        },
    }


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


async def _handoff_stream(
    *,
    seq: int,
    decision: RouterDecision,
    stats_response: StreamingResponse,
    session_id: str,
    user_id: str | None,
    user_message: str,
    agenda_before: dict,
    language: str,
) -> AsyncIterator[bytes]:
    collector = _UnifiedTurnCollector(
        seq=seq,
        decision=decision,
        user_message=user_message,
        agenda_before=agenda_before,
    )
    router_chunk = _sse("router_decision", _router_decision_payload(seq, decision))
    collector.observe_chunk(router_chunk)
    yield router_chunk

    stats_done: dict = {}
    saved = False
    async for frame, event_name, data in _iter_sse_frames(stats_response.body_iterator):
        if event_name == "done":
            stats_done = data
            continue
        collector.observe_chunk(frame)
        if collector.is_terminal and not saved:
            await _save_unified_turn(session_id=session_id, user_id=user_id, collector=collector)
            saved = True
        yield frame
        if event_name == "error":
            return

    proposal = _build_handoff_proposal(
        decision=decision,
        stats_done=stats_done,
        tool_trace=collector.tool_trace,
        language=language,
    )
    proposal_chunk = _sse("handoff_proposal", proposal)
    collector.observe_chunk(proposal_chunk)
    yield proposal_chunk

    confirmation_text = _handoff_confirmation_text(language=language)
    text_chunk = _sse("assistant_text", {"chunk": confirmation_text})
    collector.observe_chunk(text_chunk)
    yield text_chunk

    final_text = "".join(collector.assistant_chunks)
    done_chunk = _sse(
        "done",
        {
            "seq": seq,
            "final_text": final_text,
            "router_only": True,
            "handoff_requires_confirmation": True,
        },
    )
    collector.observe_chunk(done_chunk)
    if not saved:
        await _save_unified_turn(session_id=session_id, user_id=user_id, collector=collector)
    yield done_chunk


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

    if decision.route == RouteKind.HANDOFF:
        if req.agenda_snapshot is None:
            fallback = RouterDecision(
                route=RouteKind.CLARIFY,
                intent="handoff_without_agenda_snapshot",
                reason="A statistics-to-meeting handoff needs the current agenda snapshot before it can propose edits.",
                clarification_question=(
                    "I need the current agenda snapshot before I can prepare a handoff into meeting editing. "
                    "Please retry from a meeting draft page."
                ),
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

        if decision.handoff is None:
            raise RuntimeError("handoff route is missing handoff payload")
        validate_handoff_policy(decision.handoff)
        stats_response = await stats_agent_turn(
            StatisticsAgentTurnRequest(
                session_id=f"{req.session_id}:handoff:{record.seq}:statistics",
                user_message=_handoff_stats_message(req.user_message, language=language),
            ),
            user=user,
        )
        return StreamingResponse(
            _handoff_stream(
                seq=record.seq,
                decision=decision,
                stats_response=stats_response,
                session_id=req.session_id,
                user_id=user_id,
                user_message=req.user_message,
                agenda_before=req.agenda_snapshot.model_dump(mode="json"),
                language=language,
            ),
            media_type="text/event-stream",
        )

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
