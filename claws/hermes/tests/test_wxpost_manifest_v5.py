from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from wxpost_controller.contracts import SourceKind, SourceManifest
from wxpost_controller.core import InvalidRequest, WorkspaceController
from wxpost_controller.migrate_manifest_v5 import (
    MigrationError,
    apply_all,
    prepare_all,
)
from wxpost_controller.source_metadata import (
    InvalidSourceImage,
    inspect_source_bytes,
)

FIXTURE = Path(__file__).parent / "fixtures" / "source-manifest-v5.json"


def _image_bytes(*, orientation: int | None = None) -> bytes:
    output = BytesIO()
    image = Image.new("RGB", (3, 2), "#336699")
    exif = Image.Exif()
    if orientation is not None:
        exif[274] = orientation
    image.save(output, format="JPEG", exif=exif)
    return output.getvalue()


def _seed_v4(root: Path, workspace_id: str, *, corrupt_image: bool = False) -> Path:
    workspace = root / "inbox" / workspace_id
    sources_root = workspace / "sources"
    sources_root.mkdir(parents=True)
    manifest = json.loads(FIXTURE.read_text())
    manifest["schemaVersion"] = 4
    manifest["workspaceId"] = workspace_id
    source_bytes = {
        "M02": b"not-an-image" if corrupt_image else _image_bytes(),
        "M03": _image_bytes(orientation=6),
        "M04": b"video-bytes",
        "M05": b"transcript-bytes",
    }
    for source in manifest["sources"]:
        source.pop("contentSha256", None)
        source.pop("dimensions", None)
        data = source_bytes.get(source["id"])
        if data is None:
            continue
        source["sizeBytes"] = len(data)
        path = sources_root / f"{source['id']}{Path(source['filename']).suffix}"
        path.write_bytes(data)
    path = workspace / "source-manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return path


def test_source_metadata_uses_exif_display_orientation() -> None:
    metadata = inspect_source_bytes(_image_bytes(orientation=6), kind=SourceKind.IMAGE)

    assert metadata.dimensions == {"width": 2, "height": 3}
    assert len(metadata.content_sha256) == 64


def test_source_metadata_rejects_corrupt_declared_image() -> None:
    with pytest.raises(InvalidSourceImage):
        inspect_source_bytes(b"not-an-image", kind=SourceKind.IMAGE)


def test_upload_rejects_corrupt_images_atomically_and_reads_exact_version(
    tmp_path: Path,
) -> None:
    controller = WorkspaceController(tmp_path)
    created = controller.create_workspace(
        meeting_id=None,
        editorial={
            "articleType": "meeting-recap",
            "customArticleType": None,
            "voiceTone": {"presets": [], "customProfiles": []},
        },
        created_by={"id": "member-123", "name": "Test Member"},
    )
    workspace_id = created["workspaceId"]

    with pytest.raises(InvalidRequest, match="valid supported image"):
        controller.upload_source(
            workspace_id,
            expected_manifest_version=1,
            origin="web-upload",
            filename="broken.jpg",
            mime_type="image/jpeg",
            data=b"not-an-image",
        )
    unchanged = controller.get_context(workspace_id)["manifest"]
    assert unchanged["manifestVersion"] == 1
    assert unchanged["sources"] == []

    data = _image_bytes()
    manifest = controller.upload_source(
        workspace_id,
        expected_manifest_version=1,
        origin="web-upload",
        filename="valid.jpg",
        mime_type="image/jpeg",
        data=data,
    )
    content_sha256 = manifest["sources"][0]["contentSha256"]
    assert controller.read_source(
        workspace_id,
        source_id="M01",
        content_sha256=content_sha256,
    ) == (data, "image/jpeg", content_sha256)
    with pytest.raises(InvalidRequest, match="content version"):
        controller.read_source(
            workspace_id,
            source_id="M01",
            content_sha256="0" * 64,
        )


def test_manifest_v4_migration_is_validated_backed_up_and_atomic(
    tmp_path: Path,
) -> None:
    path = _seed_v4(tmp_path, "wxpost-valid")
    original = path.read_bytes()
    prepared = prepare_all(tmp_path)

    assert len(prepared) == 1
    assert prepared[0].migrated is not None
    assert path.read_bytes() == original

    backup_root = tmp_path / "backups"
    assert apply_all(tmp_path, prepared, backup_root) == 1
    migrated = json.loads(path.read_text())
    manifest = SourceManifest.model_validate(migrated)
    assert manifest.schema_version == 5
    assert manifest.manifest_version == 1
    assert manifest.sources[2].dimensions.to_wire() == {"width": 2, "height": 3}
    assert (
        backup_root / "inbox" / "wxpost-valid" / "source-manifest.json"
    ).read_bytes() == original

    assert prepare_all(tmp_path)[0].migrated is None


def test_manifest_migration_validates_every_workspace_before_writing(
    tmp_path: Path,
) -> None:
    valid_path = _seed_v4(tmp_path, "wxpost-a-valid")
    invalid_path = _seed_v4(
        tmp_path,
        "wxpost-z-invalid",
        corrupt_image=True,
    )
    valid_before = valid_path.read_bytes()
    invalid_before = invalid_path.read_bytes()

    with pytest.raises(MigrationError, match="cannot inspect"):
        prepare_all(tmp_path)

    assert valid_path.read_bytes() == valid_before
    assert invalid_path.read_bytes() == invalid_before


@pytest.mark.parametrize(
    ("unsafe_source", "message"),
    [
        ("missing", "source file is unavailable"),
        ("symlink", "source path escapes workspace"),
    ],
)
def test_manifest_migration_rejects_unavailable_source_files(
    tmp_path: Path,
    unsafe_source: str,
    message: str,
) -> None:
    path = _seed_v4(tmp_path, "wxpost-unsafe")
    original = path.read_bytes()
    source_path = path.parent / "sources" / "M02.jpg"
    source_path.unlink()
    if unsafe_source == "symlink":
        outside = tmp_path / "outside.jpg"
        outside.write_bytes(_image_bytes())
        source_path.symlink_to(outside)

    with pytest.raises(MigrationError, match=message):
        prepare_all(tmp_path)

    assert path.read_bytes() == original
