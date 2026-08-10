from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from app.services import wxpost_image_variants as variants


def _save(image: Image.Image, path, *, format: str, **kwargs) -> None:
    image.save(path, format=format, **kwargs)


def test_mislabeled_opaque_png_becomes_a_deterministic_bounded_jpeg(tmp_path) -> None:
    source = tmp_path / "actually-png.jpg"
    image = Image.effect_noise((1080, 1920), 100).convert("RGB")
    _save(image, source, format="PNG")
    assert source.stat().st_size > variants.WECHAT_BODY_HARD_MAX_BYTES

    first = variants.render_wechat_body_variant(source, material_label="Material M01 (poster.jpg)")
    second = variants.render_wechat_body_variant(source, material_label="Material M01 (poster.jpg)")

    assert first == second
    assert first.mime_type == "image/jpeg"
    assert first.extension == "jpg"
    assert first.size_bytes <= variants.WECHAT_BODY_TARGET_BYTES
    with Image.open(BytesIO(first.content)) as encoded:
        assert encoded.format == "JPEG"
        assert max(encoded.size) <= max(image.size)
        assert encoded.width * image.height == encoded.height * image.width


def test_transparent_png_preserves_transparency(tmp_path) -> None:
    source = tmp_path / "transparent.png"
    image = Image.new("RGBA", (640, 640), (20, 40, 60, 0))
    for offset in range(0, 640, 16):
        image.paste((120, 180, 220, min(255, offset)), (offset, 0, min(offset + 16, 640), 640))
    _save(image, source, format="PNG")

    rendered = variants.render_wechat_body_variant(source, material_label="Material M02 (transparent.png)")

    assert rendered.mime_type == "image/png"
    with Image.open(BytesIO(rendered.content)) as encoded:
        assert encoded.format == "PNG"
        assert "A" in encoded.convert("RGBA").getbands()
        minimum_alpha, _maximum_alpha = encoded.convert("RGBA").getchannel("A").getextrema()
        assert isinstance(minimum_alpha, int)
        assert minimum_alpha < 255


def test_palette_png_preserves_transparency(tmp_path) -> None:
    source = tmp_path / "palette-transparent.png"
    image = Image.new("P", (32, 32), color=0)
    image.putpalette([255, 0, 0, 0, 255, 0] + [0, 0, 0] * 254)
    _save(image, source, format="PNG", transparency=0)

    rendered = variants.render_wechat_body_variant(source, material_label="Material M03 (palette-transparent.png)")

    assert rendered.mime_type == "image/png"
    with Image.open(BytesIO(rendered.content)) as encoded:
        minimum_alpha, _maximum_alpha = encoded.convert("RGBA").getchannel("A").getextrema()
        assert isinstance(minimum_alpha, int)
        assert minimum_alpha < 255


def test_exif_orientation_is_applied_before_encoding(tmp_path) -> None:
    source = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (120, 60), "navy")
    exif = Image.Exif()
    exif[274] = 6
    _save(image, source, format="JPEG", exif=exif)

    rendered = variants.render_wechat_body_variant(source, material_label="Material M03 (rotated.jpg)")

    with Image.open(BytesIO(rendered.content)) as encoded:
        assert encoded.size == (60, 120)


def test_animated_gif_is_rejected_without_flattening(tmp_path) -> None:
    source = tmp_path / "animated.gif"
    first = Image.new("RGB", (32, 32), "red")
    second = Image.new("RGB", (32, 32), "blue")
    first.save(source, format="GIF", save_all=True, append_images=[second], duration=100, loop=0)

    with pytest.raises(variants.ImageVariantError, match="animated"):
        variants.render_wechat_body_variant(source, material_label="Material M04 (animated.gif)")


def test_invalid_and_excessive_decoded_images_are_rejected(tmp_path, monkeypatch) -> None:
    invalid = tmp_path / "invalid.jpg"
    invalid.write_bytes(b"not an image")
    with pytest.raises(variants.ImageVariantError, match="not a valid supported image"):
        variants.render_wechat_body_variant(invalid, material_label="Material M05 (invalid.jpg)")

    source = tmp_path / "large.png"
    _save(Image.new("RGB", (11, 10), "white"), source, format="PNG")
    monkeypatch.setattr(variants, "MAX_DECODED_PIXELS", 100)
    with pytest.raises(variants.ImageVariantError, match="decoded image limit"):
        variants.render_wechat_body_variant(source, material_label="Material M06 (large.png)")
