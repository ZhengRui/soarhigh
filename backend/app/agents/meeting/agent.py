import os

from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from app.agents.meeting import tools as _tools
from app.agents.meeting.models import AgendaDeps
from app.agents.meeting.prompts import MEETING_SYSTEM_PROMPT
from app.agents.meeting.validators import run_validators
from app.agents.runtime.model_settings import build_model_settings
from app.config import GOOGLE_API_KEY, MEETING_AGENT_MODEL, MEETING_THINKING_LEVEL, OPENAI_API_KEY

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

agent = Agent(
    MEETING_AGENT_MODEL,
    system_prompt=MEETING_SYSTEM_PROMPT,
    deps_type=AgendaDeps,
    retries=2,
    model_settings=build_model_settings(MEETING_AGENT_MODEL, thinking_level=MEETING_THINKING_LEVEL),
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
    """Unilateral: rename ONE segment's CATEGORY LABEL (e.g. 'Custom segment'
    -> 'Ice Breaker', 'Prepared Speech' -> 'Prepared Speech 2'). This is the
    bold heading shown on the segment card — NOT a per-segment title or speech
    title. For a speech title like 'AI Safety' use set_title. Keeps id,
    duration, position, role_taker, title, content, and buffers unchanged."""
    return _tools.apply_set_type(ctx, segment_id=segment_id, type=type)


@agent.tool
def set_title(
    ctx: RunContext[AgendaDeps],
    segment_id: str,
    title: str,
) -> dict:
    """Set the per-segment TITLE of ONE segment — the speech / workshop /
    custom-segment title shown beneath the type heading. Editable on
    Prepared Speech (any number) and Custom-style segments (Workshop, Ice
    Breaker, or any non-standard type). Refused on fixed standard types
    (SAA, Timer, Grammarian, Closing Remarks, ...) and on Prepared Speech
    Evaluation rows.

    Distinct from set_type, which renames the segment's CATEGORY LABEL
    (the bold heading). Common confusion: '把第一个备稿的题目改成 AI safety'
    / 'set the first speech title to AI safety' → set_title, NOT set_type."""
    return _tools.apply_set_title(ctx, segment_id=segment_id, title=title)


@agent.tool
def set_content(
    ctx: RunContext[AgendaDeps],
    segment_id: str,
    content: str,
) -> dict:
    """Set the per-segment CONTENT of ONE segment. Per-type meaning:
    Table Topic Session → WOT (Word of Today, e.g. 'Resilience');
    Prepared Speech → pathway / notes; Custom-style segments → freeform
    notes. Refused on fixed standard types and on Prepared Speech
    Evaluation rows."""
    return _tools.apply_set_content(ctx, segment_id=segment_id, content=content)


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
    end_time, no, manager, introduction."""
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
    set_buffer instead. DO NOT use this for "Word of Today" / "WOT" /
    "今日单词" / "今天的单词" — that is the `content` field of the existing
    Table Topic Session row; use `set_content` on that segment instead.

    STRICT GATE — all three of `type`, `duration_min`, and the position
    anchor (`after_id` xor `before_id`) MUST come from the user, never
    from your own guesses or "reasonable defaults". If the user did not
    state a duration or did not state an anchor, do NOT call this tool —
    reply in text asking for the missing pieces and STOP. Picking a
    plausible-looking neighbor from the snapshot to anchor a guessed
    position counts as inventing. See the `add_segment gatekeeping`
    section in the system prompt for examples."""
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
async def create_from_text(ctx: RunContext[AgendaDeps], raw_text: str) -> dict:
    """WHOLESALE REPLACE the entire agenda by parsing a pasted WeChat-style
    registration message. Call only when the user clearly wants to create a
    new agenda from the pasted text. Pass the pasted text verbatim."""
    return await _tools.apply_create_from_text(ctx, raw_text=raw_text)


@agent.tool
async def lookup_meeting(
    ctx: RunContext[AgendaDeps],
    no: int | None = None,
    name_substring: str | None = None,
    theme_substring: str | None = None,
    introduction_substring: str | None = None,
    type_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 5,
) -> dict:
    """READ-ONLY. Find historical meetings by structured filter. You — the
    model — extract the filter values from the user's intent. Do NOT pass
    the user's raw text in any field; pass the resolved values.

    Filter axes (all optional; combine as AND):

      `no`             — exact meeting number when the user names one
                         ('451' / '#451' / 'Meeting No: 451' / '第 451 期').
                         When set, other filters except `type_filter` are
                         redundant.
      Three SEPARATE substring axes — pick the one(s) that match the
      user's intent. All are case-insensitive literal substring; no
      semantic similarity, no cross-script translation, no fuzzy matching.

      `name_substring`         — match `manager.name` ONLY. Use when the
                                 user references the *meeting manager*
                                 ('Joyce 主持的', 'managed by Frank').
                                 Does NOT match theme or introduction —
                                 those are separate axes.
      `theme_substring`        — match `theme` (the meeting title/topic
                                 line) ONLY. Use for title-shaped
                                 references ('Emojis 那次', '主题里有 X').
      `introduction_substring` — match `introduction` (the descriptive
                                 paragraph below the title) ONLY. Use
                                 when user references intro content
                                 ('introduction 提到 leadership 的',
                                 'description mentioning AI'). When
                                 this filter is used, returned cards
                                 INCLUDE the full `introduction` field
                                 so you can quote the matched portion
                                 in your reply. **Quote the relevant
                                 sentence(s) verbatim from the card's
                                 `introduction` text — do NOT paraphrase
                                 or summarize from the theme. If a
                                 card lacks the `introduction` field
                                 (because the call didn't use this
                                 axis) and the user asks about intro
                                 content, call `preview_meeting(no)`
                                 to fetch the real text rather than
                                 fabricating from the theme.**

      **Search-strategy convention** — when the user gives a topic
      keyword without specifying *which* field to search, fan out to
      BOTH theme AND introduction in parallel calls and disclose which
      group surfaced each match in your reply. When the user is explicit
      ('主题有关 X' = theme only; 'introduction 提到 X' = intro only),
      use a single call.

      **Cross-language fan-out** — club themes/intros are predominantly
      English ('Aging Gracefully', 'Next-Gen Education', 'Emojis Across
      Cultures'...) but users may type Chinese topic keywords. When
      script mismatch is plausible, also fire parallel calls with the
      translated keyword. Manager names are stored as English/pinyin —
      cross-language is rarely worth the cost for `name_substring`.

      **Reply disclosure** — when you fan out across multiple axes,
      group the results and label them: '主题命中: #X, #Y. Introduction
      提到: #Z.' Empty groups omitted. This tells the user *why* each
      meeting surfaced — useful when an introduction-match is
      tangential vs. a theme-match is on-topic.

      Examples (user → call(s)):
        '上次 Joyce 主持的'
          → lookup_meeting(name_substring='Joyce', limit=1)
        '主题有关教育的是哪几期'  (explicit '主题')
          → parallel: lookup_meeting(theme_substring='教育')
                    + lookup_meeting(theme_substring='education')
        '讲教育的会议' (no field hint → search theme + intro)
          → 4-way parallel:
              lookup_meeting(theme_substring='教育')
              lookup_meeting(theme_substring='education')
              lookup_meeting(introduction_substring='教育')
              lookup_meeting(introduction_substring='education')
        'introduction 提到 leadership 的'  (explicit intro)
          → lookup_meeting(introduction_substring='leadership')
        'Emojis 那次 workshop'
          → lookup_meeting(theme_substring='Emojis', type_filter='Workshop')
        'Joyce 主持的关于教育的'  (manager AND topic, single call AND)
          → lookup_meeting(name_substring='Joyce', theme_substring='教育')
            (plus an optional parallel call swapping in 'education' for
             cross-language coverage on the theme side)

      Do NOT pass connectives or noise ('的', 'managed', 'about',
      'meeting', 'last', '有关', '主题') — they will not match.
      `type_filter`    — restrict to one of: 'Regular', 'Workshop', 'Custom'.
                         Use ONLY when the user explicitly names a type
                         ('上次 workshop', 'recent regular meetings',
                         'Custom 那次'). **Default is to leave this UNSET
                         (omit the parameter) so all meeting types match.**
                         Do NOT default to 'Regular' just because Regular
                         is the most common type — that hides results from
                         the user. Examples:
                           '主题是 X 的会议'            → omit type_filter
                                                          (search all types)
                           '主题是 X 的 workshop'        → type_filter='Workshop'
                           'Joyce 主持的会议'           → omit type_filter
                           'Joyce 主持的 regular 会议'   → type_filter='Regular'
      `date_from`      — ISO YYYY-MM-DD inclusive. Filter to meetings on
                         or after this date. Pair with `date_to` for a
                         closed range, or use alone for "since X".
      `date_to`        — ISO YYYY-MM-DD inclusive. Filter to meetings on
                         or before this date.

                         **Resolve relative time phrases yourself** using
                         the `today` line in [Session metadata]. Examples
                         (assuming today=2026-04-27):
                           '10月份的会议' / 'October meetings'
                             → date_from='2025-10-01', date_to='2025-10-31'
                             (when ambiguous which year, prefer the most
                             recent past October — users almost always
                             mean the recent one, not future)
                           '上个月'   → first/last day of previous month
                           '今年'     → '2026-01-01' to '2026-12-31'
                           '去年'     → '2025-01-01' to '2025-12-31'
                           'Q3 2025' → '2025-07-01' to '2025-09-30'
                           '最近 3 个月' → date_from = today - 90d, no date_to
                         If the user provides a specific date, pass it as
                         both date_from and date_to (single-day range).
      `limit`          — max cards returned (default 5; max 200, the
                         candidate pool size). Pick a limit appropriate
                         to the user's intent:
                           '上次' / '最近一次' / 'last' / 'most recent'   → 1
                           '最近三次' / 'recent 3'                          → 3
                           bare 'recent' / unspecified                     → 5
                           '所有' / 'all' / '哪几次' / '哪几期' / 'which'   → 50 (or higher)
                         When in doubt for an enumeration query ('哪几期',
                         'which meetings', 'list all of X'), prefer a
                         HIGHER limit (50) so the model sees enough rows;
                         the result envelope tells you when more matches
                         exist and you can disclose accordingly.

    **Always provide at least one filter axis** (`no`, `name_substring`,
    `theme_substring`, `introduction_substring`, `type_filter`, or a date
    range). A bare `lookup_meeting(limit=N)` is refused — if you can't
    extract any filter from the user's intent, ask the user for
    clarification in plain text instead of calling the tool.

    **Result envelope.** The tool returns:
        {
          "cards": [...up to `limit` cards, most recent first...],
          "total_matches": <int>,    # total in the candidate pool
          "pool_size": <int>,        # candidate pool size (200 for
                                     # descriptor scans, 1 for exact-no)
          "limit_clamped": <bool>,   # True iff total_matches > len(cards)
        }
    When `limit_clamped` is true, **disclose this in your reply**: tell
    the user how many you're showing vs. how many match in total
    ("showing 5 of 7 Custom meetings" / "为您列出最近 5 期, 共匹配到 7 期").
    If the user says "show me all" / "全部", call again with a higher
    `limit` rather than asking. Do NOT silently truncate without saying.

    Examples (user → call, assuming today=2026-04-27):
      'show me #451'                       → lookup_meeting(no=451)
      'Joyce 上次主持的'                     → lookup_meeting(name_substring='Joyce', limit=1)
                                              (NO type_filter — user didn't say 'workshop'/'regular'/'custom')
      '最近三次 Joyce 做 meeting manager 的' → lookup_meeting(name_substring='Joyce', limit=3)
                                              (NO type_filter)
      'Emojis 那次'                         → lookup_meeting(theme_substring='Emojis')
                                              (NO type_filter — searches across all types)
      '会议主题有关教育的是哪几期'             → parallel theme_substring='教育' + 'education'
                                              (NO type_filter on either call)
      '上次 workshop'                       → lookup_meeting(type_filter='Workshop', limit=1)
                                              (user said 'workshop')
      'Emojis 那次 workshop'                → lookup_meeting(theme_substring='Emojis', type_filter='Workshop')
                                              (user said 'workshop')
      '讲 AI 的 workshop 有哪几次'           → parallel theme + intro substring='AI', type_filter='Workshop'
      '10月份第一次例会的主题是什么'           → lookup_meeting(type_filter='Regular',
                                                              date_from='2025-10-01',
                                                              date_to='2025-10-31',
                                                              limit=50)
      '今年的 workshop 一共几次'              → lookup_meeting(type_filter='Workshop',
                                                              date_from='2026-01-01',
                                                              date_to='2026-12-31',
                                                              limit=50)
      'Joyce 在去年主持过几次'                → lookup_meeting(name_substring='Joyce',
                                                              date_from='2025-01-01',
                                                              date_to='2025-12-31',
                                                              limit=50)

    Returns lightweight cards (no, type, date, theme, manager_name,
    segment_count). For full segment data on a single meeting use
    `preview_meeting(no)`. Use lookup results to ask for plain-text
    confirmation before `clone_from_meeting`."""
    return await _tools.apply_lookup_meeting(
        ctx,
        no=no,
        name_substring=name_substring,
        theme_substring=theme_substring,
        introduction_substring=introduction_substring,
        type_filter=type_filter,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@agent.tool
async def show_current_agenda(ctx: RunContext[AgendaDeps]) -> dict:
    """READ-ONLY. Show the user the CURRENT draft agenda in the same folded
    meta + agenda table format used after creation / editing — with
    deterministic (member)/(guest) badges computed by the route. Use when
    the user asks to see / preview / inspect the current draft (e.g. "show
    me the agenda", "把当前议程列一下", "what's the current schedule"). Reply
    with ONE short sentence; the route appends the tables. Does NOT modify
    anything."""
    return await _tools.apply_show_current_agenda(ctx)


@agent.tool
async def preview_meeting(ctx: RunContext[AgendaDeps], no: int) -> dict:
    """READ-ONLY. Get the full structure of a single historical meeting:
    meta + ordered segment list (type / start_time / duration / role_taker).
    Does NOT modify the current agenda. Use when the user wants to see what
    a historical meeting looks like before deciding to clone it (e.g. "show me
    #425 agenda" / "把那两次会议的议程列一下"). The route appends folded meta +
    agenda tables for the preview automatically — do NOT render them yourself
    in your reply text; just acknowledge with one short sentence."""
    return await _tools.apply_preview_meeting(ctx, no=no)


@agent.tool
async def clone_from_meeting(ctx: RunContext[AgendaDeps], no: int) -> dict:
    """WHOLESALE REPLACE the current agenda by cloning meeting #no's structure.
    Cleared on clone: no, theme, manager, date, introduction, role_takers.
    The tool refuses unless recent lookup_meeting surfaced this no AND the
    current user message is an explicit confirmation."""
    return await _tools.apply_clone_from_meeting(ctx, no=no)


@agent.tool
async def create_from_image(ctx: RunContext[AgendaDeps]) -> dict:
    """WHOLESALE REPLACE the entire agenda by parsing an attached agenda image.
    Call only when the prompt includes an [Attachment] block and the user asks
    to create from it. Image bytes are read from deps."""
    return await _tools.apply_create_from_image(ctx)


@agent.tool
async def save_draft(ctx: RunContext[AgendaDeps], confirmed: bool = False) -> dict:
    """Save the current agenda as a meeting draft.

    Two-turn protocol — first call without confirmed (preview), then call
    again with confirmed=true once the user has explicitly agreed.
    """
    return await _tools.apply_save_draft(ctx, confirmed=confirmed)


@agent.tool
async def create_from_template(ctx: RunContext[AgendaDeps], template: str) -> dict:
    """WHOLESALE REPLACE the current agenda with a stock template — deterministic,
    no LLM call. Use when the user asks to create a meeting from scratch with
    NO source material (no registration text, no image, no historical meeting
    number) — i.e. they explicitly want a blank standard template.

    Supported templates:
      - "regular_2ps" — Regular meeting, 2 prepared speeches, 22 segments,
        warmup at 19:15, official start 19:30. Aliases: "regular", "regular 2 ps".
      - "custom" — blank single-segment Custom meeting; user builds up via
        subsequent edits. Aliases: "custom_blank", "blank".

    Regular/Workshop templates populate structure + a few default role takers
    (warmup="All", Opening / Awards / Closing default to current president
    "Amy Fang"). Custom is intentionally bare — no warmup, no defaults. The
    user fills theme / manager / date / location and remaining roles via
    subsequent chat edits in either case."""
    return await _tools.apply_create_from_template(ctx, template=template)


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
