"""Tests for the shared meeting-lookup service.

Covers parse_query (free-text → filters), resolve_meetings (filters → cards),
the projections (meeting_to_card / meeting_to_preview), and the lock /
exact-no fast-path invariants. The agent-facing wrappers in
`meeting_agent.tools` are exercised through their own test file."""

from __future__ import annotations

from unittest.mock import patch

from app.services.meeting_lookup import (
    MeetingFilters,
    fetch_meeting_full,
    meeting_to_card,
    meeting_to_preview,
    parse_query,
    resolve_from_query,
    resolve_meetings,
)


def _meetings_pool() -> list[dict]:
    """A small recent-meetings pool covering every filter axis. Order matches
    `get_meetings(page=1)` semantics (most recent first)."""
    return [
        {
            "id": "u1",
            "no": 451,
            "type": "Regular",
            "theme": "Aging Gracefully",
            "date": "2026-04-25",
            "manager": {"name": "Joyce Feng"},
            "segments": [{}] * 22,
        },
        {
            "id": "u2",
            "no": 450,
            "type": "Workshop",
            "theme": "Emojis Across Cultures",
            "date": "2026-04-18",
            "manager": {"name": "Rui Zheng"},
            "segments": [{}] * 18,
        },
        {
            "id": "u3",
            "no": 449,
            "type": "Regular",
            "theme": "Lessons from Failure",
            "date": "2026-04-11",
            "manager": {"name": "Joyce Feng"},
            "segments": [{}] * 21,
        },
        {
            "id": "u4",
            "no": 448,
            "type": "Custom",
            "theme": "Open Mic Night",
            "date": "2026-04-04",
            "manager": {"name": "Frank Zeng"},
            "segments": [{}] * 5,
        },
        {
            "id": "u5",
            "no": 447,
            "type": "Workshop",
            "theme": "Storytelling 101",
            "date": "2026-03-28",
            "manager": {"name": "Amy Fang"},
            "segments": [{}] * 16,
        },
    ]


# ---------- meeting_to_card / meeting_to_preview ----------


def test_meeting_to_card_extracts_manager_name_from_attendee_dict():
    card = meeting_to_card(
        {
            "no": 425,
            "type": "Workshop",
            "theme": "Emojis",
            "date": "2025-11-01",
            "manager": {"id": "m1", "name": "Joyce Feng"},
            "segments": [{}, {}, {}],
        }
    )
    assert card == {
        "no": 425,
        "type": "Workshop",
        "theme": "Emojis",
        "date": "2025-11-01",
        "manager_name": "Joyce Feng",
        "segment_count": 3,
    }


def test_meeting_to_card_handles_string_manager_and_missing_fields():
    """Some legacy DB rows store manager as a bare string, and theme/date can
    be null. Card output normalizes empties to '' rather than None so the
    chat UI doesn't render literal 'None' values."""
    card = meeting_to_card(
        {
            "no": None,
            "manager": "Rui Zheng",
            "segments": None,
        }
    )
    assert card["manager_name"] == "Rui Zheng"
    assert card["theme"] == ""
    assert card["date"] == ""
    assert card["segment_count"] == 0


def test_meeting_to_preview_projects_meta_and_segments():
    raw = {
        "no": 388,
        "type": "Workshop",
        "theme": "Test Theme",
        "date": "2026-01-01",
        "manager": {"name": "Joyce"},
        "start_time": "19:15",
        "end_time": "21:30",
        "location": "L",
        "segments": [
            {
                "type": "SAA",
                "start_time": "19:30",
                "duration": "3",
                "role_taker": {"name": "Liz Huang"},
            },
            {
                "type": "Workshop",
                "start_time": "20:00",
                "duration": 30,
                "role_taker": "Rui Zheng",
            },
        ],
    }
    preview = meeting_to_preview(raw)
    assert preview["no"] == 388
    assert preview["manager"] == "Joyce"
    assert preview["start_time"] == "19:15"
    assert preview["end_time"] == "21:30"
    assert preview["segments"][0] == {
        "type": "SAA",
        "start_time": "19:30",
        "duration": 3,
        "role_taker": "Liz Huang",
    }
    # Bare-string role_taker also resolves correctly.
    assert preview["segments"][1]["role_taker"] == "Rui Zheng"


