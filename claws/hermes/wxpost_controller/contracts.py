"""Wire and storage contracts for one canonical WXPost workspace."""

from __future__ import annotations

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

MANIFEST_SCHEMA_VERSION: Literal[3] = 3

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


class EditorialSettings(ContractModel):
    article_type: ArticleType
    custom_article_type: TrimmedText | None = None
    writing_approach: WritingApproach = WritingApproach.CHRONOLOGICAL
    transcript: str = ""
    extra_notes: str = ""
    writing_guidance: str = ""

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


class WorkspaceCreator(ContractModel):
    id: TrimmedText
    name: TrimmedText


class SourceManifest(ContractModel):
    schema_version: Literal[3]
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
            raise ValueError("schemaVersion must be the integer 3")
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


class DeleteSourceRequest(SourceActionRequest):
    confirm_referenced: bool = Field(default=False, strict=True)


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
