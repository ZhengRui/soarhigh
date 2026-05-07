from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from app.agents.meeting.prompts import SNAPSHOT_TEMPLATE
from app.agents.runtime.contracts import AgentKind
from app.agents.runtime.history import (
    prepare_history_for_agent,
    strip_foreign_agent_tool_calls,
    strip_skill_bodies_from_dumped_history,
    strip_snapshots_from_dumped_history,
    truncate_to_last_turns,
)


def _user_turn(text: str = "hello"):
    """Helper: build the 4-message pattern a simple 1-tool turn produces."""
    return [
        ModelRequest(parts=[UserPromptPart(content=text)]),
        ModelResponse(parts=[ToolCallPart(tool_name="set_role", args={"x": 1}, tool_call_id="t1")]),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="set_role",
                    content={"ok": True},
                    tool_call_id="t1",
                )
            ]
        ),
        ModelResponse(parts=[TextPart(content=f"ok, {text} done")]),
    ]


def _no_tool_turn(text: str = "hi"):
    return [
        ModelRequest(parts=[UserPromptPart(content=text)]),
        ModelResponse(parts=[TextPart(content=f"reply to {text}")]),
    ]


def test_empty_history_returns_empty():
    assert truncate_to_last_turns([], max_turns=8) == []


def test_fewer_than_max_turns_returns_all():
    history = _user_turn("t1") + _user_turn("t2") + _user_turn("t3")
    assert truncate_to_last_turns(history, max_turns=8) == history


def test_exactly_max_turns_returns_all():
    history = []
    for i in range(8):
        history += _user_turn(f"t{i}")
    assert truncate_to_last_turns(history, max_turns=8) == history


def test_more_than_max_turns_keeps_last_n():
    history = []
    for i in range(12):
        history += _user_turn(f"t{i}")
    truncated = truncate_to_last_turns(history, max_turns=8)

    # Should be exactly 8 turns * 4 messages each = 32 messages.
    assert len(truncated) == 32
    # First surviving message should be a user message from turn 4 (i.e., t4).
    first = truncated[0]
    assert isinstance(first, ModelRequest)
    user_parts = [p for p in first.parts if isinstance(p, UserPromptPart)]
    assert user_parts and user_parts[0].content == "t4"


def test_mix_of_tool_and_no_tool_turns():
    # 5 turns: tool, no-tool, tool, no-tool, tool.
    history = _user_turn("t1") + _no_tool_turn("t2") + _user_turn("t3") + _no_tool_turn("t4") + _user_turn("t5")
    # Cap at 3 turns: expect t3, t4, t5 content.
    truncated = truncate_to_last_turns(history, max_turns=3)
    # 3 turns: _user_turn (4 msgs) + _no_tool_turn (2 msgs) + _user_turn (4 msgs) = 10
    assert len(truncated) == 10
    # First message is user "t3".
    first = truncated[0]
    user_parts = [p for p in first.parts if isinstance(p, UserPromptPart)]
    assert user_parts and user_parts[0].content == "t3"


def test_max_turns_zero_returns_input_unchanged():
    # Defensive: a zero cap is a no-op (not a wipe). Prevents accidental
    # total-loss bugs if someone passes 0.
    history = _user_turn("t1")
    assert truncate_to_last_turns(history, max_turns=0) == history


def test_tool_return_parts_never_counted_as_turn_start():
    # Regression guard: ModelRequest with ToolReturnPart must NOT be treated
    # as a user turn boundary. If it were, the tool-result message of turn 3
    # would count as a turn, and we'd over-slice.
    history = _user_turn("a") + _user_turn("b") + _user_turn("c")
    # 3 user turns. If ToolReturnPart counted, we'd see 6 "turns".
    truncated = truncate_to_last_turns(history, max_turns=3)
    assert truncated == history


# ---------------------------------------------------------------------------
# strip_snapshots_from_dumped_history
# ---------------------------------------------------------------------------


def _wrap_with_snapshot(user_text: str, snapshot_segments: int = 2) -> str:
    """Build a UserPromptPart content string that looks like what the route
    actually produces: SNAPSHOT_TEMPLATE filled with a fake snapshot JSON."""
    snapshot = '{"segments": [' + ",".join(f'"s{i}"' for i in range(snapshot_segments)) + "]}"
    return SNAPSHOT_TEMPLATE.format(
        snapshot_json=snapshot,
        next_seq=1,
        tail_seq=0,
        user_message=user_text,
        attachment_block="",
        language_hint="",
        today="2026-04-27",
    )


