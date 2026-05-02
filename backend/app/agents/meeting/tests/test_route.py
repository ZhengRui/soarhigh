import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition

from app.agents.meeting import agent as agent_module
from app.agents.runtime.contracts import AgentKind, RouteKind
from app.agents.runtime.store import AgentTurnRecord
from app.api.routes.agents.meeting import _already_has_summary_table
from app.api.serv import app
from app.models.meeting import Attendee, Meeting
from app.models.meeting import Segment as MeetingSegment


class ForcedArgsTestModel(TestModel):
    """TestModel variant that forces deterministic args for specific tools."""

    def __init__(self, *, forced_args: dict[str, dict], **kwargs):
        super().__init__(**kwargs)
        self._forced_args = forced_args

    def gen_tool_args(self, tool_def: ToolDefinition):
        if tool_def.name in self._forced_args:
            return self._forced_args[tool_def.name]
        return super().gen_tool_args(tool_def)


def _parse_sse(byte_chunks):
    """Parse SSE byte stream into a list of {"event": ..., "data": ...} dicts."""
    buffer = b""
    events = []
    for chunk in byte_chunks:
        buffer += chunk
        while b"\n\n" in buffer:
            raw, buffer = buffer.split(b"\n\n", 1)
            lines = raw.decode("utf-8").splitlines()
            event_name = None
            data = None
            for line in lines:
                if line.startswith("event: "):
                    event_name = line[len("event: ") :]
                if line.startswith("data: "):
                    data = json.loads(line[len("data: ") :])
            if event_name:
                events.append({"event": event_name, "data": data})
    return events


def _turn_form(body: dict) -> dict:
    return {"payload": json.dumps(body)}


def _fake_planned_meeting() -> Meeting:
    return Meeting(
        id=None,
        no=999,
        type="Regular",
        theme="Route Summary",
        manager=Attendee(id=None, name="Rui Zheng", member_id=""),
        date="2026-05-06",
        start_time="19:15",
        end_time="21:30",
        location="华美居装饰家居城B区809",
        introduction="",
        status="draft",
        awards=[],
        segments=[
            MeetingSegment(
                id="legacy",
                type="Meeting Rules Introduction (SAA)",
                start_time="19:30",
                end_time="19:32",
                duration="2",
                role_taker=Attendee(id=None, name="Joyce Feng", member_id=""),
                title="",
                content="",
                related_segment_ids="",
            )
        ],
    )


@pytest.fixture
def client():
    return TestClient(app)


def test_turn_happy_path_streams_done(client, mock_auth_dep):
    body = {
        "session_id": "t1",
        "user_message": "change SAA to Joyce",
        "agenda_snapshot": {
            "meta": {"start_time": "19:15", "end_time": "21:30"},
            "segments": [
                {
                    "id": "s1",
                    "type": "SAA",
                    "start_time": "19:30",
                    "duration": 3,
                    "role_taker": "Liz",
                    "buffer_before": 0,
                }
            ],
        },
    }

    # TestModel will deterministically call set_role with plausible-looking args.
    # We force segment_id=s1 to match the snapshot we send; otherwise TestModel's
    # auto-generated "a" string triggers the tool's ValueError for unknown segment.
    test_model = ForcedArgsTestModel(
        call_tools=["set_role"],
        forced_args={"set_role": {"segment_id": "s1", "role_taker": "Test"}},
    )
    with patch("app.api.routes.agents.meeting.require_tool_allowed") as policy_check:
        with agent_module.agent.override(model=test_model):
            with client.stream("POST", "/meeting-agent/turn", data=_turn_form(body)) as r:
                assert r.status_code == 200
                events = _parse_sse(r.iter_bytes())

    types = [e["event"] for e in events]
    assert "tool_call_start" in types, f"expected tool_call_start, got: {types}"
    assert "tool_call_end" in types, f"expected tool_call_end, got: {types}"
    assert types[-1] == "done", f"last event should be 'done', got: {types[-1]} (full: {types})"

    # Sanity: agenda_after in the last tool_call_end should be a dict with segments
    last_tool_end = next(e for e in reversed(events) if e["event"] == "tool_call_end")
    assert "agenda_after" in last_tool_end["data"]
    assert isinstance(last_tool_end["data"]["agenda_after"], dict)

    # Regression guard: `result` must carry the actual tool return value, not None.
    # apply_set_role returns {"segment_id": ..., "role_taker": ...}. If we
    # incorrectly read event.content instead of event.result.content, this asserts.
    assert last_tool_end["data"]["result"] is not None, (
        "tool_call_end.result was None — likely using FunctionToolResultEvent.content " "instead of .result.content"
    )
    assert last_tool_end["data"]["result"] == {
        "segment_id": "s1",
        "role_taker": "Test",
    }
    policy_check.assert_called_once_with(AgentKind.MEETING, "set_role")


