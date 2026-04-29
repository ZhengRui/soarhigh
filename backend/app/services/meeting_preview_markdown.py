"""Markdown renderers for historical meeting previews.

Both the meeting agent and statistics agent expose `preview_meeting`.
The LLM should not hand-format large agenda tables; these helpers render
the same folded Meta / Introduction / Agenda blocks deterministically.

`format_role_display` lives here because it is purely a render concern
(produces the table cell text "Name (member)" / "Name (guest)" / "All" /
"—"). It used to live in `agents/meeting/tools.py` where it forced every
caller — including this module and the stats agent — to depend on the
agent's tool surface for a render decision. See `member_directory.py`
for why the membership lookup is a fallback only.
"""

from __future__ import annotations

from app.services.member_directory import is_member_name


def format_role_display(role_taker: str | None, member_id: str | None = None) -> str:
    """Render a role-taker cell with a deterministic membership badge.

    Precedence (matches the frontend edit page's badge rule, which keys
    off `attendee.member_id`):

      1. Empty / blank name → '—' regardless of member_id (no role to label).
      2. Group keyword 'All' (case-insensitive) → returned as-is, no badge
         (group roles like warmup, table topics, tea break have no
         membership concept).
      3. `member_id` truthy → '(member)'. This is the DB-authoritative path
         used by the preview renderer once `_segment_to_preview` preserves
         the sidecar.
      4. `member_id` is the empty string ('') → '(guest)'. The caller
         affirmatively had member_id available and it was empty, which
         means the DB recorded a guest. Do NOT consult `CLUB_MEMBERS` here:
         that would let the static prompt hint override DB truth (the
         exact bug this Phase A fix removes).
      5. `member_id is None` → caller had no member_id information at all
         (current-draft agenda; legacy bare-string preview rows). Fall
         back to `is_member_name` against the static directory. This is
         the only remaining use of the static list as a membership oracle.
    """
    name = (role_taker or "").strip()
    if not name:
        return "—"
    if name.lower() == "all":
        # Preserve the caller's original casing (e.g. 'all' vs 'All'). At this
        # point `role_taker` is non-None — the empty/None case returned above —
        # so the `or name` fallback is for the type checker, not behavior.
        return role_taker or name

    if member_id is None:
        # Legacy fallback: no DB signal; use the static directory.
        membership = "member" if is_member_name(name) else "guest"
    elif member_id:
        membership = "member"
    else:
        # Empty string member_id: caller affirmatively says 'guest'.
        membership = "guest"

    return f"{role_taker} ({membership})"


def display_cell(value) -> str:
    if value is None:
        return "TBD"
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else "TBD"
    return str(value)


def _table_cell(value) -> str:
    return display_cell(value).replace("|", "\\|").replace("\n", "<br>")


def _get_segment_value(segment, key: str):
    if isinstance(segment, dict):
        return segment.get(key)
    return getattr(segment, key, None)


def _split_related_segment_ids(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def format_segment_detail_cell(segment, segments_by_id: dict[str, object] | None = None) -> str:
    """Render optional title/content/related refs for an agenda table cell."""
    parts: list[str] = []
    title = (_get_segment_value(segment, "title") or "").strip()
    content = (_get_segment_value(segment, "content") or "").strip()
    related_ids = _split_related_segment_ids(_get_segment_value(segment, "related_segment_ids"))

    if title:
        parts.append(f"Title: {_table_cell(title)}")
    if content:
        parts.append(f"Content: {_table_cell(content)}")
    if related_ids:
        labels: list[str] = []
        for related_id in related_ids:
            related = (segments_by_id or {}).get(related_id)
            if related is None:
                continue
            related_type = (_get_segment_value(related, "type") or "").strip()
            if related_type:
                labels.append(_table_cell(related_type))
        if labels:
            parts.append(f"Related: {', '.join(labels)}")

    return "<br>".join(parts)


def fold(summary: str, body: str) -> str:
    """Wrap a markdown body in a folded details block."""
    return f"<details>\n<summary>{summary}</summary>\n\n{body}\n\n</details>"


def render_intro_block(text: str) -> str:
    """Fence introduction copy so it is visually separate from the fold title."""
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


def render_preview_meta_table(preview: dict) -> str:
    time_value = f"{display_cell(preview.get('start_time'))} - {display_cell(preview.get('end_time'))}"
    rows = [
        ("Meeting No.", display_cell(preview.get("no"))),
        ("Type", display_cell(preview.get("type"))),
        ("Theme", display_cell(preview.get("theme"))),
        ("Meeting Manager", display_cell(preview.get("manager"))),
        ("Date", display_cell(preview.get("date"))),
        ("Time", time_value),
        ("Location", display_cell(preview.get("location"))),
    ]
    lines = ["| Field | Value |", "|---|---|"]
    lines.extend(f"| {label} | {value} |" for label, value in rows)
    return "\n".join(lines)


def render_preview_segment_table(preview: dict) -> str:
    segments = preview.get("segments") or []
    if not segments:
        return "_(no segments)_"
    segments_by_id: dict[str, object] = {
        str(seg.get("id")): seg for seg in segments if isinstance(seg, dict) and seg.get("id")
    }
    lines = ["| Time | Duration | Type | Role taker | Details |", "|---|---|---|---|---|"]
    for seg in segments:
        # `role_taker_member_id` is the sidecar projected by
        # `_segment_to_preview`; absent (None) means legacy/draft data and
        # the renderer falls back to the static directory.
        role = format_role_display(
            seg.get("role_taker") or "",
            member_id=seg.get("role_taker_member_id"),
        )
        details = format_segment_detail_cell(seg, segments_by_id)
        lines.append(
            f"| {seg.get('start_time', '')} | {seg.get('duration', '')} | "
            f"{seg.get('type', '')} | {role} | {details} |"
        )
    return "\n".join(lines)


def render_preview_addendum(previews: list[dict]) -> str:
    """Folded meta / introduction / segment blocks for preview payloads.

    Fold summaries do not carry a "(preview)" suffix — the meeting number
    in the title is enough context, and the parenthetical was visual noise
    that crowded the chat thread when several previews stacked."""
    parts: list[str] = []
    for preview in previews:
        no = preview.get("no") or "?"
        parts.append(fold(f"📌 Meeting #{no} Meta", render_preview_meta_table(preview)))
        intro_text = (preview.get("introduction") or "").strip()
        if intro_text:
            parts.append(
                fold(
                    f"📝 Meeting #{no} Introduction",
                    render_intro_block(intro_text),
                )
            )
        parts.append(fold(f"📋 Meeting #{no} Agenda", render_preview_segment_table(preview)))
    return "\n\n" + "\n\n".join(parts) if parts else ""
