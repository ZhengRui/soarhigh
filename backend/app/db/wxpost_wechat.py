"""Service-role persistence for WeChat Official Account draft projections."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from .supabase import supabase


def get_projection(workspace_id: str) -> dict | None:
    response = supabase.table("wxpost_wechat_drafts").select("*").eq("source_workspace_id", workspace_id).execute()
    return response.data[0] if response.data else None


def claim_projection(
    *,
    workspace_id: str,
    wxpost_id: UUID,
    revision: int,
    presentation: dict,
    projection_sha256: str,
    operation_id: UUID,
) -> dict:
    response = supabase.rpc(
        "claim_wxpost_wechat_draft",
        {
            "requested_workspace_id": workspace_id,
            "requested_wxpost_id": str(wxpost_id),
            "requested_revision": revision,
            "requested_presentation": presentation,
            "requested_projection_sha256": projection_sha256,
            "requested_operation_id": str(operation_id),
        },
    ).execute()
    if not isinstance(response.data, dict):
        raise RuntimeError("Supabase returned an invalid WeChat draft claim.")
    return response.data


def update_projection(workspace_id: str, operation_id: UUID, values: dict) -> dict:
    response = (
        supabase.table("wxpost_wechat_drafts")
        .update({**values, "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("source_workspace_id", workspace_id)
        .eq("operation_id", str(operation_id))
        .execute()
    )
    if not response.data:
        raise RuntimeError("The WeChat draft operation no longer owns its projection.")
    return response.data[0]


def save_asset_mappings(workspace_id: str, operation_id: UUID, mappings: dict) -> dict:
    return update_projection(workspace_id, operation_id, {"asset_mappings": mappings})


def mark_add_started(workspace_id: str, operation_id: UUID) -> dict:
    return update_projection(
        workspace_id,
        operation_id,
        {"add_started_at": datetime.now(timezone.utc).isoformat()},
    )


def mark_projection_ready(
    workspace_id: str,
    operation_id: UUID,
    *,
    media_id: str,
    submitted_html_sha256: str,
    readback_html_sha256: str | None,
    readback_changed: bool | None,
) -> dict:
    return update_projection(
        workspace_id,
        operation_id,
        {
            "state": "ready",
            "wechat_media_id": media_id,
            "submitted_html_sha256": submitted_html_sha256,
            "readback_html_sha256": readback_html_sha256,
            "readback_changed": readback_changed,
            "add_started_at": None,
            "last_error": None,
        },
    )


def mark_projection_failed(workspace_id: str, operation_id: UUID, *, uncertain: bool, message: str) -> None:
    update_projection(
        workspace_id,
        operation_id,
        {"state": "uncertain" if uncertain else "idle", "last_error": message[:1000]},
    )


def recover_uncertain_projection(workspace_id: str, values: dict) -> dict:
    response = (
        supabase.table("wxpost_wechat_drafts")
        .update(
            {
                **values,
                "state": "ready",
                "add_started_at": None,
                "last_error": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("source_workspace_id", workspace_id)
        .eq("state", "uncertain")
        .execute()
    )
    if not response.data:
        current = get_projection(workspace_id)
        if (
            current
            and current.get("state") == "ready"
            and current.get("wechat_media_id") == values.get("wechat_media_id")
        ):
            return current
        raise RuntimeError("The uncertain WeChat draft projection could not be recovered.")
    return response.data[0]


def reset_uncertain_projection(workspace_id: str) -> dict:
    response = (
        supabase.table("wxpost_wechat_drafts")
        .update(
            {
                "wxpost_id": None,
                "state": "idle",
                "source_public_revision": None,
                "presentation": None,
                "projection_sha256": None,
                "submitted_html_sha256": None,
                "readback_html_sha256": None,
                "readback_changed": None,
                "operation_id": None,
                "add_started_at": None,
                "last_error": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("source_workspace_id", workspace_id)
        .eq("state", "uncertain")
        .is_("wechat_media_id", "null")
        .execute()
    )
    if not response.data:
        raise RuntimeError("The uncertain WeChat draft projection could not be reset.")
    return response.data[0]
