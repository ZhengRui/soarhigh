import json
import logging
import re
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from pydantic_ai.messages import ModelMessagesTypeAdapter

from ....agents.meeting.history import append_router_exchange, truncate_to_last_turns
from ....agents.router.classifier import classify_turn
from ....agents.runtime.contracts import AgentKind, RouteKind, RouterDecision
from ....agents.runtime.policy import validate_handoff_policy
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
            yield raw + b"\n\n", *_parse_sse_event(raw)


async def _save_router_turn(
    *,
    session_id: str,
    user_id: str | None,
    seq: int,
    decision: RouterDecision,
    user_message: str,
    assistant_text: str,
    prior_history: list[dict] | None = None,
    agenda_before: dict | None = None,
    tool_trace: list[dict] | None = None,
    domain_payload: dict | None = None,
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
        tool_trace=tool_trace or [],
        router_decision=decision.model_dump(mode="json"),
        agenda_before=agenda_before,
        domain_payload=domain_payload or {},
        history_cursor=history_cursor,
    )
    try:
        await agent_turn_store.save_turn(session_id, user_id=user_id, turn=record)
    except Exception:
        log.exception("failed to persist router turn for session %s", session_id)


async def _load_pending_handoff(session_id: str) -> dict | None:
    try:
        latest = await agent_turn_store.load_latest(session_id)
    except Exception:
        log.exception("failed to load pending handoff for session %s", session_id)
        return None
    if latest is None or latest.route not in {RouteKind.HANDOFF, RouteKind.HANDOFF.value}:
        return None
    proposal = latest.domain_payload.get("handoff_proposal")
    if not isinstance(proposal, dict) or proposal.get("requires_confirmation") is not True:
        return None
    return proposal


def _router_pre_dispatch_error_message(e: Exception, *, language: str) -> str:
    """Short user-readable message for failures BEFORE the router can
    return a stream — i.e. the unified history load, handoff lookup,
    or the router LLM call itself. Mirrors the shape of
    `_extract_error_info` in the specialist routes but stays inline
    since the unified route only needs the message string.
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
    the dispatch point (history load / classify / decision save fails).
    Same shape the specialists emit on agent_error so the frontend's
    onEvent handler renders the banner the same way."""
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
                facts.extend(g for g in groups if isinstance(g, dict))
            value_refs = value.get("references")
            if isinstance(value_refs, list):
                references.extend(r for r in value_refs if isinstance(r, dict))
        top_refs = result.get("references")
        if isinstance(top_refs, list):
            references.extend(r for r in top_refs if isinstance(r, dict))
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


_CONFIRMATION_TERMS = (
    "confirm",
    "confirmed",
    "yes",
    "do it",
    "go ahead",
    "okay",
    "确认",
    "好的",
    "可以",
    "就这样",
)
_ACTION_TERMS = ("assign", "set", "安排", "分配", "设为", "设置")
_LINK_TERMS = ("as ", "to ", "把")
_HANDOFF_ROLE_TERMS = (
    "saa",
    "timer",
    "grammarian",
    "hark master",
    "tom",
    "ttm",
    "tte",
    "ie",
    "ge",
    "prepared speech",
    "table topic",
    "evaluator",
    "主持",
    "计时",
    "语法官",
    "即兴",
    "备稿",
    "点评",
)


def _normalize_message(text: str) -> str:
    return " ".join(text.lower().split())


def _contains_term(text: str, term: str) -> bool:
    if term.isascii() and term.strip().replace(" ", "").isalpha() and " " not in term.strip():
        return re.search(rf"\b{re.escape(term)}\b", text) is not None
    return term in text


def _looks_like_handoff_confirmation(text: str) -> bool:
    normalized = _normalize_message(text)
    return any(_contains_term(normalized, term) for term in _CONFIRMATION_TERMS + _ACTION_TERMS)


def _handoff_confirmation_has_details(text: str) -> bool:
    normalized = _normalize_message(text)
    has_role = any(_contains_term(normalized, term) for term in _HANDOFF_ROLE_TERMS)
    has_confirmation = any(_contains_term(normalized, term) for term in _CONFIRMATION_TERMS)
    has_action = any(_contains_term(normalized, term) for term in _ACTION_TERMS)
    has_link = any(term in normalized for term in _LINK_TERMS)
    has_assignment = has_action or (has_confirmation and has_link)
    return has_role and has_assignment


def _handoff_clarification_text(*, language: str) -> str:
    if language == "zh":
        return (
            "我已经有上一轮的 handoff 候选事实, 但执行当前议程修改前还需要你明确候选人和角色。"
            "请回复类似: 确认把 Joyce Feng 安排为 Timer。"
        )
    return (
        "I still need the exact candidate and role before applying the handoff. "
        'Please reply with something like: "Confirm Joyce Feng as Timer."'
    )


def _confirmed_handoff_message(user_message: str, proposal: dict, *, language: str) -> str:
    proposal_json = json.dumps(proposal, ensure_ascii=False)
    if language == "zh":
        return (
            "[已确认的跨 agent handoff]\n"
            "用户已经确认要把上一轮统计事实用于当前议程修改。"
            "你是会议编辑 agent: 只执行用户本轮明确确认的候选人和角色, "
            "不要根据统计候选事实自行选择未被用户点名的人或角色。\n\n"
            f"[handoff proposal]\n{proposal_json}\n\n"
            f"[用户确认]\n{user_message}"
        )
    return (
        "[Confirmed cross-agent handoff]\n"
        "The user has confirmed that the prior statistics facts should be used for a current-agenda edit. "
        "You are the meeting editing agent: execute only the candidate and role explicitly confirmed "
        "in this current user message. Do not choose an unnamed candidate or role from the statistics facts.\n\n"
        f"[handoff proposal]\n{proposal_json}\n\n"
        f"[User confirmation]\n{user_message}"
    )


