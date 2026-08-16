from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable
from typing import Any

from gateway.session_context import get_session_env
from pydantic import Field, ValidationError
from wxpost_controller.contracts import (
    ContractModel,
    DraftEditOperation,
    DraftMediaChanges,
    DraftProposal,
)
from wxpost_controller.core import (
    InvalidRequest,
    WorkspaceController,
    WorkspaceError,
    error_response,
)
from wxpost_controller.draft_store import read_running_operation_id
from wxpost_controller.feishu_navigation import FeishuNavigation

TOOLSET = "wxpost_navigation"
CURRENT_TOOLSET = "wxpost_current"


# The web Draft operation identity is bound server-side (see
# _bound_operation_id); it is deliberately absent from these model-facing
# schemas so a persistent session can never replay a stale operation id.
class CurrentDraftSaveInput(ContractModel):
    expected_manifest_version: int = Field(ge=1, strict=True)
    expected_draft_version: int = Field(ge=0, strict=True)
    refresh_from_materials: bool = Field(strict=True)
    proposal: DraftProposal
    media_changes: DraftMediaChanges | None = None


class CurrentDraftEditInput(ContractModel):
    expected_manifest_version: int = Field(ge=1, strict=True)
    expected_draft_version: int = Field(ge=1, strict=True)
    edits: list[DraftEditOperation] = Field(min_length=1)


def _schema(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(required),
            "additionalProperties": False,
        },
    }


SCHEMAS = {
    "wxpost_list_workspaces": _schema(
        "wxpost_list_workspaces",
        "List WxPost workspaces. This global navigation tool is available only in Feishu.",
        {
            "page": {"type": "integer", "minimum": 1, "default": 1},
            "page_size": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "default": 10,
            },
        },
    ),
    "wxpost_search_meetings": _schema(
        "wxpost_search_meetings",
        "Search meeting or event choices before creating a linked workspace.",
        {
            "query": {"type": "string", "default": ""},
            "page": {"type": "integer", "minimum": 1, "default": 1},
            "page_size": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "default": 10,
            },
        },
    ),
    "wxpost_get_active_workspace": _schema(
        "wxpost_get_active_workspace",
        "Get the workspace selected for this Feishu conversation.",
        {},
    ),
    "wxpost_get_active_workspace_report": _schema(
        "wxpost_get_active_workspace_report",
        "Read the complete configuration report for the selected Feishu workspace without changing it.",
        {},
    ),
    "wxpost_show_material_library": _schema(
        "wxpost_show_material_library",
        "Show every candidate and imported material from the selected workspace as native Feishu media with its M ID, state, filename, and description.",
        {},
    ),
    "wxpost_describe_material": _schema(
        "wxpost_describe_material",
        "Generate an AI description suggestion for one imported image in the selected Feishu workspace, or save the exact staged suggestion after explicit confirmation in a later member message. Calling with confirmed=false never changes Materials; confirmed=true saves it as a confirmed AI description. When the member states wishes for the caption (language, length, tone, emphasis, details to mention), pass them via guidance so the image-inspecting model hears them; it still never invents facts the image does not show.",
        {
            "source_id": {"type": "string"},
            "confirmed": {"type": "boolean"},
            "guidance": {"type": "string", "maxLength": 500},
        },
        ("source_id", "confirmed"),
    ),
    "wxpost_get_draft_preview": _schema(
        "wxpost_get_draft_preview",
        "Send both the selected workspace's short-lived read-only Draft preview and authenticated Draft Edit link directly to Feishu. Use this tool alone when either or both links are requested. A successful sent=true result completes both deliveries; do not call wxpost_send_web_editor_link in the same turn and do not repeat any URL.",
        {"draft_version": {"type": "integer", "minimum": 1}},
    ),
    "wxpost_send_web_editor_link": _schema(
        "wxpost_send_web_editor_link",
        "Send only the selected workspace's authenticated web editor link directly to Feishu. Use materials for web Materials editing and draft for web Draft editing when no temporary preview is requested. Never call this after wxpost_get_draft_preview in the same turn because that tool already sends the Draft Edit link.",
        {"target": {"type": "string", "enum": ["materials", "draft"]}},
        ("target",),
    ),
    "wxpost_send_draft_preview_image": _schema(
        "wxpost_send_draft_preview_image",
        "Render the selected workspace's current saved Draft with the canonical renderer and send one readable full-page image to this Feishu conversation. Call only when the member explicitly asks for a Draft screenshot or full-page preview image.",
        {"draft_version": {"type": "integer", "minimum": 1}},
    ),
    "wxpost_select_workspace": _schema(
        "wxpost_select_workspace",
        "Select an existing workspace for this Feishu conversation.",
        {"workspace_id": {"type": "string"}},
        ("workspace_id",),
    ),
    "wxpost_create_workspace": _schema(
        "wxpost_create_workspace",
        "Create and select a workspace only after the member confirms its fixed setup.",
        {
            "source": {
                "type": "string",
                "enum": ["independent", "meeting", "event"],
            },
            "article_type": {
                "type": "string",
                "enum": [
                    "meeting-recap",
                    "member-story",
                    "event-preview",
                    "meeting-review",
                    "action-guide",
                    "custom",
                ],
            },
            "meeting_id": {"type": "string"},
            "custom_article_type": {"type": "string"},
            "confirmed": {"type": "boolean"},
        },
        ("source", "article_type", "confirmed"),
    ),
    "wxpost_delete_workspace": _schema(
        "wxpost_delete_workspace",
        "Delete the selected workspace only after explicit member confirmation.",
        {"confirmed": {"type": "boolean"}},
        ("confirmed",),
    ),
    "wxpost_import_feishu_attachments": _schema(
        "wxpost_import_feishu_attachments",
        "Import files attached to the current Feishu message into the selected workspace. Repeated delivery is idempotent.",
        {
            "attachments": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "sourcePath": {"type": "string"},
                        "filename": {"type": "string"},
                        "mimeType": {"type": "string"},
                    },
                    "required": ["sourcePath"],
                    "additionalProperties": False,
                },
            },
            "include": {"type": "boolean", "default": False},
        },
        ("attachments",),
    ),
}


