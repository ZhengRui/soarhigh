"""Canonical registry for WxPost block directives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..models.wxpost import DirectiveCapability, MediaKind


class _DirectiveModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _ImagePayload(_DirectiveModel):
    media: str = Field(min_length=1)
    caption: str | None = Field(default=None, min_length=1)


class _GalleryPayload(_DirectiveModel):
    items: list[str] = Field(min_length=2)
    caption: str | None = Field(default=None, min_length=1)


class _SectionPayload(_DirectiveModel):
    kicker: str = Field(min_length=1, max_length=64)


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
class DirectiveMediaField:
    field: str
    expected_kind: MediaKind
    multiple: bool = False


@dataclass(frozen=True)
class DirectiveMediaReference:
    media_id: str
    expected_kind: MediaKind
    payload_path: tuple[str | int, ...]


@dataclass(frozen=True)
class DirectiveDefinition:
    name: str
    payload_model: type[_DirectiveModel]
    example: dict[str, Any]
    media_fields: tuple[DirectiveMediaField, ...] = ()

    def capability(self) -> DirectiveCapability:
        required_fields = [name for name, field in self.payload_model.model_fields.items() if field.is_required()]
        optional_fields = [name for name, field in self.payload_model.model_fields.items() if not field.is_required()]
        return DirectiveCapability(
            name=self.name,
            required_fields=required_fields,
            optional_fields=optional_fields,
            example=self.example,
            payload_schema=self.payload_model.model_json_schema(),
        )

    def media_references(self, payload: _DirectiveModel) -> list[DirectiveMediaReference]:
        references: list[DirectiveMediaReference] = []
        for media_field in self.media_fields:
            value = getattr(payload, media_field.field)
            if value is None:
                continue
            if media_field.multiple:
                references.extend(
                    DirectiveMediaReference(
                        media_id=media_id,
                        expected_kind=media_field.expected_kind,
                        payload_path=(media_field.field, index),
                    )
                    for index, media_id in enumerate(value)
                )
            else:
                references.append(
                    DirectiveMediaReference(
                        media_id=value,
                        expected_kind=media_field.expected_kind,
                        payload_path=(media_field.field,),
                    )
                )
        return references


DIRECTIVE_DEFINITIONS = (
    DirectiveDefinition(
        name="section",
        payload_model=_SectionPayload,
        example={"kicker": "Opening"},
    ),
    DirectiveDefinition(
        name="image",
        payload_model=_ImagePayload,
        example={"media": "M01", "caption": "Members listen during the prepared speeches"},
        media_fields=(DirectiveMediaField("media", MediaKind.IMAGE),),
    ),
    DirectiveDefinition(
        name="gallery",
        payload_model=_GalleryPayload,
        example={"items": ["M01", "M02"], "caption": "Two moments from the evening"},
        media_fields=(DirectiveMediaField("items", MediaKind.IMAGE, multiple=True),),
    ),
    DirectiveDefinition(
        name="video",
        payload_model=_VideoPayload,
        example={"media": "V01", "caption": "A member tries the exercise again"},
        media_fields=(DirectiveMediaField("media", MediaKind.VIDEO),),
    ),
    DirectiveDefinition(
        name="takeaway",
        payload_model=_TakeawayPayload,
        example={"title": "Try this next", "text": "Make the next action small enough to begin today."},
    ),
    DirectiveDefinition(
        name="person",
        payload_model=_PersonPayload,
        example={
            "name": "Maya Chen",
            "role": "First-time speaker",
            "media": "M03",
            "summary": "She returned to the stage after feedback.",
        },
        media_fields=(DirectiveMediaField("media", MediaKind.IMAGE),),
    ),
    DirectiveDefinition(
        name="info-grid",
        payload_model=_InfoGridPayload,
        example={
            "title": "Meeting details",
            "items": [
                {"label": "Date", "value": "July 18"},
                {"label": "Theme", "value": "Learning in public"},
            ],
        },
    ),
    DirectiveDefinition(
        name="timeline",
        payload_model=_TimelinePayload,
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
    DirectiveDefinition(
        name="pull-quote",
        payload_model=_PullQuotePayload,
        example={"text": "I will add two more sentences.", "attribution": "A first-time speaker"},
    ),
)

DIRECTIVE_REGISTRY = {definition.name: definition for definition in DIRECTIVE_DEFINITIONS}

# The parser keeps payloads abstract; concrete models remain registry-owned.
DirectiveModel = _DirectiveModel