@pytest.mark.asyncio
async def test_turn_persists_history_cursor_as_json_safe_payload(client, mock_auth_dep, _force_in_memory_store):
    """Regression: `history_cursor` is persisted to Supabase JSONB, which
    supabase-py serializes via json.dumps. Pydantic AI ModelMessage objects
    carry a datetime `timestamp` field; dump_python(mode="json") is what makes
    them JSON-safe. If mode="json" is forgotten, the turn would raise
    `Object of type datetime is not JSON serializable`."""
    store = _force_in_memory_store

    body = {
        "session_id": "persist-t1",
        "user_message": "hello",
        "agenda_snapshot": {
            "meta": {},
            "segments": [
                {
                    "id": "s1",
                    "type": "SAA",
                    "start_time": "19:30",
                    "duration": 3,
                    "role_taker": "Liz",
                    "buffer_before": 0,
                }
            ],
        },
    }
    test_model = ForcedArgsTestModel(
        call_tools=["set_role"],
        forced_args={"set_role": {"segment_id": "s1", "role_taker": "Test"}},
    )
    with agent_module.agent.override(model=test_model):
        with client.stream("POST", "/meeting-agent/turn", data=_turn_form(body)) as r:
            assert r.status_code == 200
            # Drain the stream so the route's post-run save_turn() executes.
            for _ in r.iter_bytes():
                pass

    tail, history = await store.load("persist-t1", user_id="test-user")
    assert tail == 1, f"expected one turn saved, got tail={tail}"
    # The actual regression guard: json.dumps is what supabase-py does internally.
    # If any datetime slipped through, this raises TypeError.
    json.dumps(history)
    turn = await store.load_turn("persist-t1", 1, user_id="test-user")
    assert turn is not None
    json.dumps(turn.history_cursor)
    json.dumps(turn.tool_trace)
    json.dumps(turn.agenda_before)
    json.dumps(turn.agenda_after)


def test_turn_requires_auth(client):
    """Without the auth override, POST /meeting-agent/turn must reject."""
    body = {
        "session_id": "t2",
        "user_message": "hello",
        "agenda_snapshot": {
            "meta": {},
            "segments": [],
        },
    }
    r = client.post("/meeting-agent/turn", data=_turn_form(body))
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text}"


def test_turn_accepts_multipart_image(client, mock_auth_dep):
    body = {
        "session_id": "img-t1",
        "user_message": "用这张图创建",
        "agenda_snapshot": {
            "meta": {"start_time": "19:15"},
            "segments": [
                {
                    "id": "s1",
                    "type": "SAA",
                    "start_time": "19:30",
                    "duration": 3,
                    "role_taker": "Liz",
                    "buffer_before": 0,
                }
            ],
        },
    }
    test_model = ForcedArgsTestModel(
        call_tools=["set_role"],
        forced_args={"set_role": {"segment_id": "s1", "role_taker": "Test"}},
    )
    with agent_module.agent.override(model=test_model):
        with client.stream(
            "POST",
            "/meeting-agent/turn",
            data=_turn_form(body),
            files={"image": ("agenda.png", b"fake-image", "image/png")},
        ) as r:
            assert r.status_code == 200
            events = _parse_sse(r.iter_bytes())

    assert events[-1]["event"] == "done"


