"""Small helpers shared across agent route modules.

Kept narrow on purpose: only the pieces that are byte-for-byte
duplicated across `meeting.py`, `statistics.py`, and `unified.py`.
The full event-stream loop is NOT shared here — those routes diverge
on agenda_snapshot, image upload, addendum rendering, and revert
support, so a common harness would force template-method gymnastics
for one extra agent. Extract helpers, leave the loops.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


def _detect_user_language(text: str) -> str:
    """CJK majority → 'zh', otherwise 'en'. Per-turn detection so the
    model's reply language follows the user's current message regardless
    of session history. Both-zero defaults to English."""
    if not text:
        return "en"
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if cjk == 0 and latin == 0:
        return "en"
    return "zh" if cjk > latin else "en"


def _extract_error_info(e: Exception) -> tuple[str, bool]:
    """Pull a user-readable message + recoverability hint out of an agent
    exception. The raw `str(e)` on Pydantic AI errors is a huge dump of
    the provider's JSON response; the UI banner needs a single clean
    sentence."""
    try:
        from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
    except ImportError:
        return (str(e), True)

    if isinstance(e, UsageLimitExceeded):
        # Same request will hit the same limit; no point offering Retry.
        return (str(e), False)

    if isinstance(e, ModelHTTPError):
        body = e.body if isinstance(e.body, dict) else {}
        # Gemini/OpenAI convention: {"error": {"message": "..."}}
        err = body.get("error") if isinstance(body, dict) else None
        msg = err.get("message") if isinstance(err, dict) else None
        if msg:
            return (f"[{e.status_code}] {msg}", True)
        return (f"Model HTTP error {e.status_code}", True)

    return (str(e), True)


async def _error_only_stream(*, reason: str, recoverable: bool, message: str) -> AsyncIterator[bytes]:
    """Single-event SSE generator for routes that need to emit one error
    and end. Same shape the specialists emit on agent_error so the
    frontend's onEvent handler renders the banner identically."""
    yield _sse(
        "error",
        {"reason": reason, "recoverable": recoverable, "message": message},
    )


def _session_unavailable_response() -> StreamingResponse:
    """Generic 'session unavailable' SSE response — used at route entry
    when `verify_session_access` rejects a foreign-owned (or otherwise
    inaccessible) session. Identical shape across routes so 'foreign' /
    'expired' / 'invalid' are indistinguishable client-side. Returned
    BEFORE any LLM work or upload handling so a probe can't observe
    server-side processing differences."""
    return StreamingResponse(
        _error_only_stream(
            reason="session_unavailable",
            recoverable=False,
            message="Session unavailable.",
        ),
        media_type="text/event-stream",
    )
