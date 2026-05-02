import base64
from typing import get_args

from openai import OpenAI
from openai._exceptions import APIError, APITimeoutError, RateLimitError
from openai.lib._parsing._completions import type_to_response_format_param
from openai.types.chat import ChatCompletionMessageParam
from pydantic import ValidationError

from ..config import (
    DEEPSEEK_API_KEY,
    MEETING_TEXT_PLANNER_MODEL,
    MEETING_TEXT_PLANNER_REASONING_EFFORT,
    OPENAI_API_KEY,
)
from ..db.core import get_members
from ..models.meeting import (
    Attendee,
    Meeting,
    MeetingParsedFromImage,
    MeetingPlannedFromText,
    MeetingPlannedFromTextLoose,
    Segment,
    defaultSegmentTypes,
)
from .prompts import (
    parse_meeting_agenda_image_system_prompt,
    plan_meeting_from_text_developer_prompt,
    plan_meeting_from_text_user_prompt,
)

default_location = "华美居装饰家居城B区809 (1号线宝体站)"

_DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"


def _supports_reasoning(model: str) -> bool:
    model_id = model.split(":", 1)[-1].lower()
    return model_id.startswith(("o1", "o3", "o4", "gpt-5"))


def _text_planner_reasoning(model: str) -> dict[str, str] | None:
    if not _supports_reasoning(model):
        return None
    return {"effort": MEETING_TEXT_PLANNER_REASONING_EFFORT}


def _is_deepseek_model(model: str) -> bool:
    return model.split(":", 1)[-1].lower().startswith("deepseek-")


# 26 canonical segment-type strings the OpenAI strict path is forced to
# produce. Computed once from the Literal so it stays in lockstep with
# the schema; the frozenset is the membership oracle for "is this an
# already-canonical name?" before we attempt alias normalization.
_CANONICAL_SEGMENT_TYPES: frozenset[str] = frozenset(get_args(defaultSegmentTypes))

# Lowercase shorthand → canonical mapping. Used only by the DeepSeek
# path (json_object mode has no enum enforcement, so DeepSeek tends to
# emit user-style shorthand like "SAA" / "PS1" / "Warm Up" instead of
# the schema's exact strings). Names not in this map AND not already
# canonical are left unchanged — `defaultSegmentTypes` includes
# "Custom segment", and the downstream `Segment.type` is plain `str`,
# so genuinely user-defined names round-trip without normalization.
_SEGMENT_TYPE_ALIASES: dict[str, str] = {
    "saa": "Meeting Rules Introduction (SAA)",
    "meeting rules introduction": "Meeting Rules Introduction (SAA)",
    "opening remarks": "Opening Remarks (President)",
    "tom": "TOM (Toastmaster of Meeting) Introduction",
    "toastmaster of meeting": "TOM (Toastmaster of Meeting) Introduction",
    "ttm": "TTM (Table Topic Master) Opening",
    "table topic master opening": "TTM (Table Topic Master) Opening",
    "table topics": "Table Topic Session",
    "tte": "Table Topic Evaluation",
    "ie": "Prepared Speech Evaluation",
    "ie1": "Prepared Speech Evaluation",
    "ie2": "Prepared Speech Evaluation",
    "ie3": "Prepared Speech Evaluation",
    "ie4": "Prepared Speech Evaluation",
    "pse": "Prepared Speech Evaluation",
    "ge": "General Evaluation",
    "mot": "Moment of Truth",
    "ps": "Prepared Speech",
    "ps1": "Prepared Speech",
    "ps2": "Prepared Speech",
    "ps3": "Prepared Speech",
    "ps4": "Prepared Speech",
    "prepared speech 1": "Prepared Speech",
    "prepared speech 2": "Prepared Speech",
    "prepared speech 3": "Prepared Speech",
    "prepared speech 4": "Prepared Speech",
    "guest intro": "Guests Self Introduction (30s per guest)",
    "guests intro": "Guests Self Introduction (30s per guest)",
    "guests introduction": "Guests Self Introduction (30s per guest)",
    "guests self introduction": "Guests Self Introduction (30s per guest)",
    "voting": "Voting Section (TOM)",
    "voting section": "Voting Section (TOM)",
    "awards": "Awards (President)",
    "closing remarks": "Closing Remarks (President)",
    "warm up": "Members and Guests Registration, Warm up",
    "warmup": "Members and Guests Registration, Warm up",
    "members registration": "Members and Guests Registration, Warm up",
    "guests registration": "Members and Guests Registration, Warm up",
    "members and guests registration": "Members and Guests Registration, Warm up",
    # prompts.py uses capital "Warm Up" by mistake — DeepSeek follows
    # the prompt and emits the wrong case; map back to canonical.
    "members and guests registration, warm up": "Members and Guests Registration, Warm up",
    "tea break": "Tea Break & Group Photos",
    "group photos": "Tea Break & Group Photos",
    "timer report": "Timer's Report",
    "grammarian report": "Grammarian's Report",
    "aha counter report": "Aha Counter's Report",
    "hark master pop quiz": "Hark Master Pop Quiz Time",
}


def _normalize_segment_type(raw: str) -> str:
    """Map a raw segment-type string from a non-strict provider back to
    a canonical `defaultSegmentTypes` value when possible. If `raw` is
    already canonical → return it unchanged. If it matches a known
    shorthand (case-insensitive) → return the canonical. Otherwise →
    return `raw` (treated as a legitimate user-defined custom segment).
    """
    if raw in _CANONICAL_SEGMENT_TYPES:
        return raw
    return _SEGMENT_TYPE_ALIASES.get(raw.strip().lower(), raw)


