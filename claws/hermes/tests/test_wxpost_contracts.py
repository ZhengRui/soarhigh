from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from wxpost_controller.contracts import (
    MANIFEST_SCHEMA_VERSION,
    SourceManifest,
    SourceUpdate,
    UpdateSourcesRequest,
)

FIXTURES = Path(__file__).parent / "fixtures"
WEB_IMAGE_ID = "M03"


@pytest.fixture
def manifest_data() -> dict[str, Any]:
    return json.loads((FIXTURES / "source-manifest-v2.json").read_text())


def test_source_manifest_v2_fixture_is_complete(
    manifest_data: dict[str, Any],
) -> None:
    manifest = SourceManifest.model_validate(manifest_data)

    assert manifest.schema_version == MANIFEST_SCHEMA_VERSION
    assert manifest.manifest_version == 1
    assert manifest.to_wire() == manifest_data
    assert {source.origin.type for source in manifest.sources} == {
        "meeting-library",
        "web-upload",
        "feishu-upload",
    }
    assert {
        (source.workspace_ready, source.included) for source in manifest.sources
    } == {
        (False, False),
        (True, False),
        (True, True),
    }


@pytest.mark.parametrize("invalid_version", [None, 1, True, 2.0, "2"])
def test_manifest_requires_strict_schema_version_2(
    manifest_data: dict[str, Any],
    invalid_version: object,
) -> None:
    if invalid_version is None:
        manifest_data.pop("schemaVersion")
    else:
        manifest_data["schemaVersion"] = invalid_version

    with pytest.raises(ValidationError):
        SourceManifest.model_validate(manifest_data)


def test_manifest_rejects_unknown_or_python_named_fields(
    manifest_data: dict[str, Any],
) -> None:
    manifest_data["schema_version"] = manifest_data.pop("schemaVersion")

    with pytest.raises(ValidationError):
        SourceManifest.model_validate(manifest_data)


@pytest.mark.parametrize(
    "source_id",
    ["1", "M1", "M00", "MC01", "m01", "M-01"],
)
def test_source_id_requires_persisted_material_number(
    manifest_data: dict[str, Any],
    source_id: str,
) -> None:
    manifest_data["sources"][1]["id"] = source_id

    with pytest.raises(ValidationError, match="id"):
        SourceManifest.model_validate(manifest_data)


def test_workspace_path_is_derived_instead_of_stored(
    manifest_data: dict[str, Any],
) -> None:
    manifest_data["sources"][1]["workspacePath"] = "sources/M02.jpg"

    with pytest.raises(ValidationError, match="workspacePath"):
        SourceManifest.model_validate(manifest_data)


def test_next_material_number_is_a_persisted_high_water_mark(
    manifest_data: dict[str, Any],
) -> None:
    manifest_data["nextMaterialNumber"] = 5
    with pytest.raises(ValidationError, match="nextMaterialNumber"):
        SourceManifest.model_validate(manifest_data)

    manifest_data["nextMaterialNumber"] = 6
    manifest_data["sources"].pop()
    SourceManifest.model_validate(manifest_data)


def test_draft_cannot_claim_a_future_manifest_snapshot(
    manifest_data: dict[str, Any],
) -> None:
    manifest_data["draft"] = {
        "version": 1,
        "sourceManifestVersion": 2,
        "sha256": "0" * 64,
    }

    with pytest.raises(ValidationError, match="sourceManifestVersion"):
        SourceManifest.model_validate(manifest_data)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda data: data["sources"][0].update(included=True),
            "workspace-ready",
        ),
        (
            lambda data: data["sources"][2].update(
                workspaceReady=False,
                included=False,
            ),
            "direct uploads",
        ),
        (
            lambda data: data.pop("meetingId"),
            "meetingId",
        ),
    ],
)
def test_manifest_rejects_contradictory_source_state(
    manifest_data: dict[str, Any],
    mutate,
    message: str,
) -> None:
    mutate(manifest_data)

    with pytest.raises(ValidationError, match=message):
        SourceManifest.model_validate(manifest_data)


@pytest.mark.parametrize(
    ("description", "source", "status"),
    [
        ("", "user", "missing"),
        ("   ", None, "missing"),
        ("Text without provenance.", None, "confirmed"),
        ("User text cannot await AI confirmation.", "user", "needs_confirmation"),
    ],
)
def test_description_provenance_rejects_contradictions(
    manifest_data: dict[str, Any],
    description: str,
    source: str | None,
    status: str,
) -> None:
    manifest_data["sources"][0].update(
        description=description,
        descriptionSource=source,
        descriptionStatus=status,
    )

    with pytest.raises(ValidationError):
        SourceManifest.model_validate(manifest_data)


def test_description_update_is_atomic() -> None:
    SourceUpdate.model_validate(
        {
            "sourceId": WEB_IMAGE_ID,
            "description": "Member-confirmed description.",
            "descriptionSource": "user",
            "descriptionStatus": "confirmed",
        }
    )

    with pytest.raises(ValidationError, match="must be updated together"):
        SourceUpdate.model_validate(
            {
                "sourceId": WEB_IMAGE_ID,
                "description": "Only one field",
            }
        )


def test_update_request_rejects_duplicate_source_ids() -> None:
    with pytest.raises(ValidationError, match="only once"):
        UpdateSourcesRequest.model_validate(
            {
                "expectedManifestVersion": 1,
                "updates": [
                    {"sourceId": WEB_IMAGE_ID, "included": False},
                    {"sourceId": WEB_IMAGE_ID, "included": True},
                ],
            }
        )
