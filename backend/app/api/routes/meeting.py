from typing import Dict, List, Optional, Union

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from ...db.core import (
    cast_votes,
    create_meeting,
    delete_meeting,
    get_awards_by_meeting,
    get_meeting_by_id,
    get_meetings,
    get_votes_by_meeting,
    get_votes_status,
    save_meeting_awards,
    save_vote_form,
    update_meeting,
    update_meeting_status,
    update_votes_status,
)
from ...models.meeting import Award, Meeting, PaginatedMeetings, Vote, VotesStatus
from ...models.users import User
from ...utils.meeting import parse_meeting_agenda_image
from .auth import get_current_user, get_optional_user, verify_access_token

http_scheme = HTTPBearer()

meeting_router = r = APIRouter()


# Add this new model for status updates
class MeetingStatusUpdate(BaseModel):
    status: str


class AwardsList(BaseModel):
    awards: List[Award]


class Candidate(BaseModel):
    name: str
    segment: str
    count: Optional[int] = 0


class CategoryCandidatesList(BaseModel):
    category: str
    candidates: List[Candidate]


class VoteForm(BaseModel):
    votes: List[CategoryCandidatesList]


class VoteCastRecord(BaseModel):
    category: str
    name: str


class VoteCast(BaseModel):
    votes: List[VoteCastRecord]


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


@r.get("/meetings", response_model=PaginatedMeetings)
async def r_list_meetings(
    user: Optional[User] = Depends(get_optional_user),
    status: Optional[str] = Query(None, description="Filter by status (draft or published)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=50, description="Items per page"),
) -> PaginatedMeetings:
    """
    List meetings with pagination.

    This endpoint returns all published meetings for anonymous users,
    and both draft and published meetings for authenticated users.
    Results can be filtered by status and are paginated.
    """
    try:
        meetings_db = get_meetings(user_id=user.uid if user else None, status=status, page=page, page_size=page_size)
        return PaginatedMeetings(**meetings_db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


@r.get("/meetings/{meeting_id}/awards", response_model=List[Award])
async def r_get_meeting_awards(
    meeting_id: str = Path(..., description="The ID of the meeting to get awards for"),
    user: Optional[User] = Depends(get_optional_user),
) -> List[Award]:
    """
    Get all awards for a specific meeting.

    This endpoint returns all awards associated with a specific meeting.
    Authentication is optional - public meetings are viewable by anyone.
    """
    try:
        # First check if the meeting exists and is accessible
        meeting = get_meeting_by_id(meeting_id, user.uid if user else None)
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")

        # Get all awards for the meeting
        awards = get_awards_by_meeting(meeting_id)
        return [Award(**award) for award in awards]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e!s}")


@r.post("/meetings/{meeting_id}/awards", response_model=List[Award])
async def r_save_meeting_awards(
    awards_data: AwardsList,
    meeting_id: str = Path(..., description="The ID of the meeting to save awards for"),
    user: User = Depends(get_current_user),
) -> List[Award]:
    """
    Replace all awards for a meeting.

    This endpoint replaces all existing awards for a meeting with the provided ones.
    It first deletes all existing awards and then creates new ones.
    Only authenticated users can modify awards.
    """
    try:
        # Process the awards data
        awards = [award.dict(exclude={"id"}) for award in awards_data.awards]

        # Save the awards
        saved_awards = save_meeting_awards(meeting_id, awards, user.uid)

        # Return the saved awards
        return [Award(**award) for award in saved_awards]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e!s}")


