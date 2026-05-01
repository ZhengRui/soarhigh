import asyncio
import copy
import json
import logging
from datetime import datetime
from typing import AsyncIterator
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
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

from ....agents.meeting.agent import USAGE_LIMITS, agent
from ....agents.meeting.models import AgendaDeps
from ....agents.meeting.prompts import MEETING_SYSTEM_PROMPT, SNAPSHOT_TEMPLATE
from ....agents.meeting.segment_ids import shorten_agenda_dump
from ....agents.runtime.contracts import AgentKind, RouteKind
from ....agents.runtime.history import (
    replace_system_prompt,
    strip_snapshots_from_dumped_history,
    truncate_to_last_turns,
)
from ....agents.runtime.policy import AgentPolicyError, require_tool_allowed
from ....agents.runtime.store import AgentTurnRecord, agent_turn_store
from ....models.agents.meeting import MeetingAgentRevertRequest, MeetingAgentTurnRequest
from ....services.meeting_preview_markdown import (
    format_role_display,
    format_segment_detail_cell,
    render_preview_addendum,
)
from ..auth import get_current_user
from ._shared import _detect_user_language, _extract_error_info, _session_unavailable_response, _sse

log = logging.getLogger(__name__)
meeting_agent_router = r = APIRouter(prefix="/meeting-agent")

_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_CREATE_TOOL_NAMES = {"create_from_text", "create_from_image", "clone_from_meeting", "create_from_template"}
_PREVIEW_TOOL_NAMES = {"preview_meeting"}
_SHOW_CURRENT_TOOL_NAMES = {"show_current_agenda"}


def _display_cell(value) -> str:
    if value is None:
        return "TBD"
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else "TBD"
    return str(value)


def _format_missing_labels(missing) -> str:
    labels: list[str] = []
    if isinstance(missing, list):
        for item in missing:
            if isinstance(item, dict):
                label = item.get("label") or item.get("field")
            else:
                label = item
            if label:
                labels.append(str(label))
    return ", ".join(labels)


_META_TOOL_NAMES = {"set_meta"}
_SEGMENT_TOOL_NAMES = {
    "set_role",
    "set_type",
    "set_title",
    "set_content",
    "set_duration",
    "set_buffer",
    "add_segment",
    "remove_segment",
    "move_segment",
    "swap_roles",
    "swap_time",
    "shift_segment_time",
}
_REVERT_TOOL_NAMES = {"revert_last_turn", "revert_to_turn"}


def _classify_agenda_changes(tool_trace: list[dict]) -> tuple[bool, bool, bool]:
    """Returns (meta_changed, segment_changed, wholesale).

    Wholesale (creation / clone / revert) means both meta and segments may
    have changed; treat as a full replace for table-rendering purposes."""
    meta_changed = False
    segment_changed = False
    wholesale = False
    for trace in tool_trace:
        if trace.get("status") != "ok":
            continue
        name = trace.get("name", "")
        if name in _CREATE_TOOL_NAMES or name in _REVERT_TOOL_NAMES:
            wholesale = True
        elif name in _META_TOOL_NAMES:
            meta_changed = True
        elif name in _SEGMENT_TOOL_NAMES:
            segment_changed = True
    return meta_changed, segment_changed, wholesale


def _render_meta_table(agenda) -> str:
    meta = agenda.meta
    time_value = f"{_display_cell(meta.start_time)} - {_display_cell(meta.end_time)}"
    rows = [
        ("Meeting No.", _display_cell(meta.no)),
        ("Type", _display_cell(meta.type)),
        ("Theme", _display_cell(meta.theme)),
        ("Meeting Manager", _display_cell(meta.manager)),
        ("Date", _display_cell(meta.date)),
        ("Time", time_value),
        ("Location", _display_cell(meta.location)),
    ]
    lines = ["| Field | Value |", "|---|---|"]
    lines.extend(f"| {label} | {value} |" for label, value in rows)
    return "\n".join(lines)


def _render_segment_table(agenda) -> str:
    if not agenda.segments:
        return "_(no segments)_"
    # Column order matches the form UI's vertical layout (time, duration,
    # then type) — Duration before Type so the eye scans "when / how long /
    # what" left-to-right, the same shape models naturally produce when
    # asked for a schedule overview.
    segments_by_id = {seg.id: seg for seg in agenda.segments if seg.id}
    lines = ["| Time | Duration | Type | Role taker | Details |", "|---|---|---|---|---|"]
    for seg in agenda.segments:
        # Phase B: `seg.role_taker` is a structured `Attendee | None`. Pass
        # both name and DB-authoritative `member_id` so `format_role_display`
        # picks the (member)/(guest) badge from DB truth, not from the static
        # CLUB_MEMBERS list.
        rt = seg.role_taker
        role = format_role_display(
            rt.name if rt else "",
            member_id=rt.member_id if rt else "",
        )
        details = format_segment_detail_cell(seg, segments_by_id)
        lines.append(f"| {seg.start_time} | {seg.duration} | {seg.type} | {role} | {details} |")
    return "\n".join(lines)


