"""Persistence boundary for canonical WxPost source documents."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from uuid import UUID, uuid4

from postgrest.exceptions import APIError

from ..models.wxpost import ArticleDocument, ArticleType, WxPostPublicDetail
from ..services.wxpost_document import validate_and_parse
from .supabase import supabase


class WxPostNotFoundError(Exception):
    """Raised when an update target no longer exists."""


class WxPostRevisionConflictError(Exception):
    """Raised when a caller tries to overwrite a newer revision."""


class WxPostAssetConflictError(Exception):
    """Raised when an asset idempotency key resolves to different content."""


def slugify_wxpost_title(title: str) -> str:
    """Generate the initial public locator from an English article title."""

    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
    return slug or "wxpost"


def _document_values(document: ArticleDocument) -> dict:
    custom_article_type = document.custom_article_type
    if document.article_type == ArticleType.CUSTOM and custom_article_type is None:
        custom_article_type = "Custom"
    return {
        "title": document.title,
        "content": document.body_markdown,
        "is_public": True,
        "schema_version": document.schema_version,
        "article_type": document.article_type.value,
        "custom_article_type": custom_article_type,
        "source_meeting_id": document.source_meeting_id,
        "excerpt": document.excerpt,
        "byline": document.byline,
        "media_manifest": [item.model_dump(by_alias=True, mode="json") for item in document.media],
        "cover_media_id": document.cover_media_id,
        "default_presentation": document.presentation.model_dump(by_alias=True, mode="json"),
        "render_version": 1,
    }


def _is_unique_violation(error: APIError) -> bool:
    return getattr(error, "code", None) == "23505"


def create_wxpost(document: ArticleDocument) -> dict:
    """Insert a validated article, suffixing only on a real slug collision."""

    base_slug = slugify_wxpost_title(document.title)
    values = _document_values(document)

    for attempt in range(5):
        slug = base_slug if attempt == 0 else f"{base_slug}-{uuid4().hex[:6]}"
        try:
            response = supabase.table("wxposts").insert({**values, "slug": slug, "status": "ready"}).execute()
        except APIError as error:
            if _is_unique_violation(error):
                continue
            raise
        if response.data:
            return response.data[0]

    raise RuntimeError("Could not allocate a unique WxPost slug.")


def get_wxpost_by_id(wxpost_id: UUID) -> dict | None:
    response = supabase.table("wxposts").select("*").eq("id", str(wxpost_id)).execute()
    return response.data[0] if response.data else None


def get_wxpost_by_workspace_id(workspace_id: str) -> dict | None:
    response = supabase.table("wxposts").select("*").eq("source_workspace_id", workspace_id).execute()
    return response.data[0] if response.data else None


def get_wxposts_by_workspace_ids(workspace_ids: list[str]) -> list[dict]:
    if not workspace_ids:
        return []
    response = (
        supabase.table("wxposts")
        .select(
            "id,slug,status,is_public,article_revision,source_workspace_id,"
            "source_draft_version,source_draft_sha256,updated_at"
        )
        .in_("source_workspace_id", workspace_ids)
        .execute()
    )
    return response.data or []


def create_publication_shell(
    *,
    workspace_id: str,
    draft_version: int,
    draft_sha256: str,
    document: ArticleDocument,
) -> dict:
    """Create one hidden publication owner before its first asset upload."""

    existing = get_wxpost_by_workspace_id(workspace_id)
    if existing is not None:
        return existing

    base_slug = slugify_wxpost_title(document.title)
    values = _document_values(document)
    values.update(
        {
            "content": None,
            "is_public": False,
            "status": "assembling",
            "source_workspace_id": workspace_id,
            "source_draft_version": draft_version,
            "source_draft_sha256": draft_sha256,
        }
    )
    for attempt in range(5):
        slug = base_slug if attempt == 0 else f"{base_slug}-{uuid4().hex[:6]}"
        try:
            response = supabase.table("wxposts").insert({**values, "slug": slug}).execute()
        except APIError as error:
            concurrent = get_wxpost_by_workspace_id(workspace_id)
            if concurrent is not None:
                return concurrent
            if _is_unique_violation(error):
                continue
            raise
        if response.data:
            return response.data[0]
    raise RuntimeError("Could not allocate a unique WxPost slug.")


def get_ready_wxpost_asset(
    wxpost_id: UUID,
    *,
    content_sha256: str,
    kind: str,
) -> dict | None:
    response = (
        supabase.table("wxpost_assets")
        .select("*")
        .eq("wxpost_id", str(wxpost_id))
        .eq("content_sha256", content_sha256)
        .eq("kind", kind)
        .eq("status", "ready")
        .execute()
    )
    return response.data[0] if response.data else None


def get_ready_wxpost_assets(wxpost_id: UUID) -> list[dict]:
    """Return immutable public asset metadata for one ready WxPost."""

    response = (
        supabase.table("wxpost_assets")
        .select("object_key,content_sha256,size_bytes,kind")
        .eq("wxpost_id", str(wxpost_id))
        .eq("status", "ready")
        .execute()
    )
    return response.data or []


def create_pending_wxpost_asset(values: dict) -> dict:
    """Create or recover one idempotent pending public asset row."""

    try:
        response = supabase.table("wxpost_assets").insert(values).execute()
    except APIError as error:
        if not _is_unique_violation(error):
            raise
        response = (
            supabase.table("wxpost_assets")
            .select("*")
            .eq("wxpost_id", values["wxpost_id"])
            .eq(
                "upload_idempotency_key_hash",
                values["upload_idempotency_key_hash"],
            )
            .execute()
        )
        if not response.data:
            raise
        current = response.data[0]
        if current["upload_request_hash"] != values["upload_request_hash"]:
            raise WxPostAssetConflictError from error
        return current
    if not response.data:
        raise RuntimeError("Supabase did not return the pending WxPost asset.")
    return response.data[0]


def mark_wxpost_asset_ready(asset_id: UUID, *, etag: str) -> dict:
    response = (
        supabase.table("wxpost_assets")
        .update(
            {
                "status": "ready",
                "etag": etag,
                "ready_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("id", str(asset_id))
        .eq("status", "pending")
        .execute()
    )
    if response.data:
        return response.data[0]
    current = supabase.table("wxpost_assets").select("*").eq("id", str(asset_id)).execute()
    if current.data and current.data[0].get("status") == "ready":
        return current.data[0]
    raise RuntimeError("WxPost asset could not be marked ready.")


def mark_wxpost_asset_failed(asset_id: UUID) -> None:
    (
        supabase.table("wxpost_assets")
        .update({"status": "failed"})
        .eq("id", str(asset_id))
        .eq("status", "pending")
        .execute()
    )


def retry_inactive_wxpost_asset(asset_id: UUID) -> dict:
    response = (
        supabase.table("wxpost_assets")
        .update({"status": "pending", "abandoned_at": None})
        .eq("id", str(asset_id))
        .in_("status", ["failed", "abandoned"])
        .execute()
    )
    if not response.data:
        raise RuntimeError("Inactive WxPost asset could not be retried.")
    return response.data[0]


def abandon_unreferenced_wxpost_assets(
    wxpost_id: UUID,
    *,
    keep_content_sha256: set[str],
) -> list[dict]:
    response = (
        supabase.table("wxpost_assets")
        .select("id,content_sha256,status,object_key,poster_object_key")
        .eq("wxpost_id", str(wxpost_id))
        .in_("status", ["pending", "ready", "failed", "abandoned"])
        .execute()
    )
    stale = [row for row in response.data or [] if row.get("content_sha256") not in keep_content_sha256]
    stale_ids = [row["id"] for row in stale if row.get("status") != "abandoned"]
    if not stale_ids:
        return stale
    supabase.table("wxpost_assets").update(
        {
            "status": "abandoned",
            "abandoned_at": datetime.now(timezone.utc).isoformat(),
        }
    ).in_("id", stale_ids).execute()
    return stale


def delete_wxpost_assets(asset_ids: list[str]) -> None:
    if not asset_ids:
        return
    supabase.table("wxpost_assets").delete().in_("id", asset_ids).execute()


def has_abandoned_wxpost_assets(wxpost_id: UUID) -> bool:
    response = (
        supabase.table("wxpost_assets").select("id").eq("wxpost_id", str(wxpost_id)).eq("status", "abandoned").execute()
    )
    return bool(response.data)


def begin_wxpost_deletion(
    wxpost_id: UUID,
    *,
    expected_revision: int,
) -> dict:
    """Hide one public row before deleting its external assets."""

    response = (
        supabase.table("wxposts")
        .update(
            {
                "status": "assembling",
                "is_public": False,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("id", str(wxpost_id))
        .eq("article_revision", expected_revision)
        .eq("status", "ready")
        .execute()
    )
    if response.data:
        return response.data[0]
    current = get_wxpost_by_id(wxpost_id)
    if current is None:
        raise WxPostNotFoundError
    if current.get("article_revision") == expected_revision and current.get("status") == "assembling":
        return current
    raise WxPostRevisionConflictError


def delete_hidden_wxpost(
    wxpost_id: UUID,
    *,
    expected_revision: int,
) -> None:
    response = (
        supabase.table("wxposts")
        .delete()
        .eq("id", str(wxpost_id))
        .eq("article_revision", expected_revision)
        .eq("status", "assembling")
        .execute()
    )
    if response.data:
        return
    if get_wxpost_by_id(wxpost_id) is None:
        return
    raise WxPostRevisionConflictError


def finalize_workspace_publication(
    wxpost_id: UUID,
    *,
    workspace_id: str,
    expected_revision: int,
    expected_status: str,
    next_revision: int,
    draft_version: int,
    draft_sha256: str,
    document: ArticleDocument,
) -> dict:
    """Expose one complete public revision with a single guarded row update."""

    values = _document_values(document)
    values.update(
        {
            "status": "ready",
            "is_public": True,
            "source_workspace_id": workspace_id,
            "source_draft_version": draft_version,
            "source_draft_sha256": draft_sha256,
            "finalize_request_hash": draft_sha256,
            "article_revision": next_revision,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    response = (
        supabase.table("wxposts")
        .update(values)
        .eq("id", str(wxpost_id))
        .eq("source_workspace_id", workspace_id)
        .eq("article_revision", expected_revision)
        .eq("status", expected_status)
        .execute()
    )
    if response.data:
        return response.data[0]
    if get_wxpost_by_id(wxpost_id) is None:
        raise WxPostNotFoundError
    raise WxPostRevisionConflictError


def update_wxpost(
    wxpost_id: UUID,
    *,
    expected_revision: int,
    document: ArticleDocument,
) -> dict:
    """Atomically replace content when the caller still owns the revision."""

    values = _document_values(document)
    values.pop("is_public")
    values.update(
        {
            "article_revision": expected_revision + 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    response = (
        supabase.table("wxposts")
        .update(values)
        .eq("id", str(wxpost_id))
        .eq("article_revision", expected_revision)
        .is_("source_workspace_id", "null")
        .execute()
    )
    if response.data:
        return response.data[0]

    if get_wxpost_by_id(wxpost_id) is None:
        raise WxPostNotFoundError
    raise WxPostRevisionConflictError


def article_document_from_row(row: dict) -> ArticleDocument:
    """Reconstruct the sole editable document from one persisted row."""

    return ArticleDocument.model_validate(
        {
            "schemaVersion": row["schema_version"],
            "title": row["title"],
            "slug": row["slug"],
            "excerpt": row.get("excerpt"),
            "byline": row.get("byline"),
            "articleType": row["article_type"],
            "customArticleType": row.get("custom_article_type"),
            "sourceMeetingId": row.get("source_meeting_id"),
            "media": row.get("media_manifest") or [],
            "coverMediaId": row.get("cover_media_id"),
            "presentation": row["default_presentation"],
            "bodyMarkdown": row["content"],
        }
    )


def _context_label(document: ArticleDocument) -> str:
    if document.custom_article_type:
        return document.custom_article_type
    return document.article_type.value.replace("-", " ").title()


def public_wxpost_detail_from_row(row: dict) -> WxPostPublicDetail:
    document = article_document_from_row(row)
    parsed = validate_and_parse(document)
    return WxPostPublicDetail(
        id=row["id"],
        slug=row["slug"],
        is_public=True,
        article_revision=row["article_revision"],
        context_label=_context_label(document),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        render_document=parsed.render_document(document),
    )


def get_public_wxpost_by_slug(slug: str) -> WxPostPublicDetail | None:
    response = (
        supabase.table("wxposts").select("*").eq("slug", slug).eq("status", "ready").eq("is_public", True).execute()
    )
    if not response.data:
        return None
    return public_wxpost_detail_from_row(response.data[0])
