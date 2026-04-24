"""History management helpers.

Pydantic AI stores conversation as a flat list of `ModelMessage` objects. A
"turn" in our domain starts with a user message (a `ModelRequest` containing
a `UserPromptPart`) and includes everything until the next user message:
assistant tool_call responses, tool results, assistant narrations.

We cap history length by turn count rather than by raw message count so the
cap is meaningful regardless of how many tools got called in each turn.
"""

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

MAX_TURNS_KEPT = 10


def _is_user_turn_start(msg: ModelMessage) -> bool:
    """A message begins a new user turn iff it is a ModelRequest that carries
    a UserPromptPart. Tool results are also ModelRequest objects but with
    ToolReturnPart, not UserPromptPart — they belong to the preceding turn.
    """
    if not isinstance(msg, ModelRequest):
        return False
    return any(isinstance(p, UserPromptPart) for p in msg.parts)


def truncate_to_last_turns(
    history: list[ModelMessage],
    max_turns: int = MAX_TURNS_KEPT,
) -> list[ModelMessage]:
    """Return history trimmed to the last `max_turns` user turns.

    Walk backward counting user-message boundaries. Remember the index of the
    Nth such boundary (where N == max_turns). If a further (N+1)th boundary is
    encountered, that's one turn too many — slice from the remembered index
    onward. Otherwise history has fewer than max_turns turns and is returned
    unchanged.
    """
    if not history or max_turns <= 0:
        return history

    user_count = 0
    nth_turn_start: int | None = None

    for i in range(len(history) - 1, -1, -1):
        if _is_user_turn_start(history[i]):
            user_count += 1
            if user_count == max_turns:
                nth_turn_start = i
            elif user_count > max_turns and nth_turn_start is not None:
                return history[nth_turn_start:]

    # Fewer than max_turns + 1 user messages total — nothing to trim.
    return history
