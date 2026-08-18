"""Tests for OSS server-side copy and variant operations."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from app.services.wxpost_oss_ops import (
    OssOpsError,
    copy_public_object,
    generate_wechat_variant,
    head_public_object,
    sign_public_put_url,
)


class FakeObjectMeta:
    """Fake object metadata for head_object."""

    def __init__(self, size: int) -> None:
        self.content_length = size


class FakeBucket:
    """Mock OSS bucket for testing."""

    def __init__(
        self,
        *,
        head_sizes: dict[str, int] | None = None,
        copy_etag: str | None = None,
        process_sizes: list[int] | None = None,
        object_bytes: bytes | None = None,
    ) -> None:
        self.head_sizes = head_sizes or {}
        self.copy_etag = copy_etag or "AB" * 16
        self.process_sizes = process_sizes or []
        self.object_bytes = object_bytes or b""
        self.copied: list[tuple[str, str]] = []
        self.process_styles: list[str] = []
        self._process_call_count = 0
        self._head_object_call_count = 0

    def head_object(self, key: str) -> Any:
        """Mock head_object returns object metadata."""
        # First check if it's in the pre-defined head_sizes (for copy tests)
        if key in self.head_sizes:
            return FakeObjectMeta(self.head_sizes[key])

        # Otherwise, it's for variant size tracking (called after process_object)
        if self._head_object_call_count < len(self.process_sizes):
            size = self.process_sizes[self._head_object_call_count]
        else:
            size = 2**21
        self._head_object_call_count += 1

        return FakeObjectMeta(size)

    def copy_object(self, source_bucket_name: str, source_key: str, target_key: str) -> Any:
        """Mock copy_object (real oss2 signature) records the copy and returns etag."""
        self.copied.append((source_key, target_key))

        class FakeCopyResult:
            def __init__(self, etag: str) -> None:
                self.etag = etag

        return FakeCopyResult(self.copy_etag)

    def process_object(self, source_key: str, style: str) -> Any:
        """Mock process_object records style."""
        self.process_styles.append(style)

        class FakeProcessResult:
            def __init__(self) -> None:
                pass

        return FakeProcessResult()

    def get_object(self, key: str) -> Any:
        """Mock get_object returns content."""

        class FakeStreamingBody:
            def __init__(self, content: bytes) -> None:
                self._content = content

            def read(self) -> bytes:
                return self._content

        return FakeStreamingBody(self.object_bytes)


class FailingBucket:
    """Mock OSS bucket that raises exceptions."""

    def __init__(self, fail_on: str = "head") -> None:
        self.fail_on = fail_on

    def head_object(self, key: str) -> Any:
        if self.fail_on == "head":
            raise RuntimeError("OSS head_object failed")
        return FakeObjectMeta(100)

    def copy_object(self, source_bucket_name: str, source_key: str, target_key: str) -> Any:
        if self.fail_on == "copy":
            raise RuntimeError("OSS copy_object failed")
        return type("FakeCopyResult", (), {"etag": "AB" * 16})()

    def process_object(self, source_key: str, style: str) -> Any:
        if self.fail_on == "process":
            raise RuntimeError("OSS process_object failed")
        return type("FakeProcessResult", (), {})()

    def get_object(self, key: str) -> Any:
        if self.fail_on == "get":
            raise RuntimeError("OSS get_object failed")
        return type("FakeStreamingBody", (), {"read": lambda: b""})()


def test_head_public_object_returns_size_and_etag() -> None:
    bucket = FakeBucket(head_sizes={"src.jpg": 100})
    bucket.head_object = lambda key: type("Meta", (), {"content_length": 100, "etag": "AB" * 16})()  # type: ignore[method-assign]
    size, etag = head_public_object("src.jpg", bucket_factory=lambda: bucket)
    assert size == 100
    assert etag == "AB" * 16


def test_head_public_object_rejects_multipart_etag() -> None:
    bucket = FakeBucket()
    bucket.head_object = lambda key: type("Meta", (), {"content_length": 100, "etag": "AB" * 16 + "-2"})()  # type: ignore[method-assign]
    with pytest.raises(OssOpsError) as err:
        head_public_object("src.jpg", bucket_factory=lambda: bucket)
    assert err.value.code == "asset_copy_unverifiable"


def test_head_public_object_raises_asset_unavailable_on_head_failure() -> None:
    bucket = FailingBucket(fail_on="head")
    with pytest.raises(OssOpsError) as err:
        head_public_object("src.jpg", bucket_factory=lambda: bucket)
    assert err.value.code == "asset_unavailable"


def test_copy_public_object_returns_etag() -> None:
    bucket = FakeBucket(copy_etag="AB" * 16)
    etag = copy_public_object("src.jpg", "dst.jpg", bucket_factory=lambda: bucket)
    assert etag == "AB" * 16
    assert bucket.copied == [("src.jpg", "dst.jpg")]


def test_copy_public_object_rejects_multipart_etag() -> None:
    bucket = FakeBucket(copy_etag="AB" * 16 + "-2")
    with pytest.raises(OssOpsError) as err:
        copy_public_object("src.jpg", "dst.jpg", bucket_factory=lambda: bucket)
    assert err.value.code == "asset_copy_unverifiable"


def test_generate_wechat_variant_stops_at_first_fit() -> None:
    # first ladder rung produces 800KB -> accepted, content fetched & hashed
    bucket = FakeBucket(process_sizes=[800 * 1024], object_bytes=b"jpegbytes")
    variant = generate_wechat_variant("src.jpg", "dir", mime_type="image/jpeg", bucket_factory=lambda: bucket)
    assert variant.object_key == "dir/variants/wechat-body-v1.jpg"
    assert variant.sha256 == hashlib.sha256(b"jpegbytes").hexdigest()
    assert "resize,l_1920" in bucket.process_styles[0]
    assert "quality,q_90" in bucket.process_styles[0]


def test_generate_wechat_variant_walks_ladder_then_fails() -> None:
    bucket = FakeBucket(process_sizes=[2**21] * 36)  # every rung too big
    with pytest.raises(OssOpsError) as err:
        generate_wechat_variant("src.jpg", "dir", mime_type="image/jpeg", bucket_factory=lambda: bucket)
    assert err.value.code == "invalid_wechat_image"


def test_generate_wechat_variant_rejects_gif() -> None:
    with pytest.raises(OssOpsError) as err:
        generate_wechat_variant("src.gif", "dir", mime_type="image/gif", bucket_factory=lambda: FakeBucket())
    assert err.value.code == "invalid_wechat_image"


def test_generate_wechat_variant_png_ladder_stays_png() -> None:
    bucket = FakeBucket(process_sizes=[800 * 1024], object_bytes=b"pngbytes")
    variant = generate_wechat_variant("src.png", "dir", mime_type="image/png", bucket_factory=lambda: bucket)
    assert variant.extension == "png"
    assert "format,png" in bucket.process_styles[0]
    assert "quality" not in bucket.process_styles[0]


def test_copy_public_object_raises_asset_unavailable_on_copy_failure() -> None:
    bucket = FailingBucket(fail_on="copy")
    with pytest.raises(OssOpsError) as err:
        copy_public_object("src.jpg", "dst.jpg", bucket_factory=lambda: bucket)
    assert err.value.code == "asset_unavailable"


def test_generate_wechat_variant_raises_asset_unavailable_on_process_failure() -> None:
    bucket = FailingBucket(fail_on="process")
    with pytest.raises(OssOpsError) as err:
        generate_wechat_variant("src.jpg", "dir", mime_type="image/jpeg", bucket_factory=lambda: bucket)
    assert err.value.code == "asset_unavailable"


def test_generate_wechat_variant_raises_asset_unavailable_on_head_failure() -> None:
    bucket = FailingBucket(fail_on="head")
    with pytest.raises(OssOpsError) as err:
        generate_wechat_variant("src.jpg", "dir", mime_type="image/jpeg", bucket_factory=lambda: bucket)
    assert err.value.code == "asset_unavailable"


def test_generate_wechat_variant_raises_asset_unavailable_on_get_failure() -> None:
    bucket = FailingBucket(fail_on="get")
    bucket.process_object = lambda source_key, style: type("FakeProcessResult", (), {})()  # type: ignore[method-assign]
    bucket.head_object = lambda key: FakeObjectMeta(800 * 1024)  # type: ignore[method-assign]
    with pytest.raises(OssOpsError) as err:
        generate_wechat_variant("src.jpg", "dir", mime_type="image/jpeg", bucket_factory=lambda: bucket)
    assert err.value.code == "asset_unavailable"


class MissingKeyBucket:
    """head_object raises a 404-status error, like oss2.exceptions.NotFound."""

    def head_object(self, key: str) -> Any:
        error = RuntimeError("not found")
        error.status = 404  # type: ignore[attr-defined]
        raise error


class SigningBucket:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, dict[str, str]]] = []

    def sign_url(self, method: str, key: str, expires: int, headers: dict[str, str]) -> str:
        self.calls.append((method, key, expires, headers))
        return f"https://signed.invalid/{key}"


def test_head_public_object_maps_404_to_asset_missing() -> None:
    with pytest.raises(OssOpsError) as err:
        head_public_object("gone.jpg", bucket_factory=MissingKeyBucket)
    assert err.value.code == "asset_missing"


def test_sign_public_put_url_binds_md5_and_content_type() -> None:
    bucket = SigningBucket()
    url = sign_public_put_url(
        "public/wxposts/x/assets/y/original.jpg",
        content_md5="q1MKE+RmcQ2+5nvUVx4Oow==",
        content_type="image/jpeg",
        bucket_factory=lambda: bucket,
    )
    assert url == "https://signed.invalid/public/wxposts/x/assets/y/original.jpg"
    method, key, expires, headers = bucket.calls[0]
    assert method == "PUT"
    assert expires == 3600
    assert headers == {
        "Content-MD5": "q1MKE+RmcQ2+5nvUVx4Oow==",
        "Content-Type": "image/jpeg",
    }


def test_sign_public_put_url_upgrades_http_to_https() -> None:
    class HttpSigner:
        def sign_url(self, method: str, key: str, expires: int, headers: dict[str, str]) -> str:
            return f"http://soarhigh.oss-cn-shenzhen.aliyuncs.com/{key}?signature=abc"

    url = sign_public_put_url(
        "public/wxposts/x/assets/y/original.jpg",
        content_md5="AA==",
        content_type="image/jpeg",
        bucket_factory=HttpSigner,
    )
    assert url == ("https://soarhigh.oss-cn-shenzhen.aliyuncs.com/public/wxposts/x/assets/y/original.jpg?signature=abc")


def test_sign_public_put_url_raises_asset_unavailable_on_failure() -> None:
    class FailingSigner:
        def sign_url(self, method: str, key: str, expires: int, headers: dict[str, str]) -> str:
            raise RuntimeError("boom")

    with pytest.raises(OssOpsError) as err:
        sign_public_put_url(
            "k.jpg",
            content_md5="AA==",
            content_type="image/jpeg",
            bucket_factory=FailingSigner,
        )
    assert err.value.code == "asset_unavailable"
