from __future__ import annotations

import json
import os
from typing import Any
from urllib.request import Request, urlopen

from gateway.session_context import get_session_env  # type: ignore[import-not-found]
from wxpost_controller.feishu_state_store import FeishuStateStore


CONTROLLER_BASE_URL = "http://127.0.0.1:8787"
READ_ONLY_COMMAND = "/readonly"
EDITING_COMMAND = "/editing"

# Full-Controller MCP writes take a workspace ID from the model. Feishu must
# bind those writes to the workspace selected through its navigation toolset.
FEISHU_ACTIVE_WORKSPACE_WRITES = {
    "wxpost_update_workspace",
    "wxpost_import_source",
    "wxpost_set_source_included",
    "wxpost_update_sources",
    "wxpost_delete_source",
    "wxpost_save_draft",
    "wxpost_edit_draft",
}

# These tools either resolve the active workspace internally or own a separate
# confirmation flow. The current-Draft names are not exposed to Feishu today,
# but remain classified as writes if the platform toolsets change later.
FEISHU_SESSION_SCOPED_WRITES = {
    "wxpost_save_current_draft",
    "wxpost_edit_current_draft",
    "wxpost_create_workspace",
    "wxpost_delete_workspace",
    "wxpost_import_feishu_attachments",
}
FEISHU_WRITE_TOOLS = FEISHU_ACTIVE_WORKSPACE_WRITES | FEISHU_SESSION_SCOPED_WRITES


def _state_store() -> FeishuStateStore:
    return FeishuStateStore(os.environ.get("WXPOST_WORKSPACE_ROOT", "/workspace"))


def _scope_key(event: Any, gateway: Any, session_store: Any) -> str:
    source = getattr(event, "source", None)
    for owner, method_name in (
        (gateway, "_session_key_for_source"),
        (session_store, "_generate_session_key"),
    ):
        method = getattr(owner, method_name, None)
        if callable(method):
            value = method(source)
            if isinstance(value, str) and value:
                return value
    raise RuntimeError("cannot resolve the current Feishu conversation")


def _mode_instruction(mode: str) -> str:
    current_context_rule = (
        "For any factual question about the selected workspace, Materials, or "
        "Draft, read the active workspace report before answering and never "
        "reuse an older value from chat history. General conversation does not "
        "need a workspace read. "
    )
    if mode == FeishuStateStore.EDITING:
        return (
            current_context_rule
            + "The current Feishu conversation is in editing mode. Workspace, "
            "Materials, and Draft writes are allowed when the member asks for them."
        )
    return (
        current_context_rule
        + "The current Feishu conversation is read-only. You may read its selected "
        "workspace context, answer questions, search the web, and deliver previews, "
        "but must not change any workspace, Materials, or Draft state. Tell the "
        "member to send /editing if they ask for a write."
    )


def attachment_filename(raw_message: Any) -> str | None:
    event = getattr(raw_message, "event", None)
    message = getattr(event, "message", None)
    content = getattr(message, "content", "")
    if not isinstance(content, str) or not content:
        return None
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    filename = payload.get("file_name")
    return filename.strip() if isinstance(filename, str) and filename.strip() else None


