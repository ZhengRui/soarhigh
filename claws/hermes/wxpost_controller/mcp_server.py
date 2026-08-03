from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from .contracts import DraftEditOperation, DraftMediaChanges, DraftProposal
from .core import (
    WorkspaceController,
    WorkspaceError,
    error_response,
)

mcp = FastMCP(
    "soarhigh-wxpost-controller",
    instructions=(
        "Use these tools for canonical WxPost manifest and draft writes. "
        "Never edit source-manifest.json or draft/article.json directly."
    ),
)


def _controller() -> WorkspaceController:
    return WorkspaceController(os.environ.get("WXPOST_WORKSPACE_ROOT", "/workspace"))


def _run(operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return operation()
    except WorkspaceError as exc:
        raise ToolError(json.dumps(error_response(exc), ensure_ascii=False)) from exc


@mcp.tool()
def wxpost_get_context(workspace_id: str) -> dict[str, Any]:
    """Read saved Materials, Draft, and live linked-meeting authoring facts."""
    return _run(lambda: _controller().get_agent_context(workspace_id))


@mcp.tool()
def wxpost_bootstrap_workspace(
    workspace_id: str,
    editorial: dict[str, Any],
    meeting_id: str | None = None,
) -> dict[str, Any]:
    """Create a workspace and register its initial meeting media."""
    return _run(
        lambda: _controller().bootstrap_workspace(
            workspace_id,
            meeting_id=meeting_id,
            editorial=editorial,
            created_by={"id": "hermes", "name": "Hermes"},
        )
    )


@mcp.tool()
def wxpost_update_workspace(
    workspace_id: str,
    expected_manifest_version: int,
    meeting_id: str | None,
    editorial: dict[str, Any],
) -> dict[str, Any]:
    """Save workspace settings when the source manifest is still current."""
    return _run(
        lambda: _controller().update_workspace(
            workspace_id,
            expected_manifest_version=expected_manifest_version,
            meeting_id=meeting_id,
            editorial=editorial,
        )
    )


@mcp.tool()
def wxpost_import_source(
    workspace_id: str,
    expected_manifest_version: int,
    source_id: str,
) -> dict[str, Any]:
    """Copy one registered meeting-library source into the workspace."""
    return _run(
        lambda: _controller().import_source(
            workspace_id,
            expected_manifest_version=expected_manifest_version,
            source_id=source_id,
        )
    )


@mcp.tool()
def wxpost_set_source_included(
    workspace_id: str,
    expected_manifest_version: int,
    source_id: str,
    included: bool,
) -> dict[str, Any]:
    """Include or exclude a source, importing a meeting source when needed."""
    return _run(
        lambda: _controller().set_source_included(
            workspace_id,
            expected_manifest_version=expected_manifest_version,
            source_id=source_id,
            included=included,
        )
    )


@mcp.tool()
def wxpost_upload_source(
    workspace_id: str,
    expected_manifest_version: int,
    source_path: str,
    origin: Literal["web-upload", "feishu-upload"] = "feishu-upload",
    filename: str | None = None,
    mime_type: str | None = None,
    description: str = "",
    description_source: str | None = None,
    description_status: str = "missing",
) -> dict[str, Any]:
    """Collect a workspace-local file as a web or Feishu upload."""
    return _run(
        lambda: _controller().upload_source_from_path(
            workspace_id,
            expected_manifest_version=expected_manifest_version,
            source_path=source_path,
            origin=origin,
            filename=filename,
            mime_type=mime_type,
            description=description,
            description_source=description_source,
            description_status=description_status,
        )
    )


@mcp.tool()
def wxpost_update_sources(
    workspace_id: str,
    expected_manifest_version: int,
    updates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Update existing source descriptions, inclusion, or order atomically."""
    return _run(
        lambda: _controller().update_sources(
            workspace_id,
            expected_manifest_version=expected_manifest_version,
            updates=updates,
        )
    )


@mcp.tool()
def wxpost_delete_source_preflight(
    workspace_id: str,
    expected_manifest_version: int,
    source_id: str,
) -> dict[str, Any]:
    """Report whether the latest saved draft references a source."""
    return _run(
        lambda: _controller().delete_source_preflight(
            workspace_id,
            expected_manifest_version=expected_manifest_version,
            source_id=source_id,
        )
    )


@mcp.tool()
def wxpost_delete_source(
    workspace_id: str,
    expected_manifest_version: int,
    source_id: str,
) -> dict[str, Any]:
    """Delete a source that is not referenced by the current saved Draft."""
    return _run(
        lambda: _controller().delete_source(
            workspace_id,
            expected_manifest_version=expected_manifest_version,
            source_id=source_id,
        )
    )


@mcp.tool()
def wxpost_save_draft(
    workspace_id: str,
    expected_manifest_version: int,
    expected_draft_version: int,
    operation_id: str,
    refresh_from_materials: bool,
    proposal: DraftProposal,
    media_changes: DraftMediaChanges | None = None,
) -> dict[str, Any]:
    """Assemble and save a canonical draft from strict editorial output."""
    return _run(
        lambda: _controller().save_draft_proposal(
            workspace_id,
            expected_manifest_version=expected_manifest_version,
            expected_draft_version=expected_draft_version,
            proposal=proposal,
            operation_id=operation_id,
            refresh_from_materials=refresh_from_materials,
            media_changes=media_changes,
        )
    )


@mcp.tool()
def wxpost_edit_draft(
    workspace_id: str,
    expected_manifest_version: int,
    expected_draft_version: int,
    operation_id: str,
    edits: list[DraftEditOperation],
) -> dict[str, Any]:
    """Apply small, typed edits to the current saved Draft."""
    return _run(
        lambda: _controller().edit_draft(
            workspace_id,
            expected_manifest_version=expected_manifest_version,
            expected_draft_version=expected_draft_version,
            operation_id=operation_id,
            edits=[edit.to_wire() for edit in edits],
        )
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
