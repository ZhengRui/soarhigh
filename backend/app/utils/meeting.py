import base64

from openai import OpenAI
from openai._exceptions import APIError, APITimeoutError, RateLimitError
from openai.lib._parsing._completions import type_to_response_format_param
from openai.types.chat import ChatCompletionMessageParam
from pydantic import ValidationError

from ..config import OPENAI_API_KEY
from ..db.core import get_members
from ..models.meeting import (
    Attendee,
    Meeting,
    MeetingParsedFromImage,
    MeetingPlannedFromText,
    Segment,
)
from .prompts import (
    parse_meeting_agenda_image_system_prompt,
    plan_meeting_from_text_developer_prompt,
    plan_meeting_from_text_user_prompt,
)

default_location = "华美居装饰家居城B区809 (1号线宝体站）"


def convert_parsed_meeting_to_meeting(parsed_meeting: MeetingParsedFromImage | MeetingPlannedFromText) -> Meeting:
    """
    Convert a MeetingParsedFromImage object into a Meeting object.
    Maps names to member IDs using the members database.
    """
    # Get all members
    members = get_members()

    def find_member_id(query_name: str) -> str:
        """Simple case-insensitive partial name matching"""
        if not query_name:
            return ""

        # Normalize query name
        query_name = query_name.lower().strip()

        # Check each member
        for member in members:
            if member.get("full_name"):
                member_name = member["full_name"].lower()
                # Match if query name is contained within member name
                if query_name in member_name:
                    return member["id"]

        return ""

    # Create Attendee object from manager string
    manager_attendee = Attendee(id=None, name=parsed_meeting.manager, member_id=find_member_id(parsed_meeting.manager))

    # Convert segments
    segments = []
    for i, parsed_segment in enumerate(parsed_meeting.segments):
        # Tell mypy that parsed_segment has a role_taker attribute
        parsed_segment_role_taker: str = getattr(parsed_segment, "role_taker", "")

        # Create Attendee from role_taker string
        role_taker_attendee = None
        if parsed_segment_role_taker:
            role_taker_attendee = Attendee(
                id=None, name=parsed_segment_role_taker, member_id=find_member_id(parsed_segment_role_taker)
            )

        # Create Segment with converted role_taker
        segment = Segment(
            id=getattr(parsed_segment, "id", str(i)),
            type=getattr(parsed_segment, "type", ""),
            start_time=getattr(parsed_segment, "start_time", ""),
            duration=getattr(parsed_segment, "duration", ""),
            end_time=getattr(parsed_segment, "end_time", ""),
            role_taker=role_taker_attendee,
            title=getattr(parsed_segment, "title", ""),
            content=getattr(parsed_segment, "content", ""),
            related_segment_ids=getattr(parsed_segment, "related_segment_ids", ""),
        )
        segments.append(segment)

    # Create and return the Meeting object
    return Meeting(
        id=None,
        no=parsed_meeting.no,
        type=parsed_meeting.type,
        theme=parsed_meeting.theme.title(),
        manager=manager_attendee,
        date=parsed_meeting.date,
        start_time=parsed_meeting.start_time,
        end_time=parsed_meeting.end_time,
        location=parsed_meeting.location or default_location,
        introduction=getattr(parsed_meeting, "introduction", ""),
        segments=segments,
        status="draft",  # Default status
        awards=[],  # Default empty awards list
    )


