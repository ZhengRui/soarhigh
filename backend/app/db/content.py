"""Combined read model for the public Posts index."""

from __future__ import annotations

import re
from typing import Literal

from ..config import WXPOST_PUBLISHER_NAME
from .supabase import supabase

ContentKind = Literal["all", "post", "wxpost"]


def _excerpt(markdown: str, limit: int = 180) -> str:
    without_directives = re.sub(r":::[\s\S]*?:::", " ", markdown)
    plain = re.sub(r"[#*_`>\[\]()~=!-]+", " ", without_directives)
    compact = " ".join(plain.split())
    return compact if len(compact) <= limit else f"{compact[: limit - 1].rstrip()}…"


def _post_rows(*, user_id: str | None, limit: int) -> tuple[list[dict], int]:
    count_query = supabase.table("posts").select("id", count="exact")  # type: ignore
    data_query = supabase.table("posts").select("id,title,slug,content,is_public,author_id,created_at")
    if user_id is None:
        count_query = count_query.eq("is_public", True)
        data_query = data_query.eq("is_public", True)

    count = count_query.execute().count or 0
    rows = data_query.order("created_at", desc=True).limit(limit).execute().data or []

    author_ids = list({row["author_id"] for row in rows})
    authors: dict[str, str] = {}
    if author_ids:
        response = supabase.table("members").select("id,full_name").in_("id", author_ids).execute()
        authors = {author["id"]: author["full_name"] for author in response.data or []}

    items = [
        {
            "kind": "post",
            "id": row["id"],
            "title": row["title"],
            "slug": row["slug"],
            "excerpt": _excerpt(row["content"]),
            "author": {
                "member_id": row["author_id"],
                "name": authors.get(row["author_id"], ""),
            },
            "is_public": row["is_public"],
            "cover_image_url": None,
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return items, count


def _cover_url(row: dict) -> str | None:
    cover_id = row.get("cover_media_id")
    if not cover_id:
        return None
    for media in row.get("media_manifest") or []:
        if media.get("id") == cover_id and media.get("include", True):
            return media.get("sourceUrl")
    return None


def _wxpost_rows(*, limit: int) -> tuple[list[dict], int]:
    count = (
        supabase.table("wxposts")
        .select("id", count="exact")  # type: ignore
        .eq("is_public", True)
        .execute()
        .count
        or 0
    )
    rows = (
        supabase.table("wxposts")
        .select("id,title,slug,excerpt,content,is_public,media_manifest," "cover_media_id,created_at")
        .eq("is_public", True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    items = [
        {
            "kind": "wxpost",
            "id": row["id"],
            "title": row["title"],
            "slug": row["slug"],
            "excerpt": row.get("excerpt") or _excerpt(row["content"]),
            "author": {"member_id": None, "name": WXPOST_PUBLISHER_NAME},
            "is_public": True,
            "cover_image_url": _cover_url(row),
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return items, count


def get_content_items(
    *,
    kind: ContentKind,
    user_id: str | None,
    page: int,
    page_size: int,
) -> dict:
    """Merge independent sources before applying final ordering and pagination."""

    offset = (page - 1) * page_size
    source_limit = offset + page_size
    posts, post_count = _post_rows(user_id=user_id, limit=source_limit) if kind != "wxpost" else ([], 0)
    wxposts, wxpost_count = _wxpost_rows(limit=source_limit) if kind != "post" else ([], 0)

    items = sorted(posts + wxposts, key=lambda item: item["created_at"], reverse=True)
    total = post_count + wxpost_count
    return {
        "items": items[offset : offset + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0,
    }
