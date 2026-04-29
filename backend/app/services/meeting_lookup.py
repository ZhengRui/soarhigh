"""Shared meeting-lookup primitives.

Used today by `app.agents.meeting` for the clone path (`lookup_meeting` → user
confirmation → `clone_from_meeting`). Designed to be reused by the upcoming
statistics agent for analytics queries — both agents share the same fuzzy
resolver instead of each rolling their own. See plans/2026-04-27-statistics-
agent-and-router-design.md.

Three layers:

  1. **DB helpers** — sync wrappers around `app.db.core` that hold the
     module-level `DB_LOCK`. Supabase-py's underlying httpx client is sync
     and NOT thread-safe under concurrent access, so the lock serializes
     every DB call this module makes. Tests can monkeypatch the wrappers
     directly.

  2. **Projections** — `meeting_to_card`, `meeting_to_preview`. Pure
     functions that take a raw meeting dict from the DB and project it
     into the shape the agents and route surface to the chat UI.

  3. **Resolution** — `resolve_meetings(filters)` is the high-level entry
     point. Takes a `MeetingFilters` and returns a list of cards.
     `parse_query(query)` translates a free-text descriptor into filters
     (number, manager substring, theme substring via OR, type, recency).
     Both agents can call `resolve_meetings` directly with structured
     filters, or hand a free-text query to `parse_query` first.
"""

from __future__ import annotations

import asyncio
import re
import threading
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pydantic_ai import ModelRetry

from app.db.core import get_meeting_by_id, get_meeting_id_by_no, get_meetings