def prepare_feishu_event(
    *,
    event: Any,
    gateway: Any = None,
    session_store: Any = None,
    **_kwargs: Any,
) -> dict[str, str] | None:
    """Normalize the adapter fields required by Feishu-only WxPost tools.

    Keep this compatibility boundary isolated: if Hermes changes its gateway
    event contract, only this adapter and its contract tests need to change.
    """

    source = getattr(event, "source", None)
    platform = getattr(getattr(source, "platform", None), "value", "")
    message_id = getattr(event, "message_id", None)
    if platform == "feishu" and source is not None and message_id:
        source.message_id = str(message_id)

    if platform != "feishu":
        return None

    scope_key = _scope_key(event, gateway, session_store)
    store = _state_store()
    text = str(getattr(event, "text", "") or "").strip()
    lowered = text.casefold()
    if lowered == "/new" or lowered.startswith("/new "):
        store.set_interaction_mode(scope_key, FeishuStateStore.READ_ONLY)
        store.clear_confirmation(scope_key)
        return None
    if lowered == READ_ONLY_COMMAND:
        store.set_interaction_mode(scope_key, FeishuStateStore.READ_ONLY)
        store.clear_confirmation(scope_key)
        return {
            "action": "rewrite",
            "text": (
                "The member switched this Feishu conversation to read-only mode. "
                "Confirm briefly that workspace context remains available but no "
                "workspace, Materials, or Draft changes will be made."
            ),
        }
    if lowered == EDITING_COMMAND:
        user_id = str(getattr(source, "user_id", "") or "").strip()
        if not user_id or not message_id:
            raise RuntimeError("Feishu member and message identity are required")
        if store.interaction_mode(scope_key) == FeishuStateStore.EDITING:
            return {
                "action": "rewrite",
                "text": "The Feishu conversation is already in editing mode. Say so briefly.",
            }
        confirmed = store.consume_editing_confirmation(
            scope_key,
            message_id=str(message_id),
            requested_by_user_id=user_id,
        )
        if confirmed:
            store.set_interaction_mode(scope_key, FeishuStateStore.EDITING)
            return {
                "action": "rewrite",
                "text": (
                    "The member confirmed editing mode. Confirm briefly that future "
                    "explicit requests may now change the selected workspace, "
                    "Materials, or Draft until /readonly, /new, or a workspace switch."
                ),
            }
        store.stage_editing_confirmation(
            scope_key,
            message_id=str(message_id),
            requested_by_user_id=user_id,
        )
        return {
            "action": "rewrite",
            "text": (
                "The member has not entered editing mode. Reply in the member's "
                "current language and include both mandatory points: editing mode "
                "can change workspace, Materials, and Draft data; to confirm that "
                "risk, the member must send /editing again in a separate message. "
                "Do not omit either point and do not call a tool."
            ),
        }

    mode = store.interaction_mode(scope_key)
    media_urls = list(getattr(event, "media_urls", None) or [])
    if not media_urls:
        event.text = (
            f"{text}\n\n{_mode_instruction(mode)}" if text else _mode_instruction(mode)
        )
        return None
    media_types = list(getattr(event, "media_types", None) or [])
    original_filename = attachment_filename(getattr(event, "raw_message", None))
    attachments: list[dict[str, str]] = []
    for index, source_path in enumerate(media_urls):
        attachment = {"sourcePath": str(source_path)}
        if index < len(media_types) and media_types[index]:
            attachment["mimeType"] = str(media_types[index])
        if original_filename and len(media_urls) == 1:
            attachment["filename"] = original_filename
        attachments.append(attachment)

    if mode == FeishuStateStore.EDITING:
        instruction = (
            "Import the files attached to this Feishu message into the active "
            "WxPost workspace with wxpost_import_feishu_attachments. Keep them "
            "excluded unless the member explicitly asks to include them. If no "
            "workspace is active, ask the member to select or create one and "
            "resend the files. Attachment metadata: "
            + json.dumps(attachments, ensure_ascii=False)
        )
    else:
        instruction = (
            "Treat the attached files as conversation-only input. You may inspect "
            "them and answer questions about them normally. Do not import them into "
            "the active WxPost workspace. Only if the member explicitly asks to add "
            "them to Materials, explain that importing is a workspace change and "
            "they must enter editing mode with the two-step /editing confirmation, "
            "then resend the files. Attachment metadata: "
            + json.dumps(attachments, ensure_ascii=False)
        )
    instructions = f"{instruction}\n\n{_mode_instruction(mode)}"
    event.text = f"{text}\n\n{instructions}" if text else instructions
    return None


def guard_feishu_writes(
    *, tool_name: str, args: dict[str, Any], **_kwargs: Any
) -> dict[str, str] | None:
    """Block every Feishu mutation while its conversation is read-only."""

    if get_session_env("HERMES_SESSION_PLATFORM") != "feishu":
        return None
    canonical_name = tool_name.rsplit("__", 1)[-1]
    is_write = canonical_name in FEISHU_WRITE_TOOLS
    if canonical_name == "wxpost_describe_material":
        is_write = bool(args.get("confirmed"))
    if not is_write:
        return None
    scope_key = get_session_env("HERMES_SESSION_KEY")
    store = _state_store()
    if store.interaction_mode(scope_key) != FeishuStateStore.EDITING:
        return {
            "action": "block",
            "message": (
                "This Feishu conversation is read-only. No workspace data was "
                "changed. Send /editing and confirm the switch before making changes."
            ),
        }
    if canonical_name not in FEISHU_ACTIVE_WORKSPACE_WRITES:
        return None

    active_workspace_id = store.active_workspace(scope_key)
    requested_workspace_id = str(args.get("workspace_id", "")).strip()
    if active_workspace_id and requested_workspace_id == active_workspace_id:
        return None
    return {
        "action": "block",
        "message": (
            "The write was blocked because its workspaceId does not match the "
            "workspace selected in this Feishu conversation. Select that workspace "
            "first; no workspace data was changed."
        ),
    }


def retire_reset_feishu_session(
    *,
    platform: str,
    reason: str,
    old_session_id: str | None = None,
    new_session_id: str | None = None,
    **_kwargs: Any,
) -> None:
    """Queue the old native Feishu session after Hermes completes /new."""

    if (
        platform != "feishu"
        or reason != "new_session"
        or not old_session_id
        or old_session_id == new_session_id
    ):
        return
    token = os.environ.get("WXPOST_SERVICE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("WXPOST_SERVICE_TOKEN is required for session cleanup")
    base_url = os.environ.get(
        "WXPOST_CONTROLLER_BASE_URL",
        CONTROLLER_BASE_URL,
    ).rstrip("/")
    request = Request(
        f"{base_url}/sessions/retire",
        data=json.dumps({"sessionId": old_session_id}).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urlopen(request, timeout=3) as response:
        if response.status != 200:
            raise RuntimeError(
                f"Controller rejected session cleanup with HTTP {response.status}"
            )
