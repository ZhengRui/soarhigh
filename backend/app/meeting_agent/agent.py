import os

from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from app.config import GOOGLE_API_KEY, MEETING_AGENT_MODEL, OPENAI_API_KEY
from app.meeting_agent import tools as _tools
from app.meeting_agent.models import AgendaDeps
from app.meeting_agent.prompts import ROUTER_SYSTEM_PROMPT
from app.meeting_agent.validators import run_validators

# Pydantic AI providers read their API keys from os.environ at Agent()
# construction time. Our config uses starlette.Config which reads .env into
# Python variables without populating os.environ — so we have to bridge here.
# Using setdefault so real env values (CI, prod) take precedence over .env.
# "not-configured" placeholder lets the module import even without a key;
# tests using TestModel override never reach the provider. Real missing-key
# errors surface at request time, which is what we want.
os.environ.setdefault("GOOGLE_API_KEY", GOOGLE_API_KEY or "not-configured")
os.environ.setdefault("OPENAI_API_KEY", OPENAI_API_KEY or "not-configured")

# request_limit (15) is the primary guard against runaway agent loops.
# total_tokens_limit is a backstop for "something is very wrong" scenarios;
# 500K accommodates long multi-turn sessions with the full Phase 2 system
# prompt + tool schemas + growing history + per-call agenda snapshots, which
# realistically consume 10-20K tokens per model call and 3-5 calls per turn.
USAGE_LIMITS = UsageLimits(request_limit=15, total_tokens_limit=500_000)

# Gemini thinking models emit thought summaries only when explicitly asked
# via `include_thoughts: True`. Flash Lite doesn't support thinking at all —
# sending the config to it may error or be silently ignored, so guard with a
# substring match. Extend this set when new thinking-capable models ship.
_GEMINI_THINKING_MODELS = {"gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-pro"}


def _build_model_settings(model_spec: str):
    if any(m in model_spec for m in _GEMINI_THINKING_MODELS):
        # Lazy import so non-Google setups don't pay the import cost.
        from pydantic_ai.models.google import GoogleModelSettings

        return GoogleModelSettings(
            google_thinking_config={
                "thinking_budget": -1,  # dynamic; model decides per request
                "include_thoughts": True,
            },
        )
    return None


agent = Agent(
    MEETING_AGENT_MODEL,
    system_prompt=ROUTER_SYSTEM_PROMPT,
    deps_type=AgendaDeps,
    retries=2,
    model_settings=_build_model_settings(MEETING_AGENT_MODEL),
)


@agent.tool
def set_role(
    ctx: RunContext[AgendaDeps],
    segment_id: str,
    role_taker: str,
) -> dict:
    """Unilateral: set who takes a role in ONE segment. Pass empty string to clear."""
    return _tools.apply_set_role(ctx, segment_id=segment_id, role_taker=role_taker)


@agent.tool
def set_type(
    ctx: RunContext[AgendaDeps],
    segment_id: str,
    type: str,
) -> dict:
    """Unilateral: rename ONE segment's type/title (e.g. 'Prepared Speech' -> 'Ice Breaker').
    Keeps id, duration, position, role_taker, and buffers unchanged."""
    return _tools.apply_set_type(ctx, segment_id=segment_id, type=type)


@agent.tool
def set_duration(
    ctx: RunContext[AgendaDeps],
    segment_id: str,
    duration_min: int,
) -> dict:
    """Unilateral: set the duration (in minutes) of ONE segment.
    Downstream segment start times recompute automatically."""
    return _tools.apply_set_duration(ctx, segment_id=segment_id, duration_min=duration_min)


@agent.tool
def set_buffer(
    ctx: RunContext[AgendaDeps],
    segment_id: str,
    buffer_min: int,
) -> dict:
    """Set the buffer (gap/间隔) minutes BEFORE a segment. A buffer is the time gap
    between the previous segment ending and this segment starting - NOT a separate
    segment. Downstream start times recompute."""
    return _tools.apply_set_buffer(ctx, segment_id=segment_id, buffer_min=buffer_min)


@agent.tool
def set_meta(
    ctx: RunContext[AgendaDeps],
    field: str,
    value: str,
) -> dict:
    """Change a meeting-level field. Supported: type, theme, location, date, start_time,
    no, manager, introduction. end_time is derived and cannot be set directly."""
    return _tools.apply_set_meta(ctx, field=field, value=value)


@agent.tool
def add_segment(
    ctx: RunContext[AgendaDeps],
    type: str,
    duration_min: int,
    after_id: str | None = None,
    before_id: str | None = None,
    role_taker: str = "",
) -> dict:
    """Insert a new segment into the agenda. Provide exactly one of after_id or
    before_id to anchor the position. Type may be standard ('Grammarian',
    'Workshop') or custom ('Ice Breaker Game'). Downstream start times
    recompute automatically. role_taker defaults to empty; pass a name only
    when the user specifies one. DO NOT use this to add a buffer/gap — see
    set_buffer instead."""
    return _tools.apply_add_segment(
        ctx,
        type=type,
        duration_min=duration_min,
        after_id=after_id,
        before_id=before_id,
        role_taker=role_taker,
    )


