"""Publish one saved workspace Draft as a durable public WxPost revision."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, Literal
from urllib.parse import quote, unquote, urlsplit
from uuid import UUID, uuid4

import oss2  # type: ignore
from pydantic import ValidationError

from ..config import (
    ALICLOUD_ACCESS_KEY_ID,
    ALICLOUD_ACCESS_KEY_SECRET,
    ALICLOUD_OSS_BUCKET,
    ALICLOUD_OSS_ENDPOINT,
    ALICLOUD_OSS_MEETING_MEDIA_PREFIX,
    WXPOST_PUBLIC_BASE_URL,
)
from ..db.wxpost import (
    WxPostAssetConflictError,
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
    get_wxpost_asset_by_idempotency_hash,
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
    WxPostPublicationExpectedVersions,
    WxPostPublicationStatus,
    WxPostPublicationSubmitItem,
    WxPostPublicationSubmitPlan,
    WxPostPublicationUploadUrlItem,
    WxPostPublicationUploadUrlsResult,
)
from .wxpost_document import validate_and_parse
from .wxpost_image_variants import WECHAT_BODY_PROFILE, WECHAT_COVER_HARD_MAX_BYTES
from .wxpost_oss_ops import (
    OssOpsError,
    copy_public_object,
    generate_wechat_variant,
    head_public_object,
    sign_public_put_url,
)

LoadContext = Callable[[str], Awaitable[dict[str, Any]]]
CompileRender = Callable[[dict[str, Any]], Awaitable[str]]
_PUBLIC_MEDIA_PREFIX = "public/wxposts"


class PublicationError(Exception):
    def __init__(self, code: str, message: str, *, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


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


def _request_hash(
    *,
    filename: str,
    kind: str,
    mime_type: str,
    sha256: str,
    size_bytes: int,
) -> str:
    value = json.dumps(
        {
            "filename": filename,
            "kind": kind,
            "mimeType": mime_type,
            "sha256": sha256,
            "sizeBytes": size_bytes,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(value).hexdigest()


def _map_oss_error(error: OssOpsError) -> PublicationError:
    if error.code == "asset_unavailable":
        status = 503
    elif error.code in ("asset_changed", "asset_copy_unverifiable"):
        status = 409
    else:
        status = 422
    return PublicationError(error.code, str(error), status=status)


async def _copy_original_asset(
    wxpost_id: UUID,
    workspace_id: str,
    item: WxPostPublicationSubmitItem,
) -> dict:
    """Server-side copy one meeting-library original into public storage.

    Head-etag-first, insert-first: the source object is inspected via
    ``head_object`` before any write happens — verifying its size against
    the caller-declared ``item.size_bytes`` and capturing its etag — and
    the pending ``wxpost_assets`` row is created with the ``content_md5``
    (NOT NULL) derived from that etag *before* any copy is attempted. On
    the idempotent-conflict path — a concurrent or earlier attempt already
    owns this (workspace, source, sha256) key, possibly under a different
    object key — the recovered row's own stored ``content_md5`` must match
    what was just observed at the source; a mismatch means the source
    object actually changed between attempts, which is a genuine integrity
    failure (``asset_changed``), not a harmless race. The single copy that
    follows always targets the row's real object key and is verified
    against the source's own etag, so nothing is ever copied to (and
    orphaned at) a key nobody ends up using.
    """

    assert item.meeting_file_key is not None  # guaranteed by the origin validator
    prefix = f"{ALICLOUD_OSS_MEETING_MEDIA_PREFIX}/"
    if not item.meeting_file_key.startswith(prefix):
        raise PublicationError(
            "invalid_source_key",
            f"Material {item.source_id} source key is outside the meeting media prefix.",
            status=422,
        )

    try:
        source_size, source_etag = await asyncio.to_thread(head_public_object, item.meeting_file_key)
    except OssOpsError as error:
        raise _map_oss_error(error) from error

    if source_size != item.size_bytes:
        raise PublicationError(
            "asset_changed",
            f"Material {item.source_id} source object size no longer matches "
            f"(expected {item.size_bytes}, found {source_size}).",
            status=409,
        )

    content_md5 = base64.b64encode(bytes.fromhex(source_etag)).decode()

    asset_id = uuid4()
    extension = _extension(item.mime_type)
    object_key = f"{_PUBLIC_MEDIA_PREFIX}/{wxpost_id}/assets/{asset_id}/original.{extension}"

    idempotency_source = f"{workspace_id}:{item.source_id}:{item.content_sha256}"
    asset = create_pending_wxpost_asset(
        {
            "id": str(asset_id),
            "wxpost_id": str(wxpost_id),
            "status": "pending",
            "kind": item.kind,
            "object_key": object_key,
            "original_filename": item.filename,
            "mime_type": item.mime_type,
            "size_bytes": item.size_bytes,
            "content_sha256": item.content_sha256,
            "content_md5": content_md5,
            "upload_idempotency_key_hash": hashlib.sha256(idempotency_source.encode()).hexdigest(),
            "upload_request_hash": _request_hash(
                filename=item.filename,
                kind=item.kind,
                mime_type=item.mime_type,
                sha256=item.content_sha256,
                size_bytes=item.size_bytes,
            ),
            "source_type": "workspace",
            "source_metadata": {
                "workspaceId": workspace_id,
                "sourceId": item.source_id,
            },
        }
    )
    if asset.get("status") == "ready":
        return asset
    if asset.get("status") in {"failed", "abandoned"}:
        asset = retry_inactive_wxpost_asset(UUID(asset["id"]))
        if asset.get("status") == "ready":
            return asset

    if asset["object_key"] != object_key and asset.get("content_md5") != content_md5:
        raise PublicationError(
            "asset_changed",
            f"Material {item.source_id} changed since a prior publish attempt.",
            status=409,
        )

    try:
        copy_etag = await asyncio.to_thread(copy_public_object, item.meeting_file_key, asset["object_key"])
    except OssOpsError as error:
        try:
            mark_wxpost_asset_failed(UUID(asset["id"]))
        except Exception:
            pass
        raise _map_oss_error(error) from error

    if copy_etag != source_etag:
        try:
            mark_wxpost_asset_failed(UUID(asset["id"]))
        except Exception:
            pass
        raise PublicationError(
            "asset_changed",
            f"Material {item.source_id} could not be verified after copying to public storage.",
            status=409,
        )

    try:
        return mark_wxpost_asset_ready(UUID(asset["id"]), etag=copy_etag)
    except Exception as error:
        try:
            mark_wxpost_asset_failed(UUID(asset["id"]))
        except Exception:
            pass
        raise PublicationError(
            "asset_upload_failed",
            f"Material {item.source_id} could not be uploaded to public storage.",
            status=503,
        ) from error


async def _verify_uploaded_asset(
    wxpost_id: UUID,
    workspace_id: str,
    item: WxPostPublicationSubmitItem,
) -> dict:
    """Verify one browser-uploaded original landed intact at its signed key.

    The presign step is the sole creator of the pending row (with the
    controller-attested content_md5), so this step is read-only lookup +
    head verification: etag must equal the stored MD5 and the size must
    match the plan item. No object is ever written here.
    """

    idempotency_source = f"{workspace_id}:{item.source_id}:{item.content_sha256}"
    asset = get_wxpost_asset_by_idempotency_hash(
        wxpost_id,
        hashlib.sha256(idempotency_source.encode()).hexdigest(),
    )
    if asset is None:
        raise PublicationError(
            "upload_not_prepared",
            f"Material {item.source_id} has no prepared upload; retry the publish.",
            status=422,
        )
    if asset.get("status") == "ready":
        return asset
    if asset.get("status") in {"failed", "abandoned"}:
        asset = retry_inactive_wxpost_asset(UUID(asset["id"]))
        if asset.get("status") == "ready":
            return asset

    try:
        object_size, object_etag = await asyncio.to_thread(head_public_object, asset["object_key"])
    except OssOpsError as error:
        if error.code == "asset_missing":
            raise PublicationError(
                "upload_missing",
                f"Material {item.source_id} was not uploaded to public storage; retry the publish.",
                status=422,
            ) from error
        raise _map_oss_error(error) from error

    expected_etag = base64.b64decode(str(asset.get("content_md5") or "")).hex().upper()
    if object_etag.upper() != expected_etag or object_size != item.size_bytes:
        try:
            mark_wxpost_asset_failed(UUID(asset["id"]))
        except Exception:
            pass
        raise PublicationError(
            "asset_changed",
            f"Material {item.source_id} could not be verified in public storage.",
            status=409,
        )

    try:
        return mark_wxpost_asset_ready(UUID(asset["id"]), etag=object_etag)
    except Exception as error:
        try:
            mark_wxpost_asset_failed(UUID(asset["id"]))
        except Exception:
            pass
        raise PublicationError(
            "asset_upload_failed",
            f"Material {item.source_id} could not be uploaded to public storage.",
            status=503,
        ) from error


def _materialize_wechat_variant(asset: dict, *, mime_type: str, source_id: str) -> bool:
    """Idempotently materialize the WeChat body variant for one ready asset via the OSS ladder.

    Blocking, synchronous core shared by both call sites that need this:
    the live ensure-asset path (``_ensure_wechat_variant``) and the WeChat
    reconciliation backfill (``_reconcile_wechat_variant``). Both wrap this
    in ``asyncio.to_thread`` — the live path because it runs on the request's
    event loop, the backfill for parity even though its own caller
    (``scripts/backfill_wxpost_wechat_variants.py``) has no event loop of
    its own beyond the one ``asyncio.run`` gives it for this call. The only
    things that differ between call sites are the asset's ``mime_type`` and
    the ``source_id`` used in error messages, both parameterized here.
    """

    existing = get_wxpost_asset_variant(UUID(asset["id"]), profile=WECHAT_BODY_PROFILE)
    if existing is not None and existing.get("status") == "ready":
        return True

    asset_directory = str(asset["object_key"]).rsplit("/original.", 1)[0]
    try:
        rendered = generate_wechat_variant(
            asset["object_key"],
            asset_directory,
            mime_type=mime_type,
        )
    except OssOpsError as error:
        raise _map_oss_error(error) from error

    try:
        variant = create_pending_wxpost_asset_variant(
            {
                "id": str(uuid4()),
                "asset_id": asset["id"],
                "profile": WECHAT_BODY_PROFILE,
                "status": "pending",
                "object_key": rendered.object_key,
                "mime_type": rendered.mime_type,
                "size_bytes": rendered.size_bytes,
                "content_sha256": rendered.sha256,
            }
        )
    except WxPostAssetConflictError as error:
        raise PublicationError(
            "asset_variant_conflict",
            f"Material {source_id}'s existing WeChat variant no longer matches; "
            "contact an admin or retry after cleanup.",
            status=409,
        ) from error
    if variant.get("status") == "ready":
        return True
    if variant.get("status") == "failed":
        variant = retry_failed_wxpost_asset_variant(UUID(variant["id"]))
        if variant.get("status") == "ready":
            return True

    # generate_wechat_variant already wrote the winning candidate to OSS
    # server-side (via the ladder's sys/saveas step) — there is no local
    # put_object here, so the etag we record is the downloaded variant
    # bytes' MD5 rather than an OSS copy/put response etag.
    etag = hashlib.md5(rendered.content).hexdigest().upper()
    try:
        mark_wxpost_asset_variant_ready(UUID(variant["id"]), etag=etag)
    except Exception as error:
        try:
            mark_wxpost_asset_variant_failed(UUID(variant["id"]))
        except Exception:
            pass
        raise PublicationError(
            "asset_variant_upload_failed",
            f"Material {source_id} could not be prepared for WeChat delivery.",
            status=503,
        ) from error
    return True


async def _ensure_wechat_variant(asset: dict, item: WxPostPublicationSubmitItem) -> bool:
    """Idempotently materialize the WeChat body variant for one ready asset."""

    return await asyncio.to_thread(
        _materialize_wechat_variant,
        asset,
        mime_type=item.mime_type,
        source_id=item.source_id,
    )


async def ensure_publication_asset(
    workspace_id: str,
    wxpost_id: UUID,
    item: WxPostPublicationSubmitItem,
) -> dict[str, Any]:
    """Idempotently materialize one public asset (and its WeChat variant).

    Called once per media item by the async publication runner. Reuses a
    ready asset by content hash when one already exists; otherwise performs
    an OSS server-side copy from the meeting-library original.
    """

    owner = get_wxpost_by_id(wxpost_id)
    if owner is None or owner.get("source_workspace_id") != workspace_id:
        raise PublicationError(
            "wxpost_not_found",
            "The public WxPost shell no longer exists.",
            status=404,
        )

    asset: dict[str, Any]
    if item.origin == "upload":
        # Upload items always resolve through their own presign-created row —
        # the ready-by-sha shortcut would strand a duplicate-bytes item's
        # pending row, and finalize blocks while pending rows exist.
        asset = await _verify_uploaded_asset(wxpost_id, workspace_id, item)
    else:
        ready_asset = get_ready_wxpost_asset(wxpost_id, content_sha256=item.content_sha256, kind=item.kind)
        asset = ready_asset if ready_asset is not None else await _copy_original_asset(wxpost_id, workspace_id, item)

    variant_ready = False
    if item.needs_wechat_variant:
        variant_ready = await _ensure_wechat_variant(asset, item)

    return {
        "source_id": item.source_id,
        "public_url": public_asset_url(asset["object_key"]),
        "variant_ready": variant_ready,
    }


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


async def reconcile_publication_wechat_variants(wxpost_id: UUID, *, dry_run: bool = False) -> dict[str, Any]:
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

    for asset, source_id in missing_assets.values():
        await _reconcile_wechat_variant(asset, source_id)
    report["created"] = missing
    return report


async def _reconcile_wechat_variant(asset: dict, source_id: str) -> None:
    """Idempotently materialize the WeChat body variant for one ready asset.

    Thin async wrapper around the shared ``_materialize_wechat_variant``
    core (also used by the live ensure-asset path's
    ``_ensure_wechat_variant``): the original is already in OSS at
    ``asset["object_key"]``, so this generates the variant server-side via
    ``generate_wechat_variant`` instead of downloading the original for
    local Pillow rendering.
    """

    await asyncio.to_thread(
        _materialize_wechat_variant,
        asset,
        mime_type=str(asset.get("mime_type") or ""),
        source_id=source_id,
    )


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


async def prepare_publication_submit(
    workspace_id: str,
    request: WxPostPublicationExpectedVersions,
    *,
    load_context: LoadContext,
) -> WxPostPublicationSubmitPlan:
    """Validate a workspace Draft and adopt its publication shell, returning the ordered work plan."""

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
        origin_type = origin.get("type") if isinstance(origin, dict) else None
        if not isinstance(origin_type, str) or not origin_type:
            raise PublicationError(
                "missing_publication_media",
                f"Material {media.id} has no valid origin.",
                status=422,
            )
        if origin_type == "meeting-library":
            file_key = origin.get("fileKey") if isinstance(origin, dict) else None
            if not isinstance(file_key, str) or not file_key:
                raise PublicationError(
                    "missing_publication_media",
                    f"Material {media.id} has no valid source key.",
                    status=422,
                )
            item_origin: Literal["meeting-library", "upload"] = "meeting-library"
        else:
            file_key = None
            item_origin = "upload"

        raw_size_bytes = source.get("sizeBytes")
        if not isinstance(raw_size_bytes, int) or isinstance(raw_size_bytes, bool) or raw_size_bytes <= 0:
            raise PublicationError(
                "missing_publication_media",
                f"Material {media.id} has no valid size metadata.",
                status=422,
            )
        size_bytes = raw_size_bytes
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
                origin=item_origin,
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

    return WxPostPublicationSubmitPlan(
        wxpost_id=str(owner["id"]),
        draft_version=draft_version,
        manifest_version=manifest_version,
        bundle_sha256=bundle_sha256,
        items=items,
    )


FetchChecksums = Callable[[str, list[str]], Awaitable[dict[str, str]]]


async def prepare_publication_uploads(
    workspace_id: str,
    request: WxPostPublicationExpectedVersions,
    *,
    load_context: LoadContext,
    fetch_checksums: FetchChecksums,
) -> WxPostPublicationUploadUrlsResult:
    """Presign browser PUT URLs for the plan's upload-origin items.

    Runs the same validation as a submit, then creates-or-recovers the
    pending asset row for each upload-origin item so the row's minted
    object key can be signed. Items whose row is already ready need no
    upload and are omitted. This is the sole creator of upload-origin
    rows — the ensure step only verifies what landed at the signed key.
    """

    plan = await prepare_publication_submit(workspace_id, request, load_context=load_context)
    upload_items = [item for item in plan.items if item.origin == "upload"]
    if not upload_items:
        return WxPostPublicationUploadUrlsResult(uploads=[])

    checksums = await fetch_checksums(workspace_id, [item.source_id for item in upload_items])
    wxpost_id = UUID(plan.wxpost_id)
    uploads: list[WxPostPublicationUploadUrlItem] = []
    for item in upload_items:
        md5_hex = checksums.get(item.source_id)
        if not isinstance(md5_hex, str) or re.fullmatch(r"[0-9a-f]{32}", md5_hex) is None:
            raise PublicationError(
                "asset_unavailable",
                f"Material {item.source_id} has no valid workspace checksum.",
                status=503,
            )
        content_md5 = base64.b64encode(bytes.fromhex(md5_hex)).decode()
        asset = _prepare_upload_asset_row(wxpost_id, workspace_id, item, content_md5)
        if asset.get("status") == "ready":
            continue
        try:
            put_url = await asyncio.to_thread(
                sign_public_put_url,
                asset["object_key"],
                content_md5=content_md5,
                content_type=item.mime_type,
            )
        except OssOpsError as error:
            raise _map_oss_error(error) from error
        uploads.append(
            WxPostPublicationUploadUrlItem(
                source_id=item.source_id,
                content_sha256=item.content_sha256,
                put_url=put_url,
                headers={"Content-MD5": content_md5, "Content-Type": item.mime_type},
            )
        )
    return WxPostPublicationUploadUrlsResult(uploads=uploads)


def _prepare_upload_asset_row(
    wxpost_id: UUID,
    workspace_id: str,
    item: WxPostPublicationSubmitItem,
    content_md5: str,
) -> dict:
    asset_id = uuid4()
    extension = _extension(item.mime_type)
    object_key = f"{_PUBLIC_MEDIA_PREFIX}/{wxpost_id}/assets/{asset_id}/original.{extension}"
    idempotency_source = f"{workspace_id}:{item.source_id}:{item.content_sha256}"
    try:
        asset = create_pending_wxpost_asset(
            {
                "id": str(asset_id),
                "wxpost_id": str(wxpost_id),
                "status": "pending",
                "kind": item.kind,
                "object_key": object_key,
                "original_filename": item.filename,
                "mime_type": item.mime_type,
                "size_bytes": item.size_bytes,
                "content_sha256": item.content_sha256,
                "content_md5": content_md5,
                "upload_idempotency_key_hash": hashlib.sha256(idempotency_source.encode()).hexdigest(),
                "upload_request_hash": _request_hash(
                    filename=item.filename,
                    kind=item.kind,
                    mime_type=item.mime_type,
                    sha256=item.content_sha256,
                    size_bytes=item.size_bytes,
                ),
                "source_type": "workspace",
                "source_metadata": {
                    "workspaceId": workspace_id,
                    "sourceId": item.source_id,
                },
            }
        )
    except WxPostAssetConflictError as error:
        raise PublicationError(
            "asset_changed",
            f"Material {item.source_id} conflicts with a prior publish attempt.",
            status=409,
        ) from error
    if asset.get("status") in {"failed", "abandoned"}:
        asset = retry_inactive_wxpost_asset(UUID(asset["id"]))
    if asset.get("status") == "pending" and asset.get("content_md5") != content_md5:
        raise PublicationError(
            "asset_changed",
            f"Material {item.source_id} changed since a prior publish attempt.",
            status=409,
        )
    return asset


async def _finalize_publication_record(
    workspace_id: str,
    *,
    wxpost_id: UUID,
    document: ArticleDocument,
    draft_version: int,
    bundle_sha256: str,
    same_bundle: bool,
    same_draft: bool,
    owner: dict[str, Any],
    public_urls: dict[str, str],
    keep_content_sha256: set[str],
    compile_render: CompileRender,
) -> WxPostPublicationStatus:
    """Finalize tail for ``finalize_publication``: rewrite public media URLs, compile, finalize the row, sweep.

    Split out from ``finalize_publication`` so the two concerns stay
    separate: computing ``public_urls``/``keep_content_sha256``/
    ``same_bundle``/``same_draft`` from already-ready assets, versus how the
    public row actually gets finalized.
    """

    if same_bundle and same_draft:
        await asyncio.to_thread(
            _remove_unreferenced_assets,
            wxpost_id,
            keep_content_sha256=keep_content_sha256,
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
        keep_content_sha256=keep_content_sha256,
    )
    return publication_status(
        workspace_id,
        current_draft_version=draft_version,
        row=row,
    )


async def finalize_publication(
    workspace_id: str,
    wxpost_id: UUID,
    *,
    expected_manifest_version: int,
    expected_draft_version: int,
    bundle_sha256: str,
    load_context: LoadContext,
    compile_render: CompileRender,
) -> WxPostPublicationStatus:
    """Finalize a publication whose assets were already ensured out-of-band.

    Called once, after every ``ensure_publication_asset`` call for the
    submit plan has succeeded. Re-loads the workspace context to guard
    against drift since the plan was prepared, confirms every included
    media item is now backed by a ready public asset, then delegates to
    ``_finalize_publication_record`` to rewrite URLs, compile, and finalize
    the row.
    """

    context = await load_context(workspace_id)
    manifest = context.get("manifest")
    draft = context.get("draft")
    if not isinstance(manifest, dict) or not isinstance(draft, dict):
        raise PublicationError(
            "draft_required",
            "Save a Draft before finalizing the public WxPost.",
            status=422,
        )
    manifest_version = manifest.get("manifestVersion")
    draft_version = draft.get("draftVersion")
    if manifest_version != expected_manifest_version or draft_version != expected_draft_version:
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

    owner = get_wxpost_by_id(wxpost_id)
    if owner is None or owner.get("source_workspace_id") != workspace_id:
        raise PublicationError(
            "wxpost_not_found",
            "The public WxPost shell no longer exists.",
            status=404,
        )

    current_ready = bool(owner.get("status") == "ready" and owner.get("is_public"))

    sources = {
        source.get("id"): source
        for source in manifest.get("sources", [])
        if isinstance(source, dict) and isinstance(source.get("id"), str)
    }
    ready_assets = get_ready_wxpost_assets(wxpost_id)
    assets_by_sha256 = {
        str(asset["content_sha256"]): asset for asset in ready_assets if isinstance(asset.get("content_sha256"), str)
    }

    public_urls: dict[str, str] = {}
    keep_content_sha256: set[str] = set()
    for media in sorted(
        (media for media in document.media if media.include),
        key=lambda media: media.order,
    ):
        source = sources.get(media.id)
        content_sha256 = source.get("contentSha256") if isinstance(source, dict) else None
        asset = assets_by_sha256.get(content_sha256) if isinstance(content_sha256, str) else None
        if not isinstance(content_sha256, str) or asset is None:
            raise PublicationError(
                "missing_publication_media",
                f"Material {media.id} is not backed by a ready public asset.",
                status=409,
            )
        public_urls[media.id] = public_asset_url(asset["object_key"])
        keep_content_sha256.add(content_sha256)

    same_bundle = False
    same_draft = False
    if current_ready:
        same_bundle = owner.get("source_draft_sha256") == bundle_sha256
        same_draft = owner.get("source_draft_version") == draft_version

    return await _finalize_publication_record(
        workspace_id,
        wxpost_id=UUID(owner["id"]),
        document=document,
        draft_version=draft_version,
        bundle_sha256=bundle_sha256,
        same_bundle=same_bundle,
        same_draft=same_draft,
        owner=owner,
        public_urls=public_urls,
        keep_content_sha256=keep_content_sha256,
        compile_render=compile_render,
    )
