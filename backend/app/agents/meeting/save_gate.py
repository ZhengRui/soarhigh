"""Pure save-classification helpers for the meeting agent's `save_draft` tool.

Gating logic lives here (not in the prompt) so the tool re-validates on
every call — the LLM cannot bypass the time gate by setting
`confirmed=true` directly.

Time reference: Asia/Shanghai. The meetings table stores dates and times
in club-local Shenzhen time; using UTC drifts "now" by up to 8 hours
during the morning when UTC is still on the previous day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from app.agents.meeting.models import Agenda

_SH = ZoneInfo("Asia/Shanghai")
_EDIT_GRACE = timedelta(hours=1)

SaveMode = Literal["create", "update", "refuse"]
RefuseReason = Literal["create_past", "edit_past", "missing_no", "missing_schedule"]


@dataclass
class SaveClassification:
    mode: SaveMode
    reason: Optional[RefuseReason] = None
    meeting_id: Optional[str] = None


def now_shanghai() -> datetime:
    return datetime.now(_SH)


def parse_meeting_datetime(date: Optional[str], hhmm: Optional[str]) -> Optional[datetime]:
    """Combine a YYYY-MM-DD date and HH:MM time into an Asia/Shanghai datetime.
    Returns None when either side is missing/empty so callers can decide
    how to treat partial schedules."""
    if not date or not hhmm:
        return None
    try:
        return datetime.fromisoformat(f"{date}T{hhmm}").replace(tzinfo=_SH)
    except ValueError:
        return None


def classify_save(
    agenda: Agenda,
    db_meeting: Optional[dict],
    now: datetime,
) -> SaveClassification:
    """Decide whether the current agenda can be saved as create / update.

    - `no` missing → refuse(missing_no). The meeting number is the lookup
      key for create-vs-update routing; without it we can't classify.
    - `db_meeting is None` → create path: needs full schedule, refuses if
      start_time is in the past.
    - `db_meeting is not None` → update path: refuses if the persisted
      end_time is more than 1h in the past.
    """
    if agenda.meta.no is None:
        return SaveClassification(mode="refuse", reason="missing_no")

    if db_meeting is None:
        start_dt = parse_meeting_datetime(agenda.meta.date, agenda.meta.start_time)
        if start_dt is None:
            return SaveClassification(mode="refuse", reason="missing_schedule")
        if start_dt < now:
            return SaveClassification(mode="refuse", reason="create_past")
        return SaveClassification(mode="create")

    end_dt = parse_meeting_datetime(db_meeting.get("date"), db_meeting.get("end_time"))
    if end_dt is None:
        # Persisted meeting has no end_time we can parse — treat as
        # editable. The DB enforces its own constraints; we don't want
        # to lock the user out because of a malformed legacy row.
        return SaveClassification(mode="update", meeting_id=db_meeting.get("id"))
    if end_dt < now - _EDIT_GRACE:
        return SaveClassification(mode="refuse", reason="edit_past", meeting_id=db_meeting.get("id"))
    return SaveClassification(mode="update", meeting_id=db_meeting.get("id"))