def test_turn_appends_creation_summary_table(client, mock_auth_dep):
    raw_text = (
        "SOARHIGH 999th meeting: Route Summary\n"
        "✍ Theme: Route Summary\n"
        "📅 Date: 2026-05-06\n"
        "⏰ Time: 19:30 - 21:30\n"
        "📍 Location: 华美居装饰家居城B区809\n"
        "👧MM: Rui Zheng\n"
        "SAA: Joyce\n"
    )
    body = {
        "session_id": "create-summary",
        "user_message": f"请根据下面文本创建会议草稿\n\n{raw_text}",
        "agenda_snapshot": {
            "meta": {"start_time": "19:15"},
            "segments": [],
        },
    }
    test_model = ForcedArgsTestModel(
        call_tools=["create_from_text"],
        forced_args={"create_from_text": {"raw_text": raw_text}},
    )
    with patch("app.agents.meeting.tools.plan_meeting_from_text", return_value=_fake_planned_meeting()):
        with agent_module.agent.override(model=test_model):
            with client.stream("POST", "/meeting-agent/turn", data=_turn_form(body)) as r:
                assert r.status_code == 200
                events = _parse_sse(r.iter_bytes())

    assistant_text = "".join(e["data"]["chunk"] for e in events if e["event"] == "assistant_text")
    # Both tables present (creation is wholesale).
    assert "| Field | Value |" in assistant_text
    assert "| Meeting No. | 999 |" in assistant_text
    assert "| Meeting Manager | Rui Zheng |" in assistant_text
    assert "| Time | Duration | Type | Role taker |" in assistant_text
    # Tables are wrapped in <details> for default-collapsed display.
    assert "<details>" in assistant_text
    assert "<summary>📌 Meeting Meta</summary>" in assistant_text
    assert "<summary>📋 Agenda</summary>" in assistant_text
    assert "Please confirm the draft above" in assistant_text
    assert events[-1]["event"] == "done"
    assert "| Field | Value |" in events[-1]["data"]["final_text"]


def test_summary_table_detection_accepts_model_generated_chinese_table():
    assert _already_has_summary_table("| 项目 | 内容 |\n|---|---|\n| 会议编号 | 999 |")
    assert _already_has_summary_table("| 信息 | 当前值 |\n|---|---|")
    assert not _already_has_summary_table("已创建草稿, 请确认。")


def test_segment_edit_appends_segment_table_only(client, mock_auth_dep):
    """Fine-grained segment edit (set_role) → segment table only, no meta table."""
    body = {
        "session_id": "edit-segment-only",
        "user_message": "change SAA to Joyce",
        "agenda_snapshot": {
            "meta": {"start_time": "19:30", "end_time": "21:30"},
            "segments": [
                {"id": "s1", "type": "SAA", "start_time": "19:30", "duration": 3, "role_taker": "Liz"},
            ],
        },
    }
    test_model = ForcedArgsTestModel(
        call_tools=["set_role"],
        forced_args={"set_role": {"segment_id": "s1", "role_taker": "Joyce Feng"}},
    )
    with agent_module.agent.override(model=test_model):
        with client.stream("POST", "/meeting-agent/turn", data=_turn_form(body)) as r:
            assert r.status_code == 200
            events = _parse_sse(r.iter_bytes())

    text = "".join(e["data"]["chunk"] for e in events if e["event"] == "assistant_text")
    # Folded segment table present.
    assert "<summary>📋 Agenda</summary>" in text
    assert "| Time | Duration | Type | Role taker |" in text
    # Meta table NOT present (no meta change happened).
    assert "<summary>📌 Meeting Meta</summary>" not in text
    assert "| Field | Value |" not in text


def test_meta_edit_appends_meta_table_only(client, mock_auth_dep):
    """Fine-grained meta edit (set_meta) → meta table only, no segment table."""
    body = {
        "session_id": "edit-meta-only",
        "user_message": "change theme to Resilience",
        "agenda_snapshot": {
            "meta": {"theme": "Old", "start_time": "19:30", "end_time": "21:30"},
            "segments": [
                {"id": "s1", "type": "SAA", "start_time": "19:30", "duration": 3, "role_taker": "Liz"},
            ],
        },
    }
    test_model = ForcedArgsTestModel(
        call_tools=["set_meta"],
        forced_args={"set_meta": {"field": "theme", "value": "Resilience"}},
    )
    with agent_module.agent.override(model=test_model):
        with client.stream("POST", "/meeting-agent/turn", data=_turn_form(body)) as r:
            assert r.status_code == 200
            events = _parse_sse(r.iter_bytes())

    text = "".join(e["data"]["chunk"] for e in events if e["event"] == "assistant_text")
    # Meta table present, folded.
    assert "<summary>📌 Meeting Meta</summary>" in text
    assert "| Theme | Resilience |" in text
    # Segment table NOT present.
    assert "<summary>📋 Agenda</summary>" not in text