def test_meeting_to_preview_includes_introduction_field():
    """preview_meeting needs intro for the route's foldable Introduction
    block AND so the LLM has the actual paragraph if a follow-up turn
    asks 'what does the intro say'. Pre-fix the projection silently
    dropped intro and the model would paraphrase from theme."""
    raw = {
        "no": 425,
        "manager": {"name": "Joyce"},
        "introduction": "Discussing the future of AI and society.",
        "segments": [],
    }
    preview = meeting_to_preview(raw)
    assert preview["introduction"] == "Discussing the future of AI and society."


def test_meeting_to_preview_introduction_empty_string_when_missing():
    """Normalize missing/None introduction to empty string so consumers
    (route render) can do a simple `.strip() and render` check."""
    preview = meeting_to_preview({"no": 1, "manager": "M", "segments": []})
    assert preview["introduction"] == ""


def test_meeting_to_preview_coerces_string_duration_to_int():
    preview = meeting_to_preview(
        {"segments": [{"type": "X", "start_time": "19:00", "duration": "abc", "role_taker": ""}]}
    )
    # Non-int duration → 0 (rather than crashing); the model can surface the
    # weirdness if it matters.
    assert preview["segments"][0]["duration"] == 0


# ---------- parse_query ----------


def test_parse_query_blank_returns_empty_filters():
    assert parse_query("") == MeetingFilters()
    assert parse_query("   ") == MeetingFilters()
    assert parse_query(None) == MeetingFilters()  # type: ignore[arg-type]


def test_parse_query_bare_digit_takes_exact_no_path():
    assert parse_query("451") == MeetingFilters(no=451)


def test_parse_query_hash_prefix_takes_exact_no_path():
    assert parse_query("#451") == MeetingFilters(no=451)


def test_parse_query_chinese_meeting_no_takes_exact_no_path():
    """'第 451 期' is the most common Chinese phrasing — must resolve to
    a clean exact-no, not fall through to substring matching."""
    assert parse_query("第451期").no == 451


def test_parse_query_meeting_no_word_phrasing():
    assert parse_query("Meeting No: 451").no == 451
    assert parse_query("meeting no.451").no == 451


def test_parse_query_digit_with_substantial_alpha_falls_through_to_substring():
    """A query like '2024 awards' has digits but isn't a meeting-number
    request — the alpha tokens dominate. Should NOT route to exact-no.
    parse_query routes the keyword to theme_substring (most non-LLM-caller
    queries are topic-shaped; agent uses structured args directly)."""
    f = parse_query("2024 awards")
    assert f.no is None
    assert f.theme_substring is not None and "2024" in f.theme_substring


def test_parse_query_workshop_keyword_sets_type_filter():
    assert parse_query("workshop").type_filter == "Workshop"
    assert parse_query("工作坊").type_filter == "Workshop"


def test_parse_query_regular_and_custom_keywords():
    assert parse_query("regular meeting").type_filter == "Regular"
    assert parse_query("常规").type_filter == "Regular"
    assert parse_query("custom").type_filter == "Custom"


def test_parse_query_recency_one_lowers_limit_to_1():
    """'上次' / 'last' / 'previous' all map to limit=1 — most recent ONE
    meeting matching the rest of the filters."""
    for q in ("上次", "上一次 workshop", "最近一次", "last workshop", "previous"):
        assert parse_query(q).limit == 1, f"failed on {q!r}"


def test_parse_query_recency_three_lowers_limit_to_3():
    assert parse_query("最近三次").limit == 3
    assert parse_query("recent 3 workshops").limit == 3


