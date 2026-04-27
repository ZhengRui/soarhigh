import asyncio
import json
import os

import pytest

from app.meeting_agent.agent import USAGE_LIMITS, agent
from app.meeting_agent.models import Agenda, AgendaDeps, Meta, Segment
from app.meeting_agent.prompts import SNAPSHOT_TEMPLATE
from app.meeting_agent.tools import apply_create_from_text


class _FakeCtx:
    def __init__(self, deps):
        self.deps = deps


@pytest.mark.live
def test_agent_fires_set_role_for_simple_edit():
    if os.environ.get("GOOGLE_API_KEY", "") in ("", "not-configured"):
        pytest.skip("GOOGLE_API_KEY not set; cannot run live smoke test")

    agenda = Agenda(
        meta=Meta(theme="Test", start_time="19:30"),
        segments=[
            Segment(id="s1", type="SAA", start_time="19:30", duration=3, role_taker="Liz"),
        ],
    )
    deps = AgendaDeps(agenda=agenda, session_id="smoke")

    # Mirror what the real /meeting-agent/turn route does: prepend the snapshot so the
    # model can reference segment ids verbatim instead of hallucinating them.
    prompt = SNAPSHOT_TEMPLATE.format(
        snapshot_json=json.dumps(agenda.model_dump(), ensure_ascii=False, indent=2),
        next_seq=1,
        tail_seq=0,
        user_message="Change the SAA role taker to Joyce",
        attachment_block="",
        language_hint="",
    )
    agent.run_sync(prompt, deps=deps, usage_limits=USAGE_LIMITS)

    # Accept either "Joyce" alone or "Joyce Feng" or similar — the model may expand the name.
    assert "Joyce" in agenda.segments[0].role_taker


# Real-world registration text the user reported as failing in earlier rounds.
# Exercises: bare-ordinal `no` extraction (`451st`), spaces inside times
# (`19: 30`), `📅`-only date marker (no `⏰`), `Venue:` location keyword,
# wholesale buffer zeroing, and the validator's last-segment-end overflow check.
_USER_REGISTRATION_TEXT = """@ Allpeople Gather ~ 451st
✈️ ✈️ Theme: Involution or Lying Flat? — Finding a Comfortable Life Balance
Wrap it in or lie flat? Finding a comfortable balance in life
Caught between involution and lying flat—we work hard but feel drained.

📅 Date: Apr. 22th, 2026 (Wed) 19: 30 - 21: 30
📍Venue: 809, Area B, Ramet City, Shenzhen
🚇 Transport: Exit B, Baoti Station, Metro Line 1

MM: vicky Yang
#Host
TOM: Jessica
Guests Intro: Liz
TTM: vicky Yang

#Facilitator
SAA: Liz
Club Intro: Lucas
Timer: Amy
Harkmaster: Jean
MOT: Helen Chen

#Prepared Speaker
PS 1: Albert
PS 2: Victory
PS 3: Leta

#Evaluator
IE1: Amy
IE2: Zack
IE3: Rui
TTE: Shelly
GE: Alice Song
"""


@pytest.mark.live
def test_apply_create_from_text_smoke_real_registration():
    """End-to-end smoke for the create-from-text path on the user's actual
    registration text. Requires OPENAI_API_KEY (planner uses o4-mini)."""
    if os.environ.get("OPENAI_API_KEY", "") in ("", "not-configured"):
        pytest.skip("OPENAI_API_KEY not set; cannot run live planner")

    deps = AgendaDeps(agenda=Agenda(meta=Meta(), segments=[]), session_id="smoke-451")
    ctx = _FakeCtx(deps=deps)

    result = asyncio.run(apply_create_from_text(ctx, raw_text=_USER_REGISTRATION_TEXT))

    # --- Visibility for manual inspection (run with -s to see). ---
    print("\n=== meeting_summary ===")
    print(json.dumps(result["meeting_summary"], indent=2, ensure_ascii=False))
    print(f"\n=== missing_required_fields ({len(result['missing_required_fields'])}) ===")
    for m in result["missing_required_fields"]:
        print(f"  {m['label']}")
    print(f"\n=== validation_issues ({len(result['validation_issues'])}) ===")
    for issue in result["validation_issues"]:
        print(f"  [{issue['severity']}] {issue['code']}: {issue['message']}")
    print(f"\n=== segments ({result['segment_count']}) ===")
    for seg in deps.agenda.segments:
        print(
            f"  {seg.start_time}  {seg.type:40s}  " f"{seg.duration:>2}min  buf={seg.buffer_before}  {seg.role_taker}"
        )

    # --- Hard regression assertions. ---
    # #1: meeting number 451 retained (not wiped by the regex guard).
    assert deps.agenda.meta.no == 451, f"expected no=451, got {deps.agenda.meta.no}"
    # #3: start/end_time retained despite spaces inside the times in the source.
    # Planner historically outputs the first-segment start as meta.start_time
    # (per Example 1 in the developer prompt — Guests Registration at 19:15
    # before the "official" 19:30 meeting start). Either is acceptable here;
    # the regex guard would have wiped these to None if it failed to match.
    assert deps.agenda.meta.start_time, "start_time was wiped"
    assert deps.agenda.meta.end_time, "end_time was wiped"
    assert "21:30" in deps.agenda.meta.end_time
    # User preference: no buffers on creation, segments back-to-back.
    assert all(seg.buffer_before == 0 for seg in deps.agenda.segments), (
        "create_from_text must produce 0 buffer_before on every segment; "
        "the user adds buffers manually after creation"
    )
    # Soarhigh club convention: Regular meetings open with a 15-min warmup
    # at 19:15 (before the official 19:30 start). Planner is responsible
    # for emitting it per developer prompt Note 8.
    first = deps.agenda.segments[0]
    assert first.start_time == "19:15", f"expected warmup at 19:15, got {first.start_time}"
    assert first.duration == 15
    first_type_lower = (first.type or "").lower()
    assert (
        "registration" in first_type_lower or "warm up" in first_type_lower or "warmup" in first_type_lower
    ), f"first segment must look like a warmup; got type={first.type!r}"
    # Validator must NOT false-positive overflow when last-seg-end == meta.end_time.
    overflow = [i for i in result["validation_issues"] if i["code"] == "DURATION_OVERFLOW"]
    if overflow:
        # Acceptable only if last segment genuinely ends past meta.end_time.
        last = deps.agenda.segments[-1]
        from app.meeting_agent.timing import _parse_hhmm

        last_end = _parse_hhmm(last.start_time) + last.duration
        meta_end = _parse_hhmm(deps.agenda.meta.end_time)
        assert last_end > meta_end, (
            f"DURATION_OVERFLOW reported but last segment ends at "
            f"{last_end // 60}:{last_end % 60:02d} which is NOT past meta.end_time "
            f"{deps.agenda.meta.end_time} — false positive"
        )