def test_preview_meeting_appends_folded_preview_tables(client, mock_auth_dep):
    """preview_meeting is read-only — no agenda mutation — but the user still
    gets the same folded meta + agenda tables (with membership annotations)
    as the create / edit paths, labeled "preview of #N" so they don't think
    we replaced their current agenda."""
    body = {
        "session_id": "preview-1",
        "user_message": "show me #425 agenda",
        "agenda_snapshot": {
            "meta": {"start_time": "19:30"},
            "segments": [
                {"id": "s1", "type": "SAA", "start_time": "19:30", "duration": 3, "role_taker": "Liz"},
            ],
        },
    }
    fake_full_meeting = {
        "id": "uuid-425",
        "no": 425,
        "type": "Workshop",
        "manager": {"id": None, "name": "Joyce Feng", "member_id": ""},
        "theme": "Emojis",
        "date": "2025-05-21",
        "start_time": "19:15",
        "end_time": "21:30",
        "location": "Loc",
        "introduction": "Emojis are tiny pictures that pack big meaning.",
        "segments": [
            {
                "id": "1",
                "type": "Members and Guests Registration, Warm up",
                "start_time": "19:15",
                "duration": "15",
                "role_taker": {"id": None, "name": "All", "member_id": ""},
            },
            {
                "id": "2",
                "type": "Workshop",
                "start_time": "20:08",
                "duration": "29",
                "role_taker": {"id": None, "name": "Lucas", "member_id": ""},  # not in CLUB_MEMBERS
                "title": "Emoji | Storytelling",
                "content": "Workshop pathway notes\nSecond line",
                "related_segment_ids": "",
            },
            {
                "id": "3",
                "type": "Closing Remarks",
                "start_time": "21:14",
                "duration": "1",
                "role_taker": {"id": None, "name": "Amy Fang", "member_id": "m1"},
                "related_segment_ids": "2,missing",
            },
        ],
    }
    test_model = ForcedArgsTestModel(
        call_tools=["preview_meeting"],
        forced_args={"preview_meeting": {"no": 425}},
    )
    with patch("app.services.meeting_lookup.fetch_meeting_full", return_value=fake_full_meeting):
        with agent_module.agent.override(model=test_model):
            with client.stream("POST", "/meeting-agent/turn", data=_turn_form(body)) as r:
                assert r.status_code == 200
                events = _parse_sse(r.iter_bytes())

    text = "".join(e["data"]["chunk"] for e in events if e["event"] == "assistant_text")
    # Both preview tables present, folded, labeled with the meeting number,
    # plus the new Introduction fold (since the meeting has intro text).
    assert "<summary>📌 Meeting #425 Meta</summary>" in text
    assert "<summary>📝 Meeting #425 Introduction</summary>" in text
    assert "Emojis are tiny pictures that pack big meaning." in text
    assert "<summary>📋 Meeting #425 Agenda</summary>" in text
    # Meta table populated from the preview result, not the current agenda.
    assert "| Meeting No. | 425 |" in text
    assert "| Theme | Emojis |" in text
    assert "| Meeting Manager | Joyce Feng |" in text
    # Segment table includes ALL rows (including the late-time Closing Remarks
    # — guards the recent fix where late segments were truncated by the bulk
    # `_db_meetings_recent` 1000-row cap).
    assert "21:14" in text
    assert "Closing Remarks" in text
    assert "| Time | Duration | Type | Role taker | Details |" in text
    assert "Title: Emoji \\| Storytelling" in text
    assert "Content: Workshop pathway notes<br>Second line" in text
    assert "Related: Workshop" in text
    # Membership annotation comes from the route's _format_role_display.
    assert "Lucas (guest)" in text
    assert "Amy Fang (member)" in text
    # The route did NOT also emit a "current agenda" addendum since
    # preview_meeting doesn't mutate the agenda.
    assert "<summary>📋 Agenda</summary>" not in text


