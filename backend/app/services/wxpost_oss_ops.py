"""OSS server-side copy and variant operations.

Ladder implementation: for each edge in _MAX_EDGES, for each quality in _JPEG_QUALITIES:
style `image/auto-orient,1/resize,l_{edge}/quality,q_{quality}/format,jpg`, then
`sys/saveas,o_{urlsafe_b64(target_key).rstrip('=')}`. Call head_object(target) for
size; stop when <= 900 KB. PNG sources use `image/auto-orient,1/resize,l_{edge}/format,png`
(resize-only ladder, stays PNG to preserve possible transparency). GIF and any video/*
-> invalid_wechat_image immediately. WebP uses the JPEG ladder. Download the final
(small) variant to hash it.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Any, Callable

import oss2  # type: ignore

from ..config import (
    ALICLOUD_ACCESS_KEY_ID,
    ALICLOUD_ACCESS_KEY_SECRET,
    ALICLOUD_OSS_BUCKET,
    ALICLOUD_OSS_ENDPOINT,
)
from .wxpost_image_variants import (
    _JPEG_QUALITIES,
    _MAX_EDGES,
    WECHAT_BODY_PROFILE,
    WECHAT_BODY_TARGET_BYTES,
)


class OssOpsError(Exception):
    """OSS operation error with code and message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class VariantObject:
    """Variant image object metadata and content."""

    object_key: str
    mime_type: str
    extension: str
    size_bytes: int
    sha256: str
    content: bytes


def _default_bucket_factory() -> Any:
    """Create a real oss2.Bucket for production use."""
    auth = oss2.Auth(ALICLOUD_ACCESS_KEY_ID, ALICLOUD_ACCESS_KEY_SECRET)
    return oss2.Bucket(auth, ALICLOUD_OSS_ENDPOINT, ALICLOUD_OSS_BUCKET)


def copy_public_object(
    source_key: str,
    target_key: str,
    *,
    expected_size: int,
    bucket_factory: Callable[[], Any] = _default_bucket_factory,
) -> str:
    """Copy a public object server-side, verifying source size and returning etag.

    Args:
        source_key: Source object key in OSS.
        target_key: Target object key in OSS.
        expected_size: Expected size of source object in bytes.
        bucket_factory: Function that returns an oss2.Bucket instance.

    Returns:
        The etag of the copied object (32-hex uppercase).

    Raises:
        OssOpsError: If source size doesn't match, etag is not 32-hex (multipart),
            or OSS operation fails.
    """
    bucket = bucket_factory()

    # Verify source size
    try:
        source_meta = bucket.head_object(source_key)
    except Exception as e:
        raise OssOpsError(
            "asset_unavailable",
            f"Failed to verify source object: {e}",
        ) from e

    if source_meta.content_length != expected_size:
        raise OssOpsError(
            "asset_changed",
            f"Source object size mismatch: expected {expected_size}, got {source_meta.content_length}",
        )

    # Copy object
    try:
        result = bucket.copy_object(source_key, target_key)
    except Exception as e:
        raise OssOpsError(
            "asset_unavailable",
            f"Failed to copy object: {e}",
        ) from e

    etag = result.etag
    if not _is_single_part_etag(etag):
        raise OssOpsError(
            "asset_copy_unverifiable",
            f"Source object was uploaded as multipart (etag: {etag})",
        )

    return etag


def _is_single_part_etag(etag: str) -> bool:
    """Check if etag is a single-part upload (32-hex uppercase)."""
    if len(etag) != 32:
        return False
    try:
        int(etag, 16)
        return True
    except ValueError:
        return False


