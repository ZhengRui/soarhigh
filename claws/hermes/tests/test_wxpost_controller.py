from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Generator, Mapping
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[3]
HERMES_ROOT = REPO_ROOT / "claws" / "hermes"
BACKEND_ROOT = REPO_ROOT / "backend"
FIXTURES = Path(__file__).parent / "fixtures"
TOKEN = "contract-token"
GROUP_PHOTO_ID = "M01"
SPEAKER_ID = "M02"
WEB_IMAGE_ID = "M03"
FEISHU_VIDEO_ID = "M04"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from wxpost_controller.core import (  # noqa: E402
    InvalidRequest,
    InvalidWorkspace,
    ValidationUnavailable,
    VersionConflict,
    WorkspaceController,
)
from wxpost_controller.http_server import build_server  # noqa: E402

from app.models.wxpost import ArticleDocument  # noqa: E402
from app.services.wxpost_document import (  # noqa: E402
    ArticleDocumentValidationError,
    pydantic_validation_issues,
    validate_and_parse,
)


def _manifest_fixture() -> dict[str, Any]:
    return json.loads((FIXTURES / "source-manifest-v4.json").read_text())


def _seed_workspace(root: Path, workspace_id: str) -> None:
    workspace = root / "inbox" / workspace_id
    workspace.mkdir(parents=True)
    manifest = _manifest_fixture()
    manifest["workspaceId"] = workspace_id
    for index, source in enumerate(manifest["sources"], start=1):
        if not source["workspaceReady"]:
            continue
        path = (
            workspace / "sources" / f"{source['id']}{Path(source['filename']).suffix}"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes([index]) * source["sizeBytes"])
    (workspace / "source-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _article_document(*, title: str = "One Shared Workspace") -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "title": title,
        "articleType": "meeting-recap",
        "sourceMeetingId": "1cf40bec-f94d-45f4-b5df-18e3a9bffac8",
        "bodyMarkdown": "The meeting began with a warm welcome.",
        "media": [
            {
                "id": "M03",
                "kind": "image",
                "sourceUrl": "https://soarhigh.example/M03.jpg",
                "description": "Members welcome guests before the meeting.",
                "include": True,
                "order": 2,
                "descriptionSource": "user",
                "descriptionStatus": "confirmed",
            }
        ],
        "presentation": {
            "layout": "brand-default",
            "palette": "paper-neutral",
            "appearance": "light",
            "typeface": "editorial-serif",
        },
    }


def _backend_validate(document: Mapping[str, Any]) -> dict[str, Any]:
    parsed = ArticleDocument.model_validate(document)
    validate_and_parse(parsed)
    return parsed.model_dump(by_alias=True, mode="json")


def _canonical_document(document: Mapping[str, Any]) -> dict[str, Any]:
    return ArticleDocument.model_validate(document).model_dump(
        by_alias=True,
        mode="json",
    )


def _controller(root: Path) -> WorkspaceController:
    return WorkspaceController(root, article_validator=_backend_validate)


@pytest.fixture
def seeded_workspace(tmp_path: Path) -> tuple[Path, str]:
    workspace_id = "wxpost-contract-workspace"
    _seed_workspace(tmp_path, workspace_id)
    return tmp_path, workspace_id


