from typing import List, Optional

from pydantic import BaseModel, Field


class MemberMeetingRecord(BaseModel):
    """Raw data for member attendance and roles"""

    member_id: str = Field(description="The unique identifier of the member")
    username: str = Field(description="The username of the member")
    full_name: str = Field(description="The full name of the member")
    meeting_id: str = Field(description="The unique identifier of the meeting")
    meeting_date: str = Field(description="The date of the meeting (YYYY-MM-DD)")
    meeting_theme: str = Field(description="The theme of the meeting")
    meeting_no: Optional[int] = Field(default=None, description="The meeting number")
    role: str = Field(description="The role/segment type the member took")


class MeetingAttendanceRecord(BaseModel):
    """Attendance data per meeting"""

    meeting_id: str = Field(description="The unique identifier of the meeting")
    meeting_date: str = Field(description="The date of the meeting (YYYY-MM-DD)")
    meeting_theme: str = Field(description="The theme of the meeting")
    meeting_no: Optional[int] = Field(default=None, description="The meeting number")
    member_count: int = Field(description="Number of club members who attended")
    guest_count: int = Field(description="Number of guests who attended")
    member_names: List[str] = Field(description="Names of club members who attended")
    guest_names: List[str] = Field(description="Names of guests who attended")


class DashboardStats(BaseModel):
    """Combined dashboard response"""

    member_meetings: List[MemberMeetingRecord] = Field(description="Raw data for member attendance chart")
    meeting_attendance: List[MeetingAttendanceRecord] = Field(
        description="Attendance data per meeting for stacked chart"
    )