def generate_wechat_variant(
    source_key: str,
    target_directory: str,
    *,
    mime_type: str,
    bucket_factory: Callable[[], Any] = _default_bucket_factory,
) -> VariantObject:
    """Generate a WeChat-sized image variant via OSS process_object.

    Applies a ladder of image processing steps to reduce image size to <= 900 KB.
    JPEG/WebP sources use a quality ladder; PNG sources preserve format.
    GIF and video sources are rejected immediately.

    Args:
        source_key: Source image key in OSS.
        target_directory: Directory path for the variant (e.g., "dir").
        mime_type: MIME type of source image (image/jpeg, image/png, image/webp).
        bucket_factory: Function that returns an oss2.Bucket instance.

    Returns:
        VariantObject with object_key, mime_type, extension, size_bytes, sha256, content.

    Raises:
        OssOpsError: If mime_type is unsupported (gif, video), or if the ladder
            bottoms out without producing a variant <= 900 KB.
    """
    bucket = bucket_factory()

    # Reject unsupported types
    if mime_type == "image/gif":
        raise OssOpsError(
            "invalid_wechat_image",
            "GIF images are not supported for WeChat variants",
        )
    if mime_type.startswith("video/"):
        raise OssOpsError(
            "invalid_wechat_image",
            f"Video type {mime_type} is not supported for WeChat variants",
        )

    # Determine extension and target key
    if mime_type == "image/png":
        extension = "png"
    elif mime_type in ("image/jpeg", "image/webp"):
        extension = "jpg"
    else:
        raise OssOpsError(
            "invalid_wechat_image",
            f"Unsupported MIME type: {mime_type}",
        )

    target_key = f"{target_directory}/variants/{WECHAT_BODY_PROFILE}.{extension}"

    # Try the ladder
    if mime_type == "image/png":
        # PNG ladder: resize only, no quality
        for edge in _MAX_EDGES:
            style = f"image/auto-orient,1/resize,l_{edge}/format,png|sys/saveas,o_{_encode_target_key(target_key)}"
            _process_variant(bucket, source_key, style, target_key)
            size = _get_variant_size(bucket, target_key)
            if size <= WECHAT_BODY_TARGET_BYTES:
                content = _download_variant(bucket, target_key)
                return VariantObject(
                    object_key=target_key,
                    mime_type="image/png",
                    extension="png",
                    size_bytes=size,
                    sha256=hashlib.sha256(content).hexdigest(),
                    content=content,
                )
    else:
        # JPEG/WebP ladder: quality ladder
        for edge in _MAX_EDGES:
            for quality in _JPEG_QUALITIES:
                encoded_key = _encode_target_key(target_key)
                style = f"image/auto-orient,1/resize,l_{edge}/quality,q_{quality}/format,jpg|sys/saveas,o_{encoded_key}"
                _process_variant(bucket, source_key, style, target_key)
                size = _get_variant_size(bucket, target_key)
                if size <= WECHAT_BODY_TARGET_BYTES:
                    content = _download_variant(bucket, target_key)
                    return VariantObject(
                        object_key=target_key,
                        mime_type="image/jpeg",
                        extension="jpg",
                        size_bytes=size,
                        sha256=hashlib.sha256(content).hexdigest(),
                        content=content,
                    )

    # Ladder exhausted
    raise OssOpsError(
        "invalid_wechat_image",
        "Could not compress image below WeChat variant size limit (900 KB)",
    )


def _encode_target_key(target_key: str) -> str:
    """Encode target key for sys/saveas parameter."""
    encoded = base64.urlsafe_b64encode(target_key.encode()).decode()
    return encoded.rstrip("=")


def _process_variant(bucket: Any, source_key: str, style: str, target_key: str) -> None:
    """Apply image processing to create variant."""
    try:
        bucket.process_object(source_key, style)
    except Exception as e:
        raise OssOpsError(
            "asset_unavailable",
            f"Failed to process image: {e}",
        ) from e


def _get_variant_size(bucket: Any, target_key: str) -> int:
    """Get the size of a variant object."""
    try:
        meta = bucket.head_object(target_key)
        return meta.content_length
    except Exception as e:
        raise OssOpsError(
            "asset_unavailable",
            f"Failed to get variant size: {e}",
        ) from e


def _download_variant(bucket: Any, target_key: str) -> bytes:
    """Download variant content."""
    try:
        obj = bucket.get_object(target_key)
        return obj.read()
    except Exception as e:
        raise OssOpsError(
            "asset_unavailable",
            f"Failed to download variant: {e}",
        ) from e
