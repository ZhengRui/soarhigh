"""Publish one saved workspace Draft as a durable public WxPost revision."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import quote, unquote, urlsplit
from uuid import UUID, uuid4

import oss2  # type: ignore
from pydantic import ValidationError

from ..config import (
    ALICLOUD_ACCESS_KEY_ID,
    ALICLOUD_ACCESS_KEY_SECRET,
    ALICLOUD_OSS_BUCKET,
    ALICLOUD_OSS_ENDPOINT,
    WXPOST_PUBLIC_BASE_URL,
)
from ..db.wxpost import (
    WxPostNotFoundError,
    WxPostRevisionConflictError,
    abandon_unreferenced_wxpost_assets,
    article_document_from_row,
    begin_wxpost_deletion,
    create_pending_wxpost_asset,
    create_pending_wxpost_asset_variant,
    create_publication_shell,
    delete_hidden_wxpost,
    delete_wxpost_assets,
    finalize_workspace_publication,
    get_ready_wxpost_asset,
    get_ready_wxpost_assets,
    get_wxpost_asset_variant,
    get_wxpost_asset_variants,
    get_wxpost_by_id,
    get_wxpost_by_workspace_id,
    has_abandoned_wxpost_assets,
    mark_wxpost_asset_failed,
    mark_wxpost_asset_ready,
    mark_wxpost_asset_variant_failed,
    mark_wxpost_asset_variant_ready,
    retry_failed_wxpost_asset_variant,
    retry_inactive_wxpost_asset,
)
from ..models.wxpost import (
    ArticleDocument,
    WxPostPublicationStatus,
    WxPostPublicationSubmitItem,
    WxPostPublicationSubmitPlan,
    WxPostPublicationSyncRequest,
)
from .wxpost_document import validate_and_parse
from .wxpost_image_variants import (
    WECHAT_BODY_PROFILE,
    WECHAT_COVER_HARD_MAX_BYTES,
    ImageVariantError,
    render_wechat_body_variant,
)

LoadContext = Callable[[str], Awaitable[dict[str, Any]]]
LoadSource = Callable[[str, str, str], Awaitable[tuple[bytes, str]]]
CompileRender = Callable[[dict[str, Any]], Awaitable[str]]
_PUBLIC_MEDIA_PREFIX = "public/wxposts"


class PublicationError(Exception):
    def __init__(self, code: str, message: str, *, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ResolvedMedia:
    source_id: str
    kind: str
    filename: str
    mime_type: str
    content_path: Path
    size_bytes: int
    sha256: str
    md5: str


def publication_status(
    workspace_id: str,
    *,
    current_draft_version: int | None,
    row: dict[str, Any] | None,
) -> WxPostPublicationStatus:
    if row is None or row.get("status") != "ready" or not row.get("is_public"):
        return WxPostPublicationStatus(
            state="not-synced",
            workspace_id=workspace_id,
            current_draft_version=current_draft_version,
        )
    source_version = row.get("source_draft_version")
    up_to_date = current_draft_version is not None and source_version == current_draft_version
    return WxPostPublicationStatus(
        state="up-to-date" if up_to_date else "update-available",
        workspace_id=workspace_id,
        slug=row["slug"],
        public_revision=row["article_revision"],
        source_draft_version=source_version,
        current_draft_version=current_draft_version,
        published_at=row.get("updated_at"),
        public_url=f"{WXPOST_PUBLIC_BASE_URL}/posts/wxposts/{row['slug']}",
    )


def _extension(mime_type: str) -> str:
    extensions = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif",
        "video/mp4": "mp4",
        "video/quicktime": "mov",
        "video/webm": "webm",
    }
    try:
        return extensions[mime_type]
    except KeyError as error:
        raise PublicationError(
            "unsupported_media",
            f"Unsupported public media type: {mime_type}",
            status=422,
        ) from error


def public_asset_url(object_key: str) -> str:
    endpoint = ALICLOUD_OSS_ENDPOINT.removeprefix("https://").removeprefix("http://")
    return f"https://{ALICLOUD_OSS_BUCKET}.{endpoint}/" f"{quote(object_key, safe='/')}"


def _bundle_sha256_from_pairs(document: ArticleDocument, media_shas: list[tuple[str, str]]) -> str:
    payload = {
        "document": document.model_dump(by_alias=True, mode="json"),
        "media": [{"id": source_id, "sha256": sha256} for source_id, sha256 in media_shas],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _bundle_sha256(document: ArticleDocument, media: list[ResolvedMedia]) -> str:
    return _bundle_sha256_from_pairs(document, [(item.source_id, item.sha256) for item in media])


def _asset_request_hash(media: ResolvedMedia) -> str:
    value = json.dumps(
        {
            "filename": media.filename,
            "kind": media.kind,
            "mimeType": media.mime_type,
            "sha256": media.sha256,
            "sizeBytes": media.size_bytes,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(value).hexdigest()


def _upload_asset(wxpost_id: UUID, workspace_id: str, media: ResolvedMedia) -> str:
    existing = get_ready_wxpost_asset(
        wxpost_id,
        content_sha256=media.sha256,
        kind=media.kind,
    )
    if existing is not None:
        return public_asset_url(existing["object_key"])

    asset_id = uuid4()
    extension = _extension(media.mime_type)
    object_key = f"{_PUBLIC_MEDIA_PREFIX}/{wxpost_id}/assets/{asset_id}/original.{extension}"
    idempotency_source = f"{workspace_id}:{media.source_id}:{media.sha256}"
    idempotency = hashlib.sha256(idempotency_source.encode()).hexdigest()
    asset = create_pending_wxpost_asset(
        {
            "id": str(asset_id),
            "wxpost_id": str(wxpost_id),
            "status": "pending",
            "kind": media.kind,
            "object_key": object_key,
            "original_filename": media.filename,
            "mime_type": media.mime_type,
            "size_bytes": media.size_bytes,
            "content_sha256": media.sha256,
            "content_md5": media.md5,
            "upload_idempotency_key_hash": idempotency,
            "upload_request_hash": _asset_request_hash(media),
            "source_type": "workspace",
            "source_metadata": {
                "workspaceId": workspace_id,
                "sourceId": media.source_id,
            },
        }
    )
    if asset.get("status") == "ready":
        return public_asset_url(asset["object_key"])
    if asset.get("status") in {"failed", "abandoned"}:
        asset = retry_inactive_wxpost_asset(UUID(asset["id"]))

    auth = oss2.Auth(ALICLOUD_ACCESS_KEY_ID, ALICLOUD_ACCESS_KEY_SECRET)
    bucket = oss2.Bucket(auth, ALICLOUD_OSS_ENDPOINT, ALICLOUD_OSS_BUCKET)
    try:
        with media.content_path.open("rb") as content:
            result = bucket.put_object(
                asset["object_key"],
                content,
                headers={"Content-Type": media.mime_type},
            )
        ready = mark_wxpost_asset_ready(UUID(asset["id"]), etag=result.etag)
    except Exception as error:
        try:
            mark_wxpost_asset_failed(UUID(asset["id"]))
        except Exception:
            pass
        raise PublicationError(
            "asset_upload_failed",
            f"Material {media.source_id} could not be uploaded to public storage.",
            status=503,
        ) from error
    return public_asset_url(ready["object_key"])


def _ensure_wechat_body_variant(asset: dict, media: ResolvedMedia) -> dict:
    existing = get_wxpost_asset_variant(UUID(asset["id"]), profile=WECHAT_BODY_PROFILE)
    if existing is not None and existing.get("status") == "ready":
        return existing

    label = f"Material {media.source_id} ({media.filename})"
    try:
        rendered = render_wechat_body_variant(media.content_path, material_label=label)
    except ImageVariantError as error:
        raise PublicationError("invalid_wechat_image", str(error), status=422) from error

    asset_directory = str(asset["object_key"]).rsplit("/original.", 1)[0]
    object_key = f"{asset_directory}/variants/{WECHAT_BODY_PROFILE}.{rendered.extension}"
    variant = create_pending_wxpost_asset_variant(
        {
            "id": str(uuid4()),
            "asset_id": asset["id"],
            "profile": WECHAT_BODY_PROFILE,
            "status": "pending",
            "object_key": object_key,
            "mime_type": rendered.mime_type,
            "size_bytes": rendered.size_bytes,
            "content_sha256": rendered.sha256,
        }
    )
    if variant.get("status") == "ready":
        return variant
    if variant.get("status") == "failed":
        variant = retry_failed_wxpost_asset_variant(UUID(variant["id"]))
        if variant.get("status") == "ready":
            return variant

    auth = oss2.Auth(ALICLOUD_ACCESS_KEY_ID, ALICLOUD_ACCESS_KEY_SECRET)
    bucket = oss2.Bucket(auth, ALICLOUD_OSS_ENDPOINT, ALICLOUD_OSS_BUCKET)
    try:
        result = bucket.put_object(
            variant["object_key"],
            rendered.content,
            headers={"Content-Type": rendered.mime_type},
        )
        return mark_wxpost_asset_variant_ready(UUID(variant["id"]), etag=result.etag)
    except Exception as error:
        try:
            mark_wxpost_asset_variant_failed(UUID(variant["id"]))
        except Exception:
            pass
        raise PublicationError(
            "asset_variant_upload_failed",
            f"{label} could not be prepared for WeChat delivery.",
            status=503,
        ) from error


def _delete_asset_objects(assets: list[dict]) -> None:
    variants = get_wxpost_asset_variants(
        [str(asset["id"]) for asset in assets if asset.get("id")],
        statuses=["pending", "ready", "failed"],
    )
    object_keys = list(
        dict.fromkeys(
            [
                key
                for asset in assets
                for key in (asset.get("object_key"), asset.get("poster_object_key"))
                if isinstance(key, str) and key
            ]
            + [key for variant in variants if isinstance((key := variant.get("object_key")), str) and key]
        )
    )
    if not object_keys:
        return
    auth = oss2.Auth(ALICLOUD_ACCESS_KEY_ID, ALICLOUD_ACCESS_KEY_SECRET)
    bucket = oss2.Bucket(auth, ALICLOUD_OSS_ENDPOINT, ALICLOUD_OSS_BUCKET)
    try:
        for start in range(0, len(object_keys), 1000):
            bucket.batch_delete_objects(object_keys[start : start + 1000])
    except Exception as error:
        raise PublicationError(
            "asset_cleanup_failed",
            "Unused public media could not be removed from public storage.",
            status=503,
        ) from error


def _remove_unreferenced_assets(
    wxpost_id: UUID,
    *,
    keep_content_sha256: set[str],
) -> None:
    stale = abandon_unreferenced_wxpost_assets(
        wxpost_id,
        keep_content_sha256=keep_content_sha256,
    )
    _delete_asset_objects(stale)
    delete_wxpost_assets([asset["id"] for asset in stale])


def reconcile_publication_wechat_variants(wxpost_id: UUID, *, dry_run: bool = False) -> dict[str, Any]:
    """Backfill missing deterministic renditions without revising public content."""

    row = get_wxpost_by_id(wxpost_id)
    if row is None or row.get("status") != "ready" or not row.get("is_public"):
        raise PublicationError("wxpost_not_found", "Ready Public Revision not found.", status=404)
    document = article_document_from_row(row)
    parsed = validate_and_parse(document)
    required_ids = {media_id for directive in parsed.directives for media_id in directive.media_ids}
    media_by_id = {media.id: media for media in document.media if media.include and media.kind.value == "image"}
    required_ids &= media_by_id.keys()

    assets = get_ready_wxpost_assets(wxpost_id)
    assets_by_source: dict[str, dict] = {}
    assets_by_object_key = {
        str(asset["object_key"]): asset for asset in assets if isinstance(asset.get("object_key"), str)
    }
    for source_id, media in media_by_id.items():
        object_key = unquote(urlsplit(str(media.source_url)).path).lstrip("/")
        source_asset = assets_by_object_key.get(object_key)
        if source_asset is not None:
            assets_by_source[source_id] = source_asset
    for asset in assets:
        metadata = asset.get("source_metadata")
        metadata_source_id = metadata.get("sourceId") if isinstance(metadata, dict) else None
        if isinstance(metadata_source_id, str):
            assets_by_source.setdefault(metadata_source_id, asset)

    cover = media_by_id.get(document.cover_media_id or "")
    if cover is not None:
        cover_asset = assets_by_source.get(cover.id)
        if cover_asset is not None and cover_asset.get("size_bytes", 0) > WECHAT_COVER_HARD_MAX_BYTES:
            required_ids.add(cover.id)

    missing: list[str] = []
    missing_assets: dict[str, tuple[dict, str]] = {}
    for source_id in sorted(required_ids):
        source_asset = assets_by_source.get(source_id)
        if source_asset is None:
            raise PublicationError(
                "missing_publication_media",
                f"Material {source_id} is not backed by a ready public asset.",
                status=409,
            )
        variants = source_asset.get("variants")
        if not isinstance(variants, list) or not any(
            isinstance(variant, dict) and variant.get("profile") == WECHAT_BODY_PROFILE for variant in variants
        ):
            missing.append(source_id)
            missing_assets.setdefault(str(source_asset["id"]), (source_asset, source_id))

    report: dict[str, Any] = {
        "wxpostId": str(wxpost_id),
        "revision": row["article_revision"],
        "profile": WECHAT_BODY_PROFILE,
        "missing": missing,
        "created": [],
        "dryRun": dry_run,
    }
    if dry_run or not missing:
        return report

    auth = oss2.Auth(ALICLOUD_ACCESS_KEY_ID, ALICLOUD_ACCESS_KEY_SECRET)
    bucket = oss2.Bucket(auth, ALICLOUD_OSS_ENDPOINT, ALICLOUD_OSS_BUCKET)
    with TemporaryDirectory(prefix="wxpost-variant-backfill-") as temporary_directory:
        for asset_id, (asset, source_id) in missing_assets.items():
            path = Path(temporary_directory, asset_id)
            try:
                bucket.get_object_to_file(asset["object_key"], str(path))
            except Exception as error:
                raise PublicationError(
                    "asset_unavailable",
                    f"Material {source_id} could not be downloaded for WeChat reconciliation.",
                    status=503,
                ) from error
            content = path.read_bytes()
            expected_size = asset.get("size_bytes")
            expected_sha256 = asset.get("content_sha256")
            if len(content) != expected_size or hashlib.sha256(content).hexdigest() != expected_sha256:
                raise PublicationError(
                    "asset_changed",
                    f"Material {source_id} no longer matches its Public Revision metadata.",
                    status=409,
                )
            resolved = ResolvedMedia(
                source_id=source_id,
                kind="image",
                filename=str(asset.get("original_filename") or source_id),
                mime_type=str(asset.get("mime_type") or "application/octet-stream"),
                content_path=path,
                size_bytes=len(content),
                sha256=str(expected_sha256),
                md5=base64.b64encode(hashlib.md5(content).digest()).decode(),
            )
            _ensure_wechat_body_variant(asset, resolved)
        report["created"] = missing
    return report


async def delete_public_wxpost(
    wxpost_id: UUID,
    *,
    expected_revision: int,
) -> str | None:
    """Hide a public row, delete its OSS assets, then remove the row."""

    try:
        row = begin_wxpost_deletion(
            wxpost_id,
            expected_revision=expected_revision,
        )
    except WxPostNotFoundError as error:
        raise PublicationError(
            "wxpost_not_found",
            "The public WxPost no longer exists.",
            status=404,
        ) from error
    except WxPostRevisionConflictError as error:
        raise PublicationError(
            "version_conflict",
            "The public WxPost changed elsewhere.",
            status=409,
        ) from error

    await asyncio.to_thread(
        _remove_unreferenced_assets,
        wxpost_id,
        keep_content_sha256=set(),
    )
    try:
        delete_hidden_wxpost(
            wxpost_id,
            expected_revision=expected_revision,
        )
    except WxPostRevisionConflictError as error:
        raise PublicationError(
            "version_conflict",
            "The public WxPost changed before deletion finished.",
            status=409,
        ) from error
    workspace_id = row.get("source_workspace_id")
    return workspace_id if isinstance(workspace_id, str) else None


@dataclass(frozen=True)
class _PreparedSubmit:
    plan: WxPostPublicationSubmitPlan
    document: ArticleDocument
    current: dict[str, Any] | None
    current_ready: bool
    retrying_completed_revision: bool
    owner: dict[str, Any]


async def _prepare_submit(
    workspace_id: str,
    request: WxPostPublicationSyncRequest,
    *,
    load_context: LoadContext,
) -> _PreparedSubmit:
    context = await load_context(workspace_id)
    manifest = context.get("manifest")
    draft = context.get("draft")
    if not isinstance(manifest, dict) or not isinstance(draft, dict):
        raise PublicationError(
            "draft_required",
            "Save a Draft before synchronizing the public WxPost.",
            status=422,
        )
    manifest_version = manifest.get("manifestVersion")
    draft_version = draft.get("draftVersion")
    if manifest_version != request.expected_manifest_version or draft_version != request.expected_draft_version:
        raise PublicationError(
            "version_conflict",
            "This workspace or Draft changed elsewhere.",
            status=409,
        )
    try:
        document = ArticleDocument.model_validate(draft.get("document"))
    except ValidationError as error:
        raise PublicationError(
            "invalid_draft",
            "The saved Draft is not valid for public synchronization.",
            status=422,
        ) from error

    current = get_wxpost_by_workspace_id(workspace_id)
    current_ready = bool(current and current.get("status") == "ready" and current.get("is_public"))
    expected_revision = request.expected_public_revision
    retrying_completed_revision = False
    if current_ready:
        assert current is not None
        retrying_completed_revision = (
            expected_revision is not None
            and current["article_revision"] == expected_revision + 1
            and current.get("source_draft_version") == draft_version
            and has_abandoned_wxpost_assets(UUID(current["id"]))
        )
        if expected_revision != current["article_revision"] and not retrying_completed_revision:
            raise PublicationError(
                "version_conflict",
                "The public WxPost changed elsewhere.",
                status=409,
            )
    elif expected_revision is not None:
        raise PublicationError(
            "version_conflict",
            "The public WxPost state changed elsewhere.",
            status=409,
        )

    sources = {
        source.get("id"): source
        for source in manifest.get("sources", [])
        if isinstance(source, dict) and isinstance(source.get("id"), str)
    }

    parsed_source = validate_and_parse(document)
    body_media_ids = {media_id for directive in parsed_source.directives for media_id in directive.media_ids}

    items: list[WxPostPublicationSubmitItem] = []
    media_shas: list[tuple[str, str]] = []
    for media in sorted(
        (media for media in document.media if media.include),
        key=lambda media: media.order,
    ):
        source = sources.get(media.id)
        if source is None or source.get("workspaceReady") is not True or source.get("kind") != media.kind.value:
            raise PublicationError(
                "missing_publication_media",
                f"Material {media.id} is not available for public synchronization.",
                status=422,
            )
        content_sha256 = source.get("contentSha256")
        if not isinstance(content_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", content_sha256) is None:
            raise PublicationError(
                "missing_publication_media",
                f"Material {media.id} has no valid content version.",
                status=422,
            )
        origin = source.get("origin")
        file_key = origin.get("fileKey") if isinstance(origin, dict) else None
        if not isinstance(origin, dict) or origin.get("type") != "meeting-library" or not isinstance(file_key, str):
            raise PublicationError(
                "upload_origin_unsupported",
                f"Material {media.id} was uploaded directly; direct-upload publishing arrives in the next release.",
                status=422,
            )

        size_bytes = int(source.get("sizeBytes") or 0)
        is_cover = media.id == (document.cover_media_id or "")
        needs_wechat_variant = (media.id in body_media_ids and media.kind.value == "image") or (
            is_cover and media.kind.value == "image" and size_bytes > WECHAT_COVER_HARD_MAX_BYTES
        )
        items.append(
            WxPostPublicationSubmitItem(
                source_id=media.id,
                kind=media.kind.value,
                filename=str(source.get("filename") or media.id),
                mime_type=str(source.get("mimeType") or ""),
                size_bytes=size_bytes,
                content_sha256=content_sha256,
                meeting_file_key=file_key,
                needs_wechat_variant=needs_wechat_variant,
            )
        )
        media_shas.append((media.id, content_sha256))

    bundle_sha256 = _bundle_sha256_from_pairs(document, media_shas)

    if current_ready:
        assert current is not None
        if retrying_completed_revision and current.get("source_draft_sha256") != bundle_sha256:
            raise PublicationError(
                "version_conflict",
                "The public WxPost changed elsewhere.",
                status=409,
            )

    owner = current or create_publication_shell(
        workspace_id=workspace_id,
        draft_version=draft_version,
        draft_sha256=bundle_sha256,
        document=document,
    )
    if current is None:
        owner_matches = (
            owner.get("source_draft_version") == draft_version and owner.get("source_draft_sha256") == bundle_sha256
        )
        if owner.get("status") == "ready" and owner.get("is_public"):
            if not owner_matches:
                raise PublicationError(
                    "version_conflict",
                    "The public WxPost changed elsewhere.",
                    status=409,
                )
        if not owner_matches:
            raise PublicationError(
                "version_conflict",
                "The public WxPost is being synchronized elsewhere.",
                status=409,
            )

    plan = WxPostPublicationSubmitPlan(
        wxpost_id=str(owner["id"]),
        draft_version=draft_version,
        manifest_version=manifest_version,
        bundle_sha256=bundle_sha256,
        items=items,
    )
    return _PreparedSubmit(
        plan=plan,
        document=document,
        current=current,
        current_ready=current_ready,
        retrying_completed_revision=retrying_completed_revision,
        owner=owner,
    )


async def prepare_publication_submit(
    workspace_id: str,
    request: WxPostPublicationSyncRequest,
    *,
    load_context: LoadContext,
) -> WxPostPublicationSubmitPlan:
    """Validate a workspace Draft and adopt its publication shell, returning the ordered work plan."""

    prepared = await _prepare_submit(workspace_id, request, load_context=load_context)
    return prepared.plan


async def synchronize_workspace_publication(
    workspace_id: str,
    request: WxPostPublicationSyncRequest,
    *,
    load_context: LoadContext,
    load_source: LoadSource,
    compile_render: CompileRender,
) -> WxPostPublicationStatus:
    prepared = await _prepare_submit(workspace_id, request, load_context=load_context)

    with TemporaryDirectory(prefix="wxpost-publication-") as spool_directory:
        resolved: list[ResolvedMedia] = []
        for item in prepared.plan.items:
            content, response_mime = await load_source(
                workspace_id,
                item.source_id,
                item.content_sha256,
            )
            source_content_sha256 = hashlib.sha256(content).hexdigest()
            if source_content_sha256 != item.content_sha256:
                raise PublicationError(
                    "missing_publication_media",
                    f"Material {item.source_id} content does not match its version.",
                    status=422,
                )
            mime_type = item.mime_type or response_mime
            content_path = Path(spool_directory, item.source_id)
            content_path.write_bytes(content)
            resolved.append(
                ResolvedMedia(
                    source_id=item.source_id,
                    kind=item.kind,
                    filename=item.filename,
                    mime_type=mime_type,
                    content_path=content_path,
                    size_bytes=len(content),
                    sha256=source_content_sha256,
                    md5=base64.b64encode(hashlib.md5(content).digest()).decode(),
                )
            )
            del content

        return await _synchronize_resolved_publication(
            workspace_id,
            document=prepared.document,
            draft_version=prepared.plan.draft_version,
            current=prepared.current,
            current_ready=prepared.current_ready,
            retrying_completed_revision=prepared.retrying_completed_revision,
            owner=prepared.owner,
            resolved=resolved,
            compile_render=compile_render,
        )


async def _synchronize_resolved_publication(
    workspace_id: str,
    *,
    document: ArticleDocument,
    draft_version: int,
    current: dict[str, Any] | None,
    current_ready: bool,
    retrying_completed_revision: bool,
    owner: dict[str, Any],
    resolved: list[ResolvedMedia],
    compile_render: CompileRender,
) -> WxPostPublicationStatus:
    bundle_sha256 = _bundle_sha256(document, resolved)
    same_bundle = False
    same_draft = False
    if current_ready:
        assert current is not None
        if retrying_completed_revision and current.get("source_draft_sha256") != bundle_sha256:
            raise PublicationError(
                "version_conflict",
                "The public WxPost changed elsewhere.",
                status=409,
            )
        same_bundle = current.get("source_draft_sha256") == bundle_sha256
        same_draft = current.get("source_draft_version") == draft_version
    elif current is None:
        owner_matches = (
            owner.get("source_draft_version") == draft_version and owner.get("source_draft_sha256") == bundle_sha256
        )
        if owner_matches and owner.get("status") == "ready" and owner.get("is_public"):
            same_bundle = True
            same_draft = True

    wxpost_id = UUID(owner["id"])
    public_urls: dict[str, str] = {}
    public_assets: dict[str, dict] = {}
    for media in resolved:
        if not (same_bundle and same_draft):
            public_urls[media.source_id] = await asyncio.to_thread(
                _upload_asset,
                wxpost_id,
                workspace_id,
                media,
            )
        asset = get_ready_wxpost_asset(
            wxpost_id,
            content_sha256=media.sha256,
            kind=media.kind,
        )
        if asset is None:
            raise PublicationError(
                "asset_upload_failed",
                f"Material {media.source_id} did not return a ready public asset.",
                status=503,
            )
        public_assets[media.source_id] = asset
        public_urls.setdefault(media.source_id, public_asset_url(asset["object_key"]))

    parsed_source = validate_and_parse(document)
    body_media_ids = {media_id for directive in parsed_source.directives for media_id in directive.media_ids}
    resolved_by_id = {media.source_id: media for media in resolved}
    variant_media_ids = {
        media_id
        for media_id in body_media_ids
        if media_id in resolved_by_id and resolved_by_id[media_id].kind == "image"
    }
    cover_media = resolved_by_id.get(document.cover_media_id or "")
    if cover_media is not None and cover_media.kind == "image" and cover_media.size_bytes > WECHAT_COVER_HARD_MAX_BYTES:
        variant_media_ids.add(cover_media.source_id)
    variant_assets: dict[str, tuple[dict, ResolvedMedia]] = {}
    for media_id in sorted(variant_media_ids):
        asset = public_assets[media_id]
        variant_assets.setdefault(str(asset["id"]), (asset, resolved_by_id[media_id]))
    for asset, media in variant_assets.values():
        await asyncio.to_thread(
            _ensure_wechat_body_variant,
            asset,
            media,
        )

    if same_bundle and same_draft:
        await asyncio.to_thread(
            _remove_unreferenced_assets,
            wxpost_id,
            keep_content_sha256={media.sha256 for media in resolved},
        )
        return publication_status(
            workspace_id,
            current_draft_version=draft_version,
            row=owner,
        )
    public_payload = document.model_dump(by_alias=True, mode="json")
    public_payload["media"] = [item for item in public_payload["media"] if item["include"]]
    for payload_media in public_payload["media"]:
        source_id = payload_media["id"]
        if source_id in public_urls:
            payload_media["sourceUrl"] = public_urls[source_id]
        # Workspace poster URLs are private controller URLs. The public
        # projection may render a video without a poster, but must never leak
        # a workspace URL to anonymous readers.
        payload_media["posterUrl"] = None
    public_document = ArticleDocument.model_validate(public_payload)
    parsed = validate_and_parse(public_document)
    await compile_render(
        parsed.render_document(public_document).model_dump(
            by_alias=True,
            mode="json",
        )
    )
    try:
        owner_status = str(owner.get("status"))
        first_publish = owner_status == "assembling" and not owner.get("finalize_request_hash")
        row = finalize_workspace_publication(
            wxpost_id,
            workspace_id=workspace_id,
            expected_revision=owner["article_revision"],
            expected_status=owner_status,
            next_revision=(owner["article_revision"] if first_publish else owner["article_revision"] + 1),
            draft_version=draft_version,
            draft_sha256=bundle_sha256,
            document=public_document,
        )
    except (WxPostNotFoundError, WxPostRevisionConflictError) as error:
        latest = get_wxpost_by_workspace_id(workspace_id)
        if (
            latest
            and latest.get("status") == "ready"
            and latest.get("is_public")
            and latest.get("source_draft_version") == draft_version
            and latest.get("source_draft_sha256") == bundle_sha256
        ):
            return publication_status(
                workspace_id,
                current_draft_version=draft_version,
                row=latest,
            )
        raise PublicationError(
            "version_conflict",
            "The public WxPost changed before synchronization finished.",
            status=409,
        ) from error
    await asyncio.to_thread(
        _remove_unreferenced_assets,
        wxpost_id,
        keep_content_sha256={media.sha256 for media in resolved},
    )
    return publication_status(
        workspace_id,
        current_draft_version=draft_version,
        row=row,
    )
