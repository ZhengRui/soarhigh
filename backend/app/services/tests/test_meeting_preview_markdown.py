from app.agents.meeting.models import Segment
from app.services.meeting_preview_markdown import format_segment_detail_cell


def test_format_segment_detail_cell_escapes_text_and_resolves_related_dicts():
    segments_by_id = {
        "speech-1": {
            "id": "speech-1",
            "type": "Prepared Speech",
            "title": "",
            "content": "",
            "related_segment_ids": "",
        },
    }
    segment = {
        "id": "eval-1",
        "type": "Prepared Speech Evaluation",
        "title": "Evaluator | notes",
        "content": "Line one\nLine two",
        "related_segment_ids": "speech-1,missing",
    }

    assert (
        format_segment_detail_cell(segment, segments_by_id)
        == "Title: Evaluator \\| notes<br>Content: Line one<br>Line two<br>Related: Prepared Speech"
    )


def test_format_segment_detail_cell_accepts_segment_objects():
    speech = Segment(id="speech-1", type="Prepared Speech", start_time="20:00", duration=7)
    evaluation = Segment(
        id="eval-1",
        type="Prepared Speech Evaluation",
        start_time="20:10",
        duration=3,
        related_segment_ids="speech-1",
    )

    assert format_segment_detail_cell(evaluation, {"speech-1": speech}) == "Related: Prepared Speech"


def test_format_segment_detail_cell_returns_empty_string_when_details_empty_or_unresolved():
    segment = {"title": "", "content": "", "related_segment_ids": "missing"}

    assert format_segment_detail_cell(segment, {}) == ""
