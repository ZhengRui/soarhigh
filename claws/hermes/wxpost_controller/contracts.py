"""Wire and storage contracts for one canonical WxPost workspace."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

MANIFEST_SCHEMA_VERSION: Literal[4] = 4
DRAFT_PROPOSAL_SCHEMA_VERSION: Literal[2] = 2

TrimmedText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=512),
]
SourceId = Annotated[
    str,
    StringConstraints(pattern=r"^M(?:0[1-9]|[1-9][0-9]+)$"),
]


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ContractModel(BaseModel):
    """Strict camelCase model shared by disk, HTTP, and MCP boundaries."""

    model_config = ConfigDict(alias_generator=_to_camel, extra="forbid")

    def to_wire(self, *, exclude_unset: bool = False) -> dict[str, Any]:
        return self.model_dump(
            by_alias=True,
            exclude_unset=exclude_unset,
            mode="json",
        )


class ArticleType(str, Enum):
    MEETING_RECAP = "meeting-recap"
    MEMBER_STORY = "member-story"
    EVENT_PREVIEW = "event-preview"
    MEETING_REVIEW = "meeting-review"
    ACTION_GUIDE = "action-guide"
    CUSTOM = "custom"


class WritingApproach(str, Enum):
    CHRONOLOGICAL = "chronological"
    THEME_DRIVEN = "theme-driven"
    IMAGE_DRIVEN = "image-driven"
    HIGHLIGHTS_FIRST = "highlights-first"


class VoiceTonePreset(str, Enum):
    ENCOURAGING = "encouraging"
    LIGHTLY_HUMOROUS = "lightly-humorous"
    HEARTFELT = "heartfelt"
    DOCUMENTARY = "documentary"
    REFLECTIVE = "reflective"
    CELEBRATORY = "celebratory"


class SourceKind(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TRANSCRIPT = "transcript"
    DOCUMENT = "document"


class DescriptionSource(str, Enum):
    USER = "user"
    AI = "ai"


class DescriptionStatus(str, Enum):
    CONFIRMED = "confirmed"
    NEEDS_CONFIRMATION = "needs_confirmation"
    MISSING = "missing"


def _validate_description_state(
    description: str,
    source: DescriptionSource | None,
    status: DescriptionStatus,
) -> None:
    if status == DescriptionStatus.MISSING:
        if description != "" or source is not None:
            raise ValueError("missing descriptions must be empty and have no source")
    elif not description.strip() or source is None:
        raise ValueError("non-missing descriptions require text and descriptionSource")
    elif (
        status == DescriptionStatus.NEEDS_CONFIRMATION
        and source != DescriptionSource.AI
    ):
        raise ValueError("needs_confirmation is reserved for AI-proposed descriptions")


class MeetingLibraryOrigin(ContractModel):
    type: Literal["meeting-library"]
    file_key: TrimmedText


class DirectUploadOrigin(ContractModel):
    type: Literal["web-upload", "feishu-upload"]


SourceOrigin = Annotated[
    MeetingLibraryOrigin | DirectUploadOrigin,
    Field(discriminator="type"),
]


VoiceToneName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
]
VoiceToneInstruction = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
]


class CustomVoiceToneProfile(ContractModel):
    name: VoiceToneName
    instruction: VoiceToneInstruction
    selected: bool = Field(strict=True)


class VoiceToneSettings(ContractModel):
    presets: list[VoiceTonePreset]
    custom_profiles: list[CustomVoiceToneProfile]

    @model_validator(mode="after")
    def _validate_profiles(self) -> VoiceToneSettings:
        if len(self.presets) != len(set(self.presets)):
            raise ValueError("voice tone presets must be unique")

        profile_names = [profile.name.casefold() for profile in self.custom_profiles]
        if len(profile_names) != len(set(profile_names)):
            raise ValueError("custom voice tone names must be unique")

        selected_count = len(self.presets) + sum(
            profile.selected for profile in self.custom_profiles
        )
        if selected_count > 3:
            raise ValueError("at most three voice tones may be selected")
        return self


class EditorialSettings(ContractModel):
    article_type: ArticleType
    custom_article_type: TrimmedText | None = None
    writing_approach: WritingApproach = WritingApproach.CHRONOLOGICAL
    transcript: str = ""
    extra_notes: str = ""
    writing_guidance: str = ""
    voice_tone: VoiceToneSettings

    @model_validator(mode="after")
    def _validate_custom_article_type(self) -> EditorialSettings:
        if (
            self.article_type != ArticleType.CUSTOM
            and self.custom_article_type is not None
        ):
            raise ValueError(
                "customArticleType must be null unless articleType is custom"
            )
        return self


class SourceRecord(ContractModel):
    id: SourceId
    kind: SourceKind
    origin: SourceOrigin
    filename: TrimmedText
    mime_type: TrimmedText
    size_bytes: int = Field(gt=0, strict=True)
    workspace_ready: bool = Field(strict=True)
    included: bool = Field(strict=True)
    description: str = ""
    description_source: DescriptionSource | None = None
    description_status: DescriptionStatus

    @field_validator("filename")
    @classmethod
    def _validate_filename(cls, value: str) -> str:
        if value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError("filename must be a basename")
        return value

    @model_validator(mode="after")
    def _validate_source_state(self) -> SourceRecord:
        if self.included and not self.workspace_ready:
            raise ValueError("included sources must be workspace-ready")
        if (
            not isinstance(self.origin, MeetingLibraryOrigin)
            and not self.workspace_ready
        ):
            raise ValueError("direct uploads must be workspace-ready")

        _validate_description_state(
            self.description,
            self.description_source,
            self.description_status,
        )
        return self


class DraftState(ContractModel):
    version: int = Field(ge=1, strict=True)
    source_manifest_version: int = Field(ge=1, strict=True)
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    operation_id: TrimmedText | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )


class WorkspaceCreator(ContractModel):
    id: TrimmedText
    name: TrimmedText


class SourceManifest(ContractModel):
    schema_version: Literal[4]
    workspace_id: TrimmedText
    manifest_version: int = Field(ge=1, strict=True)
    next_material_number: int = Field(ge=1, strict=True)
    created_by: WorkspaceCreator
    created_at: datetime
    updated_at: datetime
    meeting_id: TrimmedText | None = None
    draft: DraftState | None = None
    editorial: EditorialSettings
    sources: list[SourceRecord]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _validate_schema_version(cls, value: Any) -> Any:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value != MANIFEST_SCHEMA_VERSION
        ):
            raise ValueError("schemaVersion must be the integer 4")
        return value

    @model_validator(mode="after")
    def _validate_manifest(self) -> SourceManifest:
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("workspace timestamps must include a timezone")
        if self.updated_at < self.created_at:
            raise ValueError("updatedAt cannot be earlier than createdAt")

        ids = [source.id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("source ids must be unique")

        used_numbers = [int(source.id[1:]) for source in self.sources]
        if used_numbers and self.next_material_number <= max(used_numbers):
            raise ValueError(
                "nextMaterialNumber must be greater than every assigned source id"
            )

        if (
            self.draft is not None
            and self.draft.source_manifest_version > self.manifest_version
        ):
            raise ValueError(
                "draft sourceManifestVersion cannot exceed manifestVersion"
            )

        for source in self.sources:
            if isinstance(source.origin, MeetingLibraryOrigin):
                if self.meeting_id is None:
                    raise ValueError("meeting-library sources require meetingId")
                if source.kind not in {SourceKind.IMAGE, SourceKind.VIDEO}:
                    raise ValueError(
                        "meeting-library sources must be image or video media"
                    )
        return self


class DraftEnvelope(ContractModel):
    """Draft metadata returned by APIs; the disk file is the raw document."""

    draft_version: int = Field(ge=1, strict=True)
    document: dict[str, Any]


class DraftMediaProposal(ContractModel):
    """Editorial fields Hermes owns for one workspace material."""

    id: SourceId
    description: TrimmedText
    credit: TrimmedText | None = None
    people: list[TrimmedText] = Field(default_factory=list)


MarkdownText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


def _reject_directive_fences(value: str) -> str:
    if any(line.strip().startswith(":::") for line in value.splitlines()):
        raise ValueError(
            "markdown blocks cannot contain directive fences; use a typed block"
        )
    return value


_ATX_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}(?:[ \t]+|$)")
_SETEXT_HEADING = re.compile(r"^[ \t]{0,3}(?:=+|-+)[ \t]*$")


def _reject_section_heading(value: str) -> str:
    _reject_directive_fences(value)
    lines = value.splitlines()
    for index, line in enumerate(lines):
        if _ATX_HEADING.match(line):
            raise ValueError(
                "section bodies cannot contain Markdown headings; use a section block"
            )
        if index > 0 and lines[index - 1].strip() and _SETEXT_HEADING.match(line):
            raise ValueError(
                "section bodies cannot contain Markdown headings; use a section block"
            )
    return value


class DraftMarkdownBlock(ContractModel):
    """Free-form prose, lists, or other ordinary Markdown."""

    type: Literal["markdown"]
    markdown: MarkdownText = Field(
        description=(
            "Ordinary prose, block quotes, or lists only. Do not include "
            "directive fences or semantic blocks."
        )
    )

    _validate_markdown = field_validator("markdown")(_reject_directive_fences)


class DraftSectionBlock(ContractModel):
    """One marked narrative section with an editable heading and body."""

    type: Literal["section"]
    kicker: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
    ]
    heading: TrimmedText
    body: MarkdownText = Field(
        description=(
            "The section prose and lists only. Do not include a heading, "
            "directive fence, or semantic block. Put media and other semantic "
            "content in separate sibling blocks after this section."
        )
    )

    _validate_body = field_validator("body")(_reject_section_heading)


class DraftImageBlock(ContractModel):
    type: Literal["image"]
    media: SourceId
    caption: TrimmedText | None = None


class DraftGalleryBlock(ContractModel):
    type: Literal["gallery"]
    items: list[SourceId] = Field(min_length=2)
    caption: TrimmedText | None = None

    @field_validator("items")
    @classmethod
    def _require_unique_items(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("gallery items must be unique")
        return value


class DraftVideoBlock(ContractModel):
    type: Literal["video"]
    media: SourceId
    caption: TrimmedText | None = None


class DraftPersonBlock(ContractModel):
    type: Literal["person"]
    name: TrimmedText
    role: TrimmedText | None = None
    media: SourceId | None = None
    summary: TrimmedText | None = None
    quote: TrimmedText | None = None


class DraftTakeawayBlock(ContractModel):
    type: Literal["takeaway"]
    text: MarkdownText
    title: TrimmedText | None = None


class DraftInfoGridItem(ContractModel):
    label: TrimmedText
    value: TrimmedText


class DraftInfoGridBlock(ContractModel):
    type: Literal["info-grid"]
    title: TrimmedText | None = None
    items: list[DraftInfoGridItem] = Field(min_length=1)


class DraftTimelineItem(ContractModel):
    label: TrimmedText
    title: TrimmedText
    description: TrimmedText | None = None


class DraftTimelineBlock(ContractModel):
    type: Literal["timeline"]
    title: TrimmedText | None = None
    items: list[DraftTimelineItem] = Field(min_length=1)


class DraftPullQuoteBlock(ContractModel):
    type: Literal["pull-quote"]
    text: TrimmedText
    attribution: TrimmedText | None = None


DraftBlock = Annotated[
    DraftMarkdownBlock
    | DraftSectionBlock
    | DraftImageBlock
    | DraftGalleryBlock
    | DraftVideoBlock
    | DraftPersonBlock
    | DraftTakeawayBlock
    | DraftInfoGridBlock
    | DraftTimelineBlock
    | DraftPullQuoteBlock,
    Field(discriminator="type"),
]


class DraftProposal(ContractModel):
    """Strict structured output authored by Hermes before canonical assembly."""

    schema_version: Literal[2]
    title: TrimmedText
    excerpt: TrimmedText | None = None
    byline: TrimmedText | None = None
    blocks: list[DraftBlock] = Field(
        min_length=1,
        description=(
            "Ordered article content. Use markdown blocks for unconstrained prose "
            "and typed semantic blocks for sections, media, quotes, timelines, "
            "information grids, people, and takeaways."
        ),
    )
    media: list[DraftMediaProposal] = Field(
        description=(
            "Editorial descriptions for every included image or video exactly "
            "once. Canonical media order is derived from first block reference."
        )
    )
    cover_media_id: SourceId | None = None

    @model_validator(mode="after")
    def _validate_media(self) -> DraftProposal:
        media_ids = [item.id for item in self.media]
        if len(media_ids) != len(set(media_ids)):
            raise ValueError("draft proposal media ids must be unique")
        if self.cover_media_id is not None and self.cover_media_id not in media_ids:
            raise ValueError("coverMediaId must reference proposal media")

        referenced_ids: list[str] = []
        for block in self.blocks:
            if isinstance(block, (DraftImageBlock, DraftVideoBlock)):
                referenced_ids.append(block.media)
            elif isinstance(block, DraftGalleryBlock):
                referenced_ids.extend(block.items)
            elif isinstance(block, DraftPersonBlock) and block.media is not None:
                referenced_ids.append(block.media)

        unexpected = sorted(set(referenced_ids) - set(media_ids))
        if unexpected:
            raise ValueError(
                "draft blocks reference media missing from proposal: "
                + ", ".join(unexpected)
            )
        permitted_ids = set(referenced_ids)
        if self.cover_media_id is not None:
            permitted_ids.add(self.cover_media_id)
        missing = sorted(set(media_ids) - permitted_ids)
        if missing:
            raise ValueError(
                "draft proposal media is not referenced by a block or cover: "
                + ", ".join(missing)
            )
        return self


class DraftCoverChange(ContractModel):
    action: Literal["preserve", "set", "clear"]
    source_id: SourceId | None = None

    @model_validator(mode="after")
    def _validate_action(self) -> DraftCoverChange:
        if self.action == "set" and self.source_id is None:
            raise ValueError("setting the Draft cover requires sourceId")
        if self.action != "set" and self.source_id is not None:
            raise ValueError("sourceId is only valid when setting the Draft cover")
        return self


class DraftMediaChanges(ContractModel):
    """Explicit media membership changes for one focused Draft revision."""

    added_media_ids: list[SourceId] = Field(default_factory=list)
    removed_media_ids: list[SourceId] = Field(default_factory=list)
    cover: DraftCoverChange

    @model_validator(mode="after")
    def _validate_changes(self) -> DraftMediaChanges:
        if len(self.added_media_ids) != len(set(self.added_media_ids)):
            raise ValueError("addedMediaIds must be unique")
        if len(self.removed_media_ids) != len(set(self.removed_media_ids)):
            raise ValueError("removedMediaIds must be unique")
        overlap = sorted(set(self.added_media_ids) & set(self.removed_media_ids))
        if overlap:
            raise ValueError(
                "media cannot be added and removed in one revision: "
                + ", ".join(overlap)
            )
        return self


class DraftMarkdownNodeInput(ContractModel):
    kind: Literal["markdown"]
    source: TrimmedText


class DraftDirectiveNodeInput(ContractModel):
    kind: Literal["directive"]
    name: TrimmedText
    payload: dict[str, Any]


DraftBodyNodeInput = Annotated[
    DraftMarkdownNodeInput | DraftDirectiveNodeInput,
    Field(discriminator="kind"),
]


class ReplaceMetadataEdit(ContractModel):
    type: Literal["replaceMetadata"]
    field: Literal["title", "excerpt", "byline"]
    value: str | None


class ReplaceBodyNodeEdit(ContractModel):
    type: Literal["replaceBodyNode"]
    node_index: int = Field(ge=0, strict=True)
    node: DraftBodyNodeInput


class InsertBodyNodeEdit(ContractModel):
    type: Literal["insertBodyNode"]
    body_index: int = Field(ge=0, strict=True)
    node: DraftBodyNodeInput


class DeleteBodyNodeEdit(ContractModel):
    type: Literal["deleteBodyNode"]
    node_index: int = Field(ge=0, strict=True)


class ReplaceDirectiveFieldEdit(ContractModel):
    type: Literal["replaceDirectiveField"]
    node_index: int = Field(ge=0, strict=True)
    path: list[str | int] = Field(min_length=1)
    value: str | None


class DeleteDirectiveItemEdit(ContractModel):
    type: Literal["deleteDirectiveItem"]
    node_index: int = Field(ge=0, strict=True)
    item_index: int = Field(ge=0, strict=True)


class SetCoverEdit(ContractModel):
    type: Literal["setCover"]
    source_id: SourceId


class ClearCoverEdit(ContractModel):
    type: Literal["clearCover"]


class InsertImageEdit(ContractModel):
    type: Literal["insertImage"]
    source_id: SourceId
    body_index: int = Field(ge=0, strict=True)
    caption: TrimmedText | None = None


class DeleteMediaOccurrenceEdit(ContractModel):
    type: Literal["deleteMediaOccurrence"]
    node_index: int = Field(ge=0, strict=True)
    source_id: SourceId


class RemoveMediaFromBodyEdit(ContractModel):
    type: Literal["removeMediaFromBody"]
    source_id: SourceId


class ReplaceMediaDescriptionEdit(ContractModel):
    type: Literal["replaceMediaDescription"]
    source_id: SourceId
    value: TrimmedText


DraftEditOperation = Annotated[
    ReplaceMetadataEdit
    | ReplaceBodyNodeEdit
    | InsertBodyNodeEdit
    | DeleteBodyNodeEdit
    | ReplaceDirectiveFieldEdit
    | DeleteDirectiveItemEdit
    | SetCoverEdit
    | ClearCoverEdit
    | InsertImageEdit
    | DeleteMediaOccurrenceEdit
    | RemoveMediaFromBodyEdit
    | ReplaceMediaDescriptionEdit,
    Field(discriminator="type"),
]


class EditDraftRequest(ContractModel):
    expected_manifest_version: int = Field(ge=1, strict=True)
    expected_draft_version: int = Field(ge=1, strict=True)
    operation_id: TrimmedText
    edits: list[DraftEditOperation] = Field(min_length=1)


class SourceUpdate(ContractModel):
    source_id: SourceId
    included: bool | None = Field(default=None, strict=True)
    move_to_index: int | None = Field(default=None, ge=0, strict=True)
    description: str | None = None
    description_source: DescriptionSource | None = None
    description_status: DescriptionStatus | None = None

    @model_validator(mode="after")
    def _validate_patch(self) -> SourceUpdate:
        changed_fields = self.model_fields_set - {"source_id"}
        if not changed_fields:
            raise ValueError("source update must change at least one field")
        if "included" in changed_fields and self.included is None:
            raise ValueError("included must be boolean")
        if "move_to_index" in changed_fields and self.move_to_index is None:
            raise ValueError("moveToIndex must be a non-negative integer")

        description_fields = {
            "description",
            "description_source",
            "description_status",
        }
        touched_description_fields = changed_fields.intersection(description_fields)
        if (
            touched_description_fields
            and touched_description_fields != description_fields
        ):
            raise ValueError(
                "description, descriptionSource, and descriptionStatus "
                "must be updated together"
            )
        return self


class UpdateSourcesRequest(ContractModel):
    expected_manifest_version: int = Field(ge=1, strict=True)
    updates: list[SourceUpdate] = Field(min_length=1)

    @model_validator(mode="after")
    def _reject_duplicate_sources(self) -> UpdateSourcesRequest:
        ids = [update.source_id for update in self.updates]
        if len(ids) != len(set(ids)):
            raise ValueError("each source may be updated only once per request")
        return self


class BootstrapWorkspaceRequest(ContractModel):
    meeting_id: TrimmedText | None = None
    editorial: EditorialSettings
    created_by: WorkspaceCreator


class UpdateWorkspaceRequest(ContractModel):
    expected_manifest_version: int = Field(ge=1, strict=True)
    meeting_id: TrimmedText | None
    editorial: EditorialSettings
    source_updates: list[SourceUpdate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _reject_duplicate_sources(self) -> UpdateWorkspaceRequest:
        ids = [update.source_id for update in self.source_updates]
        if len(ids) != len(set(ids)):
            raise ValueError("each source may be updated only once per request")
        return self


class SourceActionRequest(ContractModel):
    expected_manifest_version: int = Field(ge=1, strict=True)
    source_id: SourceId


class SourceLookupRequest(ContractModel):
    source_id: SourceId


class SetSourceInclusionRequest(SourceActionRequest):
    included: bool = Field(strict=True)


class UploadSourceRequest(ContractModel):
    expected_manifest_version: int = Field(ge=1, strict=True)
    origin: Literal["web-upload", "feishu-upload"]
    filename: TrimmedText
    mime_type: TrimmedText
    description: str = ""
    description_source: DescriptionSource | None = None
    description_status: DescriptionStatus = DescriptionStatus.MISSING

    @field_validator("filename")
    @classmethod
    def _validate_filename(cls, value: str) -> str:
        if value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError("filename must be a basename")
        return value

    @model_validator(mode="after")
    def _validate_description(self) -> UploadSourceRequest:
        _validate_description_state(
            self.description,
            self.description_source,
            self.description_status,
        )
        return self


class MeetingMediaReference(ContractModel):
    filename: TrimmedText
    url: TrimmedText
    file_key: TrimmedText
    uploaded_at: TrimmedText
    mime_type: TrimmedText
    size_bytes: int = Field(gt=0, strict=True)

    @field_validator("filename")
    @classmethod
    def _validate_filename(cls, value: str) -> str:
        if value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError("filename must be a basename")
        return value


class SaveDraftRequest(ContractModel):
    expected_manifest_version: int = Field(ge=1, strict=True)
    expected_draft_version: int = Field(ge=0, strict=True)
    document: dict[str, Any]
    operation_id: TrimmedText | None = None