def test_build_agenda_addendum_renders_every_preview_in_one_turn():
    """When multiple `preview_meeting` calls fire in one turn (parallel tool
    calls — e.g. "show me #446, #425, #413"), the route must render the
    meta + agenda fold pair for EACH preview, in call order. The previous
    `_latest_preview_payload` helper only kept the last and silently
    dropped earlier ones."""
    from app.agents.meeting.models import Agenda, Meta
    from app.api.routes.agents.meeting import _build_agenda_addendum

    tool_trace = [
        {
            "name": "preview_meeting",
            "status": "ok",
            "result": {
                "no": 446,
                "type": "Workshop",
                "theme": "Career, Growth, Choice",
                "manager": "Joyce Feng",
                "date": "2025-04-09",
                "start_time": "19:15",
                "end_time": "21:30",
                "location": "Loc",
                "segments": [
                    {"start_time": "19:30", "type": "SAA", "duration": 2, "role_taker": "Liz Huang"},
                ],
            },
        },
        {
            "name": "preview_meeting",
            "status": "ok",
            "result": {
                "no": 425,
                "type": "Workshop",
                "theme": "Emojis",
                "manager": "Lucas",
                "date": "2025-01-22",
                "start_time": "19:15",
                "end_time": "21:30",
                "location": "Loc",
                "segments": [
                    {"start_time": "20:08", "type": "Workshop", "duration": 29, "role_taker": "Lucas"},
                ],
            },
        },
    ]
    addendum = _build_agenda_addendum(tool_trace, Agenda(meta=Meta(), segments=[]), assistant_text_so_far="")

    # Both meetings get their own pair of folds.
    assert "<summary>📌 Meeting #446 Meta</summary>" in addendum
    assert "<summary>📋 Meeting #446 Agenda</summary>" in addendum
    assert "<summary>📌 Meeting #425 Meta</summary>" in addendum
    assert "<summary>📋 Meeting #425 Agenda</summary>" in addendum
    # Each meeting's data is in its own block.
    assert "| Meeting No. | 446 |" in addendum
    assert "| Meeting No. | 425 |" in addendum
    assert "Liz Huang (member)" in addendum
    # Lucas isn't in CLUB_MEMBERS — guest annotation comes from the route's helper.
    assert "Lucas (guest)" in addendum
    # Order preserved: call order, not reverse.
    assert addendum.index("Meeting #446 Meta") < addendum.index("Meeting #425 Meta")
    # Neither meeting carries an introduction in this fixture, so no
    # Introduction fold should appear (empty fold would be visual noise).
    assert "Introduction" not in addendum


def test_preview_addendum_intro_fold_omitted_when_intro_empty():
    """Preview render skips the Introduction fold entirely when the
    historical meeting has no intro text. We don't ship an empty
    section; cleaner UX to drop it."""
    from app.agents.meeting.models import Agenda, Meta
    from app.api.routes.agents.meeting import _build_agenda_addendum

    tool_trace = [
        {
            "name": "preview_meeting",
            "status": "ok",
            "result": {
                "no": 999,
                "type": "Regular",
                "theme": "X",
                "manager": "M",
                "date": "2026-01-01",
                "introduction": "",  # empty
                "segments": [],
            },
        },
    ]
    addendum = _build_agenda_addendum(tool_trace, Agenda(meta=Meta(), segments=[]), assistant_text_so_far="")
    assert "<summary>📌 Meeting #999 Meta</summary>" in addendum
    assert "<summary>📋 Meeting #999 Agenda</summary>" in addendum
    assert "Introduction" not in addendum


def test_render_intro_block_wraps_in_triple_backtick_fence():
    """Intros render inside a code fence so they're visually separated
    from the fold title — without a fence, the intro runs together with
    the summary line and reads like the agent's commentary."""
    from app.api.routes.agents.meeting import _render_intro_block

    body = _render_intro_block("Hello world")
    lines = body.splitlines()
    # Opening fence, content line, padding blank line (one-liner gets
    # padded so the rendered block isn't a cramped single row), closing fence.
    assert lines[0] == "```"
    assert lines[1] == "Hello world"
    assert lines[2] == ""
    assert lines[3] == "```"


def test_render_intro_block_single_line_padded_to_two_rows():
    """Single-line intros get a trailing blank line so the rendered
    code block has at least two visual rows. Without padding, short
    intros like 'ai is moving fast' render as a cramped one-row strip."""
    from app.api.routes.agents.meeting import _render_intro_block

    body = _render_intro_block("ai is moving at astonishing speed")
    inner_lines = body.splitlines()[1:-1]  # everything between the fences
    assert len(inner_lines) >= 2
    assert inner_lines[0] == "ai is moving at astonishing speed"
    assert inner_lines[1] == ""


def test_render_intro_block_multi_line_intro_not_padded_further():
    """Multi-line intros already have visual height; no extra blank
    line appended (would just create dead whitespace at the bottom)."""
    from app.api.routes.agents.meeting import _render_intro_block

    body = _render_intro_block("Line one\nLine two\nLine three")
    inner_lines = body.splitlines()[1:-1]
    assert inner_lines == ["Line one", "Line two", "Line three"]


def test_render_intro_block_fence_grows_to_outlast_inner_backticks():
    """If the intro itself contains a triple-backtick run (e.g. someone
    pasted a code sample), the outer fence has to be longer than the
    longest inner run so it doesn't close prematurely."""
    from app.api.routes.agents.meeting import _render_intro_block

    intro_with_fence = "Use ``` for code blocks like this."
    body = _render_intro_block(intro_with_fence)
    # Outer fence must be at least 4 backticks (1 longer than the
    # longest inner run of 3).
    first_line = body.splitlines()[0]
    assert first_line == "````"
    last_line = body.splitlines()[-1]
    assert last_line == "````"


