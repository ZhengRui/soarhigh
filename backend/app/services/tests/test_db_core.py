from app.db import core


def test_assign_segment_ids_remaps_related_ids_on_create(monkeypatch):
    ids = iter(
        [
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "00000000-0000-0000-0000-000000000003",
        ]
    )
    monkeypatch.setattr(core.uuid, "uuid4", lambda: next(ids))
    segments = [
        {"id": "s1", "related_segment_ids": "s2,missing"},
        {"id": "s2", "related_segment_ids": "s1"},
        {"id": "client-temp", "related_segment_ids": ""},
    ]

    core._assign_segment_ids_and_remap_related_ids(segments)

    assert [s["id"] for s in segments] == [
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
        "00000000-0000-0000-0000-000000000003",
    ]
    assert segments[0]["related_segment_ids"] == "00000000-0000-0000-0000-000000000002"
    assert segments[1]["related_segment_ids"] == "00000000-0000-0000-0000-000000000001"
    assert segments[2]["related_segment_ids"] == ""


def test_assign_segment_ids_preserves_existing_ids_and_remaps_new_refs(monkeypatch):
    monkeypatch.setattr(core.uuid, "uuid4", lambda: "00000000-0000-0000-0000-000000000099")
    existing_id = "00000000-0000-0000-0000-000000000010"
    segments = [
        {"id": existing_id, "related_segment_ids": "s2"},
        {"id": "s2", "related_segment_ids": f"{existing_id},unknown"},
    ]

    core._assign_segment_ids_and_remap_related_ids(segments, {existing_id})

    assert segments[0]["id"] == existing_id
    assert segments[1]["id"] == "00000000-0000-0000-0000-000000000099"
    assert segments[0]["related_segment_ids"] == "00000000-0000-0000-0000-000000000099"
    assert segments[1]["related_segment_ids"] == existing_id
