"""Tests for the shared member-directory + role-display helpers.

These helpers used to live inside `meeting_agent/tools.py`, where the static
`CLUB_MEMBERS` list doubled as both an LLM prompt hint and a membership
oracle for the route's render layer. That conflation is the root cause of
the meeting-preview member/guest mismatch (issue 2 of the Phase A bugfix):
when the DB carries an authoritative `member_id` for a role taker, that
must win over a static name list. Hence the split:

  * `app.services.member_directory` — domain: holds `CLUB_MEMBERS` (used
    only as the LLM prompt hint and as a legacy bare-string fallback).
  * `app.services.meeting_preview_markdown.format_role_display` — render:
    decides "(member)" / "(guest)" / "All" / "—". Prefers DB `member_id`
    when present; falls back to `is_member_name` for legacy bare strings
    (current draft agendas in the meeting agent never carry member_id).
"""

from __future__ import annotations

from app.services.meeting_preview_markdown import format_role_display
from app.services.member_directory import CLUB_MEMBERS, is_member_name

# ---------- is_member_name (legacy bare-string fallback only) ----------


def test_is_member_name_matches_full_name_case_insensitively():
    assert is_member_name("Liz Huang") is True
    assert is_member_name("LIZ HUANG") is True
    assert is_member_name("liz huang") is True


def test_is_member_name_returns_false_for_unknown_name():
    assert is_member_name("Lucas") is False
    assert is_member_name("Random Person") is False


def test_is_member_name_returns_false_for_blank():
    assert is_member_name("") is False
    assert is_member_name("   ") is False


def test_club_members_is_a_non_empty_list_of_strings():
    """Sanity check: the static list still holds names, not None / dicts.
    The directory module is the only place that should know its shape."""
    assert isinstance(CLUB_MEMBERS, list)
    assert all(isinstance(n, str) and n.strip() for n in CLUB_MEMBERS)
    assert len(CLUB_MEMBERS) > 0


# ---------- format_role_display: structured input (DB member_id authoritative) ----------


def test_format_role_display_uses_member_id_for_membership():
    """When the caller has the DB-authoritative member_id, that is the
    source of truth — NOT the static CLUB_MEMBERS list. The actual production
    bug: meeting #403 had Libra Lee with a real member_id; preview rendered
    her as 'guest' because she isn't in CLUB_MEMBERS."""
    libra_member_id = "00000000-0000-0000-0000-aaaaaaaaaaaa"
    assert format_role_display("Libra Lee", member_id=libra_member_id) == "Libra Lee (member)"


def test_format_role_display_member_id_overrides_club_members_disagreement():
    """Inverse direction: a name that IS in CLUB_MEMBERS but has no
    member_id (e.g. a guest who happens to share a club member's full
    name) must render as 'guest'. DB authority wins both ways."""
    # 'Joyce Feng' is in CLUB_MEMBERS, but if member_id is empty the DB is
    # telling us this segment was a guest who happens to share the name.
    assert format_role_display("Joyce Feng", member_id="") == "Joyce Feng (guest)"


def test_format_role_display_empty_member_id_for_unknown_name_renders_guest():
    assert format_role_display("Lucas", member_id="") == "Lucas (guest)"


def test_format_role_display_all_keyword_skips_membership_badge():
    """Group roles ('All' for warmup, table topic, tea break) have no
    membership concept. Same behavior as legacy bare-string path."""
    assert format_role_display("All", member_id="") == "All"
    assert format_role_display("All", member_id="some-id") == "All"
    # Case-insensitive — DB rows are not normalized.
    assert format_role_display("all", member_id="") == "all"


def test_format_role_display_blank_role_renders_dash():
    assert format_role_display("", member_id="") == "—"
    assert format_role_display("", member_id="anything") == "—"
    assert format_role_display("   ", member_id="") == "—"


# ---------- format_role_display: bare-string legacy fallback ----------


def test_format_role_display_bare_string_member_falls_back_to_club_members():
    """Without a member_id sidecar (current draft agendas, legacy data),
    the helper falls back to CLUB_MEMBERS as the only available signal."""
    assert format_role_display("Liz Huang") == "Liz Huang (member)"
    # Case-insensitive name lookup against CLUB_MEMBERS.
    assert format_role_display("amy fang") == "amy fang (member)"


def test_format_role_display_bare_string_guest_falls_back_to_club_members():
    assert format_role_display("Lucas") == "Lucas (guest)"


def test_format_role_display_bare_string_all_and_blank_legacy_paths():
    """Pin the legacy bare-string paths so we don't regress them while
    extending the helper."""
    assert format_role_display("All") == "All"
    assert format_role_display("") == "—"


def test_format_role_display_member_id_none_treated_as_legacy_fallback():
    """`member_id=None` (caller couldn't find the field) must not be
    treated as 'absent member_id ⇒ guest' — that would silently flip
    members to guests on the current-draft path which has no sidecar.
    None means 'no information', so fall back to CLUB_MEMBERS."""
    assert format_role_display("Liz Huang", member_id=None) == "Liz Huang (member)"
    assert format_role_display("Lucas", member_id=None) == "Lucas (guest)"
