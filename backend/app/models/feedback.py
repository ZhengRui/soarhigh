from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class FeedbackType(str, Enum):
    """Feedback type enumeration."""

    EXPERIENCE_OPENING = "experience_opening"
    EXPERIENCE_PEAK = "experience_peak"
    EXPERIENCE_VALLEY = "experience_valley"
    EXPERIENCE_ENDING = "experience_ending"
    SEGMENT = "segment"
    ATTENDEE = "attendee"


class FeedbackCreate(BaseModel):
    """
    Model for creating feedback for meeting experiences.
    """

    segment_id: Optional[str] = Field(default=None, description="The ID of the segment this feedback relates to.")
    type: FeedbackType = Field(description="The type of feedback being provided.")
    value: str = Field(description="The feedback content or value.")
    to_attendee_id: Optional[str] = Field(default=None, description="Target attendee ID for this feedback")


class FeedbackUpdate(BaseModel):
    """
    Model for updating existing feedback.
    """

    segment_id: Optional[str] = Field(default=None, description="The ID of the segment this feedback relates to.")
    type: Optional[FeedbackType] = Field(default=None, description="The type of feedback being provided.")
    value: Optional[str] = Field(default=None, description="The feedback content or value.")
    to_attendee_id: Optional[str] = Field(default=None, description="Target attendee ID for this feedback")


class Feedback(BaseModel):
    """
    Model representing a meeting feedback entry.
    """

    id: Optional[str] = Field(default=None, description="The unique identifier of the feedback.")
    meeting_id: str = Field(description="The ID of the meeting this feedback belongs to.")
    segment_id: Optional[str] = Field(default=None, description="The ID of the segment this feedback relates to.")
    type: str = Field(description="The type of feedback being provided.")
    value: str = Field(description="The feedback content or value.")
    from_wxid: str = Field(description="The WeChat openid of the person providing feedback.")
    to_attendee_id: Optional[str] = Field(default=None, description="Target attendee ID for this feedback")
    created_at: Optional[str] = Field(default=None, description="The timestamp when the feedback was created.")
    updated_at: Optional[str] = Field(default=None, description="The timestamp when the feedback was last updated.")


class FeedbackResponse(BaseModel):
    """
    Response model for feedback creation and updates.
    """

    success: bool = Field(description="Whether the feedback operation was successful.")
    feedback: Feedback = Field(description="The created or updated feedback.")


class FeedbackListResponse(BaseModel):
    """
    Response model for feedback list retrieval.
    """

    feedbacks: List[Feedback] = Field(description="List of feedbacks for the meeting.")