def _fold(summary: str, body: str) -> str:
    """Wrap in <details> so the table folds by default in markdown renderers
    that pass inline HTML through (the web chat panel uses @uiw/react-md-editor
    which does). Chat clients without HTML support — e.g. Telegram — will see
    the body inline; the tags are minor noise but the data stays visible."""
    return f"<details>\n<summary>{summary}</summary>\n\n{body}\n\n</details>"


def _render_intro_block(text: str) -> str:
    """Wrap intro paragraph(s) in a Markdown fenced code block so the
    content is visually separated from the fold's summary line and from
    surrounding prose — without a fence, intros run together with the
    title and look like the agent's own commentary.

    The fence length is chosen to exceed any backtick run in the text
    (CommonMark accepts variable-length fences) so an intro that
    happens to contain its own ``` won't close the outer block early.

    A single-line intro is padded with a trailing blank line so the
    rendered code block has at least two visual rows — without the
    pad a one-liner like 'ai is moving at astonishing speed' renders
    as a cramped, single-row strip."""
    longest_run = 0
    current = 0
    for ch in text:
        if ch == "`":
            current += 1
            longest_run = max(longest_run, current)
        else:
            current = 0
    fence = "`" * max(3, longest_run + 1)
    body = text if "\n" in text else text + "\n"
    return f"{fence}\n{body}\n{fence}"


def _wholesale_suffix(tool_trace: list[dict]) -> str:
    """The missing-fields nudge that historically followed the creation table.
    Reads `missing_required_fields` from the most recent successful create/clone
    tool result. Empty string when no creation tool fired or no fields missing."""
    for trace in reversed(tool_trace):
        if trace.get("name") not in _CREATE_TOOL_NAMES or trace.get("status") != "ok":
            continue
        result = trace.get("result")
        if not isinstance(result, dict):
            continue
        missing_labels = _format_missing_labels(result.get("missing_required_fields"))
        if missing_labels:
            return f"\n\nStill need: {missing_labels}. Please provide these so I can update the draft."
        return "\n\nPlease confirm the draft above; tell me which field or role to adjust if anything is off."
    return ""


def _all_preview_payloads(tool_trace: list[dict]) -> list[dict]:
    """Every successful `preview_meeting` result in this turn, in call order.

    The agent can run multiple `preview_meeting` calls in parallel within a
    single turn (e.g. user asks "show me #446, #425, and #413"). We render
    every result, not just the last — otherwise earlier previews vanish."""
    payloads: list[dict] = []
    for trace in tool_trace:
        if trace.get("name") not in _PREVIEW_TOOL_NAMES or trace.get("status") != "ok":
            continue
        result = trace.get("result")
        if isinstance(result, dict):
            payloads.append(result)
    return payloads


