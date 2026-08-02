from app.models.wxpost import MediaKind
from app.services.wxpost_directives import DIRECTIVE_DEFINITIONS, DIRECTIVE_REGISTRY


def test_registry_is_ordered_unique_and_its_examples_match_the_payload_contracts() -> None:
    names = [definition.name for definition in DIRECTIVE_DEFINITIONS]

    assert names == list(DIRECTIVE_REGISTRY)
    assert len(names) == len(set(names))

    for definition in DIRECTIVE_DEFINITIONS:
        payload = definition.payload_model.model_validate(definition.example)
        capability = definition.capability()
        schema = capability.payload_schema

        assert payload.model_dump(mode="json", exclude_none=True) == definition.example
        assert capability.required_fields == schema.get("required", [])
        assert capability.optional_fields == [
            name for name in definition.payload_model.model_fields if name not in capability.required_fields
        ]
        assert schema["additionalProperties"] is False


def test_registry_preserves_the_published_payload_schema_names() -> None:
    expected_titles = {
        "section": "_SectionPayload",
        "image": "_ImagePayload",
        "gallery": "_GalleryPayload",
        "video": "_VideoPayload",
        "takeaway": "_TakeawayPayload",
        "person": "_PersonPayload",
        "info-grid": "_InfoGridPayload",
        "timeline": "_TimelinePayload",
        "pull-quote": "_PullQuotePayload",
    }

    schemas = {definition.name: definition.capability().payload_schema for definition in DIRECTIVE_DEFINITIONS}

    assert {name: schema["title"] for name, schema in schemas.items()} == expected_titles
    assert set(schemas["info-grid"]["$defs"]) == {"_InfoGridItem"}
    assert set(schemas["timeline"]["$defs"]) == {"_TimelineItem"}


def test_registry_owns_media_ids_kinds_and_payload_paths() -> None:
    references = {}
    for definition in DIRECTIVE_DEFINITIONS:
        payload = definition.payload_model.model_validate(definition.example)
        references[definition.name] = [
            (reference.media_id, reference.expected_kind, reference.payload_path)
            for reference in definition.media_references(payload)
        ]

    assert references == {
        "section": [],
        "image": [("M01", MediaKind.IMAGE, ("media",))],
        "gallery": [
            ("M01", MediaKind.IMAGE, ("items", 0)),
            ("M02", MediaKind.IMAGE, ("items", 1)),
        ],
        "video": [("V01", MediaKind.VIDEO, ("media",))],
        "takeaway": [],
        "person": [("M03", MediaKind.IMAGE, ("media",))],
        "info-grid": [],
        "timeline": [],
        "pull-quote": [],
    }