def test_strip_removes_snapshot_wrapper_from_user_prompt_parts():
    dumped = [
        {
            "parts": [
                {
                    "content": _wrap_with_snapshot("把 SAA 改成 Joyce"),
                    "part_kind": "user-prompt",
                }
            ],
        },
        {
            "parts": [{"content": "ok done", "part_kind": "text"}],
        },
    ]
    result = strip_snapshots_from_dumped_history(dumped)
    # User prompt is now just the user's message, with snapshot JSON gone.
    assert result[0]["parts"][0]["content"] == "把 SAA 改成 Joyce"
    # Non-user-prompt parts are untouched.
    assert result[1]["parts"][0]["content"] == "ok done"


def test_strip_leaves_content_without_marker_alone():
    # Not all UserPromptPart content was necessarily wrapped. If something
    # else put a user-prompt through (or content predates this helper),
    # we must not corrupt it.
    dumped = [
        {
            "parts": [{"content": "just a plain message", "part_kind": "user-prompt"}],
        }
    ]
    assert strip_snapshots_from_dumped_history(dumped)[0]["parts"][0]["content"] == "just a plain message"


def test_strip_processes_all_past_turns():
    # Multi-turn history: every past UserPromptPart is stripped.
    dumped = [
        {"parts": [{"content": _wrap_with_snapshot("turn 1"), "part_kind": "user-prompt"}]},
        {"parts": [{"content": "reply 1", "part_kind": "text"}]},
        {"parts": [{"content": _wrap_with_snapshot("turn 2"), "part_kind": "user-prompt"}]},
        {"parts": [{"content": "reply 2", "part_kind": "text"}]},
        {"parts": [{"content": _wrap_with_snapshot("turn 3"), "part_kind": "user-prompt"}]},
    ]
    result = strip_snapshots_from_dumped_history(dumped)
    assert result[0]["parts"][0]["content"] == "turn 1"
    assert result[2]["parts"][0]["content"] == "turn 2"
    assert result[4]["parts"][0]["content"] == "turn 3"
    # No snapshot JSON remains anywhere in the stripped history.
    for msg in result:
        for part in msg["parts"]:
            if part["part_kind"] == "user-prompt":
                assert "[Current agenda" not in part["content"]
                assert "segments" not in part["content"]


def test_strip_is_safe_on_empty_and_malformed_inputs():
    # Empty list.
    assert strip_snapshots_from_dumped_history([]) == []
    # Message without parts key.
    assert strip_snapshots_from_dumped_history([{"kind": "response"}]) == [{"kind": "response"}]
    # UserPromptPart with non-string content (multimodal). Left alone.
    weird = [
        {
            "parts": [
                {
                    "content": [{"type": "image", "url": "x"}],
                    "part_kind": "user-prompt",
                }
            ]
        }
    ]
    assert strip_snapshots_from_dumped_history(weird) == weird


def test_strip_ignores_retry_prompt_parts():
    # RetryPromptPart is a separate part_kind; must not be touched even if its
    # content happens to contain the marker text (unlikely, but defensive).
    dumped = [
        {
            "parts": [
                {
                    "content": "tool failed, retry",
                    "part_kind": "retry-prompt",
                }
            ]
        }
    ]
    assert strip_snapshots_from_dumped_history(dumped) == dumped


# ---------------------------------------------------------------------------
# strip_skill_bodies_from_dumped_history
# ---------------------------------------------------------------------------


_FULL_SKILL_BODY = (
    "# Toastmasters Roles\n\n"
    "## TT (Table Topics)\n\n"
    "Lots of detailed knowledge content here that would bloat history_cursor "
    "if persisted across every future turn.\n"
)


