import json
from pathlib import Path

import pytest

from app.models.wxpost import ArticleDocument, MediaAsset, WxPostDraftEditRequest
from app.services.wxpost_document import ArticleDocumentValidationError, validate_and_parse
from app.services.wxpost_editing import apply_draft_edits

FIXTURE = Path(__file__).parents[2] / "api/routes/tests/fixtures/wxpost-meeting-recap-v1.json"


def _document() -> ArticleDocument:
    return ArticleDocument.model_validate(json.loads(FIXTURE.read_text()))


def _available_cover() -> MediaAsset:
    return MediaAsset.model_validate(
        {
            "id": "M08",
            "kind": "image",
            "sourceUrl": "https://workspace.invalid/example/materials/M08",
            "description": "Members share an easy laugh after the meeting.",
            "include": True,
            "order": 0,
            "descriptionSource": "user",
            "descriptionStatus": "confirmed",
        }
    )


def _edit(document: ArticleDocument, *edits: dict) -> ArticleDocument:
    return apply_draft_edits(
        WxPostDraftEditRequest.model_validate(
            {
                "document": document.model_dump(by_alias=True, mode="json"),
                "availableMedia": [
                    *[item.model_dump(by_alias=True, mode="json") for item in document.media],
                    _available_cover().model_dump(by_alias=True, mode="json"),
                ],
                "edits": list(edits),
            }
        )
    )


def _directive_index(document: ArticleDocument, name: str) -> int:
    return next(
        index
        for index, node in enumerate(validate_and_parse(document).body)
        if node.kind == "directive" and node.name == name
    )


def test_edit_replaces_only_requested_metadata_and_directive_field() -> None:
    document = _document()
    index = _directive_index(document, "takeaway")

    edited = _edit(
        document,
        {"type": "replaceMetadata", "field": "title", "value": "One More Try"},
        {
            "type": "replaceDirectiveField",
            "nodeIndex": index,
            "path": ["title"],
            "value": "Try this tomorrow",
        },
    )

    assert edited.title == "One More Try"
    assert "title: A small practice for this week" not in edited.body_markdown
    assert '"title": "Try this tomorrow"' in edited.body_markdown
    assert edited.media == document.media
    assert edited.cover_media_id == document.cover_media_id


def test_cover_can_use_imported_image_without_body_or_materials_membership() -> None:
    document = _document()

    edited = _edit(document, {"type": "setCover", "sourceId": "M08"})

    assert edited.cover_media_id == "M08"
    assert "M08" not in edited.body_markdown
    assert [item.id for item in edited.media][-1] == "M08"
    assert all(item.include for item in edited.media)

    cleared = _edit(edited, {"type": "clearCover"})
    assert cleared.cover_media_id is None
    assert "M08" not in {item.id for item in cleared.media}


def test_clear_cover_keeps_media_that_remains_in_body() -> None:
    document = _document()

    edited = _edit(document, {"type": "clearCover"})

    assert edited.cover_media_id is None
    assert "M01" in {item.id for item in edited.media}


def test_insert_and_remove_body_image_do_not_change_cover() -> None:
    document = _document()
    inserted = _edit(
        document,
        {
            "type": "insertImage",
            "sourceId": "M08",
            "bodyIndex": 1,
            "caption": "A warm moment after the meeting",
        },
    )
    assert inserted.cover_media_id == "M01"
    assert '"media": "M08"' in inserted.body_markdown
    assert "M08" in {item.id for item in inserted.media}

    removed = _edit(
        inserted,
        {"type": "removeMediaFromBody", "sourceId": "M08"},
    )
    assert removed.cover_media_id == "M01"
    assert "M08" not in removed.body_markdown
    assert "M08" not in {item.id for item in removed.media}