CURRENT_SCHEMAS = {
    "wxpost_get_current_context": _schema(
        "wxpost_get_current_context",
        "Read the saved Draft, imported media, and linked source facts for the current Web Draft Assistant workspace.",
        {},
    ),
    "wxpost_get_current_workspace_report": _schema(
        "wxpost_get_current_workspace_report",
        "Read the complete, non-mutating configuration and material report for the current Web Draft Assistant workspace.",
        {},
    ),
    "wxpost_save_current_draft": {
        "name": "wxpost_save_current_draft",
        "description": "Assemble and save a complete canonical Draft in the current Web Draft Assistant workspace.",
        "parameters": CurrentDraftSaveInput.model_json_schema(by_alias=True),
    },
    "wxpost_edit_current_draft": {
        "name": "wxpost_edit_current_draft",
        "description": "Apply small typed edits to the saved Draft in the current Web Draft Assistant workspace.",
        "parameters": CurrentDraftEditInput.model_json_schema(by_alias=True),
    },
}


def feishu_context() -> tuple[str, str, str, str]:
    platform = get_session_env("HERMES_SESSION_PLATFORM")
    scope_key = get_session_env("HERMES_SESSION_KEY")
    if platform != "feishu" or ":feishu:" not in scope_key:
        raise RuntimeError("WxPost workspace navigation is available only in Feishu")
    return (
        scope_key,
        get_session_env("HERMES_SESSION_MESSAGE_ID"),
        get_session_env("HERMES_SESSION_USER_ID").strip(),
        get_session_env("HERMES_SESSION_USER_NAME") or "Feishu member",
    )


def handle_navigation(name: str, args: dict[str, Any]) -> str:
    try:
        scope_key, message_id, user_id, user_name = feishu_context()
        navigation = FeishuNavigation()
        if name == "wxpost_list_workspaces":
            result = navigation.list_workspaces(
                page=int(args.get("page", 1)),
                page_size=int(args.get("page_size", 10)),
            )
        elif name == "wxpost_search_meetings":
            result = navigation.search_meetings(
                query=str(args.get("query", "")),
                page=int(args.get("page", 1)),
                page_size=int(args.get("page_size", 10)),
            )
        elif name == "wxpost_get_active_workspace":
            result = navigation.get_active_workspace(scope_key)
        elif name == "wxpost_get_active_workspace_report":
            result = navigation.get_active_workspace_report(scope_key)
        elif name == "wxpost_describe_material":
            if not message_id:
                raise RuntimeError(
                    "the current Feishu message has no stable message ID"
                )
            if not user_id:
                raise RuntimeError("the current Feishu member identity is unavailable")
            guidance = str(args.get("guidance") or "")
            # Diagnostic breadcrumb: the model composes guidance but several
            # dispatch layers sit between its tool call and this handler, so
            # record what actually arrived.
            logging.getLogger(__name__).info(
                "wxpost_describe_material dispatch: source_id=%s confirmed=%s "
                "guidance_chars=%d",
                args.get("source_id"),
                args.get("confirmed"),
                len(guidance),
            )
            result = navigation.describe_material(
                scope_key,
                message_id=message_id,
                requested_by_user_id=user_id,
                source_id=str(args["source_id"]),
                confirmed=bool(args["confirmed"]),
                guidance=guidance,
            )
        elif name == "wxpost_get_draft_preview":
            result = navigation.create_draft_preview_link(
                scope_key,
                draft_version=(
                    int(args["draft_version"])
                    if args.get("draft_version") is not None
                    else None
                ),
            )
        elif name == "wxpost_select_workspace":
            result = navigation.select_workspace(scope_key, str(args["workspace_id"]))
        elif name == "wxpost_create_workspace":
            if not message_id:
                raise RuntimeError(
                    "the current Feishu message has no stable message ID"
                )
            if not user_id:
                raise RuntimeError("the current Feishu member identity is unavailable")
            result = navigation.create_workspace(
                scope_key,
                message_id=message_id,
                source=args["source"],
                article_type=str(args["article_type"]),
                meeting_id=args.get("meeting_id"),
                custom_article_type=args.get("custom_article_type"),
                created_by_id=user_id,
                created_by_name=user_name,
                confirmed=bool(args.get("confirmed", False)),
            )
        elif name == "wxpost_delete_workspace":
            if not message_id:
                raise RuntimeError(
                    "the current Feishu message has no stable message ID"
                )
            if not user_id:
                raise RuntimeError("the current Feishu member identity is unavailable")
            result = navigation.delete_workspace(
                scope_key,
                message_id=message_id,
                requested_by_user_id=user_id,
                confirmed=bool(args.get("confirmed", False)),
            )
        elif name == "wxpost_import_feishu_attachments":
            if not message_id:
                raise RuntimeError(
                    "the current Feishu message has no stable message ID"
                )
            result = navigation.import_attachments(
                scope_key,
                message_id=message_id,
                attachments=list(args["attachments"]),
                include=bool(args.get("include", False)),
            )
        else:  # pragma: no cover - registration is static
            raise RuntimeError(f"unsupported WxPost navigation tool: {name}")
        return json.dumps(result, ensure_ascii=False)
    except WorkspaceError as exc:
        raise RuntimeError(json.dumps(error_response(exc), ensure_ascii=False)) from exc


