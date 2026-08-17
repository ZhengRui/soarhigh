"""Opt-in lifecycle smoke test for real Supabase and OSS publication storage."""

from __future__ import annotations

import hashlib
import os
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

import oss2  # type: ignore
import pytest
from PIL import Image

from app.config import (
    ALICLOUD_ACCESS_KEY_ID,
    ALICLOUD_ACCESS_KEY_SECRET,
    ALICLOUD_OSS_BUCKET,
    ALICLOUD_OSS_ENDPOINT,
    SUPABASE_URL,
)
from app.db.supabase import supabase
from app.db.wxpost import get_wxpost_by_workspace_id
from app.models.wxpost import WxPostPublicationSyncRequest
from app.services.wxpost_publication import delete_public_wxpost, synchronize_workspace_publication


def _require_explicit_live_target() -> None:
    if os.getenv("WXPOST_PUBLICATION_LIVE_TEST") != "1":
        pytest.skip("Set WXPOST_PUBLICATION_LIVE_TEST=1 to run the storage smoke test.")
    if os.getenv("WXPOST_PUBLICATION_LIVE_ALLOW_MUTATION") != "yes":
        pytest.skip("Set WXPOST_PUBLICATION_LIVE_ALLOW_MUTATION=yes to allow temporary records.")
    if os.getenv("WXPOST_PUBLICATION_LIVE_SUPABASE_URL") != SUPABASE_URL:
        pytest.fail("WXPOST_PUBLICATION_LIVE_SUPABASE_URL must exactly match SUPABASE_URL.")
    if os.getenv("WXPOST_PUBLICATION_LIVE_OSS_BUCKET") != ALICLOUD_OSS_BUCKET:
        pytest.fail("WXPOST_PUBLICATION_LIVE_OSS_BUCKET must exactly match ALICLOUD_OSS_BUCKET.")


def _document(title: str, media: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "title": title,
        "excerpt": "Temporary publication lifecycle verification.",
        "byline": "SoarHigh test suite",
        "articleType": "custom",
        "customArticleType": "Storage smoke",
        "sourceMeetingId": None,
        "media": media,
        "coverMediaId": media[0]["id"] if media else None,
        "presentation": {
            "layout": "brand-default",
            "palette": "paper-neutral",
            "appearance": "light",
            "typeface": "editorial-serif",
        },
        "bodyMarkdown": (':::image\n{"media": "M01"}\n:::' if media else "Temporary live publication smoke test."),
    }