def test_delete_gallery_occurrence_keeps_other_images_and_reorders_dependencies() -> None:
    document = _document()
    index = _directive_index(document, "gallery")

    edited = _edit(
        document,
        {
            "type": "deleteMediaOccurrence",
            "nodeIndex": index,
            "sourceId": "M02",
        },
    )

    assert "M02" not in edited.body_markdown
    assert "M02" not in {item.id for item in edited.media}
    assert "M01" in edited.body_markdown
    assert "M03" in edited.body_markdown


def test_overlapping_body_edits_are_rejected_atomically() -> None:
    document = _document()
    index = _directive_index(document, "takeaway")

    with pytest.raises(ArticleDocumentValidationError, match="validation failed"):
        _edit(
            document,
            {"type": "deleteBodyNode", "nodeIndex": index},
            {
                "type": "replaceDirectiveField",
                "nodeIndex": index,
                "path": ["title"],
                "value": "Conflicting edit",
            },
        )


def test_body_nodes_can_be_replaced_inserted_and_deleted_by_index() -> None:
    document = _document()
    first = validate_and_parse(document).body[0]
    assert first.kind == "markdown"

    replaced = _edit(
        document,
        {
            "type": "replaceBodyNode",
            "nodeIndex": 0,
            "node": {"kind": "markdown", "source": "A quieter opening."},
        },
    )
    assert replaced.body_markdown.startswith("A quieter opening.")

    inserted = _edit(
        replaced,
        {
            "type": "insertBodyNode",
            "bodyIndex": 1,
            "node": {
                "kind": "directive",
                "name": "pull-quote",
                "payload": {"text": "A precise second beat."},
            },
        },
    )
    inserted_body = validate_and_parse(inserted).body
    assert inserted_body[1].kind == "directive"
    assert inserted_body[1].payload["text"] == "A precise second beat."

    deleted = _edit(inserted, {"type": "deleteBodyNode", "nodeIndex": 1})
    assert "A precise second beat." not in deleted.body_markdown


def test_required_directive_text_rejects_empty_replacement_and_uses_item_delete() -> None:
    document = _document()
    index = _directive_index(document, "info-grid")

    with pytest.raises(ArticleDocumentValidationError, match="validation failed"):
        _edit(
            document,
            {
                "type": "replaceDirectiveField",
                "nodeIndex": index,
                "path": ["items", 0, "value"],
                "value": "",
            },
        )

    edited = _edit(
        document,
        {"type": "deleteDirectiveItem", "nodeIndex": index, "itemIndex": 0},
    )
    info_grid = next(
        node for node in validate_and_parse(edited).body if node.kind == "directive" and node.name == "info-grid"
    )
    assert len(info_grid.payload["items"]) == 2


def test_media_description_edit_is_dependency_bound() -> None:
    document = _document()
    edited = _edit(
        document,
        {
            "type": "replaceMediaDescription",
            "sourceId": "M01",
            "value": "A warm room pauses around one shared story.",
        },
    )
    media = next(item for item in edited.media if item.id == "M01")
    assert media.description == "A warm room pauses around one shared story."
    assert media.description_source.value == "ai"
    assert media.description_status.value == "needs_confirmation"

    with pytest.raises(ArticleDocumentValidationError, match="validation failed"):
        _edit(
            document,
            {
                "type": "replaceMediaDescription",
                "sourceId": "M08",
                "value": "This unused image has no Draft dependency.",
            },
        )


def test_removing_person_media_keeps_the_person_content() -> None:
    document = _document()
    index = _directive_index(document, "person")

    edited = _edit(
        document,
        {
            "type": "deleteMediaOccurrence",
            "nodeIndex": index,
            "sourceId": "M04",
        },
    )

    person = next(
        node for node in validate_and_parse(edited).body if node.kind == "directive" and node.name == "person"
    )
    assert "media" not in person.payload
    assert "M04" not in {item.id for item in edited.media}


def test_unknown_cover_media_is_rejected() -> None:
    with pytest.raises(ArticleDocumentValidationError, match="validation failed"):
        _edit(_document(), {"type": "setCover", "sourceId": "M99"})