def convert_parsed_meeting_to_meeting(
    parsed_meeting: MeetingParsedFromImage | MeetingPlannedFromText | MeetingPlannedFromTextLoose,
) -> Meeting:
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
    Plan a meeting from text. Dispatches by model: DeepSeek models go
    through their OpenAI-compatible Chat Completions endpoint;
    everything else (the default OpenAI o-series path) uses the
    Responses API as before.

    Args:
        text: The input text containing meeting details.

    Returns:
        Meeting: A structured Meeting object.
    """
    if _is_deepseek_model(MEETING_TEXT_PLANNER_MODEL):
        return _plan_meeting_from_text_via_deepseek(text)

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

            response_kwargs = {
                "model": MEETING_TEXT_PLANNER_MODEL,
                "input": [
                    {"role": "system", "content": plan_meeting_from_text_developer_prompt},
                    {"role": "user", "content": formatted_user_prompt},
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": json_schema["json_schema"]["name"],  # type: ignore
                        "schema": json_schema["json_schema"]["schema"],  # type: ignore
                    }
                },
                "store": True,
                "timeout": 60,
            }
            reasoning = _text_planner_reasoning(MEETING_TEXT_PLANNER_MODEL)
            if reasoning is not None:
                response_kwargs["reasoning"] = reasoning

            # Create a response using the Responses API
            response = client.responses.create(**response_kwargs)  # type: ignore[call-overload]
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


def _plan_meeting_from_text_via_deepseek(text: str) -> Meeting:
    """DeepSeek path for `plan_meeting_from_text`. Uses Chat Completions
    (DeepSeek's OpenAI-compatible endpoint has no Responses API). Kept
    parallel to the OpenAI path rather than unified because OpenAI's
    o-series rejects `response_format=json_schema` on Chat Completions —
    the two providers truly need different call shapes.
    """
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=_DEEPSEEK_BASE_URL)

    formatted_user_prompt = plan_meeting_from_text_user_prompt.format(text=text)

    # DeepSeek's OpenAI-compatible endpoint only supports the
    # json_object response_format (per their docs); the strict
    # json_schema variant 400s with the same OpenAI-style error string
    # OpenAI returns for o-series. Schema conformance relies on the two
    # complete JSON examples in the developer prompt — if drift becomes
    # a real problem in practice, add ValidationError to the retriable
    # set below.
    response_format = {"type": "json_object"}

    max_retries = 3
    retry_count = 0
    retriable_exceptions = (APITimeoutError, RateLimitError, APIError)
    last_exception: Exception | None = None

    # Strip any `provider:` prefix — `_is_deepseek_model` accepts both
    # `deepseek-chat` and `deepseek:deepseek-chat`, but the DeepSeek
    # endpoint only knows the bare ID.
    deepseek_model = MEETING_TEXT_PLANNER_MODEL.split(":", 1)[-1]

    while retry_count < max_retries:
        try:
            if retry_count > 0:
                print(f"Retry {retry_count}/{max_retries}")

            response = client.chat.completions.create(  # type: ignore[call-overload]
                model=deepseek_model,
                messages=[
                    {"role": "system", "content": plan_meeting_from_text_developer_prompt},
                    {"role": "user", "content": formatted_user_prompt},
                ],
                response_format=response_format,
                timeout=60,
            )
            content = response.choices[0].message.content
            if not content:
                # DeepSeek's JSON Output guide notes occasional empty
                # responses; treat as transient and retry.
                last_exception = ValueError("DeepSeek returned empty content")
                retry_count += 1
                print(f"Empty response from DeepSeek. Attempt {retry_count}/{max_retries}")
                if retry_count >= max_retries:
                    break
                continue

            # Validate against the loose model (no enum on segment.type)
            # because json_object mode can't enforce the canonical 26.
            # Then map known shorthands back to canonical; anything left
            # over is treated as a user-defined custom segment and
            # round-trips unchanged into the persisted Meeting.
            parsed_meeting = MeetingPlannedFromTextLoose.model_validate_json(content)
            for segment in parsed_meeting.segments:
                segment.type = _normalize_segment_type(segment.type)
            return convert_parsed_meeting_to_meeting(parsed_meeting)

        except retriable_exceptions as e:
            last_exception = e
            retry_count += 1
            print(f"API error occurred: {e!s}. Attempt {retry_count}/{max_retries}")
            if retry_count >= max_retries:
                break
        except ValidationError as e:
            raise ValueError(f"Failed to parse DeepSeek response into Meeting model: {e!s}")
        except Exception as e:
            raise ValueError(f"Unexpected error during meeting planning: {e!s}")

    if isinstance(last_exception, APITimeoutError):
        raise ValueError("DeepSeek API request timed out after multiple retries")
    elif isinstance(last_exception, RateLimitError):
        raise ValueError("DeepSeek API rate limit exceeded after multiple retries")
    elif isinstance(last_exception, APIError):
        raise ValueError(f"DeepSeek API error after multiple retries: {last_exception!s}")
    elif isinstance(last_exception, ValueError):
        raise ValueError(f"DeepSeek planner failed after multiple retries: {last_exception!s}")
    else:
        raise ValueError("Failed to plan meeting from text after multiple retries")
