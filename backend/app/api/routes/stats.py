from fastapi import APIRouter, Depends, HTTPException

from ...db.stats import get_meeting_attendance_stats, get_member_meeting_stats
from ...models.stats import DashboardStats, MeetingAttendanceRecord, MemberMeetingRecord
from ...models.users import User
from .auth import get_current_user

stats_router = r = APIRouter()


@r.get("/stats/dashboard", response_model=DashboardStats)
async def r_get_dashboard_stats(
    start_date: str,
    end_date: str,
    user: User = Depends(get_current_user),
) -> DashboardStats:
    """
    Get dashboard statistics for a date range.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        DashboardStats containing member_meetings and meeting_attendance data
    """
    try:
        # Get member meeting stats (Chart 1)
        member_meetings_data = get_member_meeting_stats(start_date, end_date)
        member_meetings = [MemberMeetingRecord(**record) for record in member_meetings_data]

        # Get meeting attendance stats (Chart 2)
        meeting_attendance_data = get_meeting_attendance_stats(start_date, end_date)
        meeting_attendance = [MeetingAttendanceRecord(**record) for record in meeting_attendance_data]

        return DashboardStats(
            member_meetings=member_meetings,
            meeting_attendance=meeting_attendance,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard stats: {e!s}")