def test_parse_query_last_3_resolves_to_limit_3_not_1():
    """Regression: 'last' is a substring of 'last 3', so the original
    if/elif order (ONE before THREE) made 'last 3 workshops' resolve to
    limit=1. Order swapped to THREE → ONE → FIVE so the longer phrase
    wins."""
    assert parse_query("last 3 workshops").limit == 3
    assert parse_query("近三次 regular").limit == 3


def test_parse_query_recency_general_keeps_default_limit_5():
    """General '最近' / 'recent' alone is the broadest — keep the default
    5-card cap, don't accidentally collapse to 1."""
    assert parse_query("最近的 workshop").limit == 5
    assert parse_query("recent meetings").limit == 5


def test_parse_query_extracts_keyword_from_chinese_phrasing():
    """parse_query routes the extracted keyword to `theme_substring`
    (most non-LLM-caller queries are topic-shaped). The agent uses
    structured args directly, so this is only for backwards-compat with
    admin scripts and tests."""
    f = parse_query("Joyce 主持的那次 workshop")
    assert f.theme_substring == "joyce"
    assert f.type_filter == "Workshop"


def test_parse_query_extracts_keyword_from_english_phrasing():
    f = parse_query("the one with Emojis")
    assert f.theme_substring == "emojis"


def test_parse_query_combined_descriptor():
    """Real query: '上次 Joyce 主持的 workshop' → exact-no=None,
    theme_substring='joyce' (parse_query default field), type=Workshop, limit=1."""
    f = parse_query("上次 Joyce 主持的 workshop")
    assert f.no is None
    assert f.theme_substring == "joyce"
    assert f.type_filter == "Workshop"
    assert f.limit == 1


def test_parse_query_strips_english_manager_role_tokens():
    """The model often re-phrases the user's '做 meeting manager' as English
    'managed' / 'manager' before calling — production observation. The
    parser must reduce these to the bare keyword so noise doesn't pollute
    the substring (parse_query routes to theme_substring as its single
    output field)."""
    for q in (
        "Joyce managed",
        "Joyce manager",
        "Joyce managed by",
        "Joyce hosted",
        "Joyce host",
        "Joyce led",
        "Joyce presented",
        "Joyce ran",
    ):
        f = parse_query(q)
        assert f.theme_substring == "joyce", f"failed on {q!r}: got {f.theme_substring!r}"


def test_parse_query_handles_mixed_chinese_english_manager_phrasing():
    """The exact production query that surfaced the bug, plus a few
    natural variants. All should resolve to theme_substring='joyce'."""
    for q in (
        "Joyce 最近做 meeting manager 的那次",
        "Joyce 最近 做meeting manager 的那次",
        "Joyce 最近做meeting manager的那次",
        "上次 Joyce hosted 的会议",
    ):
        f = parse_query(q)
        assert f.theme_substring == "joyce", f"failed on {q!r}: got {f.theme_substring!r}"


# ---------- resolve_meetings ----------


def test_resolve_meetings_empty_filters_returns_recent_top_5():
    """Default MeetingFilters() with limit=5 takes the recent pool and
    returns the top 5 in DB order (most recent first), with envelope
    metadata reflecting that nothing was filtered out."""
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=_meetings_pool()):
        result = resolve_meetings(MeetingFilters())
    assert [c["no"] for c in result["cards"]] == [451, 450, 449, 448, 447]
    assert result["total_matches"] == 5
    assert result["pool_size"] == 5
    assert result["limit_clamped"] is False


