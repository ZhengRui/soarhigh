"""Persistence boundary for canonical WXPost source documents."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from uuid import UUID, uuid4

from postgrest.exceptions import APIError

from ..models.wxpost import ArticleDocument, WxPostPublicDetail
from ..services.wxpost_document import validate_and_parse
from .supabase import supabase


class WxPostNotFoundError(Exception):
    """Raised when an update target no longer exists."""


class WxPostRevisionConflictError(Exception):
    """Raised when a caller tries to overwrite a newer revision."""


def slugify_wxpost_title(title: str) -> str:
    """Generate the initial public locator from an English article title."""

    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
    return slug or "wxpost"


def _document_values(document: ArticleDocument) -> dict:
    return {
        "title": document.title,
        "content": document.body_markdown,
        "is_public": True,
        "schema_version": document.schema_version,
        "article_type": document.article_type.value,
        "custom_article_type": document.custom_article_type,
        "source_meeting_id": document.source_meeting_id,
        "excerpt": document.excerpt,
        "byline": document.byline,
        "media_manifest": [item.model_dump(by_alias=True, mode="json") for item in document.media],
        "cover_media_id": document.cover_media_id,
        "default_presentation": document.presentation.model_dump(by_alias=True, mode="json"),
        "render_version": 1,
    }


def _is_slug_collision(error: APIError) -> bool:
    return getattr(error, "code", None) == "23505"


def create_wxpost(document: ArticleDocument) -> dict:
    """Insert a validated article, suffixing only on a real slug collision."""

    base_slug = slugify_wxpost_title(document.title)
    values = _document_values(document)

    for attempt in range(5):
        slug = base_slug if attempt == 0 else f"{base_slug}-{uuid4().hex[:6]}"
        try:
            response = supabase.table("wxposts").insert({**values, "slug": slug}).execute()
        except APIError as error:
            if _is_slug_collision(error):
                continue
            raise
        if response.data:
            return response.data[0]

    raise RuntimeError("Could not allocate a unique WXPost slug.")


def get_wxpost_by_id(wxpost_id: UUID) -> dict | None:
    response = supabase.table("wxposts").select("*").eq("id", str(wxpost_id)).execute()
    return response.data[0] if response.data else None


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
    response = supabase.table("wxposts").select("*").eq("slug", slug).eq("is_public", True).execute()
    if not response.data:
        return None
    return public_wxpost_detail_from_row(response.data[0])
