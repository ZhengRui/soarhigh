"""Short-prefix segment ids for the LLM, derived from real UUIDs.

The agent shows the model a 5-char prefix of each segment's real UUID
(e.g. `8c21d`) instead of the full UUID. The prefix is a **pure function**
of the real id — same UUID always maps to the same prefix — so a model
that recalls a stale id from prior tool-call history either:

  * still hits the same real segment (because that segment is still in the
    agenda and its UUID hasn't changed), or
  * gets a clean `unknown segment` refusal because no segment in the
    current agenda has a UUID starting with that prefix.

There is **no possible alias reuse** across turns. This is the key
property the earlier `s1..sN` per-turn-rebuild scheme lacked: with
positional aliasing, deleting `s27` and re-aliasing meant the next-position
segment inherited `s27`, and the model's history bias ("Closing Remarks =
s27") then targeted the wrong segment.

Wire format on both ends stays full UUIDs. The shortening only happens at
the prompt boundary (route → model JSON) and in tool result dicts;
`deps.agenda` and the SSE `agenda_after` always carry full ids so the
frontend, persistence, and DB save paths are unaffected.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from typing import TYPE_CHECKING

from pydantic_ai import ModelRetry

if TYPE_CHECKING:
    from app.agents.meeting.models import Agenda


_DEFAULT_PREFIX_LEN = 5


def shorten(real_id: str) -> str:
    """The minimum-length default prefix of a real id. Use only when there
    is no collision risk in scope (single-segment context). For a
    multi-segment agenda use `shorten_unique`."""
    return (real_id or "")[:_DEFAULT_PREFIX_LEN]


def shorten_unique(real_ids: list[str], min_len: int = _DEFAULT_PREFIX_LEN) -> dict[str, str]:
    """Compute a prefix for each real id, extending colliding ids' prefixes
    one char at a time until every short is unique.

    With random UUIDs in a typical 25-segment agenda the collision
    probability at `min_len=5` is ~0.04% (≈ 25² / 2 / 16⁵), so this rarely
    extends past the minimum. When it does, only the colliding pair grows;
    other ids keep the short default."""
    if not real_ids:
        return {}
    lens: dict[str, int] = {rid: min_len for rid in real_ids}
    while True:
        shorts = {rid: rid[: lens[rid]] for rid in real_ids}
        groups: dict[str, list[str]] = defaultdict(list)
        for rid, s in shorts.items():
            groups[s].append(rid)
        bumped = False
        for fids in groups.values():
            if len(fids) > 1:
                for fid in fids:
                    if lens[fid] < len(fid):
                        lens[fid] += 1
                        bumped = True
        if not bumped:
            return shorts


def shorten_agenda_dump(dump: dict) -> dict:
    """Return a deep-copied agenda dump with every segment's `id` and
    every comma-separated `related_segment_ids` reference rewritten as a
    short prefix. Pure function — does not mutate the input or any deps
    state. Use when serializing the snapshot JSON for the model's prompt."""
    out = copy.deepcopy(dump)
    segments = out.get("segments") or []
    real_ids = [seg["id"] for seg in segments if seg.get("id")]
    short_map = shorten_unique(real_ids)
    for seg in segments:
        sid = seg.get("id")
        if sid:
            seg["id"] = short_map.get(sid, shorten(sid))
        related = seg.get("related_segment_ids") or ""
        if related:
            refs = [x.strip() for x in related.split(",") if x.strip()]
            seg["related_segment_ids"] = ",".join(short_map.get(x, shorten(x)) for x in refs)
    return out


def resolve(agenda: "Agenda", given: str) -> str:
    """Map a model-supplied segment id to the corresponding real id in the
    current agenda. Accepts both the short prefix (what the snapshot
    showed) and the full UUID (in case the model copied a longer form
    from somewhere). Raises `ModelRetry` on no match or ambiguous match —
    the model gets a useful error and can self-correct.

    Bug class this helper closes: the prior `s1..sN` per-turn aliasing
    let a stale id from history match a different real segment after a
    delete-and-reindex. With UUID-derived prefixes a stale id either
    still resolves to the same real segment (if it's still in the agenda)
    or fails closed."""
    if not given:
        raise ModelRetry("segment id must not be empty")
    # Full match first — handles both the prompt-shortened path (short ==
    # seg.id when seg.id was already 5 chars, e.g. legacy `s27` ids that
    # round-trip from persisted history) and the rare case where the model
    # quotes the full UUID.
    for seg in agenda.segments:
        if seg.id == given:
            return seg.id
    matches = [seg.id for seg in agenda.segments if seg.id.startswith(given)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ModelRetry(f"unknown segment: {given}")
    raise ModelRetry(
        f"segment id prefix {given!r} is ambiguous "
        f"(matches {len(matches)} segments); use the longer id from the current snapshot"
    )