def test_preview_addendum_intro_fold_present_when_intro_text_present():
    from app.agents.meeting.models import Agenda, Meta
    from app.api.routes.agents.meeting import _build_agenda_addendum

    tool_trace = [
        {
            "name": "preview_meeting",
            "status": "ok",
            "result": {
                "no": 449,
                "type": "Regular",
                "theme": "Authenticity in Connection",
                "manager": "Liz Huang",
                "date": "2026-04-08",
                "introduction": "Discussing how we move beyond performative connection.",
                "segments": [],
            },
        },
    ]
    addendum = _build_agenda_addendum(tool_trace, Agenda(meta=Meta(), segments=[]), assistant_text_so_far="")
    assert "<summary>📝 Meeting #449 Introduction</summary>" in addendum
    # Intro body is wrapped in a fenced code block so it's visually
    # separated from the fold's summary line.
    # Single-line intro padded with a blank row inside the fence so the
    # rendered block is at least two rows tall.
    assert "```\nDiscussing how we move beyond performative connection.\n\n```" in addendum
    # Order: Meta → Intro → Agenda within one preview block.
    meta_idx = addendum.index("Meeting #449 Meta")
    intro_idx = addendum.index("Meeting #449 Introduction")
    agenda_idx = addendum.index("Meeting #449 Agenda")
    assert meta_idx < intro_idx < agenda_idx


def test_build_agenda_addendum_intro_fold_omitted_for_segment_only_edits():
    """A pure segment edit (set_role / set_duration) renders ONLY the
    Agenda fold. Bringing the intro fold along would clutter the reply
    on every per-segment fix; intro rides with the Meta axis."""
    from app.agents.meeting.models import Agenda, Meta, Segment
    from app.api.routes.agents.meeting import _build_agenda_addendum

    agenda = Agenda(
        meta=Meta(introduction="A meaningful description that should NOT show up here."),
        segments=[
            Segment(
                id="s1",
                type="Prepared Speech",
                start_time="19:30",
                duration=2,
                role_taker="Liz",
                title="Current | title",
                content="Current\ncontent",
            ),
            Segment(
                id="s2",
                type="Prepared Speech Evaluation",
                start_time="19:32",
                duration=3,
                related_segment_ids="s1,missing",
            ),
        ],
    )
    tool_trace = [{"name": "set_role", "status": "ok"}]
    addendum = _build_agenda_addendum(tool_trace, agenda, assistant_text_so_far="")
    assert "<summary>📋 Agenda</summary>" in addendum
    assert "Introduction" not in addendum
    assert "| Time | Duration | Type | Role taker | Details |" in addendum
    assert "Title: Current \\| title" in addendum
    assert "Content: Current<br>content" in addendum
    assert "Related: Prepared Speech" in addendum


def test_build_agenda_addendum_intro_fold_rides_with_meta_changes():
    """When Meta is rendered (wholesale or meta-edit), the Introduction
    fold rides along — same axis (meeting-level info)."""
    from app.agents.meeting.models import Agenda, Meta
    from app.api.routes.agents.meeting import _build_agenda_addendum

    agenda = Agenda(
        meta=Meta(no=500, theme="X", introduction="Why this meeting matters."),
        segments=[],
    )
    tool_trace = [{"name": "set_meta", "status": "ok"}]
    addendum = _build_agenda_addendum(tool_trace, agenda, assistant_text_so_far="")
    assert "<summary>📌 Meeting Meta</summary>" in addendum
    assert "<summary>📝 Introduction</summary>" in addendum
    # Wrapped in a fence + padded to 2-row minimum for visual block weight.
    assert "```\nWhy this meeting matters.\n\n```" in addendum


