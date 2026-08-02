"""Parse and validate the canonical Markdown body of a WxPost document."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

import yaml
from markdown_it import MarkdownIt
from pydantic import ValidationError

from ..models.wxpost import (
    Appearance,
    ArticleDocument,
    ArticleType,
    DirectiveBodyNode,
    DirectiveSummary,
    InlineExtensionSummary,
    Layout,
    MarkdownBodyNode,
    MediaAsset,
    MediaKind,
    Palette,
    Presentation,
    PresentationCapabilities,
    RenderBodyNode,
    Typeface,
    ValidationIssue,
    WxPostCapabilities,
    WxPostRenderDocument,
)
from .wxpost_directives import DIRECTIVE_DEFINITIONS, DIRECTIVE_REGISTRY, DirectiveModel

_DIRECTIVE_OPEN = re.compile(r"^:::([a-z][a-z0-9-]*)[ \t]*$")
_DIRECTIVE_CLOSE = re.compile(r"^:::[ \t]*$")
_KEY_POINT = re.compile(r"(?<!\\)==(?P<text>[^=\n][^=\n]*?)==")
_MARKDOWN = MarkdownIt("commonmark", {"html": True})


@dataclass(frozen=True)
class ParsedDirective:
    name: str
    line: int
    payload: DirectiveModel

    @property
    def media_ids(self) -> list[str]:
        definition = DIRECTIVE_REGISTRY[self.name]
        return [reference.media_id for reference in definition.media_references(self.payload)]


@dataclass(frozen=True)
class ParsedArticle:
    body: list[RenderBodyNode]
    directives: list[ParsedDirective]
    key_point_count: int

    def directive_summaries(self) -> list[DirectiveSummary]:
        return [DirectiveSummary(name=item.name, line=item.line, media_ids=item.media_ids) for item in self.directives]

    def inline_summaries(self) -> list[InlineExtensionSummary]:
        return [InlineExtensionSummary(name="key-point", count=self.key_point_count)]

    def render_document(self, document: ArticleDocument) -> WxPostRenderDocument:
        return WxPostRenderDocument(
            schema_version=document.schema_version,
            render_version=1,
            title=document.title,
            slug=document.slug,
            excerpt=document.excerpt,
            byline=document.byline,
            article_type=document.article_type,
            custom_article_type=document.custom_article_type,
            source_meeting_id=document.source_meeting_id,
            media=document.media,
            cover_media_id=document.cover_media_id,
            presentation=document.presentation,
            body=self.body,
        )


class ArticleDocumentValidationError(Exception):
    def __init__(self, errors: list[ValidationIssue]):
        self.errors = errors
        super().__init__("WxPost ArticleDocument validation failed")


def capabilities() -> WxPostCapabilities:
    return WxPostCapabilities(
        document_schema=ArticleDocument.model_json_schema(by_alias=True),
        render_document_schema=WxPostRenderDocument.model_json_schema(by_alias=True),
        article_types=[item.value for item in ArticleType],
        directives=list(DIRECTIVE_REGISTRY),
        inline_extensions=["key-point"],
        presentation=PresentationCapabilities(
            layouts=[item.value for item in Layout],
            palettes=[item.value for item in Palette],
            appearances=[item.value for item in Appearance],
            typefaces=[item.value for item in Typeface],
        ),
        default_presentation=Presentation(
            layout=Layout.BRAND_DEFAULT,
            palette=Palette.PAPER_NEUTRAL,
            appearance=Appearance.LIGHT,
            typeface=Typeface.EDITORIAL_SERIF,
        ),
        directive_syntax=":::name\\nYAML mapping\\n:::",
        directive_schemas=[definition.capability() for definition in DIRECTIVE_DEFINITIONS],
        inline_syntax={"key-point": "==important phrase=="},
    )


def pydantic_validation_issues(error: ValidationError) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for item in error.errors(include_url=False):
        issues.append(
            ValidationIssue(
                code=str(item["type"]),
                path=[part for part in item["loc"] if isinstance(part, (str, int))],
                message=str(item["msg"]),
            )
        )
    return issues


def validate_and_parse(document: ArticleDocument) -> ParsedArticle:
    errors: list[ValidationIssue] = []
    _validate_document_shape(document, errors)
    parsed = _parse_markdown(document.body_markdown, errors)
    _validate_section_structure(parsed.body, errors)
    _validate_directive_media(
        parsed.directives,
        document.media,
        document.cover_media_id,
        errors,
    )

    if errors:
        raise ArticleDocumentValidationError(errors)
    return parsed


def _validate_document_shape(document: ArticleDocument, errors: list[ValidationIssue]) -> None:
    if document.article_type != ArticleType.CUSTOM and document.custom_article_type is not None:
        errors.append(
            ValidationIssue(
                code="custom_article_type_not_allowed",
                path=["customArticleType"],
                message="customArticleType is only allowed when articleType is custom.",
            )
        )

    by_id: dict[str, MediaAsset] = {}
    orders: dict[int, str] = {}
    for index, asset in enumerate(document.media):
        if asset.id in by_id:
            errors.append(
                ValidationIssue(
                    code="duplicate_media_id",
                    path=["media", index, "id"],
                    message=f"Media ID {asset.id!r} is already used.",
                )
            )
        else:
            by_id[asset.id] = asset
        if asset.order in orders:
            errors.append(
                ValidationIssue(
                    code="duplicate_media_order",
                    path=["media", index, "order"],
                    message=f"Media order {asset.order} is already used by {orders[asset.order]!r}.",
                )
            )
        else:
            orders[asset.order] = asset.id

    if document.cover_media_id:
        cover = by_id.get(document.cover_media_id)
        if cover is None:
            errors.append(
                ValidationIssue(
                    code="unknown_cover_media",
                    path=["coverMediaId"],
                    message=f"Cover media {document.cover_media_id!r} does not exist.",
                )
            )
        elif cover.kind != MediaKind.IMAGE:
            errors.append(
                ValidationIssue(
                    code="cover_media_kind_mismatch",
                    path=["coverMediaId"],
                    message="coverMediaId must reference an image.",
                )
            )
        elif not cover.include:
            errors.append(
                ValidationIssue(
                    code="cover_media_not_included",
                    path=["coverMediaId"],
                    message="coverMediaId must reference included media.",
                )
            )


def _parse_markdown(body: str, errors: list[ValidationIssue]) -> ParsedArticle:
    lines = body.splitlines()
    markdown_lines = list(lines)
    render_body: list[RenderBodyNode] = []
    directives: list[ParsedDirective] = []
    markdown_start = 0
    index = 0

    def flush_markdown(end: int) -> None:
        source = "\n".join(lines[markdown_start:end])
        if source.strip():
            render_body.append(
                MarkdownBodyNode(
                    source=source,
                    line=markdown_start + 1,
                )
            )

    while index < len(lines):
        line = lines[index]
        opening = _DIRECTIVE_OPEN.fullmatch(line)
        if not opening:
            if _DIRECTIVE_CLOSE.fullmatch(line):
                errors.append(
                    ValidationIssue(
                        code="unexpected_directive_close",
                        path=["bodyMarkdown"],
                        line=index + 1,
                        message="Found a directive closing fence without an opening fence.",
                    )
                )
            index += 1
            continue

        flush_markdown(index)
        name = opening.group(1)
        closing_index = index + 1
        while closing_index < len(lines) and not _DIRECTIVE_CLOSE.fullmatch(lines[closing_index]):
            if _DIRECTIVE_OPEN.fullmatch(lines[closing_index]):
                errors.append(
                    ValidationIssue(
                        code="nested_directive",
                        path=["bodyMarkdown"],
                        line=closing_index + 1,
                        directive=name,
                        message="Directives cannot be nested.",
                    )
                )
            closing_index += 1

        if closing_index >= len(lines):
            errors.append(
                ValidationIssue(
                    code="unclosed_directive",
                    path=["bodyMarkdown"],
                    line=index + 1,
                    directive=name,
                    message=f"Directive {name!r} is missing its closing ::: fence.",
                )
            )
            for line_index in range(index, len(lines)):
                markdown_lines[line_index] = ""
            markdown_start = len(lines)
            break

        for line_index in range(index, closing_index + 1):
            markdown_lines[line_index] = ""

        if name not in DIRECTIVE_REGISTRY:
            errors.append(
                ValidationIssue(
                    code="unknown_directive",
                    path=["bodyMarkdown"],
                    line=index + 1,
                    directive=name,
                    message=f"Directive {name!r} is not registered.",
                )
            )
            index = closing_index + 1
            markdown_start = index
            continue

        payload_text = "\n".join(lines[index + 1 : closing_index])
        payload = _load_directive_payload(name, payload_text, index + 1, errors)
        if payload is not None:
            directives.append(ParsedDirective(name=name, line=index + 1, payload=payload))
            render_body.append(
                DirectiveBodyNode(
                    name=name,
                    line=index + 1,
                    payload=payload.model_dump(mode="json", exclude_none=True),
                )
            )
        index = closing_index + 1
        markdown_start = index

    flush_markdown(len(lines))

    markdown = "\n".join(markdown_lines)
    tokens = _MARKDOWN.parse(markdown)
    for token in tokens:
        if token.type == "heading_open" and token.tag == "h1":
            errors.append(
                ValidationIssue(
                    code="body_h1_not_allowed",
                    path=["bodyMarkdown"],
                    line=(token.map[0] + 1) if token.map else None,
                    message="ArticleDocument.title is the only title; bodyMarkdown must start with prose or H2.",
                )
            )
        if token.type in {"html_block", "html_inline"}:
            errors.append(
                ValidationIssue(
                    code="unsafe_html",
                    path=["bodyMarkdown"],
                    line=(token.map[0] + 1) if token.map else None,
                    message="Raw HTML is not allowed in WxPost Markdown.",
                )
            )
        if token.children:
            for child in token.children:
                if child.type == "html_inline":
                    errors.append(
                        ValidationIssue(
                            code="unsafe_html",
                            path=["bodyMarkdown"],
                            line=(token.map[0] + 1) if token.map else None,
                            message="Raw HTML is not allowed in WxPost Markdown.",
                        )
                    )

    key_point_count = sum(
        len(_KEY_POINT.findall(child.content))
        for token in tokens
        if token.children
        for child in token.children
        if child.type == "text"
    )
    return ParsedArticle(
        body=render_body,
        directives=directives,
        key_point_count=key_point_count,
    )


def _validate_section_structure(
    body: list[RenderBodyNode],
    errors: list[ValidationIssue],
) -> None:
    for index, node in enumerate(body):
        if not isinstance(node, DirectiveBodyNode) or node.name != "section":
            continue
        following = body[index + 1] if index + 1 < len(body) else None
        if isinstance(following, MarkdownBodyNode):
            tokens = _MARKDOWN.parse(following.source)
            if tokens and tokens[0].type == "heading_open" and tokens[0].tag == "h2":
                continue
        errors.append(
            ValidationIssue(
                code="section_heading_required",
                path=["bodyMarkdown", "directive:section"],
                line=node.line,
                directive="section",
                message=("A section directive must be followed by a Markdown H2 " "heading."),
            )
        )


def _load_directive_payload(
    name: str,
    payload_text: str,
    opening_line: int,
    errors: list[ValidationIssue],
) -> DirectiveModel | None:
    try:
        raw_payload = yaml.safe_load(payload_text)
    except yaml.YAMLError as error:
        problem = getattr(error, "problem", None) or "Invalid YAML payload."
        mark = getattr(error, "problem_mark", None)
        errors.append(
            ValidationIssue(
                code="malformed_directive_yaml",
                path=["bodyMarkdown", f"directive:{name}"],
                line=opening_line + 1 + (mark.line if mark else 0),
                directive=name,
                message=str(problem),
            )
        )
        return None

    if not isinstance(raw_payload, dict):
        errors.append(
            ValidationIssue(
                code="directive_payload_not_mapping",
                path=["bodyMarkdown", f"directive:{name}"],
                line=opening_line,
                directive=name,
                message="A directive payload must be a non-empty YAML mapping.",
            )
        )
        return None

    unsafe_path = _find_unsafe_html(raw_payload)
    if unsafe_path is not None:
        errors.append(
            ValidationIssue(
                code="unsafe_html",
                path=["bodyMarkdown", f"directive:{name}", *unsafe_path],
                line=opening_line,
                directive=name,
                message="Raw HTML is not allowed in directive text.",
            )
        )
        return None

    model = DIRECTIVE_REGISTRY[name].payload_model
    try:
        return model.model_validate(raw_payload)
    except ValidationError as error:
        for item in error.errors(include_url=False):
            errors.append(
                ValidationIssue(
                    code="invalid_directive_payload",
                    path=[
                        "bodyMarkdown",
                        f"directive:{name}",
                        *(part for part in item["loc"] if isinstance(part, (str, int))),
                    ],
                    line=opening_line,
                    directive=name,
                    message=str(item["msg"]),
                )
            )
        return None


def _find_unsafe_html(value: Any, path: tuple[str | int, ...] = ()) -> list[str | int] | None:
    if isinstance(value, str):
        tokens = _MARKDOWN.parseInline(value)
        if any(child.type == "html_inline" for token in tokens for child in (token.children or [])):
            return list(path)
    elif isinstance(value, dict):
        for key, item in value.items():
            result = _find_unsafe_html(item, (*path, str(key)))
            if result is not None:
                return result
    elif isinstance(value, list):
        for index, item in enumerate(value):
            result = _find_unsafe_html(item, (*path, index))
            if result is not None:
                return result
    return None


def _validate_directive_media(
    directives: Iterable[ParsedDirective],
    media: list[MediaAsset],
    cover_media_id: str | None,
    errors: list[ValidationIssue],
) -> None:
    by_id = {asset.id: asset for asset in media}
    referenced_ids: set[str] = set()
    for directive in directives:
        definition = DIRECTIVE_REGISTRY[directive.name]
        for reference in definition.media_references(directive.payload):
            media_id = reference.media_id
            path = ["bodyMarkdown", f"directive:{directive.name}", *reference.payload_path]
            if media_id in referenced_ids:
                errors.append(
                    ValidationIssue(
                        code="duplicate_media_reference",
                        path=path,
                        line=directive.line,
                        directive=directive.name,
                        message=f"Media {media_id!r} is already used in the article body.",
                    )
                )
            else:
                referenced_ids.add(media_id)
            asset = by_id.get(media_id)
            if asset is None:
                errors.append(
                    ValidationIssue(
                        code="unknown_media_reference",
                        path=path,
                        line=directive.line,
                        directive=directive.name,
                        message=f"Media {media_id!r} does not exist.",
                    )
                )
            elif not asset.include:
                errors.append(
                    ValidationIssue(
                        code="media_not_included",
                        path=path,
                        line=directive.line,
                        directive=directive.name,
                        message=f"Media {media_id!r} is excluded from the article.",
                    )
                )
            elif asset.kind != reference.expected_kind:
                errors.append(
                    ValidationIssue(
                        code="media_kind_mismatch",
                        path=path,
                        line=directive.line,
                        directive=directive.name,
                        message=(
                            f"Directive {directive.name!r} requires {reference.expected_kind.value} media; "
                            f"{media_id!r} is {asset.kind.value}."
                        ),
                    )
                )

    for asset in media:
        if asset.include and asset.id not in referenced_ids and asset.id != cover_media_id:
            errors.append(
                ValidationIssue(
                    code="included_media_not_referenced",
                    path=["bodyMarkdown"],
                    message=(
                        f"Included media {asset.id!r} must appear in a supported "
                        "image, gallery, video, or person directive, or be the cover."
                    ),
                )
            )
