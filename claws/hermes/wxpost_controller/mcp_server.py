from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from .core import (
    WorkspaceController,
    WorkspaceError,
    error_response,
)

mcp = FastMCP(
    "soarhigh-wxpost-controller",
    instructions=(
        "Use these tools for canonical WXPost manifest and draft writes. "
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
    """Read the latest source manifest and working draft for one workspace."""
    return _run(lambda: _controller().get_context(workspace_id))


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
def wxpost_save_draft(
    workspace_id: str,
    expected_manifest_version: int,
    expected_draft_version: int,
    document: dict[str, Any],
) -> dict[str, Any]:
    """Validate and save one complete working ArticleDocument atomically."""
    return _run(
        lambda: _controller().save_draft(
            workspace_id,
            expected_manifest_version=expected_manifest_version,
            expected_draft_version=expected_draft_version,
            document=document,
        )
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
