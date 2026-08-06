"""Deterministic Public Revision projection into one WeChat draft."""

from __future__ import annotations

import hashlib
import html as html_module
import json
import re
from html.parser import HTMLParser
from typing import Literal, Protocol
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import UUID, uuid4

import httpx

from ..config import (
    WECHAT_GATEWAY_BASE_URL,
    WECHAT_GATEWAY_SERVICE_TOKEN,
    WECHAT_OFFICIAL_ACCOUNT_NAME,
)
from ..db import wxpost_wechat as store
from ..models.wxpost import Presentation, WxPostRenderDocument, WxPostWechatDraftResult, WxPostWechatDraftStatus

WECHAT_PROJECTION_VERSION = 14
IMG_SRC_RE = re.compile(r'<img\b[^>]*\bsrc="([^"]+)"', re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")
ANCHOR_TAG_RE = re.compile(r"</?a\b[^>]*>", re.IGNORECASE)
STYLE_ATTRIBUTE_RE = re.compile(r'\bstyle\s*=\s*"([^"]*)"', re.IGNORECASE)
BORDER_DECLARATION_RE = re.compile(
    r"(?:^|;)\s*border(?:-(?:top|right|bottom|left))?(?:-color)?\s*:",
    re.IGNORECASE,
)
LIST_LEADING_WHITESPACE_RE = re.compile(r"(<(?:ul|ol)\b[^>]*>)\s+(?=<li\b)", re.IGNORECASE)
LIST_ITEM_WHITESPACE_RE = re.compile(r"(</li>)\s+(?=<(?:li\b|/(?:ul|ol)\b))", re.IGNORECASE)
IMAGE_WRAPPER_RE = re.compile(
    r'(<div\b[^>]*style=")([^"]*)("[^>]*>\s*<img\b)',
    re.IGNORECASE,
)
ARTICLE_HEADER_RE = re.compile(
    r"(?P<article><article\b[^>]*>)\s*(?P<header><header\b[^>]*>).*?</header>",
    re.IGNORECASE | re.DOTALL,
)
EDITOR_ATTRIBUTE_RE = re.compile(
    r"\s(?:data-[a-z0-9_-]+|contenteditable)" r"(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?",
    re.IGNORECASE,
)
ACTIVE_TAG_RE = re.compile(r"^<\s*/?\s*(?:script|iframe|form|style|link|object|embed)\b", re.IGNORECASE)
EVENT_ATTRIBUTE_RE = re.compile(r"\son[a-z0-9_-]+\s*=", re.IGNORECASE)
JAVASCRIPT_URL_RE = re.compile(r"\s(?:href|src)\s*=\s*(['\"])\s*javascript:", re.IGNORECASE)
CANONICAL_ROOT_PADDING = "29.44px clamp(12px,calc(5.0405% - 7.6578px),29.44px)"
WECHAT_ROOT_PADDING = "0 0 29.44px"
CANONICAL_BODY_PADDING_TOP = "32px"
WECHAT_BODY_PADDING_TOP = "0"
WECHAT_HEADER_RULE_MARGIN = "0 0 16px"
WECHAT_HEADER_RULE_PROPERTIES = {"border-top", "border-image"}
WECHAT_HEADER_RULE_MAX_WIDTH = "2px"
WECHAT_LIGHT_PALETTE_BY_DARK_TOKEN: dict[str, dict[str, str]] = {
    "brand-blue": {
        "#10131a": "#ffffff",
        "#f3f4f6": "#111827",
        "#aeb7c5": "#5f6b7a",
        "#60a5fa": "#2563eb",
        "#a78bfa": "#7c3aed",
        "#1c2332": "#eef2ff",
        "#30394b": "#dbe3f3",
    },
    "paper-neutral": {
        "#1b1a17": "#f8f6f0",
        "#f0ede4": "#25231f",
        "#b9b2a5": "#706b61",
        "#e2ddd2": "#2d2b27",
        "#9b9285": "#9b9285",
        "#2a2722": "#efebe1",
        "#514c43": "#c9c1b5",
    },
    "fresh-sage": {
        "#121915": "#f8faf5",
        "#edf5ef": "#24332a",
        "#aab8ad": "#66736a",
        "#8fc49d": "#4f7a5b",
        "#d7b66c": "#b28b3b",
        "#1e2922": "#edf4e8",
        "#39483d": "#cad8c8",
    },
    "warm-terracotta": {
        "#211612": "#fffaf2",
        "#fff1e7": "#3d2d27",
        "#c9a99a": "#80685d",
        "#fb8b61": "#d8653b",
        "#f6bd60": "#e9a23b",
        "#34231c": "#fff0dd",
        "#5c3c30": "#e6c9b7",
    },
    "minimal-mono": {
        "#111111": "#ffffff",
        "#f5f5f5": "#171717",
        "#b5b5b5": "#6b6b6b",
        "#ffffff": "#171717",
        "#a3a3a3": "#a3a3a3",
        "#222222": "#f5f5f5",
        "#404040": "#d4d4d4",
    },
}
WECHAT_BASE_TEXT_BY_PALETTE = {
    "brand-blue": "#111827",
    "paper-neutral": "#25231f",
    "fresh-sage": "#24332a",
    "warm-terracotta": "#3d2d27",
    "minimal-mono": "#171717",
}
WECHAT_ROOT_SURFACE_PROPERTIES = {"background", "border", "box-shadow"}


class WechatDraftError(Exception):
    def __init__(self, message: str, *, status_code: int = 502, uncertain: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.uncertain = uncertain


class WechatDraftApi(Protocol):
    async def close(self) -> None: ...

    async def upload_body_image(self, filename: str, content: bytes, mime_type: str) -> str: ...

    async def upload_cover(self, filename: str, content: bytes, mime_type: str) -> str: ...

    async def add_draft(self, article: dict) -> str: ...

    async def update_draft(self, media_id: str, article: dict) -> None: ...

    async def get_draft(self, media_id: str) -> dict: ...

    async def batch_get_drafts(self, *, count: int = 20) -> list[dict]: ...


def _sha256(value: bytes | str) -> str:
    data = value.encode() if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


class WechatGatewayClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client or httpx.AsyncClient(timeout=30, trust_env=False)
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        files: dict | None = None,
        params: dict[str, str] | None = None,
        uncertain_on_transport: bool = False,
    ) -> dict:
        if not WECHAT_GATEWAY_BASE_URL or not WECHAT_GATEWAY_SERVICE_TOKEN:
            raise WechatDraftError("The WeChat API gateway is not configured.", status_code=503)
        try:
            response = await self.client.request(
                method,
                f"{WECHAT_GATEWAY_BASE_URL}{path}",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {WECHAT_GATEWAY_SERVICE_TOKEN}",
                },
                params=params,
                json=json_body,
                files=files,
            )
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise WechatDraftError(
                "The WeChat API gateway response was unavailable.",
                uncertain=uncertain_on_transport,
            ) from error
        if not isinstance(payload, dict):
            raise WechatDraftError("The WeChat API gateway returned an invalid response.")
        if not response.is_success:
            message = payload.get("message")
            gateway_uncertain = payload.get("uncertain") is True
            status_code = 503 if response.status_code in {401, 403} else 502
            raise WechatDraftError(
                message if isinstance(message, str) else "The WeChat API gateway rejected the request.",
                status_code=status_code,
                uncertain=uncertain_on_transport and gateway_uncertain,
            )
        return payload

    async def upload_body_image(self, filename: str, content: bytes, mime_type: str) -> str:
        payload = await self._request("POST", "/v1/images/body", files={"media": (filename, content, mime_type)})
        if not isinstance(payload.get("url"), str):
            raise WechatDraftError("The WeChat API gateway did not return a body-image URL.")
        return payload["url"]

    async def upload_cover(self, filename: str, content: bytes, mime_type: str) -> str:
        payload = await self._request("POST", "/v1/images/cover", files={"media": (filename, content, mime_type)})
        if not isinstance(payload.get("mediaId"), str):
            raise WechatDraftError("The WeChat API gateway did not return a cover media ID.")
        return payload["mediaId"]

    async def add_draft(self, article: dict) -> str:
        payload = await self._request("POST", "/v1/drafts", json_body={"article": article}, uncertain_on_transport=True)
        if not isinstance(payload.get("mediaId"), str):
            raise WechatDraftError("The WeChat API gateway did not return a draft media ID.", uncertain=True)
        return payload["mediaId"]

    async def update_draft(self, media_id: str, article: dict) -> None:
        await self._request(
            "PUT",
            f"/v1/drafts/{quote(media_id, safe='')}",
            json_body={"article": article},
        )

    async def get_draft(self, media_id: str) -> dict:
        payload = await self._request("GET", f"/v1/drafts/{quote(media_id, safe='')}")
        article = payload.get("article")
        if not isinstance(article, dict):
            raise WechatDraftError("The WeChat API gateway returned an invalid draft readback.")
        return article

    async def batch_get_drafts(self, *, count: int = 20) -> list[dict]:
        payload = await self._request("GET", "/v1/drafts", params={"limit": str(count)})
        items = payload.get("items")
        if not isinstance(items, list):
            raise WechatDraftError("The WeChat API gateway returned an invalid draft list.")
        return [item for item in items if isinstance(item, dict)]


