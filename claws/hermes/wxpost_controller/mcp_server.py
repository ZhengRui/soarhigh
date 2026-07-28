from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .core import WorkspaceController

mcp = FastMCP(
    "soarhigh-wxpost-controller",
    instructions=(
        "Use these tools for canonical WXPost manifest and draft writes. "
        "Never edit source-manifest.json or draft/article.json directly."
    ),
)


def _controller() -> WorkspaceController:
    return WorkspaceController(os.environ.get("WXPOST_WORKSPACE_ROOT", "/workspace"))


@mcp.tool()
def wxpost_get_context(workspace_id: str) -> dict[str, Any]:
    """Read the latest source manifest and working draft for one workspace."""
    return _controller().get_context(workspace_id)


@mcp.tool()
def wxpost_update_sources(
    workspace_id: str,
    expected_version: int,
    updates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Update existing source descriptions, inclusion, or order atomically."""
    return _controller().update_sources(
        workspace_id,
        expected_version=expected_version,
        updates=updates,
    )


@mcp.tool()
def wxpost_save_draft(
    workspace_id: str,
    expected_version: int,
    document: dict[str, Any],
) -> dict[str, Any]:
    """Validate and save one complete working ArticleDocument atomically."""
    return _controller().save_draft(
        workspace_id,
        expected_version=expected_version,
        document=document,
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