@r.get("/meetings/{meeting_id}/votes", response_model=Union[List[Vote], List[CategoryCandidatesList]])
async def r_get_meeting_votes(
    meeting_id: str = Path(..., description="The ID of the meeting to get votes for"),
    user: Optional[User] = Depends(get_optional_user),
):
    """
    Get all votes for a meeting.

    This endpoint retrieves all votes for a specific meeting.
    Anyone can access this endpoint, but the response format differs based on authentication:
    - Authenticated users: Full vote data or form-structured data based on as_form parameter
    - Non-authenticated users: Only category and candidate information (no counts)
    """
    try:
        votes = get_votes_by_meeting(meeting_id)

        # Group votes by category and extract candidates
        categories_dict: Dict[str, List[Candidate]] = {}
        for vote in votes:
            if vote["category"] not in categories_dict:
                categories_dict[vote["category"]] = []
            if vote["name"] not in categories_dict[vote["category"]]:
                categories_dict[vote["category"]].append(
                    Candidate(
                        name=vote["name"],
                        segment=vote["segment"],
                        count=vote["count"] if user else 0,
                    )
                )

        # Convert to CategoryCandidatesList format
        result = [
            CategoryCandidatesList(category=category, candidates=candidates)
            for category, candidates in categories_dict.items()
        ]
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e!s}")


@r.get("/meetings/{meeting_id}/votes/status", response_model=VotesStatus)
async def r_get_votes_status(
    meeting_id: str = Path(..., description="The ID of the meeting to get votes status for"),
) -> VotesStatus:
    """
    Get the voting status for a meeting.

    This endpoint retrieves the voting status for a specific meeting.
    Anyone can access this endpoint.
    """
    try:
        status = get_votes_status(meeting_id)
        if not status:
            # Return a default status object if none exists
            return VotesStatus(id=None, meeting_id=meeting_id, open=False)
        return VotesStatus(**status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e!s}")


@r.put("/meetings/{meeting_id}/votes/status", response_model=VotesStatus)
async def r_update_votes_status(
    status_update: Dict[str, bool],
    meeting_id: str = Path(..., description="The ID of the meeting to update votes status for"),
    user: User = Depends(get_current_user),
) -> VotesStatus:
    """
    Update the voting status for a meeting.

    This endpoint updates the voting status for a specific meeting.
    Only authenticated users can update voting status.
    Request body: {"open": true/false}
    When opening voting, the meeting must have vote options defined.
    """
    try:
        if "open" not in status_update:
            raise ValueError("Request must include 'open' field")

        # If trying to open voting, check if meeting has vote form data
        if status_update["open"]:
            votes = get_votes_by_meeting(meeting_id)
            if not votes:
                raise ValueError("Cannot open voting: No vote options defined. Please set up the vote form first.")

        status = update_votes_status(meeting_id, status_update["open"], user.uid)
        if not status:
            raise HTTPException(status_code=404, detail="Meeting not found or not accessible")
        return VotesStatus(**status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e!s}")


@r.post("/meetings/{meeting_id}/votes/form", response_model=List[CategoryCandidatesList])
async def r_save_vote_form(
    vote_form: VoteForm,
    meeting_id: str = Path(..., description="The ID of the meeting to save vote form for"),
    user: User = Depends(get_current_user),
) -> List[CategoryCandidatesList]:
    """
    Save the vote form configuration for a meeting.

    This endpoint saves the vote form configuration for a specific meeting.
    Only authenticated users can save vote forms.
    """
    try:
        # Convert the Pydantic model to a list of dictionaries
        votes_list = [
            {"category": category["category"], "candidates": category["candidates"]}
            for category in vote_form.dict()["votes"]
        ]

        votes = save_vote_form(meeting_id, votes_list, user.uid)
        return [CategoryCandidatesList(**vote) for vote in votes]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e!s}")


@r.post("/meetings/{meeting_id}/vote", response_model=List[Vote])
async def r_cast_vote(
    vote_data: VoteCast,
    meeting_id: str = Path(..., description="The ID of the meeting to cast votes for"),
) -> List[Vote]:
    """
    Cast multiple votes for candidates across different categories.

    This endpoint casts votes for specific candidates in various categories.
    Anyone can cast votes, but voting must be open.
    """
    try:
        # Convert the Pydantic model to a list of dictionaries
        votes_list = [{"category": v.category, "name": v.name} for v in vote_data.votes]

        results = cast_votes(meeting_id, votes_list)
        if not results:
            raise HTTPException(status_code=400, detail="Voting is closed or none of the vote records exist")
        return [Vote(**vote) for vote in results]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e!s}")