def wechat_status(row: dict, projection: dict | None) -> WxPostWechatDraftStatus:
    if not projection:
        return WxPostWechatDraftStatus(state="not-created")
    presentation = Presentation.model_validate(projection["presentation"]) if projection.get("presentation") else None
    state = projection.get("state", "idle")
    return WxPostWechatDraftStatus(
        state="not-created" if state == "idle" else state,
        source_public_revision=projection.get("source_public_revision"),
        presentation=presentation,
        readback_changed=projection.get("readback_changed"),
        needs_update=projection.get("source_public_revision") != row["article_revision"],
        message=projection.get("last_error"),
    )


def validate_wechat_projection(render_document: WxPostRenderDocument) -> None:
    if any(node.kind == "directive" and node.name == "video" for node in render_document.body):
        raise WechatDraftError(
            "This Revision contains a Video block, which is not supported for WeChat Drafts in Phase 3.",
            status_code=422,
        )
    if len(render_document.title) > 32:
        raise WechatDraftError("The title exceeds WeChat's 32-character limit.", status_code=422)
    if render_document.byline and len(render_document.byline) > 16:
        raise WechatDraftError("The byline exceeds WeChat's 16-character author limit.", status_code=422)
    if not render_document.byline and len(WECHAT_OFFICIAL_ACCOUNT_NAME) > 16:
        raise WechatDraftError(
            "The configured Official Account name exceeds WeChat's 16-character author limit.", status_code=422
        )
    if render_document.excerpt and len(render_document.excerpt) > 120:
        raise WechatDraftError("The excerpt exceeds WeChat's 120-character digest limit.", status_code=422)
    if not render_document.cover_media_id:
        raise WechatDraftError("A cover image is required before publishing to WeChat Drafts.", status_code=422)


