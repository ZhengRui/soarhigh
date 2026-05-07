"""Capability registry for agent routing and policy checks."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.agents.runtime.contracts import AccessMode, AgentKind


class Capability(BaseModel):
    id: str
    owner_agent: AgentKind
    access: AccessMode
    supported_intents: tuple[str, ...]
    tool_names: tuple[str, ...] = Field(default_factory=tuple)
    unsupported_intents: tuple[str, ...] = Field(default_factory=tuple)
    prompt_snippet: str
    example_user_requests: tuple[str, ...] = Field(default_factory=tuple)
    expected_route: AgentKind
    eval_fixture_id: str | None = None

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not value or value.strip() != value or " " in value:
            raise ValueError("capability id must be a non-empty dot-separated token")
        return value


MEETING_MUTATION_TOOLS: tuple[str, ...] = (
    "set_role",
    "set_type",
    "set_title",
    "set_content",
    "set_duration",
    "set_buffer",
    "set_meta",
    "add_segment",
    "remove_segment",
    "move_segment",
    "swap_roles",
    "swap_time",
    "shift_segment_time",
    "create_from_text",
    "create_from_image",
    "create_from_template",
    "clone_from_meeting",
    "revert_last_turn",
    "revert_to_turn",
    "save_draft",
)

MEETING_READ_TOOLS: tuple[str, ...] = (
    "validate_agenda",
    "lookup_meeting",
    "show_current_agenda",
    "preview_meeting",
)

STATISTICS_READ_TOOLS: tuple[str, ...] = (
    "meeting_attendance_list",
    "member_role_matrix",
    "member_award_matrix",
    "meeting_manager_matrix",
    "lookup_meeting",
    "preview_meeting",
    "list_members",
)

GENERAL_KNOWLEDGE_TOOLS: tuple[str, ...] = ("view_skill",)


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        id="meeting.agenda_mutation",
        owner_agent=AgentKind.MEETING,
        access=AccessMode.WRITE,
        supported_intents=(
            "edit the current meeting draft",
            "create a meeting draft from text, image, template, or historical meeting",
            "undo or revert draft edits",
            "save the current draft as a new or existing meeting",
        ),
        unsupported_intents=("answer complete historical aggregate statistics",),
        tool_names=MEETING_MUTATION_TOOLS,
        prompt_snippet="Use the meeting specialist for current-draft creation and mutation.",
        example_user_requests=(
            "Set Timer to Joyce Feng.",
            "Create a regular meeting template.",
            "Clone meeting #451 after I confirm.",
            "Save the meeting draft.",
        ),
        expected_route=AgentKind.MEETING,
        eval_fixture_id="route.meeting.agenda_mutation",
    ),
    Capability(
        id="meeting.agenda_read",
        owner_agent=AgentKind.MEETING,
        access=AccessMode.READ,
        supported_intents=("validate or show the current draft", "preview historical meetings before cloning"),
        unsupported_intents=("mutate historical meetings",),
        tool_names=MEETING_READ_TOOLS,
        prompt_snippet="Use meeting read tools for current-draft display and clone-confirmation context.",
        example_user_requests=("Show the current agenda.", "Preview #451 before cloning it."),
        expected_route=AgentKind.MEETING,
        eval_fixture_id="route.meeting.agenda_read",
    ),
    Capability(
        id="statistics.attendance",
        owner_agent=AgentKind.STATISTICS,
        access=AccessMode.READ,
        supported_intents=("attendance counts", "attendance rankings", "member and guest totals"),
        unsupported_intents=("edit attendance data",),
        tool_names=("meeting_attendance_list",),
        prompt_snippet="Use meeting_attendance_list for dashboard-backed per-meeting attendance facts.",
        example_user_requests=("Which meeting had the highest attendance this year?",),
        expected_route=AgentKind.STATISTICS,
        eval_fixture_id="route.statistics.attendance",
    ),
    Capability(
        id="statistics.member_roles",
        owner_agent=AgentKind.STATISTICS,
        access=AccessMode.READ,
        supported_intents=("role counts by member", "role counts by meeting", "role rankings"),
        unsupported_intents=("assign future roles",),
        tool_names=("member_role_matrix",),
        prompt_snippet="Use member_role_matrix for dashboard-backed historical role assignments.",
        example_user_requests=("Who did TTE the most last year?",),
        expected_route=AgentKind.STATISTICS,
        eval_fixture_id="route.statistics.member_roles",
    ),
    Capability(
        id="statistics.awards",
        owner_agent=AgentKind.STATISTICS,
        access=AccessMode.READ,
        supported_intents=("award counts by winner", "award counts by category", "award rankings"),
        unsupported_intents=("compute awards from raw votes",),
        tool_names=("member_award_matrix",),
        prompt_snippet="Use member_award_matrix for assigned-award counts and references.",
        example_user_requests=("Who won Best Evaluator most often this year?",),
        expected_route=AgentKind.STATISTICS,
        eval_fixture_id="route.statistics.awards",
    ),
    Capability(
        id="statistics.meeting_lookup",
        owner_agent=AgentKind.STATISTICS,
        access=AccessMode.READ,
        supported_intents=("find historical meetings", "preview historical meeting details"),
        unsupported_intents=("complete aggregate topic counts from bounded lookup results",),
        tool_names=("lookup_meeting", "preview_meeting"),
        prompt_snippet="Use lookup_meeting and preview_meeting for read-only historical meeting inspection.",
        example_user_requests=("Show me the Emojis meeting.", "Preview meeting #451."),
        expected_route=AgentKind.STATISTICS,
        eval_fixture_id="route.statistics.meeting_lookup",
    ),
    Capability(
        id="statistics.meeting_manager",
        owner_agent=AgentKind.STATISTICS,
        access=AccessMode.READ,
        supported_intents=(
            "Meeting Manager counts by member",
            "Meeting Manager rankings",
            "who organized the most meetings",
        ),
        unsupported_intents=("assign Meeting Manager for upcoming meetings",),
        tool_names=("meeting_manager_matrix",),
        prompt_snippet="Use meeting_manager_matrix for exact server-side counts of Meeting Manager assignments.",
        example_user_requests=(
            "今年每个会员组织了多少次会议?",
            "Meeting Manager 排名",
        ),
        expected_route=AgentKind.STATISTICS,
        eval_fixture_id="route.statistics.meeting_manager",
    ),
    Capability(
        id="statistics.member_directory",
        owner_agent=AgentKind.STATISTICS,
        access=AccessMode.READ,
        supported_intents=("list club members", "member vs guest classification", "member roster size"),
        unsupported_intents=("add or remove members",),
        tool_names=("list_members",),
        prompt_snippet="Use list_members to enumerate the current club roster (id, username, full_name).",
        example_user_requests=("现在有哪些会员?", "我们俱乐部有多少会员?"),
        expected_route=AgentKind.STATISTICS,
        eval_fixture_id="route.statistics.member_directory",
    ),
    Capability(
        id="general.knowledge",
        owner_agent=AgentKind.GENERAL,
        access=AccessMode.READ,
        supported_intents=(
            "explain Toastmasters roles, terminology, or meeting protocol",
            "answer SoarHigh club bylaw / FAQ / policy questions",
            "explain capability boundaries of the assistant",
        ),
        unsupported_intents=(
            "edit or save a meeting draft",
            "compute historical attendance / role / award statistics",
        ),
        tool_names=GENERAL_KNOWLEDGE_TOOLS,
        prompt_snippet="Use view_skill to load knowledge base markdown for general / club Q&A.",
        example_user_requests=(
            "TT 是什么?",
            "我们俱乐部多久办一次例会?",
            "What does the Grammarian do?",
        ),
        expected_route=AgentKind.GENERAL,
        eval_fixture_id="route.general.knowledge",
    ),
)


def _coerce_agent_kind(agent_kind: AgentKind | str) -> AgentKind:
    return agent_kind if isinstance(agent_kind, AgentKind) else AgentKind(agent_kind)


def _build_tool_index(capabilities: tuple[Capability, ...]) -> dict[tuple[AgentKind, str], Capability]:
    index: dict[tuple[AgentKind, str], Capability] = {}
    for capability in capabilities:
        for tool_name in capability.tool_names:
            key = (capability.owner_agent, tool_name)
            if key in index:
                raise RuntimeError(
                    f"tool {tool_name!r} is registered by multiple capabilities for {capability.owner_agent.value}"
                )
            index[key] = capability
    return index


_CAPABILITY_BY_TOOL = _build_tool_index(CAPABILITIES)


def all_capabilities() -> tuple[Capability, ...]:
    return CAPABILITIES


def capabilities_for_agent(agent_kind: AgentKind | str) -> tuple[Capability, ...]:
    agent = _coerce_agent_kind(agent_kind)
    return tuple(capability for capability in CAPABILITIES if capability.owner_agent == agent)


def capability_for_tool(agent_kind: AgentKind | str, tool_name: str) -> Capability | None:
    return _CAPABILITY_BY_TOOL.get((_coerce_agent_kind(agent_kind), tool_name))


def tool_names_for_agent(agent_kind: AgentKind | str) -> set[str]:
    return {tool_name for capability in capabilities_for_agent(agent_kind) for tool_name in capability.tool_names}
