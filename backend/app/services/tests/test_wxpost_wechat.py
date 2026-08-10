from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID

import httpx
import pytest

from app.models.wxpost import Presentation, WxPostRenderDocument
from app.services import wxpost_wechat

WXPOST_ID = UUID("00000000-0000-4000-8000-000000000888")
IMAGE_URL = "https://cdn.example.com/article.jpg"
WECHAT_IMAGE_URL = "https://mmbiz.qpic.cn/example/article.jpg"
IMAGE_SHA256 = hashlib.sha256(b"image-bytes").hexdigest()
IMAGE_OBJECT_KEY = f"public/wxposts/{WXPOST_ID}/assets/image/original.jpg"


def _render_document(*, video: bool = False) -> WxPostRenderDocument:
    body: list[dict] = [{"kind": "markdown", "source": "Hello", "line": 1}]
    media = [
        {
            "id": "M01",
            "kind": "image",
            "sourceUrl": IMAGE_URL,
            "description": "Article image",
            "include": True,
            "order": 0,
            "descriptionSource": "user",
            "descriptionStatus": "confirmed",
        }
    ]
    if video:
        body.append({"kind": "directive", "name": "video", "payload": {"media": "V01"}, "line": 2})
        media.append(
            {
                "id": "V01",
                "kind": "video",
                "sourceUrl": "https://cdn.example.com/video.mp4",
                "description": "Video",
                "include": True,
                "order": 1,
                "descriptionSource": "user",
                "descriptionStatus": "confirmed",
            }
        )
    return WxPostRenderDocument.model_validate(
        {
            "schemaVersion": 1,
            "renderVersion": 1,
            "title": "A WeChat Draft",
            "excerpt": "A deterministic projection.",
            "byline": "SoarHigh",
            "articleType": "custom",
            "customArticleType": "Test",
            "media": media,
            "coverMediaId": "M01",
            "presentation": {
                "layout": "brand-default",
                "palette": "paper-neutral",
                "appearance": "light",
                "typeface": "modern-sans",
            },
            "body": body,
        }
    )


class FakeWechatApi:
    def __init__(
        self,
        *,
        fail_add: bool = False,
        accept_on_timeout: bool = False,
        fail_first_readback: bool = False,
        invalid_cover_once: bool = False,
        preview_url: str = "https://mp.weixin.qq.com/s/example-preview",
        batch_items: list[dict] | None = None,
    ) -> None:
        self.fail_add = fail_add
        self.accept_on_timeout = accept_on_timeout
        self.fail_first_readback = fail_first_readback
        self.invalid_cover_once = invalid_cover_once
        self.preview_url = preview_url
        self.batch_items = batch_items
        self.body_uploads = 0
        self.cover_uploads = 0
        self.adds = 0
        self.updates = 0
        self.readbacks = 0
        self.article: dict | None = None
        self.current_media_id = "wechat-draft-id"
        self.remote_missing = False

    async def close(self) -> None:
        return None

    async def upload_body_image(self, source: wxpost_wechat.WechatAssetSource) -> str:
        self.body_uploads += 1
        assert source == wxpost_wechat.WechatAssetSource(
            object_key=IMAGE_OBJECT_KEY,
            sha256=IMAGE_SHA256,
            size_bytes=len(b"image-bytes"),
        )
        return WECHAT_IMAGE_URL

    async def upload_cover(self, source: wxpost_wechat.WechatAssetSource) -> str:
        self.cover_uploads += 1
        assert source.object_key == IMAGE_OBJECT_KEY
        return "replacement-cover-media-id" if self.cover_uploads > 1 else "cover-media-id"

    async def add_draft(self, article: dict) -> str:
        self.adds += 1
        if self.invalid_cover_once and article.get("thumb_media_id") == "cover-media-id":
            raise wxpost_wechat.WechatDraftError(
                "invalid media_id",
                wechat_errcode=40007,
            )
        if self.fail_add:
            if self.accept_on_timeout:
                self.article = article
            raise wxpost_wechat.WechatDraftError("response lost", uncertain=True)
        self.article = article
        self.current_media_id = "wechat-replacement-id" if self.adds > 1 else "wechat-draft-id"
        self.remote_missing = False
        return self.current_media_id

    async def update_draft(self, media_id: str, article: dict) -> None:
        assert media_id == self.current_media_id
        self.updates += 1
        if self.invalid_cover_once and article.get("thumb_media_id") == "cover-media-id":
            raise wxpost_wechat.WechatDraftError(
                "invalid media_id",
                wechat_errcode=40007,
            )
        if self.remote_missing:
            raise wxpost_wechat.WechatDraftError(
                "invalid media_id",
                wechat_errcode=40007,
            )
        self.article = article

    async def get_draft(self, media_id: str) -> dict:
        assert media_id == self.current_media_id
        self.readbacks += 1
        if self.remote_missing:
            raise wxpost_wechat.WechatDraftError(
                "invalid media_id",
                wechat_errcode=40007,
            )
        if self.fail_first_readback and self.readbacks == 1:
            raise wxpost_wechat.WechatDraftError("readback unavailable")
        return {
            "content": self.article["content"] if self.article else "<p>readback</p>",
            "url": self.preview_url,
        }

    async def batch_get_drafts(self, *, count: int = 20) -> list[dict]:
        assert count == 20
        if self.batch_items is not None:
            return self.batch_items
        if not self.article:
            return []
        return [
            {
                "media_id": self.current_media_id,
                "content": {"news_item": [self.article]},
            }
        ]


