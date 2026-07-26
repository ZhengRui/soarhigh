"""Parse and validate the canonical Markdown body of a WePost document."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

import yaml
from markdown_it import MarkdownIt
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..models.wepost import (
    Appearance,
    ArticleDocument,
    ArticleType,
    DirectiveCapability,
    DirectiveSummary,
    InlineExtensionSummary,
    Layout,
    MediaAsset,
    MediaKind,
    Palette,
    Presentation,
    PresentationCapabilities,
    Typeface,
    ValidationIssue,
    WePostCapabilities,
)

_DIRECTIVE_OPEN = re.compile(r"^:::([a-z][a-z0-9-]*)[ \t]*$")
_DIRECTIVE_CLOSE = re.compile(r"^:::[ \t]*$")
_KEY_POINT = re.compile(r"(?<!\\)==(?P<text>[^=\n][^=\n]*?)==")
_MARKDOWN = MarkdownIt("commonmark", {"html": True})


class _DirectiveModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _GalleryPayload(_DirectiveModel):
    items: list[str] = Field(min_length=1)
    caption: str | None = Field(default=None, min_length=1)


class _VideoPayload(_DirectiveModel):
    media: str = Field(min_length=1)
    caption: str | None = Field(default=None, min_length=1)


class _TakeawayPayload(_DirectiveModel):
    text: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)


class _PersonPayload(_DirectiveModel):
    name: str = Field(min_length=1)
    role: str | None = Field(default=None, min_length=1)
    media: str | None = Field(default=None, min_length=1)
    summary: str | None = Field(default=None, min_length=1)
    quote: str | None = Field(default=None, min_length=1)


class _InfoGridItem(_DirectiveModel):
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)


class _InfoGridPayload(_DirectiveModel):
    title: str | None = Field(default=None, min_length=1)
    items: list[_InfoGridItem] = Field(min_length=1)


class _TimelineItem(_DirectiveModel):
    label: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str | None = Field(default=None, min_length=1)


class _TimelinePayload(_DirectiveModel):
    title: str | None = Field(default=None, min_length=1)
    items: list[_TimelineItem] = Field(min_length=1)


class _PullQuotePayload(_DirectiveModel):
    text: str = Field(min_length=1)
    attribution: str | None = Field(default=None, min_length=1)


@dataclass(frozen=True)
class _DirectiveDefinition:
    name: str
    payload_model: type[_DirectiveModel]
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    example: dict[str, Any]

    def capability(self) -> DirectiveCapability:
        return DirectiveCapability(
            name=self.name,
            required_fields=list(self.required_fields),
            optional_fields=list(self.optional_fields),
            example=self.example,
            payload_schema=self.payload_model.model_json_schema(),
        )


_DIRECTIVE_DEFINITIONS = (
    _DirectiveDefinition(
        name="gallery",
        payload_model=_GalleryPayload,
        required_fields=("items",),
        optional_fields=("caption",),
        example={"items": ["M01", "M02"], "caption": "Two moments from the evening"},
    ),
    _DirectiveDefinition(
        name="video",
        payload_model=_VideoPayload,
        required_fields=("media",),
        optional_fields=("caption",),
        example={"media": "V01", "caption": "A member tries the exercise again"},
    ),
    _DirectiveDefinition(
        name="takeaway",
        payload_model=_TakeawayPayload,
        required_fields=("text",),
        optional_fields=("title",),
        example={"title": "Try this next", "text": "Make the next action small enough to begin today."},
    ),
    _DirectiveDefinition(
        name="person",
        payload_model=_PersonPayload,
        required_fields=("name",),
        optional_fields=("role", "media", "summary", "quote"),
        example={
            "name": "Maya Chen",
            "role": "First-time speaker",
            "media": "M03",
            "summary": "She returned to the stage after feedback.",
        },
    ),
    _DirectiveDefinition(
        name="info-grid",
        payload_model=_InfoGridPayload,
        required_fields=("items",),
        optional_fields=("title",),
        example={
            "title": "Meeting details",
            "items": [
                {"label": "Date", "value": "July 18"},
                {"label": "Theme", "value": "Learning in public"},
            ],
        },
    ),
    _DirectiveDefinition(
        name="timeline",
        payload_model=_TimelinePayload,
        required_fields=("items",),
        optional_fields=("title",),
        example={
            "title": "How the evening unfolded",
            "items": [
                {
                    "label": "19:30",
                    "title": "The first attempt",
                    "description": "A new speaker takes the floor.",
                }
            ],
        },
    ),
    _DirectiveDefinition(
        name="pull-quote",
        payload_model=_PullQuotePayload,
        required_fields=("text",),
        optional_fields=("attribution",),
        example={"text": "I will add two more sentences.", "attribution": "A first-time speaker"},
    ),
)

_DIRECTIVE_REGISTRY = {definition.name: definition for definition in _DIRECTIVE_DEFINITIONS}


@dataclass(frozen=True)
class ParsedDirective:
    name: str
    line: int
    payload: _DirectiveModel

    @property
    def media_ids(self) -> list[str]:
        if isinstance(self.payload, _GalleryPayload):
            return self.payload.items
        if isinstance(self.payload, _VideoPayload):
            return [self.payload.media]
        if isinstance(self.payload, _PersonPayload) and self.payload.media:
            return [self.payload.media]
        return []


@dataclass(frozen=True)
class ParsedArticle:
    directives: list[ParsedDirective]
    key_point_count: int

    def directive_summaries(self) -> list[DirectiveSummary]:
        return [DirectiveSummary(name=item.name, line=item.line, media_ids=item.media_ids) for item in self.directives]

    def inline_summaries(self) -> list[InlineExtensionSummary]:
        return [InlineExtensionSummary(name="key-point", count=self.key_point_count)]


class ArticleDocumentValidationError(Exception):
    def __init__(self, errors: list[ValidationIssue]):
        self.errors = errors
        super().__init__("WePost ArticleDocument validation failed")


def capabilities() -> WePostCapabilities:
    return WePostCapabilities(
        document_schema=ArticleDocument.model_json_schema(by_alias=True),
        article_types=[item.value for item in ArticleType],
        directives=list(_DIRECTIVE_REGISTRY),
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
        directive_schemas=[definition.capability() for definition in _DIRECTIVE_DEFINITIONS],
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
    _validate_directive_media(parsed.directives, document.media, errors)

    if errors:
        raise ArticleDocumentValidationError(errors)
    return parsed


def _validate_document_shape(document: ArticleDocument, errors: list[ValidationIssue]) -> None:
    custom_label = (document.custom_article_type or "").strip()
    if document.article_type == ArticleType.CUSTOM and not custom_label:
        errors.append(
            ValidationIssue(
                code="custom_article_type_required",
                path=["customArticleType"],
                message="customArticleType is required when articleType is custom.",
            )
        )
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
    directives: list[ParsedDirective] = []
    index = 0

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
            break

        for line_index in range(index, closing_index + 1):
            markdown_lines[line_index] = ""

        if name not in _DIRECTIVE_REGISTRY:
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
            continue

        payload_text = "\n".join(lines[index + 1 : closing_index])
        payload = _load_directive_payload(name, payload_text, index + 1, errors)
        if payload is not None:
            directives.append(ParsedDirective(name=name, line=index + 1, payload=payload))
        index = closing_index + 1

    markdown = "\n".join(markdown_lines)
    tokens = _MARKDOWN.parse(markdown)
    for token in tokens:
        if token.type in {"html_block", "html_inline"}:
            errors.append(
                ValidationIssue(
                    code="unsafe_html",
                    path=["bodyMarkdown"],
                    line=(token.map[0] + 1) if token.map else None,
                    message="Raw HTML is not allowed in WePost Markdown.",
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
                            message="Raw HTML is not allowed in WePost Markdown.",
                        )
                    )

    key_point_count = sum(
        len(_KEY_POINT.findall(child.content))
        for token in tokens
        if token.children
        for child in token.children
        if child.type == "text"
    )
    return ParsedArticle(directives=directives, key_point_count=key_point_count)


def _load_directive_payload(
    name: str,
    payload_text: str,
    opening_line: int,
    errors: list[ValidationIssue],
) -> _DirectiveModel | None:
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

    model = _DIRECTIVE_REGISTRY[name].payload_model
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
    errors: list[ValidationIssue],
) -> None:
    by_id = {asset.id: asset for asset in media}
    for directive in directives:
        expected_kind: MediaKind | None = None
        references: list[tuple[str, list[str | int]]] = []
        if isinstance(directive.payload, _GalleryPayload):
            expected_kind = MediaKind.IMAGE
            references = [
                (media_id, ["bodyMarkdown", f"directive:{directive.name}", "items", index])
                for index, media_id in enumerate(directive.payload.items)
            ]
        elif isinstance(directive.payload, _VideoPayload):
            expected_kind = MediaKind.VIDEO
            references = [(directive.payload.media, ["bodyMarkdown", f"directive:{directive.name}", "media"])]
        elif isinstance(directive.payload, _PersonPayload) and directive.payload.media:
            expected_kind = MediaKind.IMAGE
            references = [(directive.payload.media, ["bodyMarkdown", f"directive:{directive.name}", "media"])]

        for media_id, path in references:
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
            elif expected_kind is not None and asset.kind != expected_kind:
                errors.append(
                    ValidationIssue(
                        code="media_kind_mismatch",
                        path=path,
                        line=directive.line,
                        directive=directive.name,
                        message=(
                            f"Directive {directive.name!r} requires {expected_kind.value} media; "
                            f"{media_id!r} is {asset.kind.value}."
                        ),
                    )
                )