def test_resolve_meetings_envelope_signals_clamp_when_pool_exceeds_limit():
    """The whole reason for the envelope: when the pool has more matches
    than `limit`, the LLM needs to know so it can disclose to the user.
    Pre-envelope the agent silently returned top-5 and users had to
    follow up with 'why didn't I see meeting X' (observed regression
    surfaced in the screenshot when listing Custom meetings)."""
    extras = [
        # Inject 4 more Workshops so total Workshop matches (6) exceeds
        # the default limit of 5.
        {
            "id": "u6",
            "no": 446,
            "type": "Workshop",
            "theme": "X",
            "date": "2026-03-21",
            "manager": {"name": "M"},
            "segments": [],
        },
        {
            "id": "u7",
            "no": 445,
            "type": "Workshop",
            "theme": "Y",
            "date": "2026-03-14",
            "manager": {"name": "M"},
            "segments": [],
        },
        {
            "id": "u8",
            "no": 444,
            "type": "Workshop",
            "theme": "Z",
            "date": "2026-03-07",
            "manager": {"name": "M"},
            "segments": [],
        },
        {
            "id": "u9",
            "no": 443,
            "type": "Workshop",
            "theme": "W",
            "date": "2026-02-28",
            "manager": {"name": "M"},
            "segments": [],
        },
    ]
    pool = [*_meetings_pool(), *extras]
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=pool):
        result = resolve_meetings(MeetingFilters(type_filter="Workshop", limit=5))
    assert len(result["cards"]) == 5
    assert result["total_matches"] == 6
    assert result["limit_clamped"] is True


def test_resolve_meetings_exact_no_uses_fetch_full_path():
    """Filter with `no=` set must hit fetch_meeting_full (targeted fetch),
    not scan the bulk recent pool — that's the URL-length / row-cap fix."""
    fake_meeting = {"no": 425, "type": "Workshop", "theme": "Test", "manager": {"name": "Joyce"}, "segments": []}
    with (
        patch("app.services.meeting_lookup.fetch_meeting_full", return_value=fake_meeting) as mock_full,
        patch("app.services.meeting_lookup.db_meetings_recent") as mock_pool,
    ):
        result = resolve_meetings(MeetingFilters(no=425))

    mock_full.assert_called_once_with(425)
    mock_pool.assert_not_called()
    assert len(result["cards"]) == 1
    assert result["cards"][0]["no"] == 425
    assert result["total_matches"] == 1
    assert result["limit_clamped"] is False


def test_resolve_meetings_exact_no_returns_empty_envelope_when_missing():
    with patch("app.services.meeting_lookup.fetch_meeting_full", return_value=None):
        result = resolve_meetings(MeetingFilters(no=99999))
    assert result["cards"] == []
    assert result["total_matches"] == 0
    assert result["limit_clamped"] is False


def test_resolve_meetings_exact_no_respects_type_filter():
    """`MeetingFilters(no=425, type_filter='Regular')` must return [] if
    the meeting exists but isn't Regular — filters AND."""
    fake = {"no": 425, "type": "Workshop", "theme": "T", "manager": {"name": "J"}, "segments": []}
    with patch("app.services.meeting_lookup.fetch_meeting_full", return_value=fake):
        assert resolve_meetings(MeetingFilters(no=425, type_filter="Regular"))["cards"] == []
        assert resolve_meetings(MeetingFilters(no=425, type_filter="Workshop"))["cards"][0]["no"] == 425


def test_resolve_meetings_filters_by_type_only():
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=_meetings_pool()):
        result = resolve_meetings(MeetingFilters(type_filter="Workshop"))
    assert [c["no"] for c in result["cards"]] == [450, 447]
    assert result["total_matches"] == 2
    assert result["limit_clamped"] is False


def test_resolve_meetings_name_substring_matches_manager_only():
    """`name_substring` matches manager.name ONLY — separated from theme
    so the model can search each field independently and disclose which
    matches came from where."""
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=_meetings_pool()):
        result = resolve_meetings(MeetingFilters(name_substring="joyce"))
    # Joyce manages 451 and 449 — both surface.
    assert {c["no"] for c in result["cards"]} == {451, 449}