def _build_agenda_addendum(tool_trace: list[dict], agenda, assistant_text_so_far: str) -> str:
    """Append meta and/or segment table(s) based on what the turn did.

    - Wholesale mutation (create / clone / revert): both tables + missing-fields
      nudge. ALWAYS fires regardless of model output — the route is the single
      source of truth for membership-annotated tables; if the model regressed
      and emitted its own (likely unannotated) table, we tolerate the cosmetic
      duplication rather than ship a table without the deterministic `(member)`
      / `(guest)` badges.
    - Meta-only edit: meta table only. Skipped if model emitted a meta-table
      marker (rare; current prompt tells fine-grained replies to be one sentence).
    - Segment-only edit: segment table only. Same skip rule.
    - No mutation but a successful `preview_meeting` ran this turn: render the
      preview's meta + segment tables (labeled "preview of #N" so users don't
      mistake them for the current agenda).
    - Otherwise (chit-chat, refusal, observation-only): empty.

    Tables are wrapped in <details> so they fold by default."""
    meta_changed, segment_changed, wholesale = _classify_agenda_changes(tool_trace)

    if meta_changed or segment_changed or wholesale:
        # Only suppress on duplicate detection for non-wholesale paths. Wholesale
        # always fires (see docstring).
        if not wholesale and _already_has_summary_table(assistant_text_so_far):
            return ""

        parts: list[str] = []
        if wholesale or meta_changed:
            parts.append(_fold("📌 Meeting Meta", _render_meta_table(agenda)))
            # Introduction fold rides with the Meta fold (same axis: meeting-
            # level info). Omit when intro is empty — no point rendering an
            # empty section.
            intro_text = (agenda.meta.introduction or "").strip()
            if intro_text:
                parts.append(_fold("📝 Introduction", _render_intro_block(intro_text)))
        if wholesale or segment_changed:
            parts.append(_fold("📋 Agenda", _render_segment_table(agenda)))
        body = "\n\n".join(parts)

        suffix = _wholesale_suffix(tool_trace) if wholesale else ""
        return "\n\n" + body + suffix

    previews = _all_preview_payloads(tool_trace)
    if previews:
        return render_preview_addendum(previews)

    if _show_current_was_called(tool_trace) or _save_draft_preview_was_called(tool_trace):
        # Read-only display path: show full draft (Meta + Intro + Agenda).
        # save_draft preview reuses this layout so the user sees what they'd
        # be saving before confirming. No missing-fields nudge (not a creation
        # event), no "(preview of #N)" label since it IS the user's current
        # agenda.
        parts = [_fold("📌 Meeting Meta", _render_meta_table(agenda))]
        intro_text = (agenda.meta.introduction or "").strip()
        if intro_text:
            parts.append(_fold("📝 Introduction", _render_intro_block(intro_text)))
        parts.append(_fold("📋 Agenda", _render_segment_table(agenda)))
        return "\n\n" + "\n\n".join(parts)

    return ""


def _show_current_was_called(tool_trace: list[dict]) -> bool:
    return any(trace.get("name") in _SHOW_CURRENT_TOOL_NAMES and trace.get("status") == "ok" for trace in tool_trace)


def _save_draft_preview_was_called(tool_trace: list[dict]) -> bool:
    for trace in tool_trace:
        if trace.get("name") != "save_draft" or trace.get("status") != "ok":
            continue
        result = trace.get("result")
        if isinstance(result, dict) and result.get("pending_confirmation") is True:
            return True
    return False


def _already_has_summary_table(text: str) -> bool:
    # Detector recognizes both English and Chinese table headers so the
    # deterministic addendum doesn't double up on whatever the model emitted.
    return any(
        marker in text
        for marker in (
            "| Meeting No.",
            "| Field | Value",
            "| Time | Type",
            "| 信息 |",
            "| 项目 |",
            "| 会议编号 |",
        )
    )


