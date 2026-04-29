"""Static club member directory + membership lookup.

Lives outside `meeting_agent/prompts.py` so non-prompt callers (the meeting
preview renderer, the route addendum, ANY render layer that wants a
membership decision for a bare-string role taker) don't have to import from
the agent's prompt module to do so. The previous setup also conflated two
roles for `CLUB_MEMBERS`:

  * **LLM prompt hint** — prompts list club members so the model can resolve
    a first-name reference ("Joyce" → "Joyce Feng") to a full name.
  * **Membership oracle** — the route addendum used the same list to render
    "(member)" / "(guest)" badges in the preview / draft tables.

The conflation is what surfaced the meeting #403 bug: a saved meeting whose
DB row carries an authoritative `member_id` for "Libra Lee" was rendered
"(guest)" because the preview projection threw away `member_id` and the
renderer fell back to the static name list (Libra isn't on it). The split
restores the correct precedence:

  * For saved / hydrated meetings (preview path): DB `member_id` is the
    source of truth. The render layer should consult the directory ONLY as
    a fallback when no `member_id` is available — i.e. legacy bare-string
    role takers from the current draft agenda, where the backend `Segment`
    model carries no member_id (Phase B will close that gap).
  * For LLM prompts: the directory remains the same hint surface — the
    model has no DB and needs the static list to resolve first-name
    references.

Phase 2 of the broader agent work plans to make this dynamic from Supabase.
Until then, edit this list when the active member roster changes."""

from __future__ import annotations

CLUB_MEMBERS: list[str] = [
    "Rui Zheng",
    "Joyce Feng",
    "Leta Li",
    "Frank Zeng",
    "Max Long",
    "Julia Cao",
    "Jessica Peng",
    "Amy Fang",
    "Jenny Li",
    "Alice Song",
    "Jean Li",
    "Helen Chen",
    "John Lin",
    "Catherine Yang",
    "Liz Huang",
    "Shelly Qu",
    "Vicky Yang",
    "Victory Liu",
    "Albert Ding",
    "Libra Lee",
]


def is_member_name(name: str) -> bool:
    """Case-insensitive full-name match against the static directory.

    LEGACY-FALLBACK USE ONLY. Callers that have a DB-authoritative
    `member_id` available MUST consult that instead — see the module
    docstring for why. This function exists for the remaining bare-string
    paths (current draft agenda; legacy preview rows that lack the
    `role_taker_member_id` sidecar).
    """
    needle = (name or "").strip().lower()
    if not needle:
        return False
    return any(member.lower() == needle for member in CLUB_MEMBERS)