@pytest.fixture
def projection_store(monkeypatch: pytest.MonkeyPatch) -> dict:
    state: dict = {}

    def claim_projection(**values):
        current = state.get("row")
        if current and current["state"] == "ready" and current["projection_sha256"] == values["projection_sha256"]:
            return {"acquired": False, "reason": "unchanged", "row": deepcopy(current)}
        if current and current["state"] in {"creating", "uncertain"}:
            return {
                "acquired": False,
                "reason": (current["state"] == "creating" and "busy") or "uncertain",
                "row": deepcopy(current),
            }
        row = {
            **(current or {}),
            "source_workspace_id": values["workspace_id"],
            "wxpost_id": str(values["wxpost_id"]),
            "state": "creating",
            "source_public_revision": values["revision"],
            "presentation": values["presentation"],
            "projection_sha256": values["projection_sha256"],
            "operation_id": str(values["operation_id"]),
            "add_started_at": None,
            "asset_mappings": (current or {}).get("asset_mappings", {}),
        }
        state["row"] = row
        return {"acquired": True, "reason": "claimed", "row": deepcopy(row)}

    def update_projection(workspace_id, operation_id, values):
        assert state["row"]["source_workspace_id"] == workspace_id
        assert state["row"]["operation_id"] == str(operation_id)
        state["row"].update(values)
        return deepcopy(state["row"])

    def mark_ready(workspace_id, operation_id, **values):
        media_id = values.pop("media_id")
        return update_projection(
            workspace_id,
            operation_id,
            {
                "state": "ready",
                "wechat_media_id": media_id,
                "add_started_at": None,
                **values,
            },
        )

    def mark_failed(workspace_id, operation_id, *, uncertain, message):
        update_projection(
            workspace_id,
            operation_id,
            {"state": "uncertain" if uncertain else "idle", "last_error": message},
        )

    def save_asset_mappings(workspace_id, operation_id, mappings):
        return update_projection(workspace_id, operation_id, {"asset_mappings": mappings})

    def mark_add_started(workspace_id, operation_id):
        state["add_started_calls"] = state.get("add_started_calls", 0) + 1
        return update_projection(
            workspace_id,
            operation_id,
            {"add_started_at": datetime.now(timezone.utc).isoformat()},
        )

    def mark_replacement_add_started(workspace_id, operation_id):
        state["replacement_add_started_calls"] = state.get("replacement_add_started_calls", 0) + 1
        return update_projection(
            workspace_id,
            operation_id,
            {
                "wechat_media_id": None,
                "submitted_html_sha256": None,
                "readback_html_sha256": None,
                "readback_changed": None,
                "add_started_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def clear_confirmed_missing_projection(
        workspace_id,
        *,
        media_id,
        projection_sha256,
        asset_mappings,
    ):
        row = state.get("row")
        if (
            not row
            or row["source_workspace_id"] != workspace_id
            or row["state"] not in {"idle", "ready"}
            or row.get("wechat_media_id") != media_id
            or row.get("projection_sha256") != projection_sha256
        ):
            return None
        row.update(
            {
                "state": "idle",
                "wechat_media_id": None,
                "submitted_html_sha256": None,
                "readback_html_sha256": None,
                "readback_changed": None,
                "asset_mappings": asset_mappings,
            }
        )
        return deepcopy(row)

    def recover_uncertain(workspace_id, values):
        assert state["row"]["state"] == "uncertain"
        state["row"].update({"state": "ready", **values})
        return deepcopy(state["row"])

    monkeypatch.setattr(wxpost_wechat.store, "claim_projection", claim_projection)
    monkeypatch.setattr(wxpost_wechat.store, "save_asset_mappings", save_asset_mappings)
    monkeypatch.setattr(wxpost_wechat.store, "mark_add_started", mark_add_started)
    monkeypatch.setattr(
        wxpost_wechat.store,
        "mark_replacement_add_started",
        mark_replacement_add_started,
    )
    monkeypatch.setattr(
        wxpost_wechat.store,
        "clear_confirmed_missing_projection",
        clear_confirmed_missing_projection,
    )
    monkeypatch.setattr(wxpost_wechat.store, "update_projection", update_projection)
    monkeypatch.setattr(wxpost_wechat.store, "mark_projection_ready", mark_ready)
    monkeypatch.setattr(wxpost_wechat.store, "mark_projection_failed", mark_failed)
    monkeypatch.setattr(wxpost_wechat.store, "recover_uncertain_projection", recover_uncertain)
    monkeypatch.setattr(wxpost_wechat.store, "get_projection", lambda workspace_id: deepcopy(state.get("row")))
    monkeypatch.setattr(
        wxpost_wechat,
        "get_ready_wxpost_assets",
        lambda wxpost_id: [
            {
                "object_key": IMAGE_OBJECT_KEY,
                "content_sha256": IMAGE_SHA256,
                "size_bytes": len(b"image-bytes"),
                "kind": "image",
                "variants": [
                    {
                        "profile": wxpost_wechat.WECHAT_BODY_PROFILE,
                        "object_key": IMAGE_OBJECT_KEY,
                        "content_sha256": IMAGE_SHA256,
                        "size_bytes": len(b"image-bytes"),
                    }
                ],
            }
        ],
    )
    monkeypatch.setattr(wxpost_wechat, "public_asset_url", lambda object_key: IMAGE_URL)
    return state


async def _publish(
    api: FakeWechatApi,
    *,
    render_document: WxPostRenderDocument | None = None,
    html: str = (
        f'<article data-testid="article" data-wxpost-line="1" data-layout="brand-default" style="color:#123">'
        f'<p contenteditable="true"><a href="{IMAGE_URL}">Source</a>'
        f'<img src="{IMAGE_URL}"></p></article>'
    ),
):
    document = render_document or _render_document()
    return await wxpost_wechat.publish_wechat_draft(
        row={
            "id": str(WXPOST_ID),
            "source_workspace_id": "wxpost-test",
            "article_revision": 3,
        },
        render_document=document,
        presentation=Presentation.model_validate(document.presentation.model_dump()),
        canonical_html=html,
        api=api,
    )


async def test_missing_variant_fails_before_projection_claim_or_remote_upload(
    projection_store: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        wxpost_wechat,
        "get_ready_wxpost_assets",
        lambda wxpost_id: [
            {
                "id": "asset-image",
                "object_key": IMAGE_OBJECT_KEY,
                "original_filename": "poster.jpg",
                "content_sha256": IMAGE_SHA256,
                "size_bytes": len(b"image-bytes"),
                "kind": "image",
                "source_metadata": {"sourceId": "M01"},
                "variants": [],
            }
        ],
    )
    monkeypatch.setattr(
        wxpost_wechat.store,
        "claim_projection",
        lambda **kwargs: pytest.fail("projection was claimed before image preflight"),
    )
    api = FakeWechatApi()

    with pytest.raises(wxpost_wechat.WechatDraftError, match=r"M01 / poster.jpg.*missing") as raised:
        await _publish(api)

    assert raised.value.status_code == 409
    assert api.body_uploads == 0
    assert api.cover_uploads == 0
    assert projection_store == {}


async def test_oversized_variant_fails_before_projection_claim(
    projection_store: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        wxpost_wechat,
        "get_ready_wxpost_assets",
        lambda wxpost_id: [
            {
                "object_key": IMAGE_OBJECT_KEY,
                "original_filename": "poster.jpg",
                "content_sha256": IMAGE_SHA256,
                "size_bytes": len(b"image-bytes"),
                "kind": "image",
                "source_metadata": {"sourceId": "M01"},
                "variants": [
                    {
                        "profile": wxpost_wechat.WECHAT_BODY_PROFILE,
                        "object_key": f"{IMAGE_OBJECT_KEY}.wechat.jpg",
                        "content_sha256": "b" * 64,
                        "size_bytes": wxpost_wechat.WECHAT_BODY_HARD_MAX_BYTES + 1,
                    }
                ],
            }
        ],
    )
    monkeypatch.setattr(
        wxpost_wechat.store,
        "claim_projection",
        lambda **kwargs: pytest.fail("projection was claimed before size preflight"),
    )

    with pytest.raises(wxpost_wechat.WechatDraftError, match=r"M01 / poster.jpg.*exceeds") as raised:
        await _publish(FakeWechatApi())

    assert raised.value.status_code == 422
    assert projection_store == {}


async def test_body_uses_variant_descriptor_while_cover_keeps_original(
    projection_store: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variant_content = b"wechat-variant"
    variant_sha = hashlib.sha256(variant_content).hexdigest()
    variant_key = f"public/wxposts/{WXPOST_ID}/assets/image/variants/wechat-body-v1.jpg"
    monkeypatch.setattr(
        wxpost_wechat,
        "get_ready_wxpost_assets",
        lambda wxpost_id: [
            {
                "id": "asset-image",
                "object_key": IMAGE_OBJECT_KEY,
                "original_filename": "poster.jpg",
                "content_sha256": IMAGE_SHA256,
                "size_bytes": len(b"image-bytes"),
                "kind": "image",
                "source_metadata": {"sourceId": "M01"},
                "variants": [
                    {
                        "profile": wxpost_wechat.WECHAT_BODY_PROFILE,
                        "object_key": variant_key,
                        "content_sha256": variant_sha,
                        "size_bytes": len(variant_content),
                    }
                ],
            }
        ],
    )

    class VariantApi(FakeWechatApi):
        async def upload_body_image(self, source):
            self.body_uploads += 1
            assert source == wxpost_wechat.WechatAssetSource(
                object_key=variant_key,
                sha256=variant_sha,
                size_bytes=len(variant_content),
            )
            return WECHAT_IMAGE_URL

    api = VariantApi()
    result = await _publish(api)

    assert result.action == "created"
    assert api.body_uploads == 1
    assert api.cover_uploads == 1
    assert projection_store["row"]["asset_mappings"] == {
        f"body:{variant_sha}": WECHAT_IMAGE_URL,
        f"cover:{IMAGE_SHA256}": "cover-media-id",
    }


async def test_oversized_original_cover_uses_the_safe_variant(
    projection_store: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variant_content = b"wechat-variant"
    variant_sha = hashlib.sha256(variant_content).hexdigest()
    variant_key = f"public/wxposts/{WXPOST_ID}/assets/image/variants/wechat-body-v1.jpg"
    monkeypatch.setattr(
        wxpost_wechat,
        "get_ready_wxpost_assets",
        lambda wxpost_id: [
            {
                "object_key": IMAGE_OBJECT_KEY,
                "content_sha256": IMAGE_SHA256,
                "size_bytes": wxpost_wechat.WECHAT_COVER_HARD_MAX_BYTES + 1,
                "kind": "image",
                "variants": [
                    {
                        "profile": wxpost_wechat.WECHAT_BODY_PROFILE,
                        "object_key": variant_key,
                        "content_sha256": variant_sha,
                        "size_bytes": len(variant_content),
                    }
                ],
            }
        ],
    )

    class VariantCoverApi(FakeWechatApi):
        async def upload_body_image(self, source):
            self.body_uploads += 1
            assert source.object_key == variant_key
            return WECHAT_IMAGE_URL

        async def upload_cover(self, source):
            self.cover_uploads += 1
            assert source.object_key == variant_key
            return "cover-media-id"

    result = await _publish(VariantCoverApi())

    assert result.action == "created"
    assert projection_store["row"]["asset_mappings"] == {
        f"body:{variant_sha}": WECHAT_IMAGE_URL,
        f"cover:{variant_sha}": "cover-media-id",
    }


def test_video_is_blocked_without_rewriting_content() -> None:
    with pytest.raises(wxpost_wechat.WechatDraftError, match="Video block") as caught:
        wxpost_wechat.validate_wechat_projection(_render_document(video=True))
    assert caught.value.status_code == 422


@pytest.mark.parametrize(
    ("byline", "expected_author"),
    [(None, "Soarhigh TMC"), ("Guest Editor", "Guest Editor")],
)
def test_article_author_defaults_without_overriding_an_explicit_byline(
    monkeypatch: pytest.MonkeyPatch,
    byline: str | None,
    expected_author: str,
) -> None:
    monkeypatch.setattr(wxpost_wechat, "WECHAT_ARTICLE_AUTHOR", "Soarhigh TMC")
    render_document = _render_document().model_copy(update={"byline": byline})

    article = wxpost_wechat._article_payload(render_document, "<p>Body</p>", "cover-media-id")

    assert article["author"] == expected_author


async def test_default_author_change_updates_the_existing_projection(
    projection_store: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    render_document = _render_document().model_copy(update={"byline": None})
    api = FakeWechatApi()
    monkeypatch.setattr(wxpost_wechat, "WECHAT_ARTICLE_AUTHOR", "Soarhigh TMC")

    created = await _publish(api, render_document=render_document)
    first_projection = projection_store["row"]["projection_sha256"]
    monkeypatch.setattr(wxpost_wechat, "WECHAT_ARTICLE_AUTHOR", "Soarhigh TMC 2")
    updated = await _publish(api, render_document=render_document)

    assert created.action == "created"
    assert updated.action == "updated"
    assert projection_store["row"]["projection_sha256"] != first_projection
    assert api.article is not None
    assert api.article["author"] == "Soarhigh TMC 2"


async def test_create_uploads_media_replaces_oss_url_and_reads_back(projection_store: dict) -> None:
    api = FakeWechatApi()
    result = await _publish(api)

    assert result.action == "created"
    assert str(result.preview_url) == "https://mp.weixin.qq.com/s/example-preview"
    assert result.readback_changed is False
    assert api.body_uploads == 1
    assert api.cover_uploads == 1
    assert api.adds == 1
    assert api.updates == 0
    assert api.article is not None
    assert f'<a href="{IMAGE_URL}">' not in api.article["content"]
    assert "Source" in api.article["content"]
    assert f'<img src="{WECHAT_IMAGE_URL}">' in api.article["content"]
    assert "data-testid=" not in api.article["content"]
    assert "data-wxpost-line=" not in api.article["content"]
    assert "data-layout=" not in api.article["content"]
    assert "contenteditable=" not in api.article["content"]
    assert 'style="text-align:left!important;color:#123"' in api.article["content"]
    assert api.article["thumb_media_id"] == "cover-media-id"
    assert projection_store["row"]["state"] == "ready"
    assert projection_store["row"]["wechat_media_id"] == "wechat-draft-id"
    assert projection_store["add_started_calls"] == 1
    assert projection_store["row"]["add_started_at"] is None


async def test_publish_rejects_an_image_without_a_ready_public_asset(
    projection_store: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wxpost_wechat, "get_ready_wxpost_assets", lambda wxpost_id: [])

    with pytest.raises(wxpost_wechat.WechatDraftError, match="not backed by a ready public asset") as caught:
        await _publish(FakeWechatApi())

    assert caught.value.status_code == 409
    assert "row" not in projection_store


async def test_publish_rejects_incomplete_public_asset_metadata(
    projection_store: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        wxpost_wechat,
        "get_ready_wxpost_assets",
        lambda wxpost_id: [
            {
                "object_key": IMAGE_OBJECT_KEY,
                "content_sha256": "invalid",
                "size_bytes": len(b"image-bytes"),
                "kind": "image",
            }
        ],
    )

    with pytest.raises(wxpost_wechat.WechatDraftError, match="incomplete asset metadata") as caught:
        await _publish(FakeWechatApi())

    assert caught.value.status_code == 409
    assert "row" not in projection_store


async def test_publish_ignores_invalid_metadata_for_an_unreferenced_ready_asset(
    projection_store: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unrelated_key = f"public/wxposts/{WXPOST_ID}/assets/image/unrelated.jpg"
    monkeypatch.setattr(
        wxpost_wechat,
        "get_ready_wxpost_assets",
        lambda wxpost_id: [
            {
                "object_key": unrelated_key,
                "content_sha256": "invalid",
                "size_bytes": 0,
                "kind": "image",
            },
            {
                "object_key": IMAGE_OBJECT_KEY,
                "content_sha256": IMAGE_SHA256,
                "size_bytes": len(b"image-bytes"),
                "kind": "image",
                "variants": [
                    {
                        "profile": wxpost_wechat.WECHAT_BODY_PROFILE,
                        "object_key": IMAGE_OBJECT_KEY,
                        "content_sha256": IMAGE_SHA256,
                        "size_bytes": len(b"image-bytes"),
                    }
                ],
            },
        ],
    )
    monkeypatch.setattr(
        wxpost_wechat,
        "public_asset_url",
        lambda object_key: IMAGE_URL if object_key == IMAGE_OBJECT_KEY else "https://cdn.example.com/unrelated.jpg",
    )

    assert (await _publish(FakeWechatApi())).action == "created"


async def test_identical_retry_is_read_only_and_changed_projection_updates_same_draft(projection_store: dict) -> None:
    api = FakeWechatApi()
    first = await _publish(api)
    unchanged = await _publish(api)
    updated = await _publish(api, html=f'<p>Changed<img src="{IMAGE_URL}"></p>')

    assert first.action == "created"
    assert unchanged.action == "unchanged"
    assert updated.action == "updated"
    assert api.adds == 1
    assert api.updates == 1
    assert api.body_uploads == 1
    assert api.cover_uploads == 1


async def test_changed_publish_replaces_a_draft_confirmed_deleted_in_wechat(
    projection_store: dict,
) -> None:
    api = FakeWechatApi()
    await _publish(api)
    api.remote_missing = True

    replaced = await _publish(
        api,
        html=f'<p>Changed<img src="{IMAGE_URL}"></p>',
    )

    assert replaced.action == "created"
    assert api.updates == 1
    assert api.adds == 2
    assert api.body_uploads == 1
    assert api.cover_uploads == 2
    assert projection_store["replacement_add_started_calls"] == 1
    assert projection_store["row"]["wechat_media_id"] == "wechat-replacement-id"
    assert projection_store["row"]["state"] == "ready"


async def test_update_refreshes_an_invalid_cover_when_the_draft_still_exists(
    projection_store: dict,
) -> None:
    api = FakeWechatApi()
    await _publish(api)
    api.invalid_cover_once = True

    updated = await _publish(
        api,
        html=f'<p>Changed<img src="{IMAGE_URL}"></p>',
    )

    assert updated.action == "updated"
    assert api.updates == 2
    assert api.adds == 1
    assert api.cover_uploads == 2
    assert projection_store["row"]["wechat_media_id"] == "wechat-draft-id"
    assert projection_store["row"]["state"] == "ready"


async def test_create_reuploads_a_cover_rejected_as_an_invalid_media_id(
    projection_store: dict,
) -> None:
    api = FakeWechatApi(invalid_cover_once=True)

    result = await _publish(api)

    assert result.action == "created"
    assert api.adds == 2
    assert api.cover_uploads == 2
    assert projection_store["row"]["state"] == "ready"


async def test_identical_publish_replaces_a_draft_confirmed_deleted_in_wechat(
    projection_store: dict,
) -> None:
    api = FakeWechatApi()
    await _publish(api)
    api.remote_missing = True

    replaced = await _publish(api)

    assert replaced.action == "created"
    assert api.updates == 0
    assert api.adds == 2
    assert api.body_uploads == 1
    assert api.cover_uploads == 2
    assert projection_store["row"]["wechat_media_id"] == "wechat-replacement-id"
    assert projection_store["row"]["state"] == "ready"


async def test_retry_repairs_readback_after_add_succeeded(projection_store: dict) -> None:
    api = FakeWechatApi(fail_first_readback=True)
    with pytest.raises(wxpost_wechat.WechatDraftError, match="readback unavailable"):
        await _publish(api)
    recovered = await _publish(api)

    assert recovered.action == "unchanged"
    assert recovered.readback_changed is False
    assert api.adds == 1
    assert api.readbacks == 2
    assert projection_store["row"]["state"] == "ready"
    assert projection_store["row"]["submitted_html_sha256"]
    assert projection_store["row"]["readback_html_sha256"]


async def test_ambiguous_add_is_not_retried(projection_store: dict) -> None:
    api = FakeWechatApi(fail_add=True)
    with pytest.raises(wxpost_wechat.WechatDraftError, match="response lost"):
        await _publish(api)
    with pytest.raises(wxpost_wechat.WechatDraftError, match="result is uncertain"):
        await _publish(api)

    assert api.adds == 1
    assert projection_store["row"]["state"] == "uncertain"


async def test_ambiguous_add_recovers_one_exact_remote_candidate_without_adding_again(
    projection_store: dict,
) -> None:
    api = FakeWechatApi(fail_add=True, accept_on_timeout=True)
    with pytest.raises(wxpost_wechat.WechatDraftError, match="response lost"):
        await _publish(api)
    recovered = await _publish(api)

    assert recovered.action == "unchanged"
    assert str(recovered.preview_url) == "https://mp.weixin.qq.com/s/example-preview"
    assert api.adds == 1
    assert projection_store["row"]["state"] == "ready"
    assert projection_store["row"]["wechat_media_id"] == "wechat-draft-id"


async def test_ambiguous_add_does_not_recover_metadata_match_with_different_content(
    projection_store: dict,
) -> None:
    api = FakeWechatApi(fail_add=True, accept_on_timeout=True)
    with pytest.raises(wxpost_wechat.WechatDraftError, match="response lost"):
        await _publish(api)
    assert api.article is not None
    decoy = deepcopy(api.article)
    decoy["content"] = decoy["content"].replace(
        WECHAT_IMAGE_URL,
        "https://mmbiz.qpic.cn/example/different.jpg",
    )
    api.batch_items = [
        {
            "media_id": "unrelated-draft-id",
            "content": {"news_item": [decoy]},
        }
    ]
    with pytest.raises(wxpost_wechat.WechatDraftError, match="could not be uniquely recovered"):
        await _publish(api)

    assert projection_store["row"]["state"] == "uncertain"
    assert projection_store["row"].get("wechat_media_id") is None


def test_recovery_content_signature_accepts_wechat_attribute_filtering() -> None:
    submitted = f'<p style="color:#123">Hello <img src="{WECHAT_IMAGE_URL}"></p>'
    readback = f'<p style="color:#456">Hello<img data-src="{WECHAT_IMAGE_URL}" loading="lazy"></p>'

    assert wxpost_wechat._content_signature(submitted) == wxpost_wechat._content_signature(readback)


async def test_ambiguous_add_does_not_reconcile_against_a_changed_projection(
    projection_store: dict,
) -> None:
    api = FakeWechatApi(fail_add=True, accept_on_timeout=True)
    with pytest.raises(wxpost_wechat.WechatDraftError, match="response lost"):
        await _publish(api)
    with pytest.raises(wxpost_wechat.WechatDraftError, match="older Public Revision"):
        await _publish(api, html=f'<p>Changed<img src="{IMAGE_URL}"></p>')

    assert api.adds == 1
    assert projection_store["row"]["state"] == "uncertain"


@pytest.mark.parametrize(
    ("wechat_url", "expected"),
    [
        (
            "http://mp.weixin.qq.com/s?tempkey=temporary#rd",
            "https://mp.weixin.qq.com/s?tempkey=temporary#rd",
        ),
        (
            "https://mp.weixin.qq.com/s/preview",
            "https://mp.weixin.qq.com/s/preview",
        ),
    ],
)
async def test_preview_accepts_official_wechat_urls_and_upgrades_http(
    projection_store: dict,
    wechat_url: str,
    expected: str,
) -> None:
    projection_store["row"] = {"wechat_media_id": "wechat-draft-id"}
    api = FakeWechatApi(preview_url=wechat_url)

    assert await wxpost_wechat.get_preview_url("wxpost-test", api=api) == expected


async def test_preview_clears_a_link_that_wechat_confirms_is_missing(
    projection_store: dict,
) -> None:
    projection_store["row"] = {
        "source_workspace_id": "wxpost-test",
        "state": "ready",
        "wechat_media_id": "wechat-draft-id",
        "projection_sha256": "a" * 64,
        "asset_mappings": {
            "body:digest": "https://mmbiz.qpic.cn/body-image",
            "cover:digest": "cover-media-id",
        },
    }
    api = FakeWechatApi()
    api.remote_missing = True

    with pytest.raises(wxpost_wechat.WechatDraftError, match="no longer exists") as caught:
        await wxpost_wechat.get_preview_url("wxpost-test", api=api)

    assert caught.value.status_code == 404
    assert projection_store["row"]["wechat_media_id"] is None
    assert projection_store["row"]["asset_mappings"] == {"body:digest": "https://mmbiz.qpic.cn/body-image"}


async def test_preview_reports_a_concurrent_projection_change(
    projection_store: dict,
) -> None:
    projection_store["row"] = {
        "source_workspace_id": "wxpost-test",
        "state": "creating",
        "wechat_media_id": "wechat-draft-id",
        "projection_sha256": "a" * 64,
        "asset_mappings": {},
    }
    api = FakeWechatApi()
    api.remote_missing = True

    with pytest.raises(wxpost_wechat.WechatDraftError, match="link changed") as caught:
        await wxpost_wechat.get_preview_url("wxpost-test", api=api)

    assert caught.value.status_code == 409
    assert projection_store["row"]["wechat_media_id"] == "wechat-draft-id"


@pytest.mark.parametrize(
    "wechat_url",
    [
        "javascript:alert(1)",
        "https://mp.weixin.qq.com.evil.example/s/preview",
        "https://evil.example/s/preview",
    ],
)
async def test_preview_rejects_non_wechat_urls(
    projection_store: dict,
    wechat_url: str,
) -> None:
    projection_store["row"] = {"wechat_media_id": "wechat-draft-id"}
    api = FakeWechatApi(preview_url=wechat_url)

    with pytest.raises(wxpost_wechat.WechatDraftError, match="valid temporary preview URL"):
        await wxpost_wechat.get_preview_url("wxpost-test", api=api)


@pytest.mark.parametrize(
    "html",
    [
        "<script>alert(1)</script>",
        '<p onclick="alert(1)">Unsafe</p>',
        '<a href="javascript:alert(1)">Unsafe</a>',
    ],
)
def test_platform_sanitizer_rejects_active_content(html: str) -> None:
    with pytest.raises(wxpost_wechat.WechatDraftError, match="active content"):
        wxpost_wechat._sanitize_wechat_html(html, _render_document().presentation)


def test_dark_appearance_mapping_never_rewrites_content_or_non_style_attributes() -> None:
    presentation = Presentation.model_validate(
        {
            "layout": "brand-default",
            "palette": "brand-blue",
            "appearance": "dark",
            "typeface": "modern-sans",
        }
    )
    html = (
        '<article style="color:#f3f4f6">'
        '<p title="#f3f4f6">Design token #f3f4f6 stays literal.</p>'
        '<img alt="swatch #f3f4f6" src="https://cdn.example/#f3f4f6.png">'
        "</article>"
    )

    sanitized = wxpost_wechat._sanitize_wechat_html(html, presentation)

    assert 'style="text-align:left!important"' in sanitized
    assert 'title="#f3f4f6"' in sanitized
    assert "Design token #f3f4f6 stays literal." in sanitized
    assert 'alt="swatch #f3f4f6"' in sanitized
    assert 'src="https://cdn.example/#f3f4f6.png"' in sanitized


def test_platform_sanitizer_applies_deterministic_wechat_compatibility() -> None:
    html = (
        '<article data-testid="wxpost-article" '
        f'style="padding:{wxpost_wechat.CANONICAL_ROOT_PADDING};border:1px solid #c9c1b5;'
        'background:#f8f6f0;color:#123;box-shadow:0 24px 64px rgba(15,23,42,0.12)">'
        '<h2 style="font-family:Baskerville,&#x22;Iowan Old Style&#x22;,serif">Heading</h2>'
        '<p>Read <a href="https://example.com"><strong>the source</strong></a>.</p>'
        '<blockquote style="margin:0;color:#123">Centered quote</blockquote>'
        '<blockquote style="margin:0;border-left:2px solid #123;color:#456">Pull quote</blockquote>'
        '<ul style="color:#123">\n<li>First</li>\n<li>Second</li>\n</ul>'
        '<figure style="margin:0"><div style="position:relative;min-width:0">'
        '<img src="https://example.com/image.jpg" style="display:block;width:100%">'
        '</div><p style="margin:8px 0 0">Caption</p></figure>'
        "</article>"
    )

    sanitized = wxpost_wechat._sanitize_wechat_html(html, _render_document().presentation)

    assert f"padding:{wxpost_wechat.WECHAT_ROOT_PADDING}" in sanitized
    assert wxpost_wechat.CANONICAL_ROOT_PADDING not in sanitized
    assert 'style="text-align:left!important;' in sanitized
    assert "background:#f8f6f0" not in sanitized
    assert "border:1px solid #c9c1b5" not in sanitized
    assert "box-shadow:" not in sanitized
    assert "color:#123" in sanitized
    assert "font-family:Baskerville,&quot;Iowan Old Style&quot;,serif" in sanitized
    assert (
        '<blockquote style="border:0!important;padding:0!important;' 'margin:0;color:#123">Centered quote</blockquote>'
    ) in sanitized
    assert (
        '<blockquote style="margin:0;border-left:2px solid #123;color:#456">' "Pull quote</blockquote>"
    ) in sanitized
    assert sanitized.count("border:0!important") == 1
    assert '<ul style="color:#123"><li>First</li><li>Second</li></ul>' in sanitized
    assert (
        '<div style="font-size:0!important;line-height:0!important;position:relative;min-width:0">'
        '<img src="https://example.com/image.jpg" style="display:block;width:100%">'
        '</div><p style="margin:8px 0 0">Caption</p>'
    ) in sanitized
    assert "<a " not in sanitized
    assert "</a>" not in sanitized
    assert "<strong>the source</strong>" in sanitized
    assert "data-testid=" not in sanitized


def test_platform_sanitizer_only_adds_root_alignment_to_other_supported_styles() -> None:
    html = (
        '<article style="padding:29.44px 24px">'
        '<h2 style="font-family:Baskerville,&quot;Iowan Old Style&quot;,serif">Heading</h2>'
        '<p style="padding:29.44px clamp(12px,calc(5.0405% - 7.6578px),29.44px)">Copy</p>'
        "</article>"
    )

    assert wxpost_wechat._sanitize_wechat_html(html, _render_document().presentation) == html.replace(
        '<article style="',
        '<article style="text-align:left!important;',
        1,
    )


def test_platform_sanitizer_removes_only_the_canonical_article_header() -> None:
    html = (
        '<article style="color:#25231f">\n'
        '<header style="padding:24px 0;border-top:4px solid transparent;'
        "border-image:linear-gradient(90deg,#2563eb,#7c3aed) 1;"
        'border-bottom:1px solid #c9c1b5">'
        "<span>Meeting recap</span>"
        "<h1>Repeated title</h1>"
        "<p>Repeated digest</p>"
        "<div>Repeated byline</div>"
        "</header>"
        '<div data-wxpost-body="true" style="display:block;padding-top:32px">'
        "<p>Opening paragraph</p><header>Semantic content header</header></div>"
        "</article>"
    )

    sanitized = wxpost_wechat._sanitize_wechat_html(html, _render_document().presentation)

    assert "Repeated title" not in sanitized
    assert "Repeated digest" not in sanitized
    assert "Repeated byline" not in sanitized
    assert (
        '<div style="border-top:2px solid transparent;'
        'border-image:linear-gradient(90deg,#2563eb,#7c3aed) 1;margin:0 0 16px"></div>'
    ) in sanitized
    assert "border-bottom:1px solid #c9c1b5" not in sanitized
    assert 'style="display:block;padding-top:0"' in sanitized
    assert "Opening paragraph" in sanitized
    assert "<header>Semantic content header</header>" in sanitized


def test_platform_sanitizer_keeps_an_existing_thin_header_rule() -> None:
    html = (
        '<article style="color:#25231f">'
        '<header style="border-top:1px solid #25231f"><h1>Repeated title</h1></header>'
        '<div data-wxpost-body="true" style="padding-top:32px"><p>Opening paragraph</p></div>'
        "</article>"
    )

    sanitized = wxpost_wechat._sanitize_wechat_html(html, _render_document().presentation)

    assert '<div style="border-top:1px solid #25231f;margin:0 0 16px"></div>' in sanitized


@pytest.mark.parametrize(
    ("palette", "appearance", "base_text", "muted_text"),
    [
        ("brand-blue", "light", "#111827", "#5f6b7a"),
        ("brand-blue", "dark", "#f3f4f6", "#aeb7c5"),
        ("paper-neutral", "light", "#25231f", "#706b61"),
        ("paper-neutral", "dark", "#f0ede4", "#b9b2a5"),
        ("fresh-sage", "light", "#24332a", "#66736a"),
        ("fresh-sage", "dark", "#edf5ef", "#aab8ad"),
        ("warm-terracotta", "light", "#3d2d27", "#80685d"),
        ("warm-terracotta", "dark", "#fff1e7", "#c9a99a"),
        ("minimal-mono", "light", "#171717", "#6b6b6b"),
        ("minimal-mono", "dark", "#f5f5f5", "#b5b5b5"),
    ],
)
def test_platform_sanitizer_delegates_base_text_color_to_wechat(
    palette: str,
    appearance: str,
    base_text: str,
    muted_text: str,
) -> None:
    presentation = Presentation.model_validate(
        {
            "layout": "brand-default",
            "palette": palette,
            "appearance": appearance,
            "typeface": "modern-sans",
        }
    )
    html = (
        f'<article style="color:{base_text};font-size:16px">'
        f'<h2 style="color:{base_text};font-weight:500">Heading</h2>'
        f'<p style="color:{base_text};line-height:1.85">Body</p>'
        f'<small style="color:{muted_text}">Caption</small>'
        "</article>"
    )

    sanitized = wxpost_wechat._sanitize_wechat_html(html, presentation)

    assert f"color:{wxpost_wechat.WECHAT_BASE_TEXT_BY_PALETTE[palette]}" not in sanitized
    assert "font-size:16px" in sanitized
    assert "font-weight:500" in sanitized
    assert "line-height:1.85" in sanitized
    expected_muted = (
        wxpost_wechat.WECHAT_LIGHT_PALETTE_BY_DARK_TOKEN[palette][muted_text] if appearance == "dark" else muted_text
    )
    assert f"color:{expected_muted}" in sanitized


@pytest.mark.parametrize(
    ("palette", "dark_tokens", "light_tokens"),
    [
        (
            "brand-blue",
            ("#10131a", "#f3f4f6", "#aeb7c5", "#60a5fa", "#a78bfa", "#1c2332", "#30394b"),
            ("#ffffff", "#111827", "#5f6b7a", "#2563eb", "#7c3aed", "#eef2ff", "#dbe3f3"),
        ),
        (
            "paper-neutral",
            ("#1b1a17", "#f0ede4", "#b9b2a5", "#e2ddd2", "#2a2722", "#514c43"),
            ("#f8f6f0", "#25231f", "#706b61", "#2d2b27", "#efebe1", "#c9c1b5"),
        ),
        (
            "fresh-sage",
            ("#121915", "#edf5ef", "#aab8ad", "#8fc49d", "#d7b66c", "#1e2922", "#39483d"),
            ("#f8faf5", "#24332a", "#66736a", "#4f7a5b", "#b28b3b", "#edf4e8", "#cad8c8"),
        ),
        (
            "warm-terracotta",
            ("#211612", "#fff1e7", "#c9a99a", "#fb8b61", "#f6bd60", "#34231c", "#5c3c30"),
            ("#fffaf2", "#3d2d27", "#80685d", "#d8653b", "#e9a23b", "#fff0dd", "#e6c9b7"),
        ),
        (
            "minimal-mono",
            ("#111111", "#f5f5f5", "#b5b5b5", "#ffffff", "#a3a3a3", "#222222", "#404040"),
            ("#ffffff", "#171717", "#6b6b6b", "#171717", "#a3a3a3", "#f5f5f5", "#d4d4d4"),
        ),
    ],
)
def test_platform_sanitizer_maps_dark_palette_to_platform_adaptive_light_tokens(
    palette: str,
    dark_tokens: tuple[str, ...],
    light_tokens: tuple[str, ...],
) -> None:
    presentation = Presentation.model_validate(
        {
            "layout": "brand-default",
            "palette": palette,
            "appearance": "dark",
            "typeface": "modern-sans",
        }
    )
    nested_styles = ";".join(f"color:{token}" for token in dark_tokens)
    html = (
        f'<article style="padding:{wxpost_wechat.CANONICAL_ROOT_PADDING};background:{dark_tokens[0]};'
        f'border:1px solid {dark_tokens[-1]};box-shadow:0 24px 64px #000">'
        f'<section style="{nested_styles}">Copy</section></article>'
    )

    sanitized = wxpost_wechat._sanitize_wechat_html(html, presentation)

    assert "background:" not in sanitized.split(">", 1)[0]
    assert "border:" not in sanitized.split(">", 1)[0]
    assert "box-shadow:" not in sanitized.split(">", 1)[0]
    base_text = wxpost_wechat.WECHAT_BASE_TEXT_BY_PALETTE[palette]
    expected_styles = ";".join(f"color:{token}" for token in light_tokens if token != base_text)
    assert f'<section style="{expected_styles}">' in sanitized


async def test_gateway_client_requires_its_independent_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wxpost_wechat, "WECHAT_GATEWAY_BASE_URL", "")
    monkeypatch.setattr(wxpost_wechat, "WECHAT_GATEWAY_SERVICE_TOKEN", "")

    def unexpected_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError(request.url)

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_request)) as http_client:
        client = wxpost_wechat.WechatGatewayClient(http_client)
        with pytest.raises(wxpost_wechat.WechatDraftError, match="gateway is not configured") as caught:
            await client.get_draft("media-id")
    assert caught.value.status_code == 503


async def test_gateway_client_uses_only_typed_routes_and_its_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wxpost_wechat, "WECHAT_GATEWAY_BASE_URL", "https://gateway.example/internal")
    monkeypatch.setattr(wxpost_wechat, "WECHAT_GATEWAY_SERVICE_TOKEN", "gateway-secret")
    requests: list[httpx.Request] = []
    source = wxpost_wechat.WechatAssetSource(
        object_key=IMAGE_OBJECT_KEY,
        sha256=IMAGE_SHA256,
        size_bytes=len(b"image-bytes"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer gateway-secret"
        if request.url.path.endswith("/images/body"):
            assert json.loads(request.content) == source.to_gateway_payload()
            return httpx.Response(200, json={"url": WECHAT_IMAGE_URL}, request=request)
        if request.url.path.endswith("/images/cover"):
            assert json.loads(request.content) == source.to_gateway_payload()
            return httpx.Response(200, json={"mediaId": "cover-id"}, request=request)
        if request.method == "POST":
            assert json.loads(request.content) == {"article": {"title": "Created"}}
            return httpx.Response(200, json={"mediaId": "draft/id"}, request=request)
        if request.method == "PUT":
            assert request.url.path.endswith("/drafts/draft/id")
            assert json.loads(request.content) == {"article": {"title": "Updated"}}
            return httpx.Response(200, json={"updated": True}, request=request)
        if request.url.params.get("limit") == "20":
            return httpx.Response(200, json={"items": [{"media_id": "draft/id"}]}, request=request)
        return httpx.Response(
            200,
            json={"article": {"content": "<p>readback</p>", "url": "https://mp.weixin.qq.com/s/preview"}},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = wxpost_wechat.WechatGatewayClient(http_client)
        assert await client.upload_body_image(source) == WECHAT_IMAGE_URL
        assert await client.upload_cover(source) == "cover-id"
        assert await client.add_draft({"title": "Created"}) == "draft/id"
        await client.update_draft("draft/id", {"title": "Updated"})
        assert (await client.get_draft("draft/id"))["content"] == "<p>readback</p>"
        assert await client.batch_get_drafts() == [{"media_id": "draft/id"}]

    assert {request.url.path for request in requests} == {
        "/internal/v1/images/body",
        "/internal/v1/images/cover",
        "/internal/v1/drafts",
        "/internal/v1/drafts/draft/id",
    }


async def test_gateway_client_preserves_wechat_error_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wxpost_wechat, "WECHAT_GATEWAY_BASE_URL", "https://gateway.example")
    monkeypatch.setattr(wxpost_wechat, "WECHAT_GATEWAY_SERVICE_TOKEN", "gateway-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "code": "wechat_api_error",
                "message": "invalid media_id",
                "uncertain": False,
                "wechatErrcode": 40007,
            },
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = wxpost_wechat.WechatGatewayClient(http_client)
        with pytest.raises(wxpost_wechat.WechatDraftError) as caught:
            await client.update_draft("missing-id", {"title": "Updated"})

    assert caught.value.wechat_errcode == 40007
    assert caught.value.status_code == 404
    assert caught.value.uncertain is False


@pytest.mark.parametrize(
    ("gateway_status", "gateway_uncertain", "expected_status", "expected_uncertain"),
    [(502, True, 502, True), (401, False, 503, False)],
)
async def test_gateway_client_preserves_add_uncertainty_and_hides_internal_auth_failures(
    monkeypatch: pytest.MonkeyPatch,
    gateway_status: int,
    gateway_uncertain: bool,
    expected_status: int,
    expected_uncertain: bool,
) -> None:
    monkeypatch.setattr(wxpost_wechat, "WECHAT_GATEWAY_BASE_URL", "https://gateway.example")
    monkeypatch.setattr(wxpost_wechat, "WECHAT_GATEWAY_SERVICE_TOKEN", "gateway-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            gateway_status,
            json={
                "code": "upstream_result_uncertain" if gateway_uncertain else "unauthorized",
                "message": "Gateway failure",
                "uncertain": gateway_uncertain,
            },
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = wxpost_wechat.WechatGatewayClient(http_client)
        with pytest.raises(wxpost_wechat.WechatDraftError, match="Gateway failure") as caught:
            await client.add_draft({"title": "Draft"})

    assert caught.value.status_code == expected_status
    assert caught.value.uncertain is expected_uncertain


async def test_gateway_transport_loss_during_add_is_uncertain_without_a_client_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wxpost_wechat, "WECHAT_GATEWAY_BASE_URL", "https://gateway.example")
    monkeypatch.setattr(wxpost_wechat, "WECHAT_GATEWAY_SERVICE_TOKEN", "gateway-secret")
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("lost", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = wxpost_wechat.WechatGatewayClient(http_client)
        with pytest.raises(wxpost_wechat.WechatDraftError, match="gateway response was unavailable") as caught:
            await client.add_draft({"title": "Draft"})

    assert caught.value.uncertain is True
    assert calls == 1