@r.post("/turn")
async def agent_turn(
    payload: str = Form(...),
    image: UploadFile | None = File(None),
    user=Depends(get_current_user),
):
    try:
        req = MeetingAgentTurnRequest.model_validate_json(payload)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e

    user_id = getattr(user, "uid", None)
    # Ownership check runs BEFORE upload validation. Two reasons:
    # (a) don't waste read/validate work on a foreign-session probe;
    # (b) keep the response shape uniform — a foreign session always
    # returns the generic `session_unavailable` SSE, regardless of
    # whether the attached image was valid. Otherwise an attacker
    # could distinguish "image rejected (HTTP 400)" from "session
    # foreign (SSE error)" and infer ownership state.
    if not await agent_turn_store.verify_session_access(req.session_id, user_id=user_id):
        return _session_unavailable_response()

    image_bytes: bytes | None = None
    image_ct: str | None = None
    if image is not None:
        image_ct = image.content_type or "application/octet-stream"
        if image_ct not in _ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail="image must be jpg, png, or webp")
        image_bytes = await image.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="image must not be empty")
        if len(image_bytes) > _MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="image must be smaller than 5 MB")

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            tail_seq, history_json = await agent_turn_store.load(req.session_id, user_id=user_id)
            next_seq = tail_seq + 1

            full_history = ModelMessagesTypeAdapter.validate_python(history_json) if history_json else []
            # Pydantic AI only injects this agent's `_sys_parts` when
            # message_history is empty — and a prior turn (specialist
            # or router) may have persisted a SystemPromptPart with a
            # different agent's prompt. Replace it with this agent's
            # prompt so we always run with the correct identity.
            full_history = replace_system_prompt(full_history, MEETING_SYSTEM_PROMPT)
            # Cap context window at the last N user turns. Older turns drop off
            # here; they remain in agent_turns (so the UI can still show the
            # full conversation), only the portion fed to the LLM is trimmed.
            history = truncate_to_last_turns(full_history)
            # Eager-fetch the live members directory once per turn. The agent
            # tools (`set_role`, `add_segment`) consult this to resolve a
            # bare-name LLM arg ("Joyce Feng") to a structured `Attendee`
            # carrying the real DB `member_id`. ~20 rows; one cheap query.
            from app.db.core import get_members

            members_directory = await asyncio.to_thread(get_members) or []
            deps = AgendaDeps(
                agenda=copy.deepcopy(req.agenda_snapshot),
                session_id=req.session_id,
                user_id=getattr(user, "uid", None),
                current_user_message=req.user_message,
                image_data=image_bytes,
                image_content_type=image_ct,
                members_directory=members_directory,
            )

            attachment_block = ""
            if image_bytes:
                attachment_block = (
                    "\n[Attachment]\n" "image_attached: true\n" f"content_type: {image_ct or 'image/jpeg'}\n"
                )

            language_hint = f"[Reply language] {_detect_user_language(req.user_message)}\n"

            # Resolve "today" in the club's local timezone (Asia/Shanghai).
            # SoarHigh is a Shenzhen club and the meetings table stores dates
            # in local Shanghai time; using UTC here would drift the model's
            # "今年/上个月/今天" resolution by up to 8 hours during morning
            # hours when UTC is still on the previous day.
            today_iso = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
            # Shorten segment ids to 5-char UUID prefixes for the model. Wire
            # format on both the request and `agenda_after` keeps full UUIDs;
            # the shortening applies ONLY to the prompt JSON the model reads.
            # See `agents/meeting/segment_ids.py` for the bug class this
            # closes vs. the prior `s1..sN` per-turn alias scheme.
            short_dump = shorten_agenda_dump(req.agenda_snapshot.model_dump())
            prompt = SNAPSHOT_TEMPLATE.format(
                snapshot_json=json.dumps(short_dump, ensure_ascii=False, indent=2),
                next_seq=next_seq,
                tail_seq=tail_seq,
                user_message=req.user_message,
                attachment_block=attachment_block,
                language_hint=language_hint,
                today=today_iso,
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
                                    # Two distinct failure modes need distinct handling:
                                    # 1) Tool name is registered on the agent BUT missing from
                                    #    capabilities.py — a configuration mistake. CI's
                                    #    `test_capability_registry_covers_registered_specialist_tools`
                                    #    should catch it, but if CI is bypassed / incomplete /
                                    #    hot-fixed, we fail closed here so the misconfiguration
                                    #    surfaces immediately instead of running the disallowed tool.
                                    # 2) Tool name is NOT registered (model hallucination like
                                    #    "api:save_draft"). Let it fall through to Pydantic AI's
                                    #    natural unknown-tool retry path so the model self-corrects
                                    #    mid-turn instead of crashing the whole turn.
                                    try:
                                        require_tool_allowed(AgentKind.MEETING, call_part.tool_name)
                                    except AgentPolicyError as policy_err:
                                        registered = {t.name for t in agent._function_toolset.tools.values()}
                                        if call_part.tool_name in registered:
                                            raise
                                        log.warning(
                                            "meeting agent policy rejected unregistered tool %r "
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
            assistant_text_so_far = "".join(assistant_text_chunks)
            agenda_addendum = _build_agenda_addendum(tool_trace, deps.agenda, assistant_text_so_far)
            if agenda_addendum:
                assistant_text_chunks.append(agenda_addendum)
                final_text = f"{final_text or ''}{agenda_addendum}"
                yield _sse("assistant_text", {"chunk": agenda_addendum})
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
            await agent_turn_store.save_turn(
                req.session_id,
                user_id=user_id,
                turn=AgentTurnRecord(
                    seq=next_seq,
                    agent_kind=AgentKind.MEETING,
                    route=RouteKind.SPECIALIST,
                    user_message=req.user_message,
                    assistant_text=assistant_text,
                    tool_trace=tool_trace,
                    router_decision=req.router_decision or {},
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

    user_id = getattr(user, "uid", None)
    turn = await agent_turn_store.load_turn(req.session_id, req.target_seq, user_id=user_id)
    if turn is None:
        raise HTTPException(status_code=404, detail=f"turn {req.target_seq} not found")
    # AgentKind is a str Enum, so equality covers both enum and raw string forms.
    if turn.agent_kind != AgentKind.MEETING or turn.agenda_before is None:
        raise HTTPException(
            status_code=400, detail=f"turn {req.target_seq} is not a meeting edit and cannot be reverted"
        )

    await agent_turn_store.delete_turns_at_or_after(req.session_id, req.target_seq, user_id=user_id)
    return {
        "agenda": turn.agenda_before,
        "new_tail_seq": req.target_seq - 1,
    }
