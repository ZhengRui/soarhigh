"""Deterministic image renditions for bounded platform delivery."""

from __future__ import annotations

import hashlib
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

WECHAT_BODY_PROFILE = "wechat-body-v1"
WECHAT_BODY_TARGET_BYTES = 900 * 1024
WECHAT_BODY_HARD_MAX_BYTES = 1024 * 1024 - 1
WECHAT_COVER_HARD_MAX_BYTES = 10 * 1024 * 1024
MAX_DECODED_PIXELS = 40_000_000

_MAX_EDGES = (1920, 1600, 1280, 1024, 800, 640)
_JPEG_QUALITIES = (90, 85, 80, 75, 70, 65)
_PNG_PALETTE_SIZES = (256, 128)


class ImageVariantError(ValueError):
    """The source cannot be represented by the bounded image profile."""


@dataclass(frozen=True)
class ImageVariant:
    content: bytes
    mime_type: str
    extension: str
    size_bytes: int
    sha256: str


def _has_transparency(image: Image.Image) -> bool:
    if image.info.get("transparency") is not None:
        return True
    if "A" not in image.getbands():
        return False
    minimum, _maximum = image.getchannel("A").getextrema()
    return isinstance(minimum, int) and minimum < 255


def _normalize_color(image: Image.Image, *, transparent: bool) -> Image.Image:
    output_mode = "RGBA" if transparent else "RGB"
    icc_profile = image.info.get("icc_profile")
    if isinstance(icc_profile, bytes) and icc_profile:
        try:
            converted = ImageCms.profileToProfile(
                image,
                ImageCms.ImageCmsProfile(BytesIO(icc_profile)),
                ImageCms.createProfile("sRGB"),
                outputMode=output_mode,
            )
            if converted is not None:
                return converted
        except (ImageCms.PyCMSError, OSError, ValueError):
            pass
    return image.convert(output_mode)


def _resized(image: Image.Image, maximum_edge: int) -> Image.Image:
    candidate = image.copy()
    candidate.thumbnail((maximum_edge, maximum_edge), Image.Resampling.LANCZOS)
    return candidate


def _encode_jpeg(image: Image.Image, quality: int) -> bytes:
    output = BytesIO()
    image.save(
        output,
        format="JPEG",
        quality=quality,
        optimize=True,
        progressive=True,
        subsampling="4:2:0",
    )
    return output.getvalue()


def _encode_png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=True, compress_level=9)
    return output.getvalue()


def _verify_variant(content: bytes, *, expected_format: str) -> None:
    if not content or len(content) > WECHAT_BODY_TARGET_BYTES:
        raise ImageVariantError("The encoded WeChat image exceeds its target size.")
    try:
        with Image.open(BytesIO(content)) as verified:
            verified.load()
            if verified.format != expected_format or getattr(verified, "is_animated", False):
                raise ImageVariantError("The encoded WeChat image has an invalid format.")
    except (OSError, UnidentifiedImageError) as error:
        raise ImageVariantError("The encoded WeChat image could not be verified.") from error


def _variant(content: bytes, *, mime_type: str, extension: str, expected_format: str) -> ImageVariant:
    _verify_variant(content, expected_format=expected_format)
    return ImageVariant(
        content=content,
        mime_type=mime_type,
        extension=extension,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def render_wechat_body_variant(source: Path, *, material_label: str) -> ImageVariant:
    """Decode actual bytes and emit one deterministic, WeChat-safe rendition."""

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as opened:
                width, height = opened.size
                if width <= 0 or height <= 0 or width * height > MAX_DECODED_PIXELS:
                    raise ImageVariantError(f"{material_label} exceeds the decoded image limit.")
                if getattr(opened, "is_animated", False) and getattr(opened, "n_frames", 1) > 1:
                    raise ImageVariantError(
                        f"{material_label} is animated and cannot be flattened for a WeChat body image."
                    )
                opened.seek(0)
                opened.load()
                oriented = ImageOps.exif_transpose(opened)
                transparent = _has_transparency(oriented)
                normalized = _normalize_color(oriented, transparent=transparent)
    except ImageVariantError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, UnidentifiedImageError) as error:
        raise ImageVariantError(f"{material_label} is not a valid supported image.") from error

    if not transparent:
        for maximum_edge in _MAX_EDGES:
            candidate = _resized(normalized, maximum_edge)
            for quality in _JPEG_QUALITIES:
                content = _encode_jpeg(candidate, quality)
                if len(content) <= WECHAT_BODY_TARGET_BYTES:
                    return _variant(
                        content,
                        mime_type="image/jpeg",
                        extension="jpg",
                        expected_format="JPEG",
                    )
    else:
        for maximum_edge in _MAX_EDGES:
            candidate = _resized(normalized, maximum_edge)
            content = _encode_png(candidate)
            if len(content) <= WECHAT_BODY_TARGET_BYTES:
                return _variant(
                    content,
                    mime_type="image/png",
                    extension="png",
                    expected_format="PNG",
                )
            for colors in _PNG_PALETTE_SIZES:
                quantized = candidate.quantize(
                    colors=colors,
                    method=Image.Quantize.FASTOCTREE,
                    dither=Image.Dither.FLOYDSTEINBERG,
                )
                content = _encode_png(quantized)
                if len(content) <= WECHAT_BODY_TARGET_BYTES:
                    return _variant(
                        content,
                        mime_type="image/png",
                        extension="png",
                        expected_format="PNG",
                    )

    raise ImageVariantError(f"{material_label} could not be compressed below the WeChat body-image limit.")
