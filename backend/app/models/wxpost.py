"""Versioned wire contracts for Hermes-authored WxPost articles."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, StringConstraints, field_validator

TrimmedText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class WireModel(BaseModel):
    """Strict camelCase JSON model used by the WxPost authoring protocol."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        populate_by_name=True,
    )


class ArticleType(str, Enum):
    MEETING_RECAP = "meeting-recap"
    MEMBER_STORY = "member-story"
    EVENT_PREVIEW = "event-preview"
    MEETING_REVIEW = "meeting-review"
    ACTION_GUIDE = "action-guide"
    CUSTOM = "custom"


class Layout(str, Enum):
    BRAND_DEFAULT = "brand-default"
    FIELD_NOTES = "field-notes"
    EDITORIAL_FEATURE = "editorial-feature"


class Palette(str, Enum):
    BRAND_BLUE = "brand-blue"
    PAPER_NEUTRAL = "paper-neutral"
    WARM_TERRACOTTA = "warm-terracotta"


class Appearance(str, Enum):
    LIGHT = "light"
    DARK = "dark"


class Typeface(str, Enum):
    MODERN_SANS = "modern-sans"
    EDITORIAL_SERIF = "editorial-serif"
    HUMANIST_MIX = "humanist-mix"


class MediaKind(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class DescriptionSource(str, Enum):
    USER = "user"
    AI = "ai"


class DescriptionStatus(str, Enum):
    CONFIRMED = "confirmed"
    NEEDS_CONFIRMATION = "needs_confirmation"


class Presentation(WireModel):
    layout: Layout
    palette: Palette
    appearance: Appearance
    typeface: Typeface


class MediaAsset(WireModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    kind: MediaKind
    source_url: AnyHttpUrl
    poster_url: AnyHttpUrl | None = None
    description: TrimmedText
    credit: TrimmedText | None = None
    people: list[TrimmedText] = Field(default_factory=list)
    include: bool
    order: int = Field(ge=0)
    description_source: DescriptionSource
    description_status: DescriptionStatus


class ArticleMetadataFields(WireModel):
    schema_version: Literal[1]
    title: TrimmedText
    slug: TrimmedText | None = None
    excerpt: TrimmedText | None = None
    byline: TrimmedText | None = None
    article_type: ArticleType
    custom_article_type: TrimmedText | None = None
    source_meeting_id: TrimmedText | None = None
    media: list[MediaAsset]
    cover_media_id: TrimmedText | None = None


class ArticleMetadata(ArticleMetadataFields):
    presentation: Presentation


class ArticleDocument(ArticleMetadata):
    body_markdown: str

    @field_validator("body_markdown")
    @classmethod
    def _require_non_empty_markdown(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("bodyMarkdown must contain visible Markdown.")
        return value


class ArticleDocumentUpdate(ArticleMetadataFields):
    """A complete content revision that may retain the stored presentation."""

    presentation: Presentation | None = None
    body_markdown: str

    @field_validator("body_markdown")
    @classmethod
    def _require_non_empty_markdown(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("bodyMarkdown must contain visible Markdown.")
        return value


class MarkdownBodyNode(WireModel):
    kind: Literal["markdown"] = "markdown"
    source: str
    line: int = Field(ge=1)


class DirectiveBodyNode(WireModel):
    kind: Literal["directive"] = "directive"
    name: str
    payload: dict[str, Any]
    line: int = Field(ge=1)


RenderBodyNode = MarkdownBodyNode | DirectiveBodyNode


class WxPostRenderDocument(ArticleMetadata):
    """Backend-owned, versioned input shared by browser and WeChat renderers."""

    render_version: Literal[1] = 1
    body: list[RenderBodyNode]


class DirectiveSummary(WireModel):
    name: str
    line: int = Field(ge=1)
    media_ids: list[str] = Field(default_factory=list)


class InlineExtensionSummary(WireModel):
    name: str
    count: int = Field(ge=0)


class ValidationIssue(WireModel):
    code: str
    path: list[str | int]
    message: str
    line: int | None = Field(default=None, ge=1)
    directive: str | None = None


class WxPostValidationSuccess(WireModel):
    valid: Literal[True] = True
    schema_version: Literal[1] = 1
    document: ArticleDocument
    article_type: ArticleType
    custom_article_type: str | None = None
    directives: list[DirectiveSummary]
    inline_extensions: list[InlineExtensionSummary]
    render_document: WxPostRenderDocument


class WxPostValidationFailure(WireModel):
    valid: Literal[False] = False
    errors: list[ValidationIssue]


class PresentationCapabilities(WireModel):
    layouts: list[str]
    palettes: list[str]
    appearances: list[str]
    typefaces: list[str]


class DirectiveCapability(WireModel):
    name: str
    required_fields: list[str]
    optional_fields: list[str]
    example: dict[str, Any]
    payload_schema: dict[str, Any]


class WxPostCapabilities(WireModel):
    schema_version: Literal[1] = 1
    render_version: Literal[1] = 1
    document_schema: dict[str, Any]
    render_document_schema: dict[str, Any]
    article_types: list[str]
    directives: list[str]
    inline_extensions: list[str]
    presentation: PresentationCapabilities
    default_presentation: Presentation
    directive_grammar_version: Literal[1] = 1
    directive_syntax: str
    directive_schemas: list[DirectiveCapability]
    inline_syntax: dict[str, str]


class WxPostPersistenceModel(BaseModel):
    """Strict snake_case envelope around camelCase article documents."""

    model_config = ConfigDict(extra="forbid")


class WxPostCreateRequest(WxPostPersistenceModel):
    document: ArticleDocument


class WxPostUpdateRequest(WxPostPersistenceModel):
    expected_revision: int = Field(ge=1)
    document: ArticleDocumentUpdate


class WxPostMutationResult(WxPostPersistenceModel):
    id: UUID
    slug: str
    article_revision: int
    preview_url: str


class WxPostPublicDetail(WxPostPersistenceModel):
    id: UUID
    slug: str
    is_public: Literal[True]
    article_revision: int
    context_label: str
    created_at: datetime
    updated_at: datetime
    render_document: WxPostRenderDocument


class WxPostPublicationSyncRequest(WireModel):
    expected_manifest_version: int = Field(ge=1, strict=True)
    expected_draft_version: int = Field(ge=1, strict=True)
    expected_public_revision: int | None = Field(default=None, ge=1, strict=True)


class WxPostPublicationDeleteRequest(WireModel):
    expected_public_revision: int = Field(ge=1, strict=True)


class WxPostPublicationDeleteResult(WireModel):
    deleted: Literal[True] = True
    workspace_id: TrimmedText | None = None


class WxPostPublicationStatus(WireModel):
    state: Literal["unavailable", "not-synced", "up-to-date", "update-available"]
    workspace_id: TrimmedText
    slug: str | None = None
    public_revision: int | None = Field(default=None, ge=1)
    source_draft_version: int | None = Field(default=None, ge=1)
    current_draft_version: int | None = Field(default=None, ge=1)
    published_at: datetime | None = None
    public_url: str | None = None
