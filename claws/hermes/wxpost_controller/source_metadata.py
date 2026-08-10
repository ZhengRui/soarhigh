from __future__ import annotations

import hashlib
import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from .contracts import SourceKind

MAX_DECODED_PIXELS = 40_000_000
_ORIENTATION_TAG = 274
_ROTATED_ORIENTATIONS = {5, 6, 7, 8}


class InvalidSourceImage(ValueError):
    """The declared image bytes cannot provide trusted display dimensions."""


@dataclass(frozen=True)
class SourceTechnicalMetadata:
    content_sha256: str
    dimensions: dict[str, int] | None

    def to_wire(self) -> dict[str, object]:
        return {
            "contentSha256": self.content_sha256,
            "dimensions": self.dimensions,
        }


def inspect_source_bytes(
    data: bytes,
    *,
    kind: SourceKind,
) -> SourceTechnicalMetadata:
    content_sha256 = hashlib.sha256(data).hexdigest()
    if kind != SourceKind.IMAGE:
        return SourceTechnicalMetadata(
            content_sha256=content_sha256,
            dimensions=None,
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > MAX_DECODED_PIXELS:
                    raise InvalidSourceImage(
                        "image dimensions exceed the decoded image limit"
                    )
                orientation = image.getexif().get(_ORIENTATION_TAG)
                image.load()
    except InvalidSourceImage:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        RuntimeError,
        UnidentifiedImageError,
        ValueError,
    ) as error:
        raise InvalidSourceImage("source is not a valid supported image") from error

    if orientation in _ROTATED_ORIENTATIONS:
        width, height = height, width
    return SourceTechnicalMetadata(
        content_sha256=content_sha256,
        dimensions={"width": width, "height": height},
    )