async def _download_image(client: httpx.AsyncClient, url: str, *, body: bool) -> tuple[bytes, str, str]:
    try:
        response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise WechatDraftError("A Public Revision image could not be downloaded.") from error
    content = response.content
    mime_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    allowed = (
        {"image/jpeg": "jpg", "image/png": "png"}
        if body
        else {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/gif": "gif",
            "image/bmp": "bmp",
        }
    )
    if mime_type not in allowed:
        message = (
            "WeChat body images must be JPG or PNG." if body else "WeChat cover images must be JPG, PNG, GIF, or BMP."
        )
        raise WechatDraftError(message, status_code=422)
    if body and len(content) >= 1024 * 1024:
        raise WechatDraftError("A WeChat body image is 1 MB or larger.", status_code=422)
    if not body and len(content) > 10 * 1024 * 1024:
        raise WechatDraftError("A WeChat cover image is larger than 10 MB.", status_code=422)
    if not content:
        raise WechatDraftError("A Public Revision image is empty.", status_code=422)
    return content, mime_type, allowed[mime_type]


def _replace_body_image_urls(
    canonical_html: str,
    body_urls: list[str],
    images: dict[str, tuple[bytes, str, str, str]],
    mappings: dict,
) -> str:
    replaced: set[str] = set()

    def replace_image_source(match: re.Match[str]) -> str:
        tag = match.group(0)
        source_match = IMG_SRC_RE.search(tag)
        if source_match is None:
            return tag
        source = html_module.unescape(source_match.group(1))
        image = images.get(source)
        if image is None:
            return tag
        replacement = html_module.escape(mappings[f"body:{image[3]}"], quote=True)
        replaced.add(source)
        start, end = source_match.span(1)
        return f"{tag[:start]}{replacement}{tag[end:]}"

    submitted_html = HTML_TAG_RE.sub(replace_image_source, canonical_html)
    if set(body_urls) != replaced:
        raise WechatDraftError("Not every Public Revision image URL could be replaced.", status_code=422)
    if len(submitted_html.encode()) >= 1_000_000 or len(submitted_html) >= 20_000:
        raise WechatDraftError("The rendered article exceeds WeChat's HTML size limit.", status_code=422)
    return submitted_html


