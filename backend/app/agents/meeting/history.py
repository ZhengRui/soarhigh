"""History management helpers.

Pydantic AI stores conversation as a flat list of `ModelMessage` objects. A
"turn" in our domain starts with a user message (a `ModelRequest` containing
a `UserPromptPart`) and includes everything until the next user message:
assistant tool_call responses, tool results, assistant narrations.

We cap history length by turn count rather than by raw message count so the
cap is meaningful regardless of how many tools got called in each turn.
"""

from datetime import datetime, timezone

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)

MAX_TURNS_KEPT = 10

# Marker used in SNAPSHOT_TEMPLATE to separate the snapshot wrapper from the
# actual user text. The user's message is everything AFTER this marker.
_USER_MESSAGE_MARKER = "[User message]\n"


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


def replace_system_prompt(
    history: list[ModelMessage],
    system_prompt: str,
) -> list[ModelMessage]:
    """Replace foreign SystemPromptParts with the given agent's prompt.

    Pydantic AI only injects an agent's registered `system_prompt` when
    `message_history` is empty (see _agent_graph.py — `if not messages:
    parts.extend(self._sys_parts(...))`). On follow-up turns history is
    NEVER empty, so the agent's own prompt is silently skipped and the
    model runs with whatever SystemPromptPart was persisted from a
    prior turn. That's the wrong agent's identity (e.g. the router
    inheriting the meeting agent's prompt).

    Stripping isn't enough either — a non-empty history with no
    SystemPromptPart still skips _sys_parts injection, leaving the
    agent prompt-less. So we strip foreign system prompts AND prepend
    our own at the head of the first ModelRequest.
    """
    if not history:
        return history  # Pydantic AI will inject _sys_parts itself
    cleaned: list[ModelMessage] = []
    for msg in history:
        if isinstance(msg, ModelRequest):
            kept_parts = [p for p in msg.parts if not isinstance(p, SystemPromptPart)]
            if not kept_parts:
                continue  # drop request that was only a system prompt
            cleaned.append(ModelRequest(parts=kept_parts, instructions=msg.instructions))
        else:
            cleaned.append(msg)
    if not cleaned:
        return cleaned
    first = cleaned[0]
    if isinstance(first, ModelRequest):
        cleaned[0] = ModelRequest(
            parts=[SystemPromptPart(content=system_prompt), *first.parts],
            instructions=first.instructions,
        )
    else:
        cleaned.insert(0, ModelRequest(parts=[SystemPromptPart(content=system_prompt)]))
    return cleaned


def append_router_exchange(
    prior_history_dumped: list[dict],
    *,
    user_message: str,
    assistant_text: str,
) -> list[dict]:
    """Append a router-only user/assistant exchange to a JSON-dumped history.

    Specialists rely on Pydantic AI's `result.all_messages()` to capture
    the full turn, but the router's structured output and server-side
    text overrides (localized clarify text, fallback question) mean what
    we actually emit can differ from the raw LLM output. Build the new
    Pydantic AI messages explicitly so the unified history chain stays
    intact across router-only turns; otherwise the next turn loads an
    empty history_cursor and the router goes blind to prior context.
    """
    now = datetime.now(timezone.utc)
    new_messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content=user_message, timestamp=now)]),
        ModelResponse(parts=[TextPart(content=assistant_text)], timestamp=now),
    ]
    new_dumped = ModelMessagesTypeAdapter.dump_python(new_messages, mode="json")
    return list(prior_history_dumped) + new_dumped


def strip_snapshots_from_dumped_history(dumped: list[dict]) -> list[dict]:
    """Remove SNAPSHOT_TEMPLATE wrappers from UserPromptPart content in a
    JSON-dumped message history, leaving just the user's actual message.

    Rationale: Pydantic AI's `all_messages()` persists the full prompt we
    injected at turn start — which by design includes a live agenda snapshot
    as the prefix. Replaying those past prompts on the NEXT turn re-feeds
    STALE snapshots to the model; small/fast LLMs latch onto the wrong one
    or answer from memory rather than the current (correct) snapshot.

    Each turn only needs its current snapshot, which is injected fresh into
    the current prompt. Older turns' snapshots are pure noise — strip them
    before persisting history_cursor.

    This operates on the dump_python(mode="json") output (dicts), mutating
    in place for simplicity. Content that doesn't contain the marker is left
    alone (e.g. pure text messages routed through some other path).
    """
    for msg in dumped:
        if not isinstance(msg, dict):
            continue
        for part in msg.get("parts", []) or []:
            if part.get("part_kind") != "user-prompt":
                continue
            content = part.get("content")
            # Skip non-string (multimodal) content; we only wrap strings.
            if not isinstance(content, str):
                continue
            marker_at = content.rfind(_USER_MESSAGE_MARKER)
            if marker_at == -1:
                continue
            # Everything after the marker is the user's actual message; strip
            # leading/trailing whitespace from the template.
            part["content"] = content[marker_at + len(_USER_MESSAGE_MARKER) :].strip()
    return dumped
