from fastapi import APIRouter, File, HTTPException, UploadFile

from ...models.meeting import Meeting
from ...utils.meeting import parse_meeting_agenda_image

meeting_router = r = APIRouter()


@r.post("/meeting/parse_agenda_image")
async def r_parse_meeting_agenda_image(image: UploadFile = File(...)) -> Meeting:
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
