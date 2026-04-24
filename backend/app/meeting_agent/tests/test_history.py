from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from app.meeting_agent.history import strip_snapshots_from_dumped_history, truncate_to_last_turns
from app.meeting_agent.prompts import SNAPSHOT_TEMPLATE


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