def _classify_handoff_confirmation(req: AgentTurnRequest, proposal: dict, *, language: str) -> RouterDecision | None:
    if not _looks_like_handoff_confirmation(req.user_message):
        return None
    if not _handoff_confirmation_has_details(req.user_message):
        return RouterDecision(
            route=RouteKind.CLARIFY,
            intent="handoff_confirmation_needs_details",
            reason="A pending handoff exists, but the confirmation does not name both a candidate and target role.",
            clarification_question=_handoff_clarification_text(language=language),
            metadata={"pending_handoff": proposal},
        )
    if req.agenda_snapshot is None:
        return RouterDecision(
            route=RouteKind.CLARIFY,
            intent="handoff_confirmation_without_agenda_snapshot",
            reason="A confirmed handoff needs the current agenda snapshot before the meeting agent can apply it.",
            clarification_question=(
                "I need the current agenda snapshot before I can apply that confirmed handoff. "
                "Please retry from a meeting draft page."
            ),
            metadata={"pending_handoff": proposal},
        )
    return RouterDecision(
        route=RouteKind.SPECIALIST,
        agent_kind=AgentKind.MEETING,
        intent="confirmed_handoff_meeting_mutation",
        reason="The user confirmed a pending statistics-to-meeting handoff with explicit candidate and role details.",
        confidence=0.9,
        metadata={"pending_handoff": proposal},
    )


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
    prior_history: list[dict],
) -> AsyncIterator[bytes]:
    """Run stats sub-call as fact gathering, suppress its done event, then
    finish with a router-owned done that carries the handoff_proposal."""
    yield _sse("router_decision", _router_decision_payload(seq, decision))

    tool_calls: dict[str, dict] = {}
    tool_trace: list[dict] = []
    stats_done: dict = {}

    async for frame, event_name, data in _iter_sse_frames(stats_response.body_iterator):
        if event_name == "tool_call_start":
            call_id = data.get("id")
            if isinstance(call_id, str):
                tool_calls[call_id] = {"name": data.get("name", ""), "args": data.get("args") or {}}
        elif event_name == "tool_call_end":
            call_id = data.get("id")
            call = tool_calls.get(call_id, {}) if isinstance(call_id, str) else {}
            tool_trace.append(
                {
                    "id": call_id,
                    "name": call.get("name", ""),
                    "args": call.get("args", {}),
                    "status": data.get("status", "ok"),
                    "result": data.get("result"),
                }
            )
        elif event_name == "done":
            stats_done = data
            continue
        yield frame
        if event_name == "error":
            return

    proposal = _build_handoff_proposal(
        decision=decision, stats_done=stats_done, tool_trace=tool_trace, language=language
    )
    yield _sse("handoff_proposal", proposal)

    confirmation_text = _handoff_confirmation_text(language=language)
    yield _sse("assistant_text", {"chunk": confirmation_text})
    yield _sse(
        "done",
        {"seq": seq, "final_text": confirmation_text, "router_only": True, "handoff_requires_confirmation": True},
    )

    await _save_router_turn(
        session_id=session_id,
        user_id=user_id,
        seq=seq,
        decision=decision,
        user_message=user_message,
        assistant_text=confirmation_text,
        prior_history=prior_history,
        agenda_before=agenda_before,
        tool_trace=tool_trace,
        domain_payload={"handoff_proposal": proposal},
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

    # Wrap all pre-stream work (history load, handoff lookup, router LLM
    # call, decision persistence) in try/except. Any failure here would
    # otherwise propagate as a 500 with no SSE body, leaving the frontend
    # to silently swallow the error and the user staring at a stuck "…"
    # bubble. We return a tiny error-only stream so the existing onEvent
    # handler renders the banner with Retry like any other agent_error.
    try:
        _tail_seq, prior_history = await agent_turn_store.load(req.session_id)

        pending_handoff = await _load_pending_handoff(req.session_id)
        decision = (
            _classify_handoff_confirmation(req, pending_handoff, language=language)
            if pending_handoff is not None
            else None
        )
        if decision is None:
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

    # HANDOFF: run stats fact-gathering, then emit proposal that requires confirmation.
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
        if decision.handoff is None:
            raise RuntimeError("handoff route is missing handoff payload")
        validate_handoff_policy(decision.handoff)
        stats_response = await stats_agent_turn(
            StatisticsAgentTurnRequest(
                session_id=f"{req.session_id}:handoff:{seq}:statistics",
                user_message=_handoff_stats_message(req.user_message, language=language),
            ),
            user=user,
        )
        return StreamingResponse(
            _handoff_stream(
                seq=seq,
                decision=decision,
                stats_response=stats_response,
                session_id=req.session_id,
                user_id=user_id,
                user_message=req.user_message,
                agenda_before=req.agenda_snapshot.model_dump(mode="json"),
                language=language,
                prior_history=prior_history,
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
        confirmed_handoff = decision.metadata.get("pending_handoff")
        handoff_context = confirmed_handoff if isinstance(confirmed_handoff, dict) else None
        meeting_user_message = (
            _confirmed_handoff_message(req.user_message, handoff_context, language=language)
            if handoff_context is not None
            else req.user_message
        )
        specialist_response = await meeting_agent_turn(
            payload=MeetingAgentTurnRequest(
                session_id=req.session_id,
                user_message=meeting_user_message,
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
