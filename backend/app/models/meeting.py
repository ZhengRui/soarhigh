from typing import List, Optional

from pydantic import BaseModel, Field


class Attendee(BaseModel):
    id: str = Field(description="The unique identifier of the attendee.")
    name: str = Field(description="The name of the attendee.")
    member_id: str = Field(description="The member ID of the attendee.")


class Segment(BaseModel):
    id: str = Field(description="A unique identifier for each segment of the meeting.")
    type: str = Field(
        description="The type of segment, e.g., timer introduction, prepared speech, table topic session, \
            table topic evaluation."
    )
    start_time: str = Field(description="The start time of the segment.")
    duration: str = Field(description="The duration of the segment.")
    end_time: str = Field(description="The end time of the segment.")
    role_taker: Optional[Attendee] = Field(description="The attendee/attendees who is/are performing the segment.")
    title: str = Field(
        description="The title of the speech or workshop, applicable if the segment is a prepared speech or workshop."
    )
    content: str = Field(description="Detailed scripts or notes about the speech, evaluation, or activity.")
    related_segment_ids: str = Field(
        description="A list of IDs of related segments, stored as a comma-separated string."
    )


class Meeting(BaseModel):
    """
    Single model for all meeting operations (create, update, response).

    For create operations, id will be None.
    For update operations, all fields should be provided.
    For responses, id will be populated.
    """

    id: Optional[str] = Field(None, description="The unique identifier of the meeting.")
    no: Optional[int] = Field(None, description="The meeting number.")
    type: str = Field(description="The type of meeting, e.g., Regular, Workshop, Custom.")
    theme: str = Field(description="The theme for the meeting.")
    manager: Attendee = Field(description="The person organizing/managing the meeting.")
    date: str = Field(description="The date of the meeting.")
    start_time: str = Field(description="The start time of the meeting.")
    end_time: str = Field(description="The end time of the meeting.")
    location: str = Field(description="The location where the meeting is held.")
    introduction: str = Field(description="The introduction of the meeting.")
    segments: List[Segment] = Field(description="A list of segments that the meeting is composed of.")
    status: str = Field(default="draft", description="The status of the meeting, either 'draft' or 'published'.")