def _map_wechat_appearance(rendered_html: str, presentation: Presentation) -> str:
    if presentation.appearance != "dark":
        return rendered_html
    palette = WECHAT_LIGHT_PALETTE_BY_DARK_TOKEN[presentation.palette]
    token_pattern = re.compile(
        "|".join(re.escape(token) for token in palette),
        flags=re.IGNORECASE,
    )

    def map_tag(match: re.Match[str]) -> str:
        tag = match.group(0)

        def map_style(style_match: re.Match[str]) -> str:
            style = token_pattern.sub(
                lambda token_match: palette[token_match.group(0).lower()],
                style_match.group(1),
            )
            return f'style="{style}"'

        return STYLE_ATTRIBUTE_RE.sub(map_style, tag)

    return HTML_TAG_RE.sub(map_tag, rendered_html)


def _remove_root_surface(style: str) -> str:
    declarations = []
    for declaration in style.split(";"):
        declaration = declaration.strip()
        if not declaration:
            continue
        property_name, separator, _ = declaration.partition(":")
        if separator and property_name.strip().lower() in WECHAT_ROOT_SURFACE_PROPERTIES:
            continue
        declarations.append(declaration)
    return ";".join(declarations)


def _remove_base_text_color(style: str, palette: str) -> str:
    base_text = WECHAT_BASE_TEXT_BY_PALETTE[palette]
    declarations = []
    for declaration in style.split(";"):
        declaration = declaration.strip()
        if not declaration:
            continue
        property_name, separator, value = declaration.partition(":")
        if separator and property_name.strip().lower() == "color" and value.strip().lower() == base_text:
            continue
        declarations.append(declaration)
    return ";".join(declarations)


def _replace_article_header(match: re.Match[str]) -> str:
    style_match = STYLE_ATTRIBUTE_RE.search(match.group("header"))
    if style_match is None:
        return match.group("article")
    rule_declarations = []
    for declaration in style_match.group(1).split(";"):
        declaration = declaration.strip()
        property_name, separator, value = declaration.partition(":")
        if separator and property_name.strip().lower() in WECHAT_HEADER_RULE_PROPERTIES:
            if property_name.strip().lower() == "border-top":
                value = re.sub(r"^4px\b", WECHAT_HEADER_RULE_MAX_WIDTH, value.strip())
                declaration = f"{property_name}:{value}"
            rule_declarations.append(declaration)
    if not rule_declarations:
        return match.group("article")
    rule_style = ";".join([*rule_declarations, f"margin:{WECHAT_HEADER_RULE_MARGIN}"])
    return f'{match.group("article")}<div style="{rule_style}"></div>'


def _sanitize_wechat_html(rendered_html: str, presentation: Presentation) -> str:
    rendered_html = _map_wechat_appearance(rendered_html, presentation)

    def transform_style(tag: str) -> str:
        def replace_style(match: re.Match[str]) -> str:
            style = _remove_base_text_color(match.group(1), presentation.palette)
            if tag.lower().startswith("<blockquote") and not BORDER_DECLARATION_RE.search(style):
                style = f"border:0!important;padding:0!important;{style}"

            return f'style="{style}"'

        return STYLE_ATTRIBUTE_RE.sub(replace_style, tag, count=1)

    def sanitize_tag(match: re.Match[str]) -> str:
        tag = match.group(0)
        if ACTIVE_TAG_RE.search(tag) or EVENT_ATTRIBUTE_RE.search(tag) or JAVASCRIPT_URL_RE.search(tag):
            raise WechatDraftError(
                "Canonical HTML contains active content that cannot be submitted to WeChat.",
                status_code=422,
            )
        if tag.lower().startswith("<article"):
            tag = tag.replace(
                f"padding:{CANONICAL_ROOT_PADDING}",
                f"padding:{WECHAT_ROOT_PADDING}",
            )
            tag = STYLE_ATTRIBUTE_RE.sub(
                lambda match: f'style="{_remove_root_surface(match.group(1))}"',
                tag,
                count=1,
            )
            if "text-align:" not in tag.lower():
                tag = tag.replace('style="', 'style="text-align:left!important;', 1)
        if "data-wxpost-body" in tag.lower():
            tag = tag.replace(
                f"padding-top:{CANONICAL_BODY_PADDING_TOP}",
                f"padding-top:{WECHAT_BODY_PADDING_TOP}",
            )
        if tag.lower().startswith("<h2"):
            tag = re.sub(r"&#(?:x22|34);", "&quot;", tag, flags=re.IGNORECASE)
        return EDITOR_ATTRIBUTE_RE.sub("", transform_style(tag))

    sanitized = HTML_TAG_RE.sub(sanitize_tag, rendered_html)
    sanitized = ARTICLE_HEADER_RE.sub(_replace_article_header, sanitized, count=1)
    sanitized = ANCHOR_TAG_RE.sub("", sanitized)
    sanitized = IMAGE_WRAPPER_RE.sub(
        r"\1font-size:0!important;line-height:0!important;\2\3",
        sanitized,
    )
    sanitized = LIST_LEADING_WHITESPACE_RE.sub(r"\1", sanitized)
    return LIST_ITEM_WHITESPACE_RE.sub(r"\1", sanitized)


