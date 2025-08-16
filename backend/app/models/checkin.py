from typing import List, Optional

from pydantic import BaseModel, Field


class CheckinCreate(BaseModel):
    """
    Model for creating checkins for meeting segments.
    """

    segment_ids: Optional[List[str]] = Field(
        default=None,
        description=(
            "Array of segment IDs the user is checking in for. "
            "None=general attendance, []=uncheckin, [ids]=specific segments."
        ),
    )
    name: Optional[str] = Field(default=None, description="Optional nickname for validation.")


class Checkin(BaseModel):
    """
    Model representing a meeting checkin.
    """

    id: Optional[str] = Field(default=None, description="The unique identifier of the checkin.")
    meeting_id: str = Field(description="The ID of the meeting this checkin belongs to.")
    wxid: str = Field(description="The WeChat openid of the person checking in.")
    segment_id: Optional[str] = Field(default=None, description="The ID of the segment the person is checking in for.")
    name: Optional[str] = Field(default=None, description="Optional nickname provided during checkin.")
    created_at: Optional[str] = Field(default=None, description="The timestamp when the checkin was created.")
    updated_at: Optional[str] = Field(default=None, description="The timestamp when the checkin was last updated.")


class CheckinResponse(BaseModel):
    """
    Response model for checkin creation.
    """

    success: bool = Field(description="Whether the checkin operation was successful.")
    checkins: List[Checkin] = Field(description="List of created checkins.")


class CheckinListResponse(BaseModel):
    """
    Response model for checkin list retrieval.
    """

    checkins: List[Checkin] = Field(description="List of checkins for the meeting.")