def navigation_handler(name: str) -> Callable[..., str]:
    def handle(args: dict[str, Any], **_kwargs: Any) -> str:
        return handle_navigation(name, args)

    return handle


def async_navigation_handler(name: str) -> Callable[..., Any]:
    async def handle(args: dict[str, Any], **_kwargs: Any) -> str:
        return await asyncio.to_thread(handle_navigation, name, args)

    return handle


def _bound_operation_id(controller: WorkspaceController, workspace_id: str) -> str:
    """Return the trusted per-turn Draft operation id bound by the Controller.

    The Controller's durable operation record — created before the turn
    starts and settled when it ends — is the single source of truth. The
    model never supplies the value, so a persistent session cannot attribute
    a save to a stale operation id copied from an earlier turn's context.
    """

    operation_id = read_running_operation_id(
        controller.workspace_root,
        workspace_id,
    )
    if operation_id is None:
        raise InvalidRequest("no Draft operation is active for this workspace")
    return operation_id


def current_workspace() -> tuple[WorkspaceController, str]:
    """Resolve the Web workspace from Hermes' task-local, Controller-set cwd."""

    from agent.runtime_cwd import resolve_agent_cwd

    controller = WorkspaceController(
        os.environ.get("WXPOST_WORKSPACE_ROOT", "/workspace")
    )
    cwd = resolve_agent_cwd().resolve()
    inbox = controller.inbox_root.resolve()
    if cwd.parent != inbox or not cwd.name:
        raise InvalidRequest(
            "the current Hermes session is not bound to a WxPost workspace"
        )
    workspace_id = cwd.name
    controller.get_context(workspace_id)
    return controller, workspace_id


def handle_current(name: str, args: dict[str, Any]) -> str:
    try:
        controller, workspace_id = current_workspace()
        if name == "wxpost_get_current_context":
            result = controller.get_agent_context(workspace_id)
        elif name == "wxpost_get_current_workspace_report":
            result = controller.get_workspace_report(workspace_id)
        elif name == "wxpost_save_current_draft":
            save_request = CurrentDraftSaveInput.model_validate(args)
            result = controller.save_draft_proposal(
                workspace_id,
                expected_manifest_version=save_request.expected_manifest_version,
                expected_draft_version=save_request.expected_draft_version,
                proposal=save_request.proposal,
                operation_id=_bound_operation_id(controller, workspace_id),
                refresh_from_materials=save_request.refresh_from_materials,
                media_changes=save_request.media_changes,
            )
        elif name == "wxpost_edit_current_draft":
            edit_request = CurrentDraftEditInput.model_validate(args)
            result = controller.edit_draft(
                workspace_id,
                expected_manifest_version=edit_request.expected_manifest_version,
                expected_draft_version=edit_request.expected_draft_version,
                operation_id=_bound_operation_id(controller, workspace_id),
                edits=[edit.to_wire() for edit in edit_request.edits],
            )
        else:  # pragma: no cover - registration is static
            raise RuntimeError(f"unsupported current WxPost tool: {name}")
        return json.dumps(result, ensure_ascii=False)
    except ValidationError as exc:
        error = InvalidRequest(f"invalid current-workspace tool input: {exc}")
        raise RuntimeError(
            json.dumps(error_response(error), ensure_ascii=False)
        ) from exc
    except WorkspaceError as exc:
        raise RuntimeError(json.dumps(error_response(exc), ensure_ascii=False)) from exc


def current_handler(name: str) -> Callable[..., str]:
    def handle(args: dict[str, Any], **_kwargs: Any) -> str:
        return handle_current(name, args)

    return handle
