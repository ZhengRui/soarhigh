from typing import List, Optional

from pydantic import BaseModel, Field


class TimingCreate(BaseModel):
    """Model for creating a single timing record."""

    segment_id: str = Field(description="The ID of the segment being timed.")
    name: Optional[str] = Field(
        default=None,
        description="Speaker name (required for Table Topics, optional for other segments).",
    )
    planned_duration_minutes: int = Field(description="The planned duration in minutes.")
    actual_start_time: str = Field(description="ISO timestamp when timing started.")
    actual_end_time: str = Field(description="ISO timestamp when timing ended.")


class TimingBatchItem(BaseModel):
    """A single timing item within a batch (for Table Topics)."""

    name: str = Field(description="Speaker name (required for Table Topics).")
    planned_duration_minutes: int = Field(description="The planned duration in minutes.")
    actual_start_time: str = Field(description="ISO timestamp when timing started.")
    actual_end_time: str = Field(description="ISO timestamp when timing ended.")


class TimingBatchCreate(BaseModel):
    """Model for batch creating timing records (Table Topics)."""

    segment_id: str = Field(description="The ID of the Table Topics segment.")
    timings: List[TimingBatchItem] = Field(description="List of timing records to create.")


class Timing(BaseModel):
    """Model representing a timing record."""

    id: Optional[str] = Field(default=None, description="The unique identifier of the timing.")
    meeting_id: str = Field(description="The ID of the meeting.")
    segment_id: str = Field(description="The ID of the segment.")
    name: Optional[str] = Field(default=None, description="Speaker name.")
    planned_duration_minutes: int = Field(description="The planned duration in minutes.")
    actual_start_time: str = Field(description="ISO timestamp when timing started.")
    actual_end_time: str = Field(description="ISO timestamp when timing ended.")
    actual_duration_seconds: int = Field(description="Calculated duration in seconds.")
    dot_color: str = Field(description="Calculated dot color: gray/green/yellow/red/bell.")
    created_at: Optional[str] = Field(default=None, description="Timestamp when created.")
    updated_at: Optional[str] = Field(default=None, description="Timestamp when last updated.")


class TimingsListResponse(BaseModel):
    """Response model for timing list retrieval."""

    can_control: bool = Field(description="Whether the current user can control the timer.")
    timings: List[Timing] = Field(description="List of timing records for the meeting.")


class TimingResponse(BaseModel):
    """Response model for single timing creation."""

    success: bool = Field(description="Whether the operation was successful.")
    timing: Timing = Field(description="The created timing record.")


class TimingBatchResponse(BaseModel):
    """Response model for batch timing creation."""

    success: bool = Field(description="Whether the operation was successful.")
    timings: List[Timing] = Field(description="List of created timing records.")


class TimingBatchAllItem(BaseModel):
    """A single timing item within a batch-all segment."""

    name: Optional[str] = Field(
        default=None,
        description="Speaker name (required for Table Topics, optional for other segments).",
    )
    planned_duration_minutes: int = Field(description="The planned duration in minutes.")
    actual_start_time: str = Field(description="ISO timestamp when timing started.")
    actual_end_time: str = Field(description="ISO timestamp when timing ended.")


class TimingBatchAllSegment(BaseModel):
    """A segment with its timing records for batch-all creation."""

    segment_id: str = Field(description="The ID of the segment.")
    timings: List[TimingBatchAllItem] = Field(description="List of timing records for this segment.")


class TimingBatchAllCreate(BaseModel):
    """Model for batch creating timing records across multiple segments."""

    segments: List[TimingBatchAllSegment] = Field(description="List of segments with their timing records.")


class TimingUpdate(BaseModel):
    """Model for updating an existing timing record."""

    name: Optional[str] = Field(
        default=None,
        description="Speaker name (optional, can be updated).",
    )
    planned_duration_minutes: Optional[int] = Field(
        default=None,
        description="The planned duration in minutes.",
    )
    actual_start_time: Optional[str] = Field(
        default=None,
        description="ISO timestamp when timing started.",
    )
    actual_end_time: Optional[str] = Field(
        default=None,
        description="ISO timestamp when timing ended.",
    )


class TimingDeleteResponse(BaseModel):
    """Response model for timing deletion."""

    success: bool = Field(description="Whether the deletion was successful.")
