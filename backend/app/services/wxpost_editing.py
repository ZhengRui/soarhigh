"""Deterministic, version-agnostic edits for a canonical WxPost Draft document."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, cast

from ..models.wxpost import (
    ArticleDocument,
    ClearCoverEdit,
    DeleteBodyNodeEdit,
    DeleteDirectiveItemEdit,
    DeleteMediaOccurrenceEdit,
    DescriptionSource,
    DescriptionStatus,
    DirectiveBodyNode,
    DraftBodyNodeInput,
    DraftDirectiveNodeInput,
    DraftEditOperation,
    DraftMarkdownNodeInput,
    InsertBodyNodeEdit,
    InsertImageEdit,
    MediaAsset,
    RemoveMediaFromBodyEdit,
    ReplaceBodyNodeEdit,
    ReplaceDirectiveFieldEdit,
    ReplaceMediaDescriptionEdit,
    ReplaceMetadataEdit,
    SetCoverEdit,
    ValidationIssue,
    WxPostDraftEditRequest,
)
from .wxpost_directives import DIRECTIVE_REGISTRY
from .wxpost_document import (
    ArticleDocumentValidationError,
    ParsedArticle,
    parse_body_markdown,
    validate_and_parse,
)


@dataclass(frozen=True)
class _BodyPatch:
    start: int
    end: int
    replacement: list[str]


def _invalid(message: str, *, path: list[str | int] | None = None) -> ArticleDocumentValidationError:
    return ArticleDocumentValidationError(
        [
            ValidationIssue(
                code="invalid_draft_edit",
                path=path or ["edits"],
                message=message,
            )
        ]
    )


def _node_lines(node: DraftBodyNodeInput | DirectiveBodyNode) -> list[str]:
    if isinstance(node, DraftMarkdownNodeInput):
        return node.source.splitlines()
    return [
        f":::{node.name}",
        *json.dumps(node.payload, ensure_ascii=False, indent=2).splitlines(),
        ":::",
    ]


def _node_range(lines: list[str], parsed: ParsedArticle, node_index: int) -> tuple[int, int]:
    if node_index >= len(parsed.body):
        raise _invalid(f"Draft body node {node_index} does not exist.")
    node = parsed.body[node_index]
    start = node.line - 1
    if node.kind == "markdown":
        return start, start + len(node.source.splitlines())
    closing = next(
        (index for index in range(start + 1, len(lines)) if lines[index].strip() == ":::"),
        None,
    )
    if closing is None:
        raise _invalid(f"Draft directive node {node_index} has no closing fence.")
    return start, closing + 1


def _insert_lines(lines: list[str], parsed: ParsedArticle, body_index: int, node_lines: list[str]) -> _BodyPatch:
    if body_index > len(parsed.body):
        raise _invalid(f"Draft body insertion index {body_index} is outside the article.")
    if body_index < len(parsed.body):
        start = parsed.body[body_index].line - 1
        replacement = [*node_lines, ""]
    else:
        start = len(lines)
        replacement = ([""] if lines and lines[-1].strip() else []) + node_lines
    return _BodyPatch(start=start, end=start, replacement=replacement)


def _updated_nested_value(current: Any, path: list[str | int], value: str | None) -> Any:
    if not path:
        return value
    head, *tail = path
    if isinstance(head, int):
        if not isinstance(current, list) or head < 0 or head >= len(current):
            raise _invalid("Directive edit path does not match an array item.")
        if value is None and not tail:
            raise _invalid("Use deleteDirectiveItem to remove a repeated item.")
        updated_list = list(current)
        updated_list[head] = _updated_nested_value(updated_list[head], tail, value)
        return updated_list
    if not isinstance(current, dict) or head not in current:
        raise _invalid(f"Directive edit field {head!r} does not exist.")
    updated_dict = dict(current)
    if not tail:
        if value is None:
            del updated_dict[head]
        else:
            updated_dict[head] = value
        return updated_dict
    updated_dict[head] = _updated_nested_value(updated_dict[head], tail, value)
    return updated_dict


def _directive_node(
    parsed: ParsedArticle,
    node_index: int,
    *,
    label: str = "directive",
) -> DirectiveBodyNode:
    if node_index >= len(parsed.body) or parsed.body[node_index].kind != "directive":
        raise _invalid(f"Draft body node {node_index} is not a {label}.")
    return cast(DirectiveBodyNode, parsed.body[node_index])


def _directive_patch(
    lines: list[str],
    parsed: ParsedArticle,
    node_index: int,
    payload: dict[str, Any] | None,
    *,
    replacement_name: str | None = None,
) -> _BodyPatch:
    node = _directive_node(parsed, node_index)
    start, end = _node_range(lines, parsed, node_index)
    replacement = (
        []
        if payload is None
        else _node_lines(
            DraftDirectiveNodeInput(
                kind="directive",
                name=replacement_name or node.name,
                payload=payload,
            )
        )
    )
    return _BodyPatch(start=start, end=end, replacement=replacement)


def _media_occurrence_patch(
    lines: list[str],
    parsed: ParsedArticle,
    node_index: int,
    source_id: str,
) -> _BodyPatch:
    node = _directive_node(parsed, node_index, label="media directive")
    payload = copy.deepcopy(node.payload)
    if node.name in {"image", "video"} and payload.get("media") == source_id:
        return _directive_patch(lines, parsed, node_index, None)
    if node.name == "person" and payload.get("media") == source_id:
        del payload["media"]
        return _directive_patch(lines, parsed, node_index, payload)
    if node.name == "gallery" and source_id in payload.get("items", []):
        remaining = [item for item in payload["items"] if item != source_id]
        if len(remaining) > 1:
            payload["items"] = remaining
            return _directive_patch(lines, parsed, node_index, payload)
        if len(remaining) == 1:
            image_payload: dict[str, Any] = {"media": remaining[0]}
            if payload.get("caption"):
                image_payload["caption"] = payload["caption"]
            return _directive_patch(
                lines,
                parsed,
                node_index,
                image_payload,
                replacement_name="image",
            )
        return _directive_patch(lines, parsed, node_index, None)
    raise _invalid(f"Draft media {source_id} is not referenced by body node {node_index}.")


def _body_media_occurrence(parsed: ParsedArticle, source_id: str) -> int | None:
    for index, node in enumerate(parsed.body):
        if node.kind != "directive":
            continue
        definition = DIRECTIVE_REGISTRY[node.name]
        payload = definition.payload_model.model_validate(node.payload)
        if any(reference.media_id == source_id for reference in definition.media_references(payload)):
            return index
    return None


def _compile_body_patch(
    operation: DraftEditOperation,
    lines: list[str],
    parsed: ParsedArticle,
) -> _BodyPatch | None:
    if isinstance(operation, ReplaceBodyNodeEdit):
        start, end = _node_range(lines, parsed, operation.node_index)
        return _BodyPatch(start, end, _node_lines(operation.node))
    if isinstance(operation, DeleteBodyNodeEdit):
        start, end = _node_range(lines, parsed, operation.node_index)
        return _BodyPatch(start, end, [])
    if isinstance(operation, InsertBodyNodeEdit):
        return _insert_lines(lines, parsed, operation.body_index, _node_lines(operation.node))
    if isinstance(operation, ReplaceDirectiveFieldEdit):
        directive_node = _directive_node(parsed, operation.node_index)
        directive_payload = _updated_nested_value(
            copy.deepcopy(directive_node.payload),
            operation.path,
            operation.value,
        )
        return _directive_patch(
            lines,
            parsed,
            operation.node_index,
            directive_payload,
        )
    if isinstance(operation, DeleteDirectiveItemEdit):
        directive_node = _directive_node(parsed, operation.node_index)
        item_payload = copy.deepcopy(directive_node.payload)
        items = item_payload.get("items")
        if not isinstance(items, list) or operation.item_index >= len(items):
            raise _invalid("Directive item no longer exists.")
        remaining = [item for index, item in enumerate(items) if index != operation.item_index]
        if not remaining:
            return _directive_patch(lines, parsed, operation.node_index, None)
        if directive_node.name == "gallery" and len(remaining) == 1:
            image_payload: dict[str, Any] = {"media": remaining[0]}
            if item_payload.get("caption"):
                image_payload["caption"] = item_payload["caption"]
            return _directive_patch(
                lines,
                parsed,
                operation.node_index,
                image_payload,
                replacement_name="image",
            )
        item_payload["items"] = remaining
        return _directive_patch(lines, parsed, operation.node_index, item_payload)
    if isinstance(operation, InsertImageEdit):
        image_payload = {"media": operation.source_id}
        if operation.caption is not None:
            image_payload["caption"] = operation.caption
        image_node = DraftDirectiveNodeInput(
            kind="directive",
            name="image",
            payload=image_payload,
        )
        return _insert_lines(
            lines,
            parsed,
            operation.body_index,
            _node_lines(image_node),
        )
    if isinstance(operation, DeleteMediaOccurrenceEdit):
        return _media_occurrence_patch(
            lines,
            parsed,
            operation.node_index,
            operation.source_id,
        )
    if isinstance(operation, RemoveMediaFromBodyEdit):
        node_index = _body_media_occurrence(parsed, operation.source_id)
        if node_index is None:
            raise _invalid(f"Draft media {operation.source_id} is not used in the article body.")
        return _media_occurrence_patch(lines, parsed, node_index, operation.source_id)
    return None


def _apply_patches(lines: list[str], patches: list[_BodyPatch]) -> str:
    ordered = sorted(patches, key=lambda patch: (patch.start, patch.end))
    for previous, current in pairwise(ordered):
        overlaps = current.start < previous.end or (
            current.start == previous.start and (current.start == current.end or previous.start == previous.end)
        )
        if overlaps:
            raise _invalid("Draft edit operations target overlapping body locations.")
    updated = list(lines)
    for patch in reversed(ordered):
        updated[patch.start : patch.end] = patch.replacement
    return "\n".join(updated)


def _rebuild_media(
    document: ArticleDocument,
    available_media: list[MediaAsset],
    parsed: ParsedArticle,
    descriptions: dict[str, str],
) -> list[MediaAsset]:
    current = {item.id: item for item in document.media}
    available = {item.id: item for item in available_media}
    pool = {**available, **current}
    ordered_ids: list[str] = []
    for directive in parsed.directives:
        for source_id in directive.media_ids:
            if source_id not in ordered_ids:
                ordered_ids.append(source_id)
    if document.cover_media_id and document.cover_media_id not in ordered_ids:
        ordered_ids.append(document.cover_media_id)
    missing = [source_id for source_id in ordered_ids if source_id not in pool]
    if missing:
        raise _invalid("Draft edit references unavailable workspace media: " + ", ".join(missing))

    rebuilt: list[MediaAsset] = []
    for order, source_id in enumerate(ordered_ids):
        item = pool[source_id]
        update: dict[str, Any] = {"order": order, "include": True}
        if source_id in descriptions:
            update.update(
                {
                    "description": descriptions[source_id],
                    "description_source": DescriptionSource.AI,
                    "description_status": DescriptionStatus.NEEDS_CONFIRMATION,
                }
            )
        rebuilt.append(item.model_copy(update=update))
    return rebuilt


def apply_draft_edits(request: WxPostDraftEditRequest) -> ArticleDocument:
    """Apply typed edits against one validated Draft snapshot, then revalidate it."""

    document = request.document.model_copy(deep=True)
    parsed = validate_and_parse(document)
    lines = document.body_markdown.split("\n")
    patches: list[_BodyPatch] = []
    descriptions: dict[str, str] = {}

    for operation in request.edits:
        patch = _compile_body_patch(operation, lines, parsed)
        if patch is not None:
            patches.append(patch)
            continue
        if isinstance(operation, ReplaceMetadataEdit):
            if operation.field == "title" and not (operation.value or "").strip():
                raise _invalid("Draft title cannot be empty.")
            setattr(
                document,
                operation.field,
                operation.value.strip() if operation.value is not None else None,
            )
        elif isinstance(operation, SetCoverEdit):
            document.cover_media_id = operation.source_id
        elif isinstance(operation, ClearCoverEdit):
            document.cover_media_id = None
        elif isinstance(operation, ReplaceMediaDescriptionEdit):
            descriptions[operation.source_id] = operation.value

    if patches:
        document.body_markdown = _apply_patches(lines, patches)

    parsed = parse_body_markdown(document.body_markdown)
    dependency_ids = {source_id for directive in parsed.directives for source_id in directive.media_ids}
    if document.cover_media_id is not None:
        dependency_ids.add(document.cover_media_id)
    unused_description_edits = sorted(set(descriptions) - dependency_ids)
    if unused_description_edits:
        raise _invalid(
            "Draft media descriptions can only be changed for body or cover media: "
            + ", ".join(unused_description_edits)
        )
    document.media = _rebuild_media(
        document,
        request.available_media,
        parsed,
        descriptions,
    )
    validate_and_parse(document)
    return document