def test_show_current_agenda_appends_folded_tables_for_current_draft(client, mock_auth_dep):
    """`show_current_agenda` is read-only — no mutation — but the user gets
    the same folded meta + agenda tables (with membership annotations) as
    after a create / edit. The summary labels are the plain "Meeting Meta"
    / "Agenda" headers (not "preview of #N") because this IS the current
    draft, not a historical lookup."""
    body = {
        "session_id": "show-current-1",
        "user_message": "show me the current agenda",
        "agenda_snapshot": {
            "meta": {
                "no": 451,
                "type": "Regular",
                "theme": "Lying Flat",
                "manager": "Vicky Yang",
                "start_time": "19:30",
                "end_time": "21:30",
                "introduction": "Why are young people choosing to lie flat?",
            },
            # Phase B: agenda_snapshot carries structured `role_taker` so
            # the route addendum can render the (member)/(guest) badge from
            # the DB-authoritative `member_id`. Liz is a club member with a
            # real member_id; Lucas is a guest with empty member_id.
            "segments": [
                {
                    "id": "s1",
                    "type": "SAA",
                    "start_time": "19:30",
                    "duration": 2,
                    "role_taker": {"id": "att-liz", "name": "Liz Huang", "member_id": "m-liz"},
                },
                {
                    "id": "s2",
                    "type": "Opening Remarks",
                    "start_time": "19:32",
                    "duration": 2,
                    "role_taker": {"id": None, "name": "Lucas", "member_id": ""},
                },
            ],
        },
    }
    test_model = ForcedArgsTestModel(
        call_tools=["show_current_agenda"],
        forced_args={"show_current_agenda": {}},
    )
    with agent_module.agent.override(model=test_model):
        with client.stream("POST", "/meeting-agent/turn", data=_turn_form(body)) as r:
            assert r.status_code == 200
            events = _parse_sse(r.iter_bytes())

    text = "".join(e["data"]["chunk"] for e in events if e["event"] == "assistant_text")
    # Plain summaries — NOT the "preview of #N" labels used by preview_meeting.
    # Includes the new Introduction fold (snapshot has intro text).
    assert "<summary>📌 Meeting Meta</summary>" in text
    assert "<summary>📝 Introduction</summary>" in text
    assert "Why are young people choosing to lie flat?" in text
    assert "<summary>📋 Agenda</summary>" in text
    # Meta drawn from the snapshot.
    assert "| Meeting No. | 451 |" in text
    assert "| Theme | Lying Flat |" in text
    # Segment table includes the membership annotations from the route.
    assert "Liz Huang (member)" in text
    assert "Lucas (guest)" in text


def test_chitchat_does_not_append_any_table(client, mock_auth_dep):
    """No tools fired → no addendum."""
    body = {
        "session_id": "chitchat-1",
        "user_message": "hi",
        "agenda_snapshot": {
            "meta": {"start_time": "19:30"},
            "segments": [],
        },
    }
    # TestModel without call_tools just emits text and finishes.
    test_model = ForcedArgsTestModel(call_tools=[], forced_args={})
    with agent_module.agent.override(model=test_model):
        with client.stream("POST", "/meeting-agent/turn", data=_turn_form(body)) as r:
            assert r.status_code == 200
            events = _parse_sse(r.iter_bytes())

    text = "".join(e["data"]["chunk"] for e in events if e["event"] == "assistant_text")
    assert "<details>" not in text
    assert "| Field | Value |" not in text
    assert "| Time | Type" not in text


def test_turn_rejects_unsupported_image_type(client, mock_auth_dep):
    body = {"session_id": "img-bad", "user_message": "create", "agenda_snapshot": {"meta": {}, "segments": []}}
    r = client.post(
        "/meeting-agent/turn",
        data=_turn_form(body),
        files={"image": ("agenda.gif", b"fake-image", "image/gif")},
    )
    assert r.status_code == 400


def test_route_renders_folds_for_save_draft_preview():
    """save_draft preview triggers Meta + Introduction + Agenda folds."""
    from app.agents.meeting.models import Agenda, Meta
    from app.api.routes.agents.meeting import _build_agenda_addendum

    agenda = Agenda(
        meta=Meta(
            no=451,
            theme="T",
            manager="M",
            date="2026-06-01",
            start_time="19:30",
            end_time="21:30",
            introduction="hi",
        ),
        segments=[],
    )
    tool_trace = [
        {
            "name": "save_draft",
            "status": "ok",
            "result": {"mode": "create", "pending_confirmation": True, "preview": {}},
        }
    ]
    out = _build_agenda_addendum(tool_trace, agenda, assistant_text_so_far="")
    assert "📌 Meeting Meta" in out
    assert "📝 Introduction" in out
    assert "📋 Agenda" in out


