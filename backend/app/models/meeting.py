from typing import List

from pydantic import BaseModel, Field


class MeetingSegment(BaseModel):
    segment_id: str = Field(description="A unique identifier for each segment of the meeting.")
    segment_type: str = Field(
        description="The type of segment, e.g., timer introduction, prepared speech, table topic session, \
            table topic evaluation."
    )
    start_time: str = Field(description="The start time of the segment.")
    duration: str = Field(description="The duration of the segment.")
    end_time: str = Field(description="The end time of the segment.")
    role_taker: str = Field(description="The attendee/attendees who is/are performing the segment.")
    title: str = Field(
        description="The title of the speech or workshop, applicable if the segment is a prepared speech or workshop."
    )
    content: str = Field(description="Detailed scripts or notes about the speech, evaluation, or activity.")
    related_segment_ids: str = Field(
        description="A list of IDs of related segments, stored as a comma-separated string."
    )

    class Config:
        extra = "forbid"


class Meeting(BaseModel):
    meeting_type: str = Field(description="The type of meeting, e.g., Regular, Workshop, Activity.")
    theme: str = Field(description="The theme for the meeting.")
    meeting_manager: str = Field(description="The person organizing/managing the meeting.")
    date: str = Field(description="The date of the meeting.")
    start_time: str = Field(description="The start time of the meeting.")
    end_time: str = Field(description="The end time of the meeting.")
    location: str = Field(description="The location where the meeting is held.")
    introduction: str = Field(description="The introduction of the meeting.")
    segments: List[MeetingSegment] = Field(description="A list of segments that the meeting is composed of.")

    class Config:
        extra = "forbid"
