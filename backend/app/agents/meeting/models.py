from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.meeting import Attendee


class Meta(BaseModel):
    no: Optional[int] = None
    type: Optional[str] = None
    theme: Optional[str] = None
    manager: Optional[str] = None
    date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    location: Optional[str] = None
    introduction: Optional[str] = None


class Segment(BaseModel):
    """One agenda segment.

    `role_taker` carries the structured `Attendee` (name + DB member_id) so
    member/guest classification at render time is DB-authoritative — see
    Phase B of the agent rework. The field accepts several shapes for
    backwards-compat with callers that historically passed a bare name
    string (most existing tests, the prior wire format from the frontend
    snapshot, persisted session history that pre-dates Phase B):

      * `None` / `""` → no role taker assigned
      * bare `str` → coerced to `Attendee(name=<str>, member_id="")` (guest
        with no DB id; the render layer + frontend `applyAgendaSnapshot`
        upgrade member_id when the name resolves against the live members
        list)
      * `dict` / `Attendee` → preserved as-is
    """

    id: str
    type: str
    start_time: str
    duration: int
    role_taker: Optional[Attendee] = None
    buffer_before: int = 0
    # Phase 3: preserve segment-level details so they round-trip through the
    # agent without the form silently dropping them. These are render-only as
    # far as the agent is concerned (no fine-grained mutation tools yet — see
    # the original Phase C writeup, "Later add explicit tools if needed"); the
    # agent simply carries them through `meeting_to_agenda` / clone / preview
    # / show_current_agenda so a turn that only edits role_taker doesn't
    # silently wipe a prepared speech's title.
    #   * title — speech / workshop title; relevant for Prepared Speech and
    #     Workshop segment types only.
    #   * content — long-form notes / script / WOT (Word of the Day) details
    #     that the form supports inline per segment.
    #   * related_segment_ids — comma-separated string referencing other
    #     segments (e.g. an Evaluation row points back to the Speech it
    #     evaluates). String-typed because the frontend's `BaseSegment`
    #     stores it that way; canonicalizing here would be a separate change.
    title: str = ""
    content: str = ""
    related_segment_ids: str = ""

    # Run the role_taker coercer on direct attribute writes too. The agent's
    # tool implementations frequently mutate `seg.role_taker = "Alice"` on
    # an existing Segment (set_role, swap_roles, clone reset, etc.); without
    # validate_assignment those writes would bypass the coercer and leave a
    # bare string in the field, breaking downstream code that expects an
    # Attendee.
    model_config = {"validate_assignment": True}

    @field_validator("role_taker", mode="before")
    @classmethod
    def _coerce_role_taker(cls, value):
        if value is None:
            return None
        if isinstance(value, Attendee):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            return Attendee(id=None, name=stripped, member_id="")
        if isinstance(value, dict):
            # Empty-name dict equivalent to no role taker. Avoids surfacing
            # `Attendee(name="", member_id="")` rows that would render as "—"
            # but still occupy the structured slot for no good reason.
            if not (value.get("name") or "").strip():
                return None
            return value
        return value


class Agenda(BaseModel):
    meta: Meta
    segments: list[Segment] = Field(default_factory=list)


class AgendaDeps(BaseModel):
    agenda: Agenda
    session_id: str
    user_id: Optional[str] = None  # set by route from get_current_user; needed by save_draft
    current_user_message: str = ""
    image_data: Optional[bytes] = None
    image_content_type: Optional[str] = None
    # Per-turn pool cache for the meeting-lookup service. Deps is built fresh
    # each turn so the cache invalidates naturally at turn boundaries.
    # `meeting_pool_lock` is lazily set to an asyncio.Lock on first lookup
    # call (must bind to the current event loop, not the one that built
    # deps). Multiple parallel `lookup_meeting` tool calls within one turn
    # — e.g. cross-language theme + intro fan-out — share a single DB
    # fetch instead of each hitting Supabase.
    meeting_pool_cache: Optional[list[dict]] = None
    meeting_pool_lock: Any = None
    # Live members directory, eager-fetched at turn boundary by the route.
    # Each row carries the DB shape `{"id": <uuid>, "username": <str>,
    # "full_name": <str>}`. `set_role` / `add_segment` consult it to resolve
    # a bare-name LLM arg ("Joyce Feng") to a structured `Attendee` with the
    # real `member_id`. Without this, the chat addendum would briefly render
    # such a role taker as `(guest)` until the frontend re-resolved on the
    # next snapshot — see Phase B closing fix.
    members_directory: list[dict] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}