def _article_payload(render_document: WxPostRenderDocument, submitted_html: str, cover_media_id: str) -> dict:
    article = {
        "article_type": "news",
        "title": render_document.title,
        "content": submitted_html,
        "thumb_media_id": cover_media_id,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }
    author = render_document.byline or WECHAT_OFFICIAL_ACCOUNT_NAME
    if author:
        article["author"] = author
    if render_document.excerpt:
        article["digest"] = render_document.excerpt
    return article


def _draft_candidate_article(item: dict) -> tuple[str, dict] | None:
    media_id = item.get("media_id")
    content = item.get("content")
    news_items = content.get("news_item") if isinstance(content, dict) else None
    if not isinstance(media_id, str) or not isinstance(news_items, list) or not news_items:
        return None
    article = news_items[0]
    return (media_id, article) if isinstance(article, dict) else None


class _ContentSignatureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.parts.append(("start", tag))
        if tag == "img":
            attributes = {name.lower(): value for name, value in attrs}
            source = attributes.get("src") or attributes.get("data-src")
            if source:
                self.parts.append(("image", source))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        self.parts.append(("end", tag))

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", data).strip()
        if text:
            self.parts.append(("text", text))


def _content_signature(content: str) -> tuple[tuple[str, str], ...]:
    parser = _ContentSignatureParser()
    parser.feed(content)
    parser.close()
    return tuple(parser.parts)


