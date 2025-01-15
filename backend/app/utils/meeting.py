import base64

from openai import OpenAI
from openai._exceptions import APIError, APITimeoutError
from openai.lib._parsing._completions import type_to_response_format_param
from openai.types.chat import ChatCompletionMessageParam
from pydantic import ValidationError

from ..config import OPENAI_API_KEY
from ..models.meeting import Meeting
from .prompts import parse_meeting_agenda_image_system_prompt


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

    json_schema = type_to_response_format_param(Meeting)

    try:
        reply = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            response_format=json_schema,
            temperature=0.01,
            timeout=30,
        )

        content = reply.choices[0].message.content
        if content is None:
            raise ValueError("OpenAI API returned no content")

        meeting = Meeting.model_validate_json(content)
        return meeting

    except APITimeoutError:
        raise ValueError("OpenAI API request timed out")
    except APIError as e:
        raise ValueError(f"OpenAI API error: {e!s}")
    except ValidationError as e:
        raise ValueError(f"Failed to parse OpenAI response into Meeting model: {e!s}")
    except Exception as e:
        raise ValueError(f"Unexpected error during meeting parsing: {e!s}")