@pytest.mark.live
@pytest.mark.asyncio
async def test_real_publication_storage_lifecycle() -> None:
    """Publish, retry, replace assets, and clean up one isolated live record."""

    _require_explicit_live_target()
    workspace_id = f"wxpost-live-storage-{uuid4().hex}"
    title = f"WxPost live storage smoke {uuid4().hex[:8]}"
    media_buffer = BytesIO()
    Image.new("RGB", (64, 64), "navy").save(media_buffer, format="PNG")
    media_bytes = media_buffer.getvalue()
    media = [
        {
            "id": "M01",
            "kind": "image",
            "sourceUrl": f"https://workspace.invalid/{workspace_id}/M01",
            "description": "Temporary image for publication storage verification.",
            "include": True,
            "order": 0,
            "descriptionSource": "user",
            "descriptionStatus": "confirmed",
        }
    ]
    context: dict[str, Any] = {
        "workspaceId": workspace_id,
        "manifest": {
            "manifestVersion": 1,
            "sources": [
                {
                    "id": "M01",
                    "kind": "image",
                    "filename": "live-smoke.png",
                    "mimeType": "image/png",
                    "workspaceReady": True,
                    "contentSha256": hashlib.sha256(media_bytes).hexdigest(),
                    "origin": {"type": "meeting-library", "fileKey": f"public/meetings/{workspace_id}/M01.png"},
                }
            ],
        },
        "draft": {"draftVersion": 1, "document": _document(title, media)},
    }

    async def load_context(requested_workspace_id: str) -> dict[str, Any]:
        assert requested_workspace_id == workspace_id
        return context

    async def load_source(
        requested_workspace_id: str,
        source_id: str,
        content_sha256: str,
    ) -> tuple[bytes, str]:
        assert (requested_workspace_id, source_id) == (workspace_id, "M01")
        assert content_sha256 == hashlib.sha256(media_bytes).hexdigest()
        return media_bytes, "image/png"

    async def compile_render(render_document: dict[str, Any]) -> str:
        assert render_document["title"] == title
        return "<article>live storage smoke</article>"

    bucket = oss2.Bucket(
        oss2.Auth(ALICLOUD_ACCESS_KEY_ID, ALICLOUD_ACCESS_KEY_SECRET),
        ALICLOUD_OSS_ENDPOINT,
        ALICLOUD_OSS_BUCKET,
    )
    object_key: str | None = None
    variant_object_key: str | None = None
    try:
        first = await synchronize_workspace_publication(
            workspace_id,
            WxPostPublicationSyncRequest(expected_manifest_version=1, expected_draft_version=1),
            load_context=load_context,
            load_source=load_source,
            compile_render=compile_render,
        )
        assert first.state == "up-to-date"
        assert first.public_revision == 1

        row = get_wxpost_by_workspace_id(workspace_id)
        assert row is not None
        wxpost_id = UUID(row["id"])
        assets = (
            supabase.table("wxpost_assets")
            .select("id,object_key,status")
            .eq("wxpost_id", str(wxpost_id))
            .execute()
            .data
        )
        assert len(assets) == 1
        object_key = assets[0]["object_key"]
        assert assets[0]["status"] == "ready"
        assert bucket.object_exists(object_key)
        variants = (
            supabase.table("wxpost_asset_variants")
            .select("object_key,status,profile")
            .eq("asset_id", assets[0]["id"])
            .execute()
            .data
        )
        assert len(variants) == 1
        assert variants[0]["status"] == "ready"
        assert variants[0]["profile"] == "wechat-body-v1"
        variant_object_key = variants[0]["object_key"]
        assert bucket.object_exists(variant_object_key)

        repeated = await synchronize_workspace_publication(
            workspace_id,
            WxPostPublicationSyncRequest(
                expected_manifest_version=1,
                expected_draft_version=1,
                expected_public_revision=1,
            ),
            load_context=load_context,
            load_source=load_source,
            compile_render=compile_render,
        )
        assert repeated.public_revision == 1
        repeated_variants = (
            supabase.table("wxpost_asset_variants").select("id").eq("asset_id", assets[0]["id"]).execute().data
        )
        assert len(repeated_variants) == 1

        context["manifest"] = {"manifestVersion": 2, "sources": []}
        context["draft"] = {"draftVersion": 2, "document": _document(title, [])}
        replaced = await synchronize_workspace_publication(
            workspace_id,
            WxPostPublicationSyncRequest(
                expected_manifest_version=2,
                expected_draft_version=2,
                expected_public_revision=1,
            ),
            load_context=load_context,
            load_source=load_source,
            compile_render=compile_render,
        )
        assert replaced.public_revision == 2
        assert not bucket.object_exists(object_key)
        assert not bucket.object_exists(variant_object_key)
        remaining_assets = supabase.table("wxpost_assets").select("id").eq("wxpost_id", str(wxpost_id)).execute().data
        assert remaining_assets == []
        remaining_variants = (
            supabase.table("wxpost_asset_variants").select("id").eq("asset_id", assets[0]["id"]).execute().data
        )
        assert remaining_variants == []

        deleted_workspace_id = await delete_public_wxpost(wxpost_id, expected_revision=2)
        assert deleted_workspace_id == workspace_id
        assert get_wxpost_by_workspace_id(workspace_id) is None
    finally:
        row = get_wxpost_by_workspace_id(workspace_id)
        if row is not None:
            await delete_public_wxpost(UUID(row["id"]), expected_revision=row["article_revision"])
        if object_key is not None and bucket.object_exists(object_key):
            bucket.delete_object(object_key)
        if variant_object_key is not None and bucket.object_exists(variant_object_key):
            bucket.delete_object(variant_object_key)