def test_route_does_not_render_folds_for_save_draft_persisted():
    """Confirmed save: model already showed the folds last turn; no
    duplicate render here."""
    from app.agents.meeting.models import Agenda, Meta
    from app.api.routes.agents.meeting import _build_agenda_addendum

    agenda = Agenda(meta=Meta(no=451), segments=[])
    tool_trace = [
        {
            "name": "save_draft",
            "status": "ok",
            "result": {"mode": "create", "pending_confirmation": False, "meeting_id": "x"},
        }
    ]
    out = _build_agenda_addendum(tool_trace, agenda, assistant_text_so_far="")
    assert out == ""


# ---------------------------------------------------------------------------
# /meeting-agent/revert
# ---------------------------------------------------------------------------


def _meeting_turn(seq: int, **overrides) -> AgentTurnRecord:
    """Test helper: build an AgentTurnRecord shaped like a meeting specialist turn."""
    return AgentTurnRecord(
        seq=seq,
        agent_kind=AgentKind.MEETING,
        route=RouteKind.SPECIALIST,
        user_message=overrides.get("user_message", f"msg {seq}"),
        assistant_text=overrides.get("assistant_text", f"reply {seq}"),
        tool_trace=overrides.get("tool_trace", []),
        agenda_before=overrides.get("agenda_before", {"snapshot_taken_before": seq}),
        agenda_after=overrides.get("agenda_after", {"snapshot_taken_after": seq}),
        history_cursor=overrides.get("history_cursor", [{"m": seq}]),
    )


@pytest.mark.asyncio
async def test_revert_returns_agenda_before_and_deletes_later_turns(client, mock_auth_dep, _force_in_memory_store):
    """Seeding the store directly is simpler than driving N turns through the
    SSE route. This exercises just the revert endpoint."""
    store = _force_in_memory_store
    for seq in range(1, 4):  # seeds turns 1, 2, 3
        await store.save_turn("rev-s1", user_id="test-user", turn=_meeting_turn(seq))

    r = client.post("/meeting-agent/revert", json={"session_id": "rev-s1", "target_seq": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    # Reverting to turn 2 returns the agenda as it was BEFORE turn 2 ran.
    assert body["agenda"] == {"snapshot_taken_before": 2}
    assert body["new_tail_seq"] == 1

    # Turns 2 and 3 are gone; turn 1 survives.
    assert await store.load_turn("rev-s1", 1, user_id="test-user") is not None
    assert await store.load_turn("rev-s1", 2, user_id="test-user") is None
    assert await store.load_turn("rev-s1", 3, user_id="test-user") is None
    tail, _ = await store.load("rev-s1", user_id="test-user")
    assert tail == 1


@pytest.mark.asyncio
async def test_revert_to_first_turn_rewinds_to_zero(client, mock_auth_dep, _force_in_memory_store):
    store = _force_in_memory_store
    await store.save_turn(
        "rev-s2",
        user_id="test-user",
        turn=_meeting_turn(
            1, agenda_before={"initial": True}, agenda_after={"initial": True, "after": True}, history_cursor=[]
        ),
    )
    r = client.post("/meeting-agent/revert", json={"session_id": "rev-s2", "target_seq": 1})
    assert r.status_code == 200, r.text
    assert r.json()["new_tail_seq"] == 0
    assert r.json()["agenda"] == {"initial": True}

    tail, _ = await store.load("rev-s2", user_id="test-user")
    assert tail == 0


@pytest.mark.asyncio
async def test_revert_rejects_non_meeting_turns(client, mock_auth_dep, _force_in_memory_store):
    """Stats and router-only turns have no agenda to revert to."""
    store = _force_in_memory_store
    await store.save_turn(
        "rev-stats",
        user_id="test-user",
        turn=AgentTurnRecord(
            seq=1,
            agent_kind=AgentKind.STATISTICS,
            route=RouteKind.SPECIALIST,
            user_message="who won most awards?",
            assistant_text="...",
            agenda_before=None,
        ),
    )
    r = client.post("/meeting-agent/revert", json={"session_id": "rev-stats", "target_seq": 1})
    assert r.status_code == 400
    assert "not a meeting edit" in r.json()["detail"]


def test_revert_unknown_turn_returns_404(client, mock_auth_dep):
    r = client.post("/meeting-agent/revert", json={"session_id": "rev-none", "target_seq": 1})
    assert r.status_code == 404


def test_revert_bad_seq_returns_400(client, mock_auth_dep):
    r = client.post("/meeting-agent/revert", json={"session_id": "rev-x", "target_seq": 0})
    assert r.status_code == 400


def test_revert_requires_auth(client):
    r = client.post("/meeting-agent/revert", json={"session_id": "whatever", "target_seq": 1})
    assert r.status_code in (401, 403)