@agent.tool
def remove_segment(ctx: RunContext[AgendaDeps], segment_id: str) -> dict:
    """Delete an existing segment by id. Downstream start times recompute
    automatically."""
    return _tools.apply_remove_segment(ctx, segment_id=segment_id)


@agent.tool
def move_segment(
    ctx: RunContext[AgendaDeps],
    segment_id: str,
    after_id: str | None = None,
    before_id: str | None = None,
) -> dict:
    """UNILATERAL sequence reorder: relocate ONE segment to a new slot. Other
    segments stay in place; only their indices shift to make room. NOT a swap
    (use swap_time for that). NOT for 'earlier/later by N minutes' (use
    shift_segment_time). Provide exactly one of after_id or before_id.
    Downstream start times recompute."""
    return _tools.apply_move_segment(
        ctx,
        segment_id=segment_id,
        after_id=after_id,
        before_id=before_id,
    )


@agent.tool
def swap_roles(
    ctx: RunContext[AgendaDeps],
    segment_id_a: str,
    segment_id_b: str,
) -> dict:
    """BIDIRECTIONAL: swap the role takers of TWO segments — atomic exchange of
    only the role_taker field. Positions and times do NOT change. Use for
    'swap A and B's roles'. Does NOT move the cards."""
    return _tools.apply_swap_roles(ctx, segment_id_a=segment_id_a, segment_id_b=segment_id_b)


@agent.tool
def swap_time(
    ctx: RunContext[AgendaDeps],
    segment_id_a: str,
    segment_id_b: str,
) -> dict:
    """BIDIRECTIONAL: swap the time slots / positions of TWO segments — they
    exchange where they sit in the sequence. Both segments keep their
    id/type/duration/role_taker; only sequence positions (and thus times)
    swap. Use for 'swap A and B's time slots'. Works for adjacent AND
    non-adjacent pairs — one call is always enough."""
    return _tools.apply_swap_time(ctx, segment_id_a=segment_id_a, segment_id_b=segment_id_b)


@agent.tool
def shift_segment_time(
    ctx: RunContext[AgendaDeps],
    segment_id: str,
    delta_min: int,
) -> dict:
    """UNILATERAL clock-time shift: move ONE segment earlier/later by signed
    minutes while keeping agenda order unchanged. Positive delta pushes later
    by inflating the gap before the segment. Negative delta pulls earlier by
    consuming the EXISTING gap — refuses if that gap is insufficient. Cannot
    move the first segment earlier (use set_meta(start_time) instead). NOT
    for reordering (use move_segment)."""
    return _tools.apply_shift_segment_time(ctx, segment_id=segment_id, delta_min=delta_min)


@agent.tool
def validate_agenda(ctx: RunContext[AgendaDeps]) -> list[dict]:
    """Check all global invariants and return a list of issues (empty if clean).
    HARD issues (TTE_ORDER, BUFFER_SEGMENT_ANTIPATTERN) must be fixed before
    you reply — use other tools to correct them and call validate_agenda again.
    SOFT issues (DURATION_OVERFLOW, DURATION_UNDERFLOW) should be surfaced to
    the user in your summary reply, not silently corrected."""
    return [i.model_dump() for i in run_validators(ctx.deps.agenda)]


@agent.tool
async def revert_last_turn(ctx: RunContext[AgendaDeps]) -> dict:
    """SOFT REVERT: undo the most recent edit turn. Walks past chit-chat
    turns silently. Use when the user says '撤销' / 'revert' / 'undo last
    change' / '取消上一步' / similar. Chat history preserved.

    Refuses if (a) no prior edits, or (b) the most recent meaningful turn
    was itself a revert (ping-pong guard — refusal directs you to use
    revert_to_turn with an explicit `after_seq` restore point). Do NOT
    manually reverse edits via set_role/set_duration/etc."""
    return await _tools.apply_revert_last_turn(ctx)


@agent.tool
async def revert_to_turn(ctx: RunContext[AgendaDeps], after_seq: int) -> dict:
    """SOFT REVERT to a specific restore point. `after_seq` semantics:

        after_seq = 0  → initial state (before any turns)
        after_seq = N  → state AFTER turn N completed

    Pass the seq the user picked VERBATIM. Do NOT subtract or transform.
    If the refusal from revert_last_turn listed 'seq 2: state AFTER X' and
    the user says 'seq 2', call revert_to_turn(after_seq=2)."""
    return await _tools.apply_revert_to_turn(ctx, after_seq=after_seq)
