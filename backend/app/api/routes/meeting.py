from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ...db.core import create_meeting
from ...models.meeting import Meeting, MeetingCreate, MeetingResponse
from ...models.users import User
from ...utils.meeting import parse_meeting_agenda_image
from .auth import get_current_user

meeting_router = r = APIRouter()


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


@r.post("/meetings", response_model=MeetingResponse)
async def create_new_meeting(meeting_data: MeetingCreate, user: User = Depends(get_current_user)) -> MeetingResponse:
    """
    Create a new meeting.

    This endpoint creates a new meeting with the provided data.
    By default, new meetings are created with 'draft' status.
    Only authenticated users can create meetings.
    """
    try:
        # Convert the meeting model to a dictionary
        meeting_dict = meeting_data.dict()

        # Create the meeting in the database
        meeting_db = create_meeting(meeting_dict, user.uid)

        # Convert database meeting to response model
        # We need to inject the segments data back into the response
        segments = meeting_dict.get("segments", [])
        meeting_db["segments"] = segments

        # Convert type to meeting_type for consistency with our models
        meeting_db["meeting_type"] = meeting_db.pop("type", "")

        return MeetingResponse(**meeting_db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e!s}")
