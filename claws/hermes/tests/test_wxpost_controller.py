from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from wxpost_controller.core import (
    InvalidWorkspace,
    VersionConflict,
    WorkspaceController,
)
from wxpost_controller.http_server import build_server

HERMES_ROOT = Path(__file__).resolve().parents[1]
TOKEN = "probe-token"


def _seed_workspace(root: Path, workspace_id: str) -> None:
    workspace = root / "inbox" / workspace_id
    workspace.mkdir(parents=True)
    manifest = {
        "schemaVersion": 1,
        "workspaceId": workspace_id,
        "version": 1,
        "sources": [
            {
                "id": "M01",
                "kind": "image",
                "included": False,
                "description": "",
                "order": 0,
            },
            {
                "id": "M02",
                "kind": "image",
                "included": False,
                "description": "",
                "order": 1,
            },
        ],
        "editorial": {
            "articleType": "meeting-recap",
            "writingApproach": "chronological",
        },
    }
    (workspace / "source-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def seeded_workspace(tmp_path: Path) -> tuple[Path, str]:
    workspace_id = "architecture-probe"
    _seed_workspace(tmp_path, workspace_id)
    return tmp_path, workspace_id


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    token: str = TOKEN,
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
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


def test_core_updates_sources_and_saves_draft(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = WorkspaceController(root)

    context = controller.get_context(workspace_id)
    assert context["manifest"]["version"] == 1
    assert context["draft"] is None

    manifest = controller.update_sources(
        workspace_id,
        expected_version=1,
        updates=[
            {
                "sourceId": "M01",
                "included": True,
                "description": "Opening group photo",
            }
        ],
    )
    assert manifest["version"] == 2
    assert manifest["sources"][0]["included"] is True

    draft = controller.save_draft(
        workspace_id,
        expected_version=0,
        document={
            "schemaVersion": 1,
            "title": "A Small Architecture Probe",
            "articleType": "meeting-recap",
            "bodyMarkdown": "One shared workspace is enough.",
            "media": [],
        },
    )
    assert draft["workspaceVersion"] == 1
    assert controller.get_context(workspace_id)["draft"] == draft


def test_stale_updates_are_rejected_without_data_loss(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = WorkspaceController(root)
    controller.update_sources(
        workspace_id,
        expected_version=1,
        updates=[{"sourceId": "M01", "description": "First writer"}],
    )

    with pytest.raises(VersionConflict) as conflict:
        controller.update_sources(
            workspace_id,
            expected_version=1,
            updates=[{"sourceId": "M02", "description": "Stale writer"}],
        )

    assert conflict.value.actual == 2
    context = controller.get_context(workspace_id)
    assert context["manifest"]["sources"][0]["description"] == "First writer"
    assert context["manifest"]["sources"][1]["description"] == ""


def test_concurrent_updates_serialize_and_one_conflicts(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def update(source_id: str) -> None:
        controller = WorkspaceController(root)
        barrier.wait()
        try:
            controller.update_sources(
                workspace_id,
                expected_version=1,
                updates=[{"sourceId": source_id, "included": True}],
            )
        except VersionConflict:
            outcomes.append("conflict")
        else:
            outcomes.append("updated")

    threads = [
        threading.Thread(target=update, args=("M01",)),
        threading.Thread(target=update, args=("M02",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert sorted(outcomes) == ["conflict", "updated"]
    assert (
        WorkspaceController(root).get_context(workspace_id)["manifest"]["version"] == 2
    )


def test_expected_versions_reject_booleans(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = WorkspaceController(root)

    with pytest.raises(InvalidWorkspace, match="expectedVersion"):
        controller.update_sources(
            workspace_id,
            expected_version=True,
            updates=[{"sourceId": "M01", "included": True}],
        )

    with pytest.raises(InvalidWorkspace, match="expectedVersion"):
        controller.save_draft(
            workspace_id,
            expected_version=False,
            document={
                "schemaVersion": 1,
                "title": "Invalid version",
                "articleType": "meeting-recap",
                "bodyMarkdown": "This write must not happen.",
            },
        )


def test_workspace_identifier_and_symlink_escape_are_rejected(
    seeded_workspace: tuple[Path, str],
    tmp_path: Path,
) -> None:
    root, workspace_id = seeded_workspace
    controller = WorkspaceController(root)
    with pytest.raises(InvalidWorkspace):
        controller.get_context("../outside")

    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "inbox" / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(InvalidWorkspace):
        controller.get_context("escape")

    assert controller.get_context(workspace_id)["workspaceId"] == workspace_id


def test_operations_create_only_the_declared_workspace_files(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = WorkspaceController(root)
    controller.save_draft(
        workspace_id,
        expected_version=0,
        document={
            "schemaVersion": 1,
            "title": "Probe",
            "articleType": "meeting-recap",
            "bodyMarkdown": "Draft",
        },
    )

    assert {path.name for path in root.iterdir()} == {"inbox"}
    workspace = root / "inbox" / workspace_id
    assert {path.name for path in workspace.iterdir()} == {
        ".source-manifest.lock",
        "draft",
        "source-manifest.json",
    }
    assert {path.name for path in (workspace / "draft").iterdir()} == {"article.json"}


def test_http_adapter_uses_auth_and_the_same_controller(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    server = build_server(
        workspace_root=str(root), bearer_token=TOKEN, host="127.0.0.1", port=0
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        unauthorized, _ = _json_request(
            f"{base_url}/workspaces/{workspace_id}/context", token="wrong"
        )
        assert unauthorized == 401

        status, manifest = _json_request(
            f"{base_url}/workspaces/{workspace_id}/sources",
            method="PATCH",
            payload={
                "expectedVersion": 1,
                "updates": [{"sourceId": "M01", "description": "HTTP writer"}],
            },
        )
        assert status == 200
        assert manifest["version"] == 2

        status, context = _json_request(f"{base_url}/workspaces/{workspace_id}/context")
        assert status == 200
        assert context["manifest"]["sources"][0]["description"] == "HTTP writer"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_adapter_returns_structured_version_conflict(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    server = build_server(
        workspace_root=str(root), bearer_token=TOKEN, host="127.0.0.1", port=0
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{server.server_port}"
            f"/workspaces/{workspace_id}/sources",
            method="PATCH",
            payload={
                "expectedVersion": 0,
                "updates": [{"sourceId": "M01", "included": True}],
            },
        )
        assert status == 409
        assert payload["error"]["code"] == "version_conflict"
        assert payload["error"]["actualVersion"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_mcp_adapter_exposes_only_the_three_domain_operations(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "wxpost_controller.mcp_server"],
        cwd=str(root),
        env={
            **os.environ,
            "PYTHONPATH": str(HERMES_ROOT),
            "WXPOST_WORKSPACE_ROOT": str(root),
        },
    )
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "wxpost_get_context",
                "wxpost_save_draft",
                "wxpost_update_sources",
            }

            updated = await session.call_tool(
                "wxpost_update_sources",
                {
                    "workspace_id": workspace_id,
                    "expected_version": 1,
                    "updates": [{"sourceId": "M02", "description": "MCP writer"}],
                },
            )
            assert _mcp_value(updated)["version"] == 2

            context = await session.call_tool(
                "wxpost_get_context", {"workspace_id": workspace_id}
            )
            value = _mcp_value(context)
            assert value["manifest"]["sources"][1]["description"] == "MCP writer"

            saved = await session.call_tool(
                "wxpost_save_draft",
                {
                    "workspace_id": workspace_id,
                    "expected_version": 0,
                    "document": {
                        "schemaVersion": 1,
                        "title": "MCP draft",
                        "articleType": "meeting-recap",
                        "bodyMarkdown": "Saved through the standard MCP adapter.",
                        "media": [],
                    },
                },
            )
            assert _mcp_value(saved)["workspaceVersion"] == 1


def test_controller_state_survives_a_new_instance(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    first = WorkspaceController(root)
    first.update_sources(
        workspace_id,
        expected_version=1,
        updates=[{"sourceId": "M01", "description": "Persisted"}],
    )

    restarted = WorkspaceController(root)
    context = restarted.get_context(workspace_id)
    assert context["manifest"]["version"] == 2
    assert context["manifest"]["sources"][0]["description"] == "Persisted"