def test_resolve_meetings_name_substring_does_not_match_theme():
    """A theme containing the substring must NOT surface via
    name_substring — that's the whole point of the split. Use
    `theme_substring` for theme search."""
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=_meetings_pool()):
        result = resolve_meetings(MeetingFilters(name_substring="emojis"))
    # 'Emojis' is in meeting 450's theme, but no manager has 'emojis' in
    # their name — should be empty.
    assert result["cards"] == []


def test_resolve_meetings_theme_substring_matches_theme_only():
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=_meetings_pool()):
        result = resolve_meetings(MeetingFilters(theme_substring="emojis"))
    assert [c["no"] for c in result["cards"]] == [450]


def test_resolve_meetings_theme_substring_does_not_match_manager():
    """Symmetric to the name-doesn't-match-theme test — `theme_substring`
    is field-isolated."""
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=_meetings_pool()):
        result = resolve_meetings(MeetingFilters(theme_substring="joyce"))
    assert result["cards"] == []


def test_resolve_meetings_introduction_substring_matches_intro_field():
    pool = [
        {
            "id": "u1",
            "no": 500,
            "type": "Regular",
            "theme": "Generic Topic",
            "introduction": "This meeting will explore leadership in modern startups.",
            "date": "2026-04-01",
            "manager": {"name": "M"},
            "segments": [],
        },
        {
            "id": "u2",
            "no": 499,
            "type": "Regular",
            "theme": "Leadership",
            "introduction": "A short description.",
            "date": "2026-03-25",
            "manager": {"name": "M"},
            "segments": [],
        },
    ]
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=pool):
        result = resolve_meetings(MeetingFilters(introduction_substring="leadership"))
    # Only #500 — 499 has 'Leadership' in theme but not in introduction.
    assert [c["no"] for c in result["cards"]] == [500]


def test_resolve_meetings_includes_full_introduction_when_intro_filter_used():
    """When the call uses `introduction_substring`, returned cards carry
    the full `introduction` text so the LLM has the actual matched
    passage to quote — prevents the hallucination regression where the
    model paraphrased intros from theme alone."""
    intro_text = (
        "This meeting will explore leadership in modern startups, " "from product founders to engineering managers."
    )
    pool = [
        {
            "id": "u1",
            "no": 500,
            "type": "Regular",
            "theme": "T",
            "introduction": intro_text,
            "date": "2026-04-01",
            "manager": {"name": "M"},
            "segments": [],
        },
    ]
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=pool):
        result = resolve_meetings(MeetingFilters(introduction_substring="leadership"))
    assert result["cards"][0]["introduction"] == intro_text


def test_resolve_meetings_omits_introduction_for_non_intro_queries():
    """Theme / name / no / date queries keep the lightweight card shape
    (no introduction field). Adding intro for every query would inflate
    the model's tool-result tokens at limit=50 by ~15KB for a query
    that doesn't need them."""
    pool = [
        {
            "id": "u1",
            "no": 500,
            "type": "Regular",
            "theme": "Leadership",
            "introduction": "Long paragraph the model doesn't need.",
            "date": "2026-04-01",
            "manager": {"name": "Joyce"},
            "segments": [],
        },
    ]
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=pool):
        # theme-only filter
        r1 = resolve_meetings(MeetingFilters(theme_substring="leadership"))
        # name-only filter
        r2 = resolve_meetings(MeetingFilters(name_substring="joyce"))
        # type-only filter
        r3 = resolve_meetings(MeetingFilters(type_filter="Regular"))
    for r in (r1, r2, r3):
        assert "introduction" not in r["cards"][0]