def _view_skill_turn(skill_name: str, body: str = _FULL_SKILL_BODY, call_id: str = "vs1"):
    """Build the 4-message pattern produced by a successful view_skill call:
    user prompt → assistant tool_call → tool return → assistant text reply.
    Same dumped-dict shape produced by Pydantic AI's all_messages_json()."""
    return [
        {
            "kind": "request",
            "parts": [{"content": f"问关于 {skill_name} 的问题", "part_kind": "user-prompt"}],
        },
        {
            "kind": "response",
            "parts": [
                {
                    "part_kind": "tool-call",
                    "tool_name": "view_skill",
                    "args": {"name": skill_name},
                    "tool_call_id": call_id,
                }
            ],
        },
        {
            "kind": "request",
            "parts": [
                {
                    "part_kind": "tool-return",
                    "tool_name": "view_skill",
                    "content": body,
                    "tool_call_id": call_id,
                }
            ],
        },
        {
            "kind": "response",
            "parts": [{"content": "Here's what that skill says...", "part_kind": "text"}],
        },
    ]


def test_strip_replaces_view_skill_body_with_placeholder():
    dumped = _view_skill_turn("toastmasters-roles")
    result = strip_skill_bodies_from_dumped_history(dumped)

    # tool-return content is no longer the original body.
    tool_return = result[2]["parts"][0]
    assert _FULL_SKILL_BODY not in tool_return["content"]
    # Placeholder tells the model to re-call if needed.
    assert "view_skill" in tool_return["content"]
    assert "trimmed" in tool_return["content"].lower() or "placeholder" in tool_return["content"].lower()


def test_strip_preserves_tool_call_part_with_skill_name():
    # The model needs to see WHICH skill was called earlier — we strip the
    # return body, not the call. The skill name lives in args.name on the
    # tool-call part, which must remain intact.
    dumped = _view_skill_turn("meeting-protocol")
    result = strip_skill_bodies_from_dumped_history(dumped)

    tool_call = result[1]["parts"][0]
    assert tool_call["part_kind"] == "tool-call"
    assert tool_call["tool_name"] == "view_skill"
    assert tool_call["args"]["name"] == "meeting-protocol"


def test_strip_leaves_other_tool_returns_untouched():
    # A view_skill return should be stripped, but other tools (set_role,
    # lookup_meeting, etc.) must NOT have their bodies touched.
    dumped = [
        {
            "kind": "request",
            "parts": [
                {
                    "part_kind": "tool-return",
                    "tool_name": "set_role",
                    "content": '{"ok": true, "data": "important result"}',
                    "tool_call_id": "sr1",
                }
            ],
        },
        {
            "kind": "request",
            "parts": [
                {
                    "part_kind": "tool-return",
                    "tool_name": "view_skill",
                    "content": _FULL_SKILL_BODY,
                    "tool_call_id": "vs1",
                }
            ],
        },
    ]
    result = strip_skill_bodies_from_dumped_history(dumped)

    # set_role result is preserved verbatim.
    assert result[0]["parts"][0]["content"] == '{"ok": true, "data": "important result"}'
    # view_skill body is stripped.
    assert _FULL_SKILL_BODY not in result[1]["parts"][0]["content"]


def test_strip_handles_multiple_view_skill_returns_in_one_history():
    dumped = (
        _view_skill_turn("toastmasters-roles", call_id="vs1")
        + _view_skill_turn("meeting-protocol", call_id="vs2")
        + _view_skill_turn("soarhigh-bylaws", call_id="vs3")
    )
    result = strip_skill_bodies_from_dumped_history(dumped)

    # All three view_skill returns have the placeholder.
    for msg in result:
        for part in msg.get("parts", []):
            if part.get("part_kind") == "tool-return" and part.get("tool_name") == "view_skill":
                assert _FULL_SKILL_BODY not in part["content"]


def test_strip_preserves_user_prompts_and_text_responses():
    dumped = _view_skill_turn("toastmasters-roles")
    result = strip_skill_bodies_from_dumped_history(dumped)

    # User prompt (turn 0) untouched.
    assert result[0]["parts"][0]["content"] == "问关于 toastmasters-roles 的问题"
    # Assistant text reply (turn 3) untouched.
    assert result[3]["parts"][0]["content"] == "Here's what that skill says..."


def test_strip_skill_is_safe_on_empty_and_malformed_inputs():
    assert strip_skill_bodies_from_dumped_history([]) == []
    # Message without parts key.
    assert strip_skill_bodies_from_dumped_history([{"kind": "response"}]) == [{"kind": "response"}]
    # Non-dict entry — skipped without crashing.
    weird = ["not a dict", {"kind": "response", "parts": []}]
    assert strip_skill_bodies_from_dumped_history(weird) == weird