def parse_iso_date_or_raise(label: str, value: str) -> date:
    """Validate that `value` is a real ISO YYYY-MM-DD calendar date.

    A bare regex (`^\\d{4}-\\d{2}-\\d{2}$`) accepts impossible dates like
    '2025-13-01' or '2025-02-31'. Those would compare lexicographically
    inside the resolver and silently mis-filter (e.g. '2025-13-01' >
    '2025-12-31' is True). `date.fromisoformat` rejects them outright so
    the model gets a useful retry message.

    Shared between `meeting_lookup` (date_from / date_to in agent tools)
    and `meeting_stats` (analytics tool date filters)."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ModelRetry(
            f"{label} must be a real ISO calendar date (YYYY-MM-DD, " f"e.g. '2025-10-01'); got {value!r}."
        ) from None


# Supabase-py wraps a sync httpx client whose HTTP/2 stream state corrupts
# under concurrent access — surfaces as `httpx.RemoteProtocolError: Server
# disconnected`. Every DB call in this module goes through this lock so
# parallel agent tools (e.g. several preview_meeting in one turn) fall back
# to sequential DB I/O. Costs a few hundred ms per extra call but is fully
# reliable.
DB_LOCK = threading.Lock()

MeetingType = Literal["Regular", "Workshop", "Custom"]


@dataclass(frozen=True)
class MeetingFilters:
    """Structured filter spec for `resolve_meetings`.

    Composition is AND across distinct axes. Each substring axis searches
    one field only — the model orchestrates OR-across-fields by firing
    multiple parallel calls (e.g. theme + introduction for a topic
    keyword). This separation lets reply text disclose which result came
    from which field, which is itself useful information.

      `no`                        — exact display number; bypasses the
                                    pool scan via fetch_meeting_full.
      `name_substring`            — case-insensitive substring on
                                    `manager.name` ONLY. Use for "Joyce
                                    主持的" / "managed by Frank" queries.
                                    Does NOT match theme or intro.
      `theme_substring`           — case-insensitive substring on `theme`.
                                    Use when user references the meeting
                                    title/topic ("Emojis 那次", "主题
                                    有关教育的").
      `introduction_substring`    — case-insensitive substring on
                                    `introduction` (description paragraph
                                    body). Use when user references intro
                                    content ("提到 leadership 的").
      `type_filter`               — restrict to Regular / Workshop / Custom.
      `date_from`                 — ISO YYYY-MM-DD inclusive lower bound.
      `date_to`                   — ISO YYYY-MM-DD inclusive upper bound.
      `limit`                     — max cards returned.
    """

    no: int | None = None
    name_substring: str | None = None
    theme_substring: str | None = None
    introduction_substring: str | None = None
    type_filter: MeetingType | None = None
    date_from: str | None = None
    date_to: str | None = None
    limit: int = 5


# ---------- DB helpers (locked) ----------


def db_meetings_recent(limit: int = 50) -> list[dict]:
    """Most-recent N meetings as raw DB dicts. Use for candidate-pool scans
    where targeted-by-no isn't applicable (fuzzy descriptor queries)."""
    with DB_LOCK:
        page = get_meetings(user_id=None, status=None, page=1, page_size=limit)
    return page.get("items", [])


def fetch_meeting_full(no: int) -> dict | None:
    """Resolve a meeting by display number to a fully-hydrated dict (meta +
    all segments + manager attendee).

    Two cheap targeted queries (`get_meeting_id_by_no` then
    `get_meeting_by_id`) instead of a bulk `db_meetings_recent(N)` scan.
    The bulk path uses `.in_(meeting_ids)` whose URL grows with N and
    overflows PostgREST / Cloudflare URL-length limits when several preview
    or clone tools fire concurrently in one turn. The targeted path also
    sidesteps the PostgREST 1000-row response cap that truncated cloned
    agendas past 21:03."""
    with DB_LOCK:
        meeting_id = get_meeting_id_by_no(no)
        if meeting_id is None:
            return None
        return get_meeting_by_id(meeting_id, user_id=None)


# ---------- Projections ----------


def _meeting_manager_name(meeting: dict) -> str:
    """Manager rows can be either an attendee dict or a bare string,
    depending on which DB code path produced them. Normalize."""
    manager = meeting.get("manager") or {}
    if isinstance(manager, dict):
        return manager.get("name") or ""
    return manager or ""


def meeting_to_card(meeting: dict, *, include_introduction: bool = False) -> dict:
    """Project a raw meeting dict into the lightweight card shape the
    agents surface to the chat UI from `lookup_meeting`.

    `include_introduction` adds the meeting's full `introduction` field
    to the card. The resolver sets this when the call used
    `introduction_substring` so the LLM has the actual matched text to
    quote in its reply instead of paraphrasing (or, worse, fabricating
    plausible-sounding intro content from the theme alone — observed
    regression in production)."""
    card = {
        "no": meeting.get("no"),
        "type": meeting.get("type", ""),
        "date": meeting.get("date", ""),
        "theme": meeting.get("theme", ""),
        "manager_name": _meeting_manager_name(meeting),
        "segment_count": len(meeting.get("segments") or []),
    }
    if include_introduction:
        card["introduction"] = meeting.get("introduction") or ""
    return card


def _segment_to_preview(seg: dict) -> dict:
    """Project a DB segment row into the preview shape.

    `role_taker` stays a bare string so the model-facing tool result keeps
    a uniform shape across creation, edit, and preview paths (the LLM never
    needs to reason about membership). The DB-authoritative `member_id`
    rides as a sidecar field `role_taker_member_id` that the preview
    renderer uses to decide the (member)/(guest) badge — see
    `meeting_preview_markdown.format_role_display`. Without this sidecar,
    the renderer would have to guess membership from the static
    `CLUB_MEMBERS` list, overriding DB truth (the meeting #403 'Libra Lee
    (guest)' bug)."""
    role = seg.get("role_taker") or {}
    if isinstance(role, dict):
        role_name = role.get("name") or ""
        role_member_id = role.get("member_id") or ""
    else:
        role_name = role or ""
        role_member_id = ""
    try:
        duration = int(seg.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    return {
        "id": seg.get("id", ""),
        "type": seg.get("type", ""),
        "start_time": seg.get("start_time", ""),
        "duration": duration,
        "role_taker": role_name,
        "role_taker_member_id": role_member_id,
        "title": seg.get("title") or "",
        "content": seg.get("content") or "",
        "related_segment_ids": seg.get("related_segment_ids") or "",
    }


def meeting_to_preview(meeting: dict) -> dict:
    """Project a fully-hydrated meeting dict into the preview shape
    surfaced by `preview_meeting` (meta + introduction + ordered segments).

    `introduction` is included in the preview projection so the route can
    render a foldable Introduction block alongside the Meta and Agenda
    folds, AND so the model has the actual intro text in the tool result
    if the user follows up about intro content (avoids the
    paraphrase-from-theme hallucination)."""
    return {
        "no": meeting.get("no"),
        "type": meeting.get("type", ""),
        "theme": meeting.get("theme", ""),
        "date": meeting.get("date", ""),
        "manager": _meeting_manager_name(meeting),
        "start_time": meeting.get("start_time", ""),
        "end_time": meeting.get("end_time", ""),
        "location": meeting.get("location", ""),
        "introduction": meeting.get("introduction") or "",
        "segments": [_segment_to_preview(s) for s in (meeting.get("segments") or [])],
    }


# ---------- Free-text query parsing ----------


_RECENCY_ONE_KEYWORDS = ("上次", "上一次", "最近一次", "最新一次", "last", "previous")
_RECENCY_THREE_KEYWORDS = ("最近三次", "近三次", "recent 3", "last 3")
_RECENCY_FIVE_KEYWORDS = ("最近", "近期", "recent", "lately")
_TYPE_KEYWORDS: tuple[tuple[tuple[str, ...], MeetingType], ...] = (
    (("workshop", "工作坊"), "Workshop"),
    (("regular", "常规"), "Regular"),
    (("custom",), "Custom"),
)
# Filler / connective words that are noise inside a fuzzy query — strip
# before treating the remainder as a name/theme substring. The model often
# translates the user's Chinese phrasing into English before calling the
# tool ('做meeting manager' → 'managed' / 'manager'), so this list covers
# both languages plus common LLM rephrasings.
_NOISE_WORDS = (
    *_RECENCY_ONE_KEYWORDS,
    *_RECENCY_THREE_KEYWORDS,
    *_RECENCY_FIVE_KEYWORDS,
    # Type tokens — surfaced separately into type_filter; noise here too.
    "workshop",
    "regular",
    "custom",
    "工作坊",
    "常规",
    # Manager-role tokens — Chinese
    "主持的",
    "主持",
    "做meeting manager",
    "做 meeting manager",
    "做的",
    "讲的",
    # Manager-role tokens — English (model rephrasings of '做 meeting manager')
    "managed by",
    "managed",
    "managing",
    "manager",
    "manages",
    "hosted by",
    "hosted",
    "hosting",
    "host",
    "ran",
    "led by",
    "led",
    "presented by",
    "presented",
    # Theme phrasings
    "the one with",
    "the one about",
    "about",
    # Connectors / determiners
    "的",
    "那次",
    "那个",
    "那场",
    # Generic meeting / event words
    "meeting",
    "meetings",
    "会议",
    "session",
)


_EXACT_NO_RE = re.compile(
    # Optional prefix tokens: '#', '第' (Chinese ordinal lead-in), or
    # English 'meeting'/'no.'/'meeting no.' in any combination.
    r"^\s*(?:#|第\s*|meeting\s*no\.?\s*|meeting\s*|no\.?\s*)?"
    # Optional colon (ASCII or fullwidth) between prefix and digits.
    r"\s*[:：]?\s*"  # noqa: RUF001
    r"(\d{1,4})"
    # Optional ordinal suffix: 期/次 (Chinese), or English ordinal (451st).
    r"\s*(?:期|次|st|nd|rd|th)?"
    r"\s*$",
    re.IGNORECASE,
)


def parse_query(query: str) -> MeetingFilters:
    """Translate a free-text descriptor into structured `MeetingFilters`.

    Handles four signals:

      • Bare digit / `#NNN` / `第 NNN 期` / `Meeting No: NNN` → `no` (exact lookup).
      • Type keywords (workshop / regular / custom / 工作坊 / 常规) → `type_filter`.
      • Recency keywords (上次 / 最近一次 / 最近三次 / recent / last) → `limit`.
      • Remaining tokens (after stripping noise above) → `name_substring`.

    Returns an empty `MeetingFilters()` for a blank / null query — caller
    should treat that as "no match" rather than "match everything"."""
    q = (query or "").strip()
    if not q:
        return MeetingFilters()

    # Exact-no fast path: query is entirely a meeting-number reference (no
    # other intent). Mid-query digits like "2024 awards" don't match because
    # the regex demands end-of-string after the digits.
    m = _EXACT_NO_RE.match(q)
    if m:
        return MeetingFilters(no=int(m.group(1)))

    ql = q.lower()

    # Type filter
    type_filter: MeetingType | None = None
    for keywords, kind in _TYPE_KEYWORDS:
        if any(kw in ql for kw in keywords):
            type_filter = kind
            break

    # Recency → limit. Order matters: longer phrases are checked FIRST
    # because their keyword sets share substrings with shorter phrases.
    # 'last 3' contains 'last' so we'd otherwise resolve 'last 3 workshops'
    # as limit=1; '最近一次' contains '最近' so 最近一次 would otherwise
    # resolve via the broad fallback. Check THREE → ONE → FIVE
    # (broadest fallback last).
    limit = 5
    if any(kw in ql for kw in _RECENCY_THREE_KEYWORDS):
        limit = 3
    elif any(kw in ql for kw in _RECENCY_ONE_KEYWORDS):
        limit = 1
    elif any(kw in ql for kw in _RECENCY_FIVE_KEYWORDS):
        limit = 5

    # Substring: strip noise + the matched type keyword. Whatever's left
    # is the user's free-form keyword and we route it to `theme_substring`
    # since most non-LLM-caller queries are topic-shaped. parse_query is
    # off the agent hot path (the agent passes structured args directly);
    # admin scripts wanting name-only search should construct
    # `MeetingFilters` themselves rather than going through the parser.
    remainder = ql
    for kw in _NOISE_WORDS:
        remainder = remainder.replace(kw, " ")
    # Collapse whitespace & punctuation that survived stripping.
    remainder = " ".join(remainder.split()).strip(" ,.;:!?、，。")  # noqa: RUF001
    theme_substring = remainder or None

    return MeetingFilters(
        theme_substring=theme_substring,
        type_filter=type_filter,
        limit=limit,
    )


# ---------- Resolution ----------


def _matches_filters(meeting: dict, filters: MeetingFilters) -> bool:
    if filters.type_filter and meeting.get("type") != filters.type_filter:
        return False
    if filters.name_substring:
        if filters.name_substring.lower() not in _meeting_manager_name(meeting).lower():
            return False
    if filters.theme_substring:
        if not _field_matches_substring(meeting.get("theme") or "", filters.theme_substring):
            return False
    if filters.introduction_substring:
        if not _field_matches_substring(
            meeting.get("introduction") or "",
            filters.introduction_substring,
        ):
            return False
    if filters.date_from or filters.date_to:
        # ISO date strings sort lexicographically. Missing meeting.date
        # treated as "doesn't match the range" — preserves the typical
        # user intent ("show me meetings in October" → must HAVE a date).
        meeting_date = meeting.get("date") or ""
        if not meeting_date:
            return False
        if filters.date_from and meeting_date < filters.date_from:
            return False
        if filters.date_to and meeting_date > filters.date_to:
            return False
    return True


def _field_matches_substring(value: str, needle: str) -> bool:
    """Case-insensitive field match with token boundaries for short ASCII.

    Literal substring matching is useful for natural meeting titles, but
    short English acronyms like "AI" should not match inside unrelated
    words such as "Gain". For two- or three-character alphanumeric ASCII
    needles, require non-alphanumeric boundaries on both sides; longer
    terms keep the original substring behavior.
    """
    haystack = value or ""
    query = (needle or "").strip()
    if not query:
        return True
    if re.fullmatch(r"[A-Za-z0-9]{2,3}", query):
        return (
            re.search(
                rf"(?<![A-Za-z0-9]){re.escape(query)}(?![A-Za-z0-9])",
                haystack,
                re.IGNORECASE,
            )
            is not None
        )
    return query.lower() in haystack.lower()


_POOL_SIZE = 200


def resolve_meetings(filters: MeetingFilters, *, pool: list[dict] | None = None) -> dict:
    """Apply `filters` against the recent-meetings pool. Returns:

        {
            "cards": [...up to filters.limit cards, most-recent first...],
            "total_matches": int,   # full count in the candidate pool
            "pool_size": int,       # how big the candidate pool is (200)
            "limit_clamped": bool,  # True if total_matches > len(cards)
        }

    The pool is bounded at 200 most-recent meetings (covers ~4 years of
    weekly meetings — enough for typical fuzzy queries; deeper history
    needs the explicit `no=` path). Filtering scans the whole pool so
    `total_matches` reflects ALL pool matches, not the post-limit slice.

    Exact-`no` filter is a fast path: targeted fetch_meeting_full bypasses
    the pool scan. Other filters still apply (e.g. `no=425,
    type_filter="Workshop"` returns the meeting only if it's a Workshop).

    `pool` (kw-only) lets the caller pre-fetch the candidate pool ONCE and
    reuse it across multiple resolve calls — the agent uses this to share
    one DB fetch across parallel `lookup_meeting` tool calls within a
    single turn (e.g. cross-language theme + intro fan-out)."""
    # Introduction text is included in cards only when the call used
    # `introduction_substring` — the model needs the actual matched text
    # to quote rather than paraphrase. For other queries we keep the
    # lightweight default to avoid bloating the LLM's tool-result context.
    include_intro = filters.introduction_substring is not None

    if filters.no is not None:
        meeting = fetch_meeting_full(filters.no)
        if meeting is None or not _matches_filters(meeting, filters):
            return {
                "cards": [],
                "total_matches": 0,
                "pool_size": 1,
                "limit_clamped": False,
            }
        return {
            "cards": [meeting_to_card(meeting, include_introduction=include_intro)],
            "total_matches": 1,
            "pool_size": 1,
            "limit_clamped": False,
        }

    items = pool if pool is not None else db_meetings_recent(limit=_POOL_SIZE)
    all_matches = [m for m in items if _matches_filters(m, filters)]
    capped = all_matches[: filters.limit]
    return {
        "cards": [meeting_to_card(m, include_introduction=include_intro) for m in capped],
        "total_matches": len(all_matches),
        "pool_size": len(items),
        "limit_clamped": len(all_matches) > len(capped),
    }


# ---------- Convenience: free-text → cards ----------


def resolve_from_query(query: str) -> dict:
    """Convenience composition: `parse_query(query)` then
    `resolve_meetings(filters)`. Returns the empty result dict for an
    empty / no-intent query (we treat 'user said nothing meaningful' as
    'no match' rather than 'match everything', which is what
    `resolve_meetings(MeetingFilters())` would otherwise do — that's the
    right default for a fuzzy chat tool)."""
    filters = parse_query(query)
    if filters == MeetingFilters():
        return {"cards": [], "total_matches": 0, "pool_size": 0, "limit_clamped": False}
    return resolve_meetings(filters)


# ---------- Agent-facing tool wrappers (shared by every agent) ----------
#
# The meeting agent and the statistics agent both register a `lookup_meeting`
# and a `preview_meeting` tool. Both registrations delegate to the helpers
# here so there is exactly one definition of arg-validation, one pool-cache
# helper, and one set of envelope-shape rules. Both agents' deps types
# (`AgendaDeps`, `StatsDeps`) carry the per-turn pool cache fields
# (`meeting_pool_cache`, `meeting_pool_lock`) — the helpers duck-type on
# those attributes.


async def get_or_fetch_pool(deps: Any) -> list[dict]:
    """Lazy-fetch the candidate-meetings pool once per turn and cache it
    on `deps`. The asyncio.Lock is bound to the current event loop on
    first use (cannot be created at deps construction time because the
    loop may not exist yet there).

    Multiple parallel `lookup_meeting` calls within one turn — the
    typical pattern for cross-language theme + intro fan-out — share
    one Supabase fetch instead of each hitting the DB through `DB_LOCK`
    sequentially."""
    if deps.meeting_pool_lock is None:
        deps.meeting_pool_lock = asyncio.Lock()
    async with deps.meeting_pool_lock:
        if deps.meeting_pool_cache is None:
            deps.meeting_pool_cache = await asyncio.to_thread(db_meetings_recent, _POOL_SIZE)
    return deps.meeting_pool_cache


async def apply_lookup_meeting(
    ctx,
    no: int | None = None,
    name_substring: str | None = None,
    theme_substring: str | None = None,
    introduction_substring: str | None = None,
    type_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 5,
) -> dict:
    """Find historical meetings by structured filter. Builds a
    `MeetingFilters` from the LLM-supplied args and delegates to
    `resolve_meetings`. The model is expected to extract the filter
    values itself (see the registered tool docstring); no free-text
    parsing happens here.

    Returns the resolver's full result envelope ({cards, total_matches,
    pool_size, limit_clamped}) so the LLM can disclose to the user when
    its result was clamped."""
    if type_filter is not None and type_filter not in {"Regular", "Workshop", "Custom"}:
        raise ModelRetry(f"type_filter must be one of: Regular, Workshop, Custom. Got: {type_filter!r}.")
    parsed_from = parse_iso_date_or_raise("date_from", date_from) if date_from else None
    parsed_to = parse_iso_date_or_raise("date_to", date_to) if date_to else None
    if parsed_from and parsed_to and parsed_from > parsed_to:
        raise ModelRetry(f"date_from ({date_from}) must not be after date_to ({date_to}).")
    if limit < 1:
        raise ModelRetry(f"limit must be >= 1; got {limit}")
    if limit > _POOL_SIZE:
        raise ModelRetry(
            f"limit must be <= {_POOL_SIZE} (the candidate pool size). "
            f"For deeper history use no= for an exact lookup."
        )
    filters = MeetingFilters(
        no=no,
        name_substring=(name_substring or None),
        theme_substring=(theme_substring or None),
        introduction_substring=(introduction_substring or None),
        type_filter=type_filter,  # type: ignore[arg-type]
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
    if filters == MeetingFilters(limit=limit):
        # No real filter axis set — refuse rather than return the recent
        # top-N. The model should have extracted *something* from the
        # user intent. Most common cause: model thought substring matching
        # was inadequate for a topic keyword and tried to give up; the
        # right move is to pass the keyword anyway and let the result speak.
        raise ModelRetry(
            "lookup_meeting was called with no filter axes (only limit). "
            "If the user mentioned a manager name, pass it as `name_substring`. "
            "If the user mentioned a topic keyword (e.g. '教育', 'AI', "
            "'aging', 'storytelling'), pass it as `theme_substring` and/or "
            "`introduction_substring` — substring matching is the supported "
            "mechanism even if you suspect no field contains that exact word; "
            "an empty result is a valid answer. If the user mentioned a "
            "meeting type, pass `type_filter`. If you genuinely can't "
            "extract any filter, do NOT call this tool — ask the user for "
            "clarification in text."
        )
    # Exact-no path skips the pool entirely; everything else shares the
    # per-turn pool cache so parallel calls don't redundantly hit Supabase.
    if filters.no is not None:
        return await asyncio.to_thread(resolve_meetings, filters)
    pool = await get_or_fetch_pool(ctx.deps)
    return await asyncio.to_thread(resolve_meetings, filters, pool=pool)


async def apply_preview_meeting(ctx, no: int) -> dict:
    """Read-only fetch of a single historical meeting's full structure —
    meta + introduction + ordered segments. The route auto-renders
    folded meta + intro + agenda tables for this tool's payload (see
    `_render_preview_addendum` in the route)."""
    meeting_dict = await asyncio.to_thread(fetch_meeting_full, no)
    if meeting_dict is None:
        raise ModelRetry(f"Meeting #{no} not found in recent history.")
    return meeting_to_preview(meeting_dict)