def test_resolve_meetings_intro_included_on_exact_no_path_when_filter_used():
    """The exact-`no` fast path also needs to honor the conditional-intro
    rule — if the user asks lookup_meeting(no=500, introduction_substring='X')
    they get the intro on the card."""
    fake = {
        "no": 500,
        "type": "Regular",
        "theme": "T",
        "introduction": "Something about leadership.",
        "manager": {"name": "M"},
        "segments": [],
    }
    with patch("app.services.meeting_lookup.fetch_meeting_full", return_value=fake):
        with_intro = resolve_meetings(MeetingFilters(no=500, introduction_substring="leadership"))
        without_intro = resolve_meetings(MeetingFilters(no=500))
    assert with_intro["cards"][0]["introduction"] == "Something about leadership."
    assert "introduction" not in without_intro["cards"][0]


def test_resolve_meetings_three_substring_axes_compose_with_and():
    """All three substring axes set means ALL must match within the
    SAME meeting (AND across distinct fields). Demonstrates the
    structural-AND semantics — for OR-across-fields the agent fires
    multiple parallel calls."""
    pool = [
        {
            "id": "u1",
            "no": 600,
            "type": "Regular",
            "theme": "AI in Society",
            "introduction": "Discuss the impact of AI.",
            "date": "2026-04-01",
            "manager": {"name": "Joyce Feng"},
            "segments": [],
        },
        # Wrong manager
        {
            "id": "u2",
            "no": 601,
            "type": "Regular",
            "theme": "AI in Society",
            "introduction": "Discuss the impact of AI.",
            "date": "2026-04-01",
            "manager": {"name": "Frank Zeng"},
            "segments": [],
        },
        # Wrong intro
        {
            "id": "u3",
            "no": 602,
            "type": "Regular",
            "theme": "AI in Society",
            "introduction": "Other content.",
            "date": "2026-04-01",
            "manager": {"name": "Joyce Feng"},
            "segments": [],
        },
    ]
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=pool):
        result = resolve_meetings(
            MeetingFilters(
                name_substring="Joyce",
                theme_substring="AI",
                introduction_substring="impact",
            )
        )
    assert [c["no"] for c in result["cards"]] == [600]


def test_resolve_meetings_date_from_inclusive():
    """`date_from` filters out meetings strictly before that date."""
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=_meetings_pool()):
        result = resolve_meetings(MeetingFilters(date_from="2026-04-11"))
    # 451 (04-25), 450 (04-18), 449 (04-11) match; 448 (04-04), 447 (03-28) drop.
    assert {c["no"] for c in result["cards"]} == {451, 450, 449}


def test_resolve_meetings_date_to_inclusive():
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=_meetings_pool()):
        result = resolve_meetings(MeetingFilters(date_to="2026-04-11"))
    # 449 (04-11), 448 (04-04), 447 (03-28) match.
    assert {c["no"] for c in result["cards"]} == {449, 448, 447}


def test_resolve_meetings_closed_date_range():
    """date_from + date_to combine for a closed inclusive interval."""
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=_meetings_pool()):
        result = resolve_meetings(MeetingFilters(date_from="2026-04-04", date_to="2026-04-18"))
    assert {c["no"] for c in result["cards"]} == {450, 449, 448}


def test_resolve_meetings_date_filter_excludes_undated_meetings():
    """A meeting with no date can't satisfy a date filter — preserves
    the natural user intent ('meetings in October' must HAVE a date)."""
    pool = [
        {"id": "u1", "no": 500, "type": "Regular", "theme": "T", "date": "", "manager": {"name": "M"}, "segments": []},
    ]
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=pool):
        result = resolve_meetings(MeetingFilters(date_from="2026-01-01"))
    assert result["cards"] == []