def test_strip_skill_leaves_non_string_content_alone():
    # Pydantic AI permits structured (dict) tool returns. We only blank
    # string bodies; structured returns from a hypothetical future
    # view_skill variant would be left intact.
    dumped = [
        {
            "kind": "request",
            "parts": [
                {
                    "part_kind": "tool-return",
                    "tool_name": "view_skill",
                    "content": {"body": "structured return"},
                    "tool_call_id": "vs1",
                }
            ],
        }
    ]
    assert strip_skill_bodies_from_dumped_history(dumped) == dumped


def test_strip_skill_and_strip_snapshot_compose():
    # Both strippers run in sequence in the route handler. Verify they
    # don't interfere — each leaves the other's targets alone.
    user_prompt = SNAPSHOT_TEMPLATE.format(
        snapshot_json='{"segments": []}',
        next_seq=1,
        tail_seq=0,
        user_message="把 SAA 改成 Joyce",
        attachment_block="",
        language_hint="",
        today="2026-05-07",
    )
    dumped = [
        {"kind": "request", "parts": [{"content": user_prompt, "part_kind": "user-prompt"}]},
        {
            "kind": "response",
            "parts": [
                {
                    "part_kind": "tool-call",
                    "tool_name": "view_skill",
                    "args": {"name": "toastmasters-roles"},
                    "tool_call_id": "vs1",
                }
            ],
        },
        {
            "kind": "request",
            "parts": [
                {
                    "part_kind": "tool-return",
                    "tool_name": "view_skill",
                    "content": _FULL_SKILL_BODY,
                    "tool_call_id": "vs1",
                }
            ],
        },
    ]

    result = strip_skill_bodies_from_dumped_history(strip_snapshots_from_dumped_history(dumped))

    # Snapshot stripped from user prompt.
    assert result[0]["parts"][0]["content"] == "把 SAA 改成 Joyce"
    # Skill body stripped from tool return.
    assert _FULL_SKILL_BODY not in result[2]["parts"][0]["content"]
    # tool-call part with skill name still intact.
    assert result[1]["parts"][0]["args"]["name"] == "toastmasters-roles"


# ---------------------------------------------------------------------------
# strip_foreign_agent_tool_calls
# ---------------------------------------------------------------------------


def _meeting_set_role_turn(call_id: str = "sr1"):
    """Build a 4-message pattern for a Meeting-agent set_role turn."""
    return [
        {"kind": "request", "parts": [{"content": "把 Timer 改成 Joyce", "part_kind": "user-prompt"}]},
        {
            "kind": "response",
            "parts": [
                {
                    "part_kind": "tool-call",
                    "tool_name": "set_role",
                    "args": {"segment_id": "abc12", "role": "Timer", "name": "Joyce"},
                    "tool_call_id": call_id,
                }
            ],
        },
        {
            "kind": "request",
            "parts": [
                {
                    "part_kind": "tool-return",
                    "tool_name": "set_role",
                    "content": '{"ok": true}',
                    "tool_call_id": call_id,
                }
            ],
        },
        {"kind": "response", "parts": [{"content": "改好了。", "part_kind": "text"}]},
    ]


def _statistics_list_members_turn(call_id: str = "lm1"):
    """Build a 4-message pattern for a Statistics-agent list_members turn.

    Uses `list_members` because it's exclusively registered to Statistics —
    `lookup_meeting` and `preview_meeting` are shared with Meeting, so they
    pass through both agents' filters.
    """
    return [
        {"kind": "request", "parts": [{"content": "列一下所有会员", "part_kind": "user-prompt"}]},
        {
            "kind": "response",
            "parts": [
                {
                    "part_kind": "tool-call",
                    "tool_name": "list_members",
                    "args": {},
                    "tool_call_id": call_id,
                }
            ],
        },
        {
            "kind": "request",
            "parts": [
                {
                    "part_kind": "tool-return",
                    "tool_name": "list_members",
                    "content": '[{"english_name": "Joyce"}]',
                    "tool_call_id": call_id,
                }
            ],
        },
        {"kind": "response", "parts": [{"content": "共 1 位会员。", "part_kind": "text"}]},
    ]


