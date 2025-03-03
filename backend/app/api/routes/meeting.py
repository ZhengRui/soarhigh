from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from ...db.core import (
    create_meeting,
    delete_meeting,
    get_meeting_by_id,
    get_meetings,
    update_meeting,
    update_meeting_status,
)
from ...models.meeting import Meeting
from ...models.users import User
from ...utils.meeting import parse_meeting_agenda_image
from .auth import get_current_user, get_optional_user, verify_access_token

http_scheme = HTTPBearer()

meeting_router = r = APIRouter()


# Add this new model for status updates
class MeetingStatusUpdate(BaseModel):
    status: str


@r.post("/meeting/parse_agenda_image")
async def r_parse_meeting_agenda_image(
    image: UploadFile = File(...), user: User = Depends(get_current_user)
) -> Meeting:
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload an image.")

    content_type = image.content_type or "image/jpeg"
    try:
        image_bytes = await image.read()
        meeting = parse_meeting_agenda_image(image_bytes, content_type)
        return meeting
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="An unexpected error occurred while processing the image")


@r.post("/meetings", response_model=Meeting)
async def r_create_meeting(meeting_data: Meeting, user: User = Depends(get_current_user)) -> Meeting:
    """
    Create a new meeting.

    This endpoint creates a new meeting with the provided data.
    By default, new meetings are created with 'draft' status.
    Only authenticated users can create meetings.
    """
    try:
        # Convert the meeting model to a dictionary
        meeting_dict = meeting_data.dict(exclude={"id"})  # Exclude id for creation

        # Create the meeting in the database
        meeting_db = create_meeting(meeting_dict)

        return Meeting(**meeting_db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e!s}")


@r.get("/meetings", response_model=List[Meeting])
async def r_list_meetings(
    user: Optional[User] = Depends(get_optional_user),
    status: Optional[str] = Query(None, description="Filter by status (draft or published)"),
) -> List[Meeting]:
    """
    Get a list of meetings.

    For authenticated users, returns all meetings (both draft and published).
    For unauthenticated users, returns only published meetings.
    Optional status parameter can filter results by status.
    """
    try:
        # Get user ID (None for unauthenticated users)
        user_id = user.uid if user else None

        # Get meetings from database
        meetings_db = get_meetings(user_id, status)

        # Convert database results to response models
        meetings_response = []

        for meeting in meetings_db:
            meetings_response.append(Meeting(**meeting))

        return meetings_response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e!s}")


@r.get("/meetings/{meeting_id}", response_model=Meeting)
async def r_get_meeting(
    meeting_id: str = Path(..., description="The ID of the meeting to retrieve"),
    user: Optional[User] = Depends(get_optional_user),
) -> Meeting:
    """
    Get a specific meeting by ID.

    For authenticated users, returns any meeting.
    For unauthenticated users, returns only published meetings.
    """
    try:
        # Get user ID (None for unauthenticated users)
        user_id = user.uid if user else None

        # Get meeting from database
        meeting_db = get_meeting_by_id(meeting_id, user_id)

        if not meeting_db:
            raise HTTPException(status_code=404, detail="Meeting not found")

        return Meeting(**meeting_db)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e!s}")


@r.put("/meetings/{meeting_id}", response_model=Meeting)
async def r_update_meeting(
    meeting_data: Meeting,
    meeting_id: str = Path(..., description="The ID of the meeting to update"),
    user: User = Depends(get_current_user),
) -> Meeting:
    """
    Update an existing meeting.

    This endpoint updates an existing meeting with the provided data.
    Only authenticated users can update meetings.
    """
    try:
        # Convert the meeting model to a dictionary and exclude id (we'll use the path parameter)
        meeting_dict = meeting_data.dict(exclude={"id"})

        # Update the meeting in the database
        meeting_db = update_meeting(meeting_id, meeting_dict, user.uid)

        if not meeting_db:
            raise HTTPException(status_code=404, detail="Meeting not found")

        return Meeting(**meeting_db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e!s}")


@r.put("/meetings/{meeting_id}/status", response_model=Meeting)
async def r_update_meeting_status(
    meeting_status: MeetingStatusUpdate,
    meeting_id: str = Path(..., description="The ID of the meeting to update"),
    user: User = Depends(get_current_user),
) -> Meeting:
    """
    Update the status of a meeting (draft/published).

    This endpoint updates the status of an existing meeting.
    Only authenticated users can update meeting status.
    """
    try:
        # Get the status from the request body
        status = meeting_status.status

        # Check if status is valid
        if status not in ["draft", "published"]:
            raise HTTPException(status_code=400, detail="Invalid status. Must be 'draft' or 'published'")

        # Update the meeting status in the database
        meeting_db = update_meeting_status(meeting_id, status, user.uid)

        if not meeting_db:
            raise HTTPException(status_code=404, detail="Meeting not found")

        return Meeting(**meeting_db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e!s}")


@r.delete("/meetings/{meeting_id}")
async def r_delete_meeting(
    meeting_id: str = Path(..., description="The ID of the meeting to delete"),
    credentials: HTTPAuthorizationCredentials = Depends(http_scheme),
):
    """
    Delete a meeting.

    This endpoint deletes a meeting and all its associated segments.
    Only authenticated users can delete meetings.
    The Row Level Security policies will ensure that only the meeting manager
    or admin users can delete a meeting.
    """
    try:
        user_token = credentials.credentials
        payload = verify_access_token(user_token)

        # Delete the meeting from the database
        success = delete_meeting(meeting_id, payload["sub"], user_token)

        if not success:
            raise HTTPException(status_code=404, detail="Meeting not found or you don't have permission to delete it")

        return {"success": True, "message": "Meeting deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e!s}")