def test_resolve_meetings_date_combines_with_type_filter():
    """Real query: '10月份第一次例会' → type_filter='Regular' AND
    date_from='2025-10-01' AND date_to='2025-10-31'."""
    pool = [
        {
            "id": "u1",
            "no": 425,
            "type": "Workshop",
            "theme": "Wx",
            "date": "2025-10-15",
            "manager": {"name": "M"},
            "segments": [],
        },
        {
            "id": "u2",
            "no": 424,
            "type": "Regular",
            "theme": "Rx",
            "date": "2025-10-08",
            "manager": {"name": "M"},
            "segments": [],
        },
        {
            "id": "u3",
            "no": 423,
            "type": "Regular",
            "theme": "Ry",
            "date": "2025-09-24",
            "manager": {"name": "M"},
            "segments": [],
        },
    ]
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=pool):
        result = resolve_meetings(MeetingFilters(type_filter="Regular", date_from="2025-10-01", date_to="2025-10-31"))
    # Only the Regular meeting in October.
    assert {c["no"] for c in result["cards"]} == {424}


def test_resolve_meetings_combined_type_and_name():
    """`Joyce` + `Workshop` should narrow further than each filter alone.
    Joyce never managed a Workshop in the fixture → empty."""
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=_meetings_pool()):
        result = resolve_meetings(MeetingFilters(name_substring="joyce", type_filter="Workshop"))
    assert result["cards"] == []
    assert result["total_matches"] == 0


def test_resolve_meetings_limit_clamps_results():
    """Recency='上次' parses to limit=1; resolve must clamp to first
    match. The envelope still reports total_matches across the WHOLE
    pool so the LLM knows there's more."""
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=_meetings_pool()):
        result = resolve_meetings(MeetingFilters(name_substring="joyce", limit=1))
    assert [c["no"] for c in result["cards"]] == [451]
    assert result["total_matches"] == 2  # Joyce manages 451 AND 449
    assert result["limit_clamped"] is True


def test_resolve_meetings_returns_card_shape_not_raw_dict():
    """resolve_meetings must always return projected cards, never the raw
    DB dicts (which would leak internal id and full segment lists)."""
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=_meetings_pool()):
        result = resolve_meetings(MeetingFilters(limit=1))
    assert "id" not in result["cards"][0]
    assert "segment_count" in result["cards"][0]


# ---------- resolve_from_query convenience ----------


def test_resolve_from_query_composes_parse_and_resolve():
    """End-to-end: free text → envelope. parse_query routes to
    theme_substring, so a theme-shaped query like 'Emojis 那次' yields
    the meeting with that theme. Manager-only queries like 'Joyce 主持的'
    no longer compose through parse_query — agent uses structured args
    directly with name_substring for that case."""
    with patch("app.services.meeting_lookup.db_meetings_recent", return_value=_meetings_pool()):
        result = resolve_from_query("Emojis 那次")
    assert [c["no"] for c in result["cards"]] == [450]


def test_resolve_from_query_blank_returns_empty_envelope():
    empty = {"cards": [], "total_matches": 0, "pool_size": 0, "limit_clamped": False}
    assert resolve_from_query("") == empty
    assert resolve_from_query("   ") == empty


# ---------- fetch_meeting_full / DB helper invariants ----------


def test_fetch_meeting_full_uses_targeted_two_query_path():
    """Don't fall back to bulk db_meetings_recent — see the URL-length and
    1000-row-cap regressions documented in the source."""
    with (
        patch("app.services.meeting_lookup.get_meeting_id_by_no", return_value="uuid-X") as mock_id,
        patch("app.services.meeting_lookup.get_meeting_by_id", return_value={"id": "uuid-X", "no": 425}) as mock_full,
        patch("app.services.meeting_lookup.db_meetings_recent") as mock_bulk,
    ):
        result = fetch_meeting_full(425)
    mock_id.assert_called_once_with(425)
    mock_full.assert_called_once_with("uuid-X", user_id=None)
    mock_bulk.assert_not_called()
    assert result["no"] == 425


def test_fetch_meeting_full_returns_none_on_id_miss():
    with (
        patch("app.services.meeting_lookup.get_meeting_id_by_no", return_value=None),
        patch("app.services.meeting_lookup.get_meeting_by_id") as mock_full,
    ):
        assert fetch_meeting_full(99999) is None
    mock_full.assert_not_called()