def test_foreign_filter_strips_view_skill_for_statistics_agent():
    # Statistics loading a session where General previously called view_skill.
    # The Statistics agent must NOT see the view_skill tool-call/return parts,
    # because view_skill is registered to General only.
    history = _view_skill_turn("toastmasters-roles")
    result = strip_foreign_agent_tool_calls(history, AgentKind.STATISTICS)

    # User prompts and assistant text replies survive (no tool_name on those).
    user_prompts = [part for msg in result for part in msg.get("parts", []) if part.get("part_kind") == "user-prompt"]
    text_parts = [part for msg in result for part in msg.get("parts", []) if part.get("part_kind") == "text"]
    assert len(user_prompts) == 1
    assert len(text_parts) == 1
    # No view_skill ToolCallParts or ToolReturnParts left in any message.
    for msg in result:
        for part in msg.get("parts", []):
            assert part.get("tool_name") != "view_skill"


def test_foreign_filter_keeps_view_skill_for_general_agent():
    # General loading its OWN view_skill calls — must keep them so the model
    # retains in-agent audit of what skills it has consulted earlier.
    history = _view_skill_turn("toastmasters-roles")
    result = strip_foreign_agent_tool_calls(history, AgentKind.GENERAL)

    tool_calls = [
        part
        for msg in result
        for part in msg.get("parts", [])
        if part.get("part_kind") == "tool-call" and part.get("tool_name") == "view_skill"
    ]
    tool_returns = [
        part
        for msg in result
        for part in msg.get("parts", [])
        if part.get("part_kind") == "tool-return" and part.get("tool_name") == "view_skill"
    ]
    assert len(tool_calls) == 1
    assert len(tool_returns) == 1


def test_foreign_filter_strips_meeting_tools_for_general_agent():
    # General loading a session where Meeting previously called set_role.
    # General must not see Meeting's tool calls.
    history = _meeting_set_role_turn()
    result = strip_foreign_agent_tool_calls(history, AgentKind.GENERAL)

    for msg in result:
        for part in msg.get("parts", []):
            assert part.get("tool_name") != "set_role"
    # User prompt and assistant text reply are kept.
    assert any(part.get("part_kind") == "user-prompt" for msg in result for part in msg.get("parts", []))
    assert any(part.get("part_kind") == "text" for msg in result for part in msg.get("parts", []))


def test_foreign_filter_strips_statistics_tools_for_meeting_agent():
    # Meeting loading a session where Statistics called list_members.
    # Meeting must not see Statistics' tool calls.
    history = _statistics_list_members_turn()
    result = strip_foreign_agent_tool_calls(history, AgentKind.MEETING)

    for msg in result:
        for part in msg.get("parts", []):
            assert part.get("tool_name") != "list_members"


def test_foreign_filter_keeps_meeting_tools_for_meeting_agent():
    # Meeting loading its own set_role turn — kept.
    history = _meeting_set_role_turn()
    result = strip_foreign_agent_tool_calls(history, AgentKind.MEETING)

    tool_returns = [
        part
        for msg in result
        for part in msg.get("parts", [])
        if part.get("part_kind") == "tool-return" and part.get("tool_name") == "set_role"
    ]
    assert len(tool_returns) == 1


def test_foreign_filter_mixed_history_keeps_only_current_agents_calls():
    # Realistic shared-session history: General turn + Statistics turn + Meeting turn.
    # Statistics agent loads — should see ONLY its own tool calls.
    history = (
        _view_skill_turn("toastmasters-roles", call_id="vs1")
        + _statistics_list_members_turn(call_id="lm1")
        + _meeting_set_role_turn(call_id="sr1")
    )
    result = strip_foreign_agent_tool_calls(history, AgentKind.STATISTICS)

    seen_tool_names = {
        part.get("tool_name") for msg in result for part in msg.get("parts", []) if part.get("tool_name") is not None
    }
    assert seen_tool_names == {"list_members"}
    # All three turns' user prompts + assistant text replies survive.
    user_prompts = [part for msg in result for part in msg.get("parts", []) if part.get("part_kind") == "user-prompt"]
    text_parts = [part for msg in result for part in msg.get("parts", []) if part.get("part_kind") == "text"]
    assert len(user_prompts) == 3
    assert len(text_parts) == 3


