from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from app.agent.history import truncate_to_last_turns


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