class _ValidationHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/posts/wxposts/validate":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length", "0"))
        document = json.loads(self.rfile.read(length))
        try:
            parsed = ArticleDocument.model_validate(document)
            validate_and_parse(parsed)
        except ValidationError as exc:
            errors = [
                issue.model_dump(by_alias=True, mode="json")
                for issue in pydantic_validation_issues(exc)
            ]
            self._send(
                HTTPStatus.UNPROCESSABLE_ENTITY, {"valid": False, "errors": errors}
            )
        except ArticleDocumentValidationError as exc:
            errors = [
                issue.model_dump(by_alias=True, mode="json") for issue in exc.errors
            ]
            self._send(
                HTTPStatus.UNPROCESSABLE_ENTITY, {"valid": False, "errors": errors}
            )
        else:
            self._send(
                HTTPStatus.OK,
                {
                    "valid": True,
                    "document": parsed.model_dump(by_alias=True, mode="json"),
                },
            )

    def _send(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


@pytest.fixture
def validation_url() -> Generator[str, None, None]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ValidationHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    token: str = TOKEN,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload).encode()
    request_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    request_headers.update(headers or {})
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers=request_headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _upload_request(
    url: str,
    *,
    filename: str,
    expected_manifest_version: int,
    data: bytes,
    mime_type: str,
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        f"{url}?{urllib.parse.urlencode({'filename': filename})}",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": mime_type,
            "X-Expected-Manifest-Version": str(expected_manifest_version),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _mcp_value(result) -> dict[str, Any]:
    assert not result.isError
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(result.content[0].text)


def test_http_workspace_delete_requires_the_current_manifest_version(
    tmp_path: Path,
) -> None:
    server = build_server(
        workspace_root=str(tmp_path),
        bearer_token=TOKEN,
        host="127.0.0.1",
        port=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/workspaces/delete-versioned"
    try:
        status, created = _json_request(
            url,
            method="PUT",
            payload={
                "meetingId": None,
                "editorial": {
                    "articleType": "meeting-recap",
                    "customArticleType": None,
                    "voiceTone": {"presets": [], "customProfiles": []},
                },
                "createdBy": {"id": "member-123", "name": "Test Member"},
            },
        )
        assert status == 200

        status, missing = _json_request(url, method="DELETE")
        assert status == HTTPStatus.UNPROCESSABLE_ENTITY
        assert missing["error"]["code"] == "invalid_request"

        status, stale = _json_request(
            url,
            method="DELETE",
            headers={"X-Expected-Manifest-Version": "2"},
        )
        assert status == HTTPStatus.CONFLICT
        assert stale["error"]["code"] == "version_conflict"

        status, deleted = _json_request(
            url,
            method="DELETE",
            headers={
                "X-Expected-Manifest-Version": str(
                    created["manifest"]["manifestVersion"]
                )
            },
        )
        assert status == 200
        assert deleted["deleted"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _mcp_parameters(root: Path, validation_url: str) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "wxpost_controller.mcp_server"],
        cwd=str(root),
        env={
            **os.environ,
            "PYTHONPATH": str(HERMES_ROOT),
            "WXPOST_WORKSPACE_ROOT": str(root),
            "SOARHIGH_API_BASE_URL": validation_url,
        },
    )


def test_manifest_and_draft_versions_advance_independently(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)

    context = controller.get_context(workspace_id)
    assert context["manifest"]["schemaVersion"] == 4
    assert context["manifest"]["manifestVersion"] == 1
    assert context["manifest"]["draft"] is None
    assert context["draft"] is None

    unchanged = controller.update_sources(
        workspace_id,
        expected_manifest_version=1,
        updates=[{"sourceId": WEB_IMAGE_ID, "included": True}],
    )
    assert unchanged["manifestVersion"] == 1

    manifest = controller.update_sources(
        workspace_id,
        expected_manifest_version=1,
        updates=[
            {
                "sourceId": FEISHU_VIDEO_ID,
                "description": "A confirmed Table Topics highlight.",
                "descriptionSource": "user",
                "descriptionStatus": "confirmed",
            }
        ],
    )
    assert manifest["manifestVersion"] == 2

    draft = controller.save_draft(
        workspace_id,
        expected_manifest_version=2,
        expected_draft_version=0,
        document=_article_document(),
    )
    assert draft["draftVersion"] == 1

    manifest = controller.update_sources(
        workspace_id,
        expected_manifest_version=2,
        updates=[{"sourceId": FEISHU_VIDEO_ID, "included": True}],
    )
    context = controller.get_context(workspace_id)
    assert manifest["manifestVersion"] == 3
    assert context["draft"]["draftVersion"] == 1
    assert context["draft"]["document"] == draft["document"]


def test_article_json_is_the_raw_backend_normalized_document(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    document = _article_document()
    document["title"] = "  Normalized title  "
    document["media"][0]["description"] = (
        "An editorial description derived from the confirmed source fact."
    )
    document["media"][0]["include"] = 1
    document["media"][0]["order"] = "2"

    saved = _controller(root).save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=document,
    )

    workspace = root / "inbox" / workspace_id
    stored = json.loads((workspace / "draft" / "article.json").read_text())
    manifest = json.loads((workspace / "source-manifest.json").read_text())
    assert saved["document"] == stored
    assert stored == _canonical_document(document)
    assert stored["title"] == "Normalized title"
    assert stored["media"][0]["include"] is True
    assert stored["media"][0]["order"] == 2
    assert "draftVersion" not in stored
    assert "document" not in stored
    assert manifest["draft"]["version"] == 1
    assert manifest["draft"]["sourceManifestVersion"] == 1


def test_authoritative_backend_validation_rejects_invalid_draft(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    document = _article_document()
    document.pop("presentation")

    with pytest.raises(InvalidRequest, match="presentation"):
        _controller(root).save_draft(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=0,
            document=document,
        )

    workspace = root / "inbox" / workspace_id
    assert not (workspace / "draft" / "article.json").exists()
    assert json.loads((workspace / "source-manifest.json").read_text())["draft"] is None


def test_remote_validator_is_required_when_no_test_validator_is_injected(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace

    with pytest.raises(ValidationUnavailable, match="SOARHIGH_API_BASE_URL"):
        WorkspaceController(root, soarhigh_api_base_url="").save_draft(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=0,
            document=_article_document(),
        )


def test_source_reorder_is_stored_in_canonical_array_order(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace

    manifest = _controller(root).update_sources(
        workspace_id,
        expected_manifest_version=1,
        updates=[{"sourceId": SPEAKER_ID, "moveToIndex": 0}],
    )

    assert [source["id"] for source in manifest["sources"][:2]] == [
        SPEAKER_ID,
        GROUP_PHOTO_ID,
    ]
    assert all("order" not in source for source in manifest["sources"])


def test_invalid_source_transition_is_rejected_without_data_loss(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)

    with pytest.raises(InvalidRequest, match="workspace-ready"):
        controller.update_sources(
            workspace_id,
            expected_manifest_version=1,
            updates=[{"sourceId": GROUP_PHOTO_ID, "included": True}],
        )

    context = controller.get_context(workspace_id)
    assert context["manifest"]["manifestVersion"] == 1
    assert context["manifest"]["sources"][0]["included"] is False


def test_stale_manifest_and_draft_writes_report_correct_versions(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    controller.update_sources(
        workspace_id,
        expected_manifest_version=1,
        updates=[
            {
                "sourceId": FEISHU_VIDEO_ID,
                "description": "Confirmed Table Topics highlight.",
                "descriptionSource": "user",
                "descriptionStatus": "confirmed",
            }
        ],
    )

    with pytest.raises(VersionConflict) as manifest_conflict:
        controller.update_sources(
            workspace_id,
            expected_manifest_version=1,
            updates=[{"sourceId": FEISHU_VIDEO_ID, "included": True}],
        )
    assert manifest_conflict.value.resource == "manifest"
    assert manifest_conflict.value.actual == 2

    with pytest.raises(VersionConflict) as draft_manifest_conflict:
        controller.save_draft(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=0,
            document=_article_document(),
        )
    assert draft_manifest_conflict.value.resource == "manifest"
    assert draft_manifest_conflict.value.actual == 2

    controller.save_draft(
        workspace_id,
        expected_manifest_version=2,
        expected_draft_version=0,
        document=_article_document(),
    )
    with pytest.raises(VersionConflict) as draft_conflict:
        controller.save_draft(
            workspace_id,
            expected_manifest_version=2,
            expected_draft_version=0,
            document=_article_document(title="Stale writer"),
        )
    assert draft_conflict.value.resource == "draft"
    assert draft_conflict.value.actual == 1


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "M99", "not in the source manifest"),
        ("kind", "video", "kind does not match"),
        ("include", False, "include"),
        ("order", 0, "order"),
        ("descriptionSource", "ai", "descriptionSource"),
        (
            "descriptionStatus",
            "needs_confirmation",
            "descriptionStatus",
        ),
    ],
)
def test_draft_media_must_match_the_manifest_snapshot(
    seeded_workspace: tuple[Path, str],
    field: str,
    value: object,
    message: str,
) -> None:
    root, workspace_id = seeded_workspace
    document = _article_document()
    document["media"][0][field] = value

    with pytest.raises(InvalidRequest, match=message):
        _controller(root).save_draft(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=0,
            document=document,
        )


def test_draft_contains_every_included_manifest_media_source(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    document = _article_document()
    document["media"] = []

    with pytest.raises(InvalidRequest, match="missing included manifest sources: M03"):
        _controller(root).save_draft(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=0,
            document=document,
        )


def test_concurrent_manifest_updates_serialize_and_one_conflicts(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def update(source_id: str, included: bool) -> None:
        barrier.wait()
        try:
            _controller(root).update_sources(
                workspace_id,
                expected_manifest_version=1,
                updates=[{"sourceId": source_id, "included": included}],
            )
        except VersionConflict:
            outcomes.append("conflict")
        else:
            outcomes.append("updated")

    threads = [
        threading.Thread(target=update, args=(WEB_IMAGE_ID, False)),
        threading.Thread(target=update, args=(FEISHU_VIDEO_ID, True)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert sorted(outcomes) == ["conflict", "updated"]


@pytest.mark.parametrize("failure", ["missing", "size", "symlink", "sources-symlink"])
def test_workspace_ready_requires_the_real_declared_file(
    seeded_workspace: tuple[Path, str],
    tmp_path: Path,
    failure: str,
) -> None:
    root, workspace_id = seeded_workspace
    workspace = root / "inbox" / workspace_id
    source = _manifest_fixture()["sources"][2]
    path = workspace / "sources" / f"{source['id']}{Path(source['filename']).suffix}"
    if failure == "missing":
        path.unlink()
    elif failure == "size":
        path.write_bytes(b"wrong")
    elif failure == "symlink":
        target = tmp_path / "outside.jpg"
        target.write_bytes(b"x" * source["sizeBytes"])
        path.unlink()
        path.symlink_to(target)
    else:
        source_dir = path.parent
        target_dir = workspace / "real-sources"
        source_dir.rename(target_dir)
        source_dir.symlink_to(target_dir, target_is_directory=True)

    with pytest.raises(InvalidWorkspace, match="source"):
        _controller(root).get_context(workspace_id)


def test_draft_hash_detects_out_of_band_changes(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    path = root / "inbox" / workspace_id / "draft" / "article.json"
    changed = json.loads(path.read_text())
    changed["title"] = "Changed outside the controller"
    path.write_text(json.dumps(changed))

    with pytest.raises(InvalidWorkspace, match="manifest hash"):
        controller.get_context(workspace_id)


def test_interrupted_first_draft_save_is_rolled_back_on_next_read(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    draft_dir = root / "inbox" / workspace_id / "draft"
    draft_dir.mkdir()
    pending = draft_dir / ".article-save-pending.json"
    pending.write_text(json.dumps({"previousDocument": None}))
    (draft_dir / "article.json").write_text(
        json.dumps(_canonical_document(_article_document()))
    )

    context = _controller(root).get_context(workspace_id)

    assert context["draft"] is None
    assert not (draft_dir / "article.json").exists()
    assert not pending.exists()


def test_interrupted_draft_overwrite_restores_the_manifest_version(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    saved = controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    draft_dir = root / "inbox" / workspace_id / "draft"
    pending = draft_dir / ".article-save-pending.json"
    pending.write_text(json.dumps({"previousDocument": saved["document"]}))
    interrupted = _canonical_document(
        _article_document(title="Interrupted replacement")
    )
    (draft_dir / "article.json").write_text(json.dumps(interrupted))

    context = _controller(root).get_context(workspace_id)

    assert context["draft"] == saved
    assert json.loads((draft_dir / "article.json").read_text()) == saved["document"]
    assert not pending.exists()


def test_completed_draft_save_discards_a_stale_pending_record(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    saved = _controller(root).save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    pending = root / "inbox" / workspace_id / "draft" / ".article-save-pending.json"
    pending.write_text(json.dumps({"previousDocument": None}))

    context = _controller(root).get_context(workspace_id)

    assert context["draft"] == saved
    assert not pending.exists()


@pytest.mark.parametrize("manifest_replaced", [False, True])
def test_manifest_write_failure_keeps_disk_state_self_consistent(
    seeded_workspace: tuple[Path, str],
    monkeypatch: pytest.MonkeyPatch,
    manifest_replaced: bool,
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    original_write = controller._atomic_write_json

    def fail_manifest_write(path: Path, value: Mapping[str, Any]) -> None:
        if path.name == "source-manifest.json":
            if manifest_replaced:
                original_write(path, value)
            raise InvalidWorkspace("simulated manifest fsync failure")
        original_write(path, value)

    monkeypatch.setattr(controller, "_atomic_write_json", fail_manifest_write)

    with pytest.raises(InvalidWorkspace, match="simulated"):
        controller.save_draft(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=0,
            document=_article_document(),
        )

    context = _controller(root).get_context(workspace_id)
    if manifest_replaced:
        assert context["draft"]["draftVersion"] == 1
    else:
        assert context["draft"] is None
    assert not (
        root / "inbox" / workspace_id / "draft" / ".article-save-pending.json"
    ).exists()


def test_v1_manifest_is_rejected_without_runtime_compatibility(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    path = root / "inbox" / workspace_id / "source-manifest.json"
    manifest = json.loads(path.read_text())
    manifest["schemaVersion"] = 1
    path.write_text(json.dumps(manifest))

    with pytest.raises(InvalidWorkspace, match="source-manifest v4"):
        _controller(root).get_context(workspace_id)


def test_workspace_identifier_and_symlink_escape_are_rejected(
    seeded_workspace: tuple[Path, str],
    tmp_path: Path,
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    with pytest.raises(InvalidRequest):
        controller.get_context("../outside")

    outside = tmp_path / "outside"
    outside.mkdir()
    symlink = root / "inbox" / "linked-workspace"
    symlink.symlink_to(outside, target_is_directory=True)
    with pytest.raises(InvalidWorkspace):
        controller.get_context("linked-workspace")


def test_materials_update_preserves_a_saved_draft(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    saved = controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    assert saved["draftVersion"] == 1

    current = controller.get_context(workspace_id)
    editorial = {
        **current["manifest"]["editorial"],
        "articleType": "member-story",
    }
    updated = controller.update_workspace(
        workspace_id,
        expected_manifest_version=current["manifest"]["manifestVersion"],
        meeting_id=current["manifest"]["meetingId"],
        editorial=editorial,
        source_updates=[
            {
                "sourceId": WEB_IMAGE_ID,
                "included": False,
                "description": "Updated source fact.",
                "descriptionSource": "user",
                "descriptionStatus": "confirmed",
            }
        ],
    )

    assert updated["workspaceId"] == workspace_id
    assert updated["manifest"]["manifestVersion"] == 2
    assert updated["manifest"]["editorial"]["articleType"] == "member-story"
    updated_source = next(
        source
        for source in updated["manifest"]["sources"]
        if source["id"] == WEB_IMAGE_ID
    )
    assert updated_source["included"] is False
    assert updated_source["description"] == "Updated source fact."
    assert updated["manifest"]["draft"] == current["manifest"]["draft"]
    assert updated["draft"] == saved
    raw = json.loads(
        (root / "inbox" / workspace_id / "draft" / "article.json").read_text()
    )
    assert raw == _canonical_document(_article_document())


def test_meeting_source_change_invalidates_a_saved_draft(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    current = controller.get_context(workspace_id)

    updated = controller.update_workspace(
        workspace_id,
        expected_manifest_version=current["manifest"]["manifestVersion"],
        meeting_id=None,
        editorial=current["manifest"]["editorial"],
    )

    assert updated["manifest"]["manifestVersion"] == 2
    assert updated["manifest"]["meetingId"] is None
    assert updated["manifest"]["draft"] is None
    assert updated["draft"] is None
    assert not (root / "inbox" / workspace_id / "draft" / "article.json").exists()
    assert all(
        source["origin"]["type"] != "meeting-library"
        for source in updated["manifest"]["sources"]
    )


@pytest.mark.asyncio
async def test_http_and_mcp_share_auth_contract_state_and_raw_draft(
    seeded_workspace: tuple[Path, str],
    validation_url: str,
) -> None:
    root, workspace_id = seeded_workspace
    server = build_server(
        workspace_root=str(root),
        bearer_token=TOKEN,
        host="127.0.0.1",
        port=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        unauthorized, _ = _json_request(
            f"{base_url}/workspaces/{workspace_id}/context",
            token="wrong",
        )
        assert unauthorized == 401

        status, listing = _json_request(
            f"{base_url}/workspaces?page=1&page_size=1",
        )
        assert status == 200
        assert listing["page"] == 1
        assert listing["page_size"] == 1
        assert listing["total"] == 1
        assert listing["pages"] == 1
        assert [item["workspaceId"] for item in listing["items"]] == [workspace_id]

        status, invalid_pagination = _json_request(
            f"{base_url}/workspaces?page=one",
        )
        assert status == 422
        assert invalid_pagination["error"]["code"] == "invalid_request"

        status, invalid = _json_request(
            f"{base_url}/workspaces/{workspace_id}/sources",
            method="PATCH",
            payload={
                "expectedManifestVersion": 1,
                "updates": [{"sourceId": WEB_IMAGE_ID, "included": False}],
                "unexpected": True,
            },
        )
        assert status == 422
        assert invalid["error"]["code"] == "invalid_request"

        status, http_manifest = _json_request(
            f"{base_url}/workspaces/{workspace_id}/sources",
            method="PATCH",
            payload={
                "expectedManifestVersion": 1,
                "updates": [
                    {
                        "sourceId": WEB_IMAGE_ID,
                        "description": "Updated confirmed source fact.",
                        "descriptionSource": "user",
                        "descriptionStatus": "confirmed",
                    }
                ],
            },
        )
        assert status == 200

        async with stdio_client(_mcp_parameters(root, validation_url)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                context = _mcp_value(
                    await session.call_tool(
                        "wxpost_get_context",
                        {"workspace_id": workspace_id},
                    )
                )
                assert context["manifest"] == http_manifest

                saved = _mcp_value(
                    await session.call_tool(
                        "wxpost_save_draft",
                        {
                            "workspace_id": workspace_id,
                            "expected_manifest_version": 2,
                            "expected_draft_version": 0,
                            "document": _article_document(),
                        },
                    )
                )
                assert saved["draftVersion"] == 1

        persisted = _controller(root).get_context(workspace_id)
        assert persisted["manifest"]["manifestVersion"] == 2
        assert persisted["draft"] == saved
        raw = json.loads(
            (root / "inbox" / workspace_id / "draft" / "article.json").read_text()
        )
        assert raw == _canonical_document(_article_document())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_http_and_mcp_share_the_complete_material_operation_state(
    tmp_path: Path,
    validation_url: str,
) -> None:
    workspace_id = "transport-materials"
    server = build_server(
        workspace_root=str(tmp_path),
        bearer_token=TOKEN,
        host="127.0.0.1",
        port=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        status, created = _json_request(
            f"{base_url}/workspaces/{workspace_id}",
            method="PUT",
            payload={
                "meetingId": None,
                "editorial": {
                    "articleType": "meeting-recap",
                    "customArticleType": None,
                    "voiceTone": {"presets": [], "customProfiles": []},
                },
                "createdBy": {
                    "id": "member-123",
                    "name": "Test Member",
                },
            },
        )
        assert status == 200
        assert created["manifest"]["manifestVersion"] == 1
        assert created["manifest"]["sources"] == []

        status, uploaded = _upload_request(
            f"{base_url}/workspaces/{workspace_id}/uploads",
            filename="网页照片.jpg",
            expected_manifest_version=1,
            data=b"web-photo",
            mime_type="image/jpeg",
        )
        assert status == 200
        assert uploaded["sources"][0]["id"] == "M01"
        assert uploaded["sources"][0]["origin"] == {"type": "web-upload"}

        request = urllib.request.Request(
            f"{base_url}/workspaces/{workspace_id}/sources/M01/content",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 200
            assert response.headers["Content-Type"] == "image/jpeg"
            assert response.headers["Cache-Control"] == "private, no-store"
            assert response.read() == b"web-photo"

        status, saved = _json_request(
            f"{base_url}/workspaces/{workspace_id}",
            method="PATCH",
            payload={
                "expectedManifestVersion": uploaded["manifestVersion"],
                "meetingId": None,
                "editorial": created["manifest"]["editorial"],
                "sourceUpdates": [
                    {
                        "sourceId": "M01",
                        "included": False,
                        "description": "Saved through the real HTTP route.",
                        "descriptionSource": "user",
                        "descriptionStatus": "confirmed",
                    }
                ],
            },
        )
        assert status == 200
        assert saved["manifest"]["manifestVersion"] == 3
        assert saved["manifest"]["sources"][0] == {
            **uploaded["sources"][0],
            "description": "Saved through the real HTTP route.",
            "descriptionSource": "user",
            "descriptionStatus": "confirmed",
        }
        status, conflict = _json_request(
            f"{base_url}/workspaces/{workspace_id}",
            method="PATCH",
            payload={
                "expectedManifestVersion": uploaded["manifestVersion"],
                "meetingId": None,
                "editorial": created["manifest"]["editorial"],
                "sourceUpdates": [],
            },
        )
        assert status == 409
        assert conflict["error"]["code"] == "version_conflict"

        incoming = tmp_path / "incoming"
        incoming.mkdir()
        clip_path = incoming / "clip.mp4"
        clip_path.write_bytes(b"feishu-video")

        async with stdio_client(_mcp_parameters(tmp_path, validation_url)) as (
            read,
            write,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {tool.name for tool in (await session.list_tools()).tools}
                assert {
                    "wxpost_bootstrap_workspace",
                    "wxpost_update_workspace",
                    "wxpost_import_source",
                    "wxpost_set_source_included",
                    "wxpost_upload_source",
                    "wxpost_delete_source_preflight",
                    "wxpost_delete_source",
                }.issubset(tools)

                mcp_uploaded = _mcp_value(
                    await session.call_tool(
                        "wxpost_upload_source",
                        {
                            "workspace_id": workspace_id,
                            "expected_manifest_version": 3,
                            "source_path": str(clip_path),
                        },
                    )
                )
                assert mcp_uploaded["manifestVersion"] == 4
                assert mcp_uploaded["sources"][1]["id"] == "M02"
                assert mcp_uploaded["sources"][1]["origin"] == {"type": "feishu-upload"}

                status, http_conflict = _json_request(
                    f"{base_url}/workspaces/{workspace_id}/sources/M01/inclusion",
                    method="PUT",
                    payload={
                        "expectedManifestVersion": 1,
                        "included": True,
                    },
                )
                assert status == 409
                mcp_conflict = await session.call_tool(
                    "wxpost_set_source_included",
                    {
                        "workspace_id": workspace_id,
                        "expected_manifest_version": 1,
                        "source_id": "M01",
                        "included": True,
                    },
                )
                assert mcp_conflict.isError
                mcp_error_text = mcp_conflict.content[0].text
                assert (
                    json.loads(mcp_error_text[mcp_error_text.index("{") :])
                    == http_conflict
                )
                assert http_conflict["error"] == {
                    "code": "version_conflict",
                    "message": (
                        "expected manifest version 1, current manifest version is 4"
                    ),
                    "versionKind": "manifest",
                    "expectedVersion": 1,
                    "actualVersion": 4,
                }

                status, included = _json_request(
                    f"{base_url}/workspaces/{workspace_id}/sources/M01/inclusion",
                    method="PUT",
                    payload={
                        "expectedManifestVersion": 4,
                        "included": True,
                    },
                )
                assert status == 200
                assert included["manifestVersion"] == 5
                assert included["sources"][0]["included"] is True

                status, preflight = _json_request(
                    f"{base_url}/workspaces/{workspace_id}/sources/M02/delete-preflight",
                    headers={"X-Expected-Manifest-Version": "5"},
                )
                assert status == 200
                assert preflight["referenced"] is False
                assert preflight["manifestVersion"] == 5

                deleted = _mcp_value(
                    await session.call_tool(
                        "wxpost_delete_source",
                        {
                            "workspace_id": workspace_id,
                            "expected_manifest_version": 5,
                            "source_id": "M02",
                        },
                    )
                )
                assert deleted["manifestVersion"] == 6
                assert [source["id"] for source in deleted["sources"]] == ["M01"]

        status, final_context = _json_request(
            f"{base_url}/workspaces/{workspace_id}/context"
        )
        assert status == 200
        assert final_context["manifest"] == deleted
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