def test_foreign_filter_drops_messages_with_no_remaining_parts():
    # When a ModelResponse has only ToolCallParts and they're all foreign, the
    # whole ModelResponse should be dropped — Pydantic AI doesn't accept a
    # parts-less response.
    history = [
        {
            "kind": "response",
            "parts": [
                {
                    "part_kind": "tool-call",
                    "tool_name": "view_skill",
                    "args": {"name": "x"},
                    "tool_call_id": "vs1",
                }
            ],
        },
    ]
    result = strip_foreign_agent_tool_calls(history, AgentKind.STATISTICS)
    assert result == []


def test_foreign_filter_is_safe_on_empty_input():
    assert strip_foreign_agent_tool_calls([], AgentKind.GENERAL) == []
    assert strip_foreign_agent_tool_calls([], AgentKind.MEETING) == []
    assert strip_foreign_agent_tool_calls([], AgentKind.STATISTICS) == []


def test_foreign_filter_keeps_messages_with_no_tool_parts():
    # A pure user/assistant exchange (no tool calls) should pass through unchanged.
    history = [
        {"kind": "request", "parts": [{"content": "hi", "part_kind": "user-prompt"}]},
        {"kind": "response", "parts": [{"content": "hello!", "part_kind": "text"}]},
    ]
    result = strip_foreign_agent_tool_calls(history, AgentKind.STATISTICS)
    assert result == history


# ---------------------------------------------------------------------------
# prepare_history_for_agent — model_view vs storage_prior split
# ---------------------------------------------------------------------------


def test_prepare_returns_filtered_model_view_and_unfiltered_storage_prior():
    # General turn (carries view_skill ToolCallPart) followed by a Statistics
    # turn (carries list_members). When STATISTICS loads, the model_view
    # must NOT show General's view_skill, but storage_prior MUST keep it so
    # the next save doesn't scrub it from the shared cursor.
    history = _view_skill_turn("toastmasters-roles", call_id="vs1") + _statistics_list_members_turn(call_id="lm1")

    model_view, storage_prior = prepare_history_for_agent(
        history,
        current_agent=AgentKind.STATISTICS,
        system_prompt="STATS PROMPT",
    )

    # model_view: foreign tool parts gone.
    model_view_tool_names = set()
    for msg in model_view:
        for part in msg.parts:
            tool_name = getattr(part, "tool_name", None)
            if tool_name is not None:
                model_view_tool_names.add(tool_name)
    assert "view_skill" not in model_view_tool_names
    assert "list_members" in model_view_tool_names

    # storage_prior: full audit retained.
    storage_tool_names = set()
    for msg in storage_prior:
        for part in msg.parts:
            tool_name = getattr(part, "tool_name", None)
            if tool_name is not None:
                storage_tool_names.add(tool_name)
    assert "view_skill" in storage_tool_names  # ← preserved for the next save
    assert "list_members" in storage_tool_names


def test_prepare_empty_input_returns_two_empty_lists():
    model_view, storage_prior = prepare_history_for_agent(
        [],
        current_agent=AgentKind.GENERAL,
        system_prompt="X",
    )
    assert model_view == []
    assert storage_prior == []


def test_prepare_storage_prior_used_at_save_time_preserves_general_view_skill():
    # Regression test for the bug Codex caught: if a route had used
    # `final_result.all_messages()` (= filtered_view + new_turn) as the
    # save base, General's prior view_skill ToolCallPart would be scrubbed
    # by every Statistics turn. The fix uses (storage_prior + new_messages)
    # instead. This test simulates that save and asserts General's audit
    # survives.
    prior = _view_skill_turn("soarhigh-bylaws", call_id="vs1")

    # Statistics loads — gets a filtered model_view and the unfiltered
    # storage_prior.
    _, storage_prior = prepare_history_for_agent(
        prior,
        current_agent=AgentKind.STATISTICS,
        system_prompt="STATS PROMPT",
    )

    # Statistics' new turn (just user prompt + assistant text — no tool call).
    new_messages = [
        ModelRequest(parts=[UserPromptPart(content="顺便再问一句")]),
        ModelResponse(parts=[TextPart(content="收到。")]),
    ]

    # The route saves storage_prior + new_messages, NOT all_messages of
    # the filtered view. Verify the saved cursor still contains the
    # General view_skill audit.
    saved = list(storage_prior) + new_messages
    saved_tool_names = set()
    for msg in saved:
        for part in msg.parts:
            tool_name = getattr(part, "tool_name", None)
            if tool_name is not None:
                saved_tool_names.add(tool_name)
    assert "view_skill" in saved_tool_names