async def publish_wechat_draft(
    *,
    row: dict,
    render_document: WxPostRenderDocument,
    presentation: Presentation,
    canonical_html: str,
    api: WechatDraftApi | None = None,
    download_client: httpx.AsyncClient | None = None,
) -> WxPostWechatDraftResult:
    validate_wechat_projection(render_document)
    workspace_id = row.get("source_workspace_id")
    if not isinstance(workspace_id, str) or not workspace_id:
        raise WechatDraftError("Only workspace-backed Public Revisions can be published to WeChat.", status_code=422)

    platform_html = _sanitize_wechat_html(canonical_html, presentation)
    media_by_url = {str(item.source_url): item for item in render_document.media if item.kind == "image"}
    body_urls = list(dict.fromkeys(html_module.unescape(url) for url in IMG_SRC_RE.findall(platform_html)))
    unknown = [url for url in body_urls if url not in media_by_url]
    if unknown:
        raise WechatDraftError("Canonical HTML contains an unknown image URL.", status_code=422)
    cover = next((item for item in render_document.media if item.id == render_document.cover_media_id), None)
    if cover is None or cover.kind != "image":
        raise WechatDraftError("The selected cover is not an available image.", status_code=422)

    owns_download = download_client is None
    downloader = download_client or httpx.AsyncClient(timeout=30, trust_env=False)
    images: dict[str, tuple[bytes, str, str, str]] = {}
    try:
        for url in list(dict.fromkeys([*body_urls, str(cover.source_url)])):
            content, mime_type, extension = await _download_image(downloader, url, body=url in body_urls)
            images[url] = (content, mime_type, extension, _sha256(content))
    finally:
        if owns_download:
            await downloader.aclose()

    projection_payload = {
        "workspace": workspace_id,
        "wxpost": str(row["id"]),
        "revision": row["article_revision"],
        "presentation": presentation.model_dump(by_alias=True, mode="json"),
        "renderVersion": render_document.render_version,
        "wechatProjectionVersion": WECHAT_PROJECTION_VERSION,
        "platformHtmlSha256": _sha256(platform_html),
        "assets": [images[url][3] for url in [*body_urls, str(cover.source_url)]],
    }
    projection_sha256 = _sha256(json.dumps(projection_payload, sort_keys=True, separators=(",", ":")))
    operation_id = uuid4()
    claim = store.claim_projection(
        workspace_id=workspace_id,
        wxpost_id=UUID(str(row["id"])),
        revision=row["article_revision"],
        presentation=projection_payload["presentation"],
        projection_sha256=projection_sha256,
        operation_id=operation_id,
    )
    projection = claim["row"]
    mappings = dict(projection.get("asset_mappings") or {})
    cover_digest = images[str(cover.source_url)][3]
    cover_key = f"cover:{cover_digest}"
    if not claim["acquired"]:
        reason = claim["reason"]
        if reason == "busy":
            raise WechatDraftError("Another WeChat draft operation is already running.", status_code=409)
        if reason == "uncertain":
            if projection.get("projection_sha256") != projection_sha256:
                raise WechatDraftError(
                    "The previous WeChat draft creation result is uncertain for an older Public Revision. "
                    "Resolve that draft before publishing the current Revision.",
                    status_code=409,
                )
            required_keys = {f"body:{images[url][3]}" for url in body_urls} | {cover_key}
            if not required_keys.issubset(mappings):
                raise WechatDraftError(
                    "The previous WeChat draft creation result is uncertain. "
                    "Check the Official Account draft box before retrying.",
                    status_code=409,
                )
            submitted_html = _replace_body_image_urls(platform_html, body_urls, images, mappings)
            expected_article = _article_payload(render_document, submitted_html, mappings[cover_key])
            client = api or WechatGatewayClient()
            try:
                candidates: list[str] = []
                for item in await client.batch_get_drafts():
                    candidate = _draft_candidate_article(item)
                    if candidate is None:
                        continue
                    media_id, article = candidate
                    fields = ("title", "author", "digest", "thumb_media_id")
                    candidate_content = article.get("content")
                    if (
                        all((article.get(field) or "") == (expected_article.get(field) or "") for field in fields)
                        and isinstance(candidate_content, str)
                        and _content_signature(candidate_content) == _content_signature(submitted_html)
                    ):
                        candidates.append(media_id)
                if len(candidates) != 1:
                    raise WechatDraftError(
                        "The previous WeChat draft creation result is uncertain and could not be uniquely recovered. "
                        "Check the Official Account draft box before retrying.",
                        status_code=409,
                    )
                media_id = candidates[0]
                readback = await client.get_draft(media_id)
            finally:
                if api is None:
                    await client.close()
            readback_content = readback.get("content")
            if not isinstance(readback_content, str):
                raise WechatDraftError("WeChat readback did not contain HTML content.")
            submitted_sha = _sha256(submitted_html)
            readback_sha = _sha256(readback_content)
            store.recover_uncertain_projection(
                workspace_id,
                {
                    "wechat_media_id": media_id,
                    "submitted_html_sha256": submitted_sha,
                    "readback_html_sha256": readback_sha,
                    "readback_changed": readback_sha != submitted_sha,
                },
            )
            return WxPostWechatDraftResult(
                state="ready",
                action="unchanged",
                source_public_revision=projection.get("source_public_revision"),
                presentation=Presentation.model_validate(projection["presentation"]),
                readback_changed=readback_sha != submitted_sha,
                needs_update=False,
                preview_url=readback.get("url"),
            )
        media_id = projection.get("wechat_media_id")
        if not media_id:
            raise WechatDraftError("The existing WeChat projection is incomplete.", status_code=409)
        required_keys = {f"body:{images[url][3]}" for url in body_urls} | {cover_key}
        if not required_keys.issubset(mappings):
            raise WechatDraftError("The existing WeChat projection is incomplete.", status_code=409)
        submitted_html = _replace_body_image_urls(platform_html, body_urls, images, mappings)
        client = api or WechatGatewayClient()
        try:
            readback = await client.get_draft(media_id)
        finally:
            if api is None:
                await client.close()
        readback_content = readback.get("content")
        if not isinstance(readback_content, str):
            raise WechatDraftError("WeChat readback did not contain HTML content.")
        submitted_sha = _sha256(submitted_html)
        readback_sha = _sha256(readback_content)
        readback_changed = readback_sha != submitted_sha
        if (
            projection.get("submitted_html_sha256") != submitted_sha
            or projection.get("readback_html_sha256") != readback_sha
            or projection.get("readback_changed") != readback_changed
        ):
            operation_id = projection.get("operation_id")
            if not operation_id:
                raise WechatDraftError("The existing WeChat projection is incomplete.", status_code=409)
            store.mark_projection_ready(
                workspace_id,
                UUID(str(operation_id)),
                media_id=media_id,
                submitted_html_sha256=submitted_sha,
                readback_html_sha256=readback_sha,
                readback_changed=readback_changed,
            )
        return WxPostWechatDraftResult(
            state="ready",
            action="unchanged",
            source_public_revision=projection.get("source_public_revision"),
            presentation=Presentation.model_validate(projection["presentation"]),
            readback_changed=readback_changed,
            needs_update=False,
            preview_url=readback.get("url"),
        )

    client = api or WechatGatewayClient()
    try:
        for index, url in enumerate(body_urls):
            content, mime_type, extension, digest = images[url]
            key = f"body:{digest}"
            if key not in mappings:
                mappings[key] = await client.upload_body_image(f"body-{index + 1}.{extension}", content, mime_type)
                store.save_asset_mappings(workspace_id, operation_id, mappings)
        cover_content, cover_mime, cover_extension, cover_digest = images[str(cover.source_url)]
        if cover_key not in mappings:
            mappings[cover_key] = await client.upload_cover(f"cover.{cover_extension}", cover_content, cover_mime)
            store.save_asset_mappings(workspace_id, operation_id, mappings)

        submitted_html = _replace_body_image_urls(platform_html, body_urls, images, mappings)
        article = _article_payload(render_document, submitted_html, mappings[cover_key])

        existing_media_id = projection.get("wechat_media_id")
        action: Literal["created", "updated"] = "updated" if existing_media_id else "created"
        if existing_media_id:
            await client.update_draft(existing_media_id, article)
            media_id = existing_media_id
        else:
            store.mark_add_started(workspace_id, operation_id)
            media_id = await client.add_draft(article)
            store.update_projection(workspace_id, operation_id, {"wechat_media_id": media_id})

        submitted_sha = _sha256(submitted_html)
        try:
            readback = await client.get_draft(media_id)
            readback_content = readback.get("content")
            if not isinstance(readback_content, str):
                raise WechatDraftError("WeChat readback did not contain HTML content.")
            readback_sha = _sha256(readback_content)
            preview_url = readback.get("url")
        except WechatDraftError:
            store.mark_projection_ready(
                workspace_id,
                operation_id,
                media_id=media_id,
                submitted_html_sha256=submitted_sha,
                readback_html_sha256=None,
                readback_changed=None,
            )
            raise
        ready = store.mark_projection_ready(
            workspace_id,
            operation_id,
            media_id=media_id,
            submitted_html_sha256=submitted_sha,
            readback_html_sha256=readback_sha,
            readback_changed=readback_sha != submitted_sha,
        )
        return WxPostWechatDraftResult(
            state="ready",
            action=action,
            source_public_revision=row["article_revision"],
            presentation=presentation,
            readback_changed=ready["readback_changed"],
            needs_update=False,
            preview_url=preview_url,
        )
    except WechatDraftError as error:
        current = store.get_projection(workspace_id)
        if not current or current.get("state") != "ready":
            store.mark_projection_failed(workspace_id, operation_id, uncertain=error.uncertain, message=str(error))
        raise
    finally:
        if api is None:
            await client.close()


async def get_preview_url(workspace_id: str, api: WechatDraftApi | None = None) -> str:
    projection = store.get_projection(workspace_id)
    if not projection or not projection.get("wechat_media_id"):
        raise WechatDraftError("No WeChat draft is linked to this Public Revision.", status_code=404)
    client = api or WechatGatewayClient()
    try:
        readback = await client.get_draft(projection["wechat_media_id"])
    finally:
        if api is None:
            await client.close()
    url = readback.get("url")
    if not isinstance(url, str):
        raise WechatDraftError("WeChat did not return a temporary preview URL.")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or parts.netloc.lower() != "mp.weixin.qq.com":
        raise WechatDraftError("WeChat did not return a valid temporary preview URL.")
    return urlunsplit(("https", parts.netloc, parts.path, parts.query, parts.fragment))
