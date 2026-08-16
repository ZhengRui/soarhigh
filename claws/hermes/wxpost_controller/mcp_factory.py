from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from .contracts import DraftEditOperation, DraftMediaChanges, DraftProposal
from .core import WorkspaceController, WorkspaceError, error_response
from .draft_store import read_running_operation_id


def _controller() -> WorkspaceController:
    return WorkspaceController(os.environ.get("WXPOST_WORKSPACE_ROOT", "/workspace"))


def _trusted_operation_id(
    controller: WorkspaceController,
    workspace_id: str,
    model_supplied: str,
) -> str:
    """Attribute writes to the Controller-run operation when one is in flight.

    The Controller's durable operation record is the single source of truth
    for an in-flight Draft turn. The model-supplied argument is only trusted
    when no operation is running (a Feishu turn on an idle workspace): a
    model-minted id would misattribute the write and fail the web turn's
    post-turn verification.
    """

    bound = read_running_operation_id(controller.workspace_root, workspace_id)
    return bound if bound is not None else model_supplied


def _run(operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return operation()
    except WorkspaceError as exc:
        raise ToolError(json.dumps(error_response(exc), ensure_ascii=False)) from exc


def create_mcp(*, include_material_mutations: bool, name: str) -> FastMCP:
    """Build one platform-specific MCP surface over the shared controller."""

    server = FastMCP(
        name,
        instructions=(
            "Canonical WxPost reads and writes for Feishu conversations, "
            "which span many workspaces and so pass workspace_id explicitly. "
            "In a Web Draft Assistant session, use the session-bound "
            "wxpost_*_current_* tools for Draft writes instead — they take "
            "no workspace or operation id. Never edit source-manifest.json "
            "or draft/article.json directly."
        ),
    )

    @server.tool()
    def wxpost_get_context(workspace_id: str) -> dict[str, Any]:
        """Read saved Materials, Draft, and live linked-meeting authoring facts."""
        return _run(lambda: _controller().get_agent_context(workspace_id))

    @server.tool()
    def wxpost_get_workspace_report(workspace_id: str) -> dict[str, Any]:
        """Read a deterministic, non-mutating report of one workspace."""
        return _run(lambda: _controller().get_workspace_report(workspace_id))

    if include_material_mutations:

        @server.tool()
        def wxpost_update_workspace(
            workspace_id: str,
            expected_manifest_version: int,
            meeting_id: str | None,
            editorial: dict[str, Any],
        ) -> dict[str, Any]:
            """Save Materials settings while the source manifest is current."""
            return _run(
                lambda: _controller().update_workspace(
                    workspace_id,
                    expected_manifest_version=expected_manifest_version,
                    meeting_id=meeting_id,
                    editorial=editorial,
                )
            )

        @server.tool()
        def wxpost_import_source(
            workspace_id: str,
            expected_manifest_version: int,
            source_id: str,
        ) -> dict[str, Any]:
            """Import one candidate from the linked meeting or event."""
            return _run(
                lambda: _controller().import_source(
                    workspace_id,
                    expected_manifest_version=expected_manifest_version,
                    source_id=source_id,
                )
            )

        @server.tool()
        def wxpost_set_source_included(
            workspace_id: str,
            expected_manifest_version: int,
            source_id: str,
            included: bool,
        ) -> dict[str, Any]:
            """Change whether imported media is used by the next generation."""
            return _run(
                lambda: _controller().set_source_included(
                    workspace_id,
                    expected_manifest_version=expected_manifest_version,
                    source_id=source_id,
                    included=included,
                )
            )

        @server.tool()
        def wxpost_update_sources(
            workspace_id: str,
            expected_manifest_version: int,
            updates: list[dict[str, Any]],
        ) -> dict[str, Any]:
            """Update imported Materials descriptions, inclusion, or order."""
            return _run(
                lambda: _controller().update_sources(
                    workspace_id,
                    expected_manifest_version=expected_manifest_version,
                    updates=updates,
                )
            )

        @server.tool()
        def wxpost_delete_source_preflight(
            workspace_id: str,
            expected_manifest_version: int,
            source_id: str,
        ) -> dict[str, Any]:
            """Report whether the latest saved Draft references a material."""
            return _run(
                lambda: _controller().delete_source_preflight(
                    workspace_id,
                    expected_manifest_version=expected_manifest_version,
                    source_id=source_id,
                )
            )

        @server.tool()
        def wxpost_delete_source(
            workspace_id: str,
            expected_manifest_version: int,
            source_id: str,
        ) -> dict[str, Any]:
            """Delete imported media not referenced by the saved Draft."""
            return _run(
                lambda: _controller().delete_source(
                    workspace_id,
                    expected_manifest_version=expected_manifest_version,
                    source_id=source_id,
                )
            )

    @server.tool()
    def wxpost_save_draft(
        workspace_id: str,
        expected_manifest_version: int,
        expected_draft_version: int,
        operation_id: str,
        refresh_from_materials: bool,
        proposal: DraftProposal,
        media_changes: DraftMediaChanges | None = None,
    ) -> dict[str, Any]:
        """Save a complete Draft proposal in a Feishu conversation.

        Web Draft Assistant sessions use wxpost_save_current_draft instead:
        it takes the same proposal but no workspace or operation id.
        """

        def save() -> dict[str, Any]:
            controller = _controller()
            return controller.save_draft_proposal(
                workspace_id,
                expected_manifest_version=expected_manifest_version,
                expected_draft_version=expected_draft_version,
                proposal=proposal,
                operation_id=_trusted_operation_id(
                    controller, workspace_id, operation_id
                ),
                refresh_from_materials=refresh_from_materials,
                media_changes=media_changes,
            )

        return _run(save)

    @server.tool()
    def wxpost_edit_draft(
        workspace_id: str,
        expected_manifest_version: int,
        expected_draft_version: int,
        operation_id: str,
        edits: list[DraftEditOperation],
    ) -> dict[str, Any]:
        """Apply small, typed Draft edits in a Feishu conversation.

        Web Draft Assistant sessions use wxpost_edit_current_draft instead:
        it takes the same edits but no workspace or operation id.
        """

        def apply_edits() -> dict[str, Any]:
            controller = _controller()
            return controller.edit_draft(
                workspace_id,
                expected_manifest_version=expected_manifest_version,
                expected_draft_version=expected_draft_version,
                operation_id=_trusted_operation_id(
                    controller, workspace_id, operation_id
                ),
                edits=[edit.to_wire() for edit in edits],
            )

        return _run(apply_edits)

    return server