def parse_meeting_agenda_image(image_bytes: bytes, content_type: str) -> Meeting:
    client = OpenAI(api_key=OPENAI_API_KEY)

    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": [{"type": "text", "text": parse_meeting_agenda_image_system_prompt}]},
        {
            "role": "user",
            "content": [{"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{base64_image}"}}],
        },
    ]

    json_schema = type_to_response_format_param(MeetingParsedFromImage)

    # Retry configuration
    max_retries = 3
    retry_count = 0
    # base_delay = 2  # Initial backoff delay in seconds

    # Retriable exceptions
    retriable_exceptions = (APITimeoutError, RateLimitError, APIError)

    last_exception = None

    while retry_count < max_retries:
        try:
            # If this is a retry, add a short delay with exponential backoff
            if retry_count > 0:
                # delay = base_delay * (2 ** (retry_count - 1))  # Exponential backoff
                print(f"Retry {retry_count}/{max_retries}")
                # time.sleep(delay)

            reply = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                response_format=json_schema,
                temperature=0.01,
                timeout=60,
            )

            content = reply.choices[0].message.content
            if content is None:
                raise ValueError("OpenAI API returned no content")

            parsed_meeting = MeetingParsedFromImage.model_validate_json(content)

            # Convert the parsed meeting to a Meeting object
            meeting = convert_parsed_meeting_to_meeting(parsed_meeting)
            return meeting

        except retriable_exceptions as e:
            # These are retriable errors
            last_exception = e
            retry_count += 1
            print(f"API error occurred: {e!s}. Attempt {retry_count}/{max_retries}")
            if retry_count >= max_retries:
                # We've exhausted all retries
                break
        except ValidationError as e:
            # Don't retry validation errors (likely a problem with the response format)
            raise ValueError(f"Failed to parse OpenAI response into Meeting model: {e!s}")
        except Exception as e:
            # Don't retry unexpected errors
            raise ValueError(f"Unexpected error during meeting parsing: {e!s}")

    # If we've exhausted all retries
    if isinstance(last_exception, APITimeoutError):
        raise ValueError("OpenAI API request timed out after multiple retries")
    elif isinstance(last_exception, RateLimitError):
        raise ValueError("OpenAI API rate limit exceeded after multiple retries")
    elif isinstance(last_exception, APIError):
        raise ValueError(f"OpenAI API error after multiple retries: {last_exception!s}")
    else:
        raise ValueError("Failed to process meeting agenda image after multiple retries")


def plan_meeting_from_text(text: str) -> Meeting:
    """
    Plan a meeting from text using OpenAI's Responses API.

    Args:
        text: The input text containing meeting details.

    Returns:
        Meeting: A structured Meeting object.
    """
    client = OpenAI(api_key=OPENAI_API_KEY)

    # Format the user prompt with the input text
    formatted_user_prompt = plan_meeting_from_text_user_prompt.format(text=text)

    json_schema = type_to_response_format_param(MeetingPlannedFromText)

    # Retry configuration
    max_retries = 3
    retry_count = 0

    # Retriable exceptions
    retriable_exceptions = (APITimeoutError, RateLimitError, APIError)

    last_exception = None

    while retry_count < max_retries:
        try:
            # If this is a retry, add a message about the retry
            if retry_count > 0:
                print(f"Retry {retry_count}/{max_retries}")

            # Create a response using the Responses API
            response = client.responses.create(
                model="o3-mini",
                input=[
                    {"role": "system", "content": plan_meeting_from_text_developer_prompt},
                    {"role": "user", "content": formatted_user_prompt},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": json_schema["json_schema"]["name"],  # type: ignore
                        "schema": json_schema["json_schema"]["schema"],  # type: ignore
                    }
                },
                reasoning={"effort": "low"},
                store=True,
                timeout=60,
            )
            # Parse the JSON response into a MeetingPlannedFromText object
            parsed_meeting = MeetingPlannedFromText.model_validate_json(response.output_text)

            # Convert the parsed meeting to a Meeting object
            meeting = convert_parsed_meeting_to_meeting(parsed_meeting)
            return meeting

        except retriable_exceptions as e:
            # These are retriable errors
            last_exception = e
            retry_count += 1
            print(f"API error occurred: {e!s}. Attempt {retry_count}/{max_retries}")
            if retry_count >= max_retries:
                # We've exhausted all retries
                break
        except ValidationError as e:
            # Don't retry validation errors (likely a problem with the response format)
            raise ValueError(f"Failed to parse OpenAI response into Meeting model: {e!s}")
        except Exception as e:
            # Don't retry unexpected errors
            raise ValueError(f"Unexpected error during meeting planning: {e!s}")

    # If we've exhausted all retries
    if isinstance(last_exception, APITimeoutError):
        raise ValueError("OpenAI API request timed out after multiple retries")
    elif isinstance(last_exception, RateLimitError):
        raise ValueError("OpenAI API rate limit exceeded after multiple retries")
    elif isinstance(last_exception, APIError):
        raise ValueError(f"OpenAI API error after multiple retries: {last_exception!s}")
    else:
        raise ValueError("Failed to plan meeting from text after multiple retries")
