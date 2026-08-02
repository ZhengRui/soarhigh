from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import mimetypes
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, ValidationError

from .contracts import (
    BootstrapWorkspaceRequest,
    DraftGalleryBlock,
    DraftEnvelope,
    DraftImageBlock,
    DraftMarkdownBlock,
    DraftPersonBlock,
    DraftProposal,
    DraftSectionBlock,
    DraftVideoBlock,
    MANIFEST_SCHEMA_VERSION,
    MeetingLibraryOrigin,
    MeetingMediaReference,
    SaveDraftRequest,
    SetSourceInclusionRequest,
    SourceActionRequest,
    SourceKind,
    SourceLookupRequest,
    SourceManifest,
    SourceRecord,
    SourceUpdate,
    UploadSourceRequest,
    UpdateSourcesRequest,
    UpdateWorkspaceRequest,
)

WORKSPACE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MAX_SOURCE_BYTES = 50 * 1024 * 1024
ArticleValidator = Callable[[Mapping[str, Any]], Mapping[str, Any]]
MeetingMediaLoader = Callable[[str], list[Mapping[str, Any]]]
MeetingContextLoader = Callable[[str], Mapping[str, Any]]
SourceLoader = Callable[[str], bytes]
RequestModel = TypeVar("RequestModel", bound=BaseModel)
logger = logging.getLogger(__name__)
DEFAULT_DRAFT_PRESENTATION = {
    "layout": "brand-default",
    "palette": "paper-neutral",
    "appearance": "light",
    "typeface": "editorial-serif",
}


def _draft_excerpt(draft: DraftEnvelope | None, limit: int = 180) -> str | None:
    if draft is None:
        return None
    excerpt = draft.document.get("excerpt")
    if isinstance(excerpt, str) and excerpt.strip():
        return excerpt.strip()
    markdown = draft.document.get("bodyMarkdown")
    if not isinstance(markdown, str):
        return None
    without_directives = re.sub(r":::[\s\S]*?:::", " ", markdown)
    plain = re.sub(r"[#*_`>\[\]()~=!-]+", " ", without_directives)
    compact = " ".join(plain.split())
    if not compact:
        return None
    return compact if len(compact) <= limit else f"{compact[: limit - 1].rstrip()}…"


class WorkspaceError(Exception):
    """Base error for a rejected workspace operation."""

    code = "workspace_error"

    def error_details(self) -> dict[str, Any]:
        return {}


class WorkspaceNotFound(WorkspaceError):
    """The opaque workspace identifier does not resolve to a workspace."""

    code = "workspace_not_found"


class WorkspaceAlreadyExists(WorkspaceError):
    """A create operation targeted an existing workspace."""

    code = "workspace_already_exists"


class InvalidWorkspace(WorkspaceError):
    """Stored workspace state does not satisfy the production contract."""

    code = "invalid_workspace"


class InvalidRequest(WorkspaceError):
    """A caller request does not satisfy the production operation contract."""

    code = "invalid_request"


class ValidationUnavailable(WorkspaceError):
    """The authoritative SoarHigh ArticleDocument validator is unavailable."""

    code = "validation_unavailable"


class UpstreamUnavailable(WorkspaceError):
    """SoarHigh meeting media or its source file cannot be read safely."""

    code = "upstream_unavailable"


class SourceReferencedByDraft(WorkspaceError):
    """A source cannot be deleted while the saved Draft references it."""

    code = "source_referenced_by_draft"

    def __init__(self, source_id: str, references: list[str]):
        super().__init__(
            f"source {source_id} is referenced by the saved Draft; "
            "remove it from the Draft before deleting the source"
        )
        self.source_id = source_id
        self.references = references

    def error_details(self) -> dict[str, Any]:
        return {
            "sourceId": self.source_id,
            "references": self.references,
        }


class VersionConflict(WorkspaceError):
    """The caller attempted to update a stale manifest or draft version."""

    code = "version_conflict"

    def __init__(
        self,
        *,
        resource: str,
        expected: int,
        actual: int,
    ) -> None:
        super().__init__(
            f"expected {resource} version {expected}, "
            f"current {resource} version is {actual}"
        )
        self.resource = resource
        self.expected = expected
        self.actual = actual

    def error_details(self) -> dict[str, Any]:
        return {
            "versionKind": self.resource,
            "expectedVersion": self.expected,
            "actualVersion": self.actual,
        }


def error_response(error: WorkspaceError) -> dict[str, Any]:
    """Return the transport-neutral error envelope used by HTTP and MCP."""

    return {
        "error": {
            "code": error.code,
            "message": str(error),
            **error.error_details(),
        }
    }


class WorkspaceController:
    """Validated, versioned, atomic access to WxPost authoring workspaces."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        article_validator: ArticleValidator | None = None,
        soarhigh_api_base_url: str | None = None,
        soarhigh_service_token: str | None = None,
        meeting_media_loader: MeetingMediaLoader | None = None,
        meeting_context_loader: MeetingContextLoader | None = None,
        source_loader: SourceLoader | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.inbox_root = self.workspace_root / "inbox"
        self.inbox_root.mkdir(parents=True, exist_ok=True)
        if self.inbox_root.is_symlink():
            raise InvalidWorkspace("workspace inbox must not be a symlink")
        self._resolved_inbox = self.inbox_root.resolve()
        self._article_validator = article_validator
        self._soarhigh_api_base_url = (
            soarhigh_api_base_url
            if soarhigh_api_base_url is not None
            else os.environ.get("SOARHIGH_API_BASE_URL", "")
        ).rstrip("/")
        self._soarhigh_service_token = (
            soarhigh_service_token
            if soarhigh_service_token is not None
            else os.environ.get("WXPOST_SERVICE_TOKEN", "")
        )
        self._meeting_media_loader = meeting_media_loader
        self._meeting_context_loader = meeting_context_loader
        self._source_loader = source_loader

    def bootstrap_workspace(
        self,
        workspace_id: str,
        *,
        meeting_id: str | None,
        editorial: Mapping[str, Any],
        created_by: Mapping[str, Any],
    ) -> dict[str, Any]:
        self._validate_workspace_id(workspace_id)
        request = self._validate_request(
            BootstrapWorkspaceRequest,
            {
                "meetingId": meeting_id,
                "editorial": editorial,
                "createdBy": created_by,
            },
            label="workspace bootstrap",
        )
        candidate = self.inbox_root / workspace_id
        if candidate.exists() or candidate.is_symlink():
            existing_workspace = self._resolve_workspace(workspace_id)
            with self._workspace_lock(existing_workspace):
                existing_manifest = existing_workspace / "source-manifest.json"
                if existing_manifest.is_symlink():
                    raise InvalidWorkspace("source manifest must not be a symlink")
                if existing_manifest.exists():
                    raise WorkspaceAlreadyExists(
                        f"workspace already exists: {workspace_id}"
                    )
        meeting_media = (
            self._load_meeting_media(request.meeting_id)
            if request.meeting_id is not None
            else []
        )
        workspace = self._resolve_workspace(workspace_id, create=True)
        with self._workspace_lock(workspace):
            manifest_path = workspace / "source-manifest.json"
            if manifest_path.is_symlink():
                raise InvalidWorkspace("source manifest must not be a symlink")
            if manifest_path.exists():
                raise WorkspaceAlreadyExists(
                    f"workspace already exists: {workspace_id}"
                )
            unexpected = [
                path.name
                for path in workspace.iterdir()
                if path.name != ".source-manifest.lock"
            ]
            if unexpected:
                raise InvalidWorkspace("workspace has files but no source manifest")
            manifest = self._new_manifest(
                workspace_id,
                request,
                meeting_media,
            )
            self._atomic_write_json(manifest_path, manifest.to_wire())
            draft = self._read_draft(workspace, manifest)
        return self._context_response(workspace_id, manifest, draft)

    def update_workspace(
        self,
        workspace_id: str,
        *,
        expected_manifest_version: int,
        meeting_id: str | None,
        editorial: Mapping[str, Any],
        source_updates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        request = self._validate_request(
            UpdateWorkspaceRequest,
            {
                "expectedManifestVersion": expected_manifest_version,
                "meetingId": meeting_id,
                "editorial": editorial,
                "sourceUpdates": source_updates or [],
            },
            label="workspace update",
        )
        workspace = self._resolve_workspace(workspace_id)

        with self._workspace_lock(workspace):
            manifest = self._read_manifest(workspace, workspace_id)
            self._check_manifest_version(
                manifest,
                request.expected_manifest_version,
            )
            meeting_changed = manifest.meeting_id != request.meeting_id
            if meeting_changed and request.source_updates:
                raise InvalidRequest(
                    "sourceUpdates cannot be combined with a meetingId change"
                )
            meeting_media = (
                self._load_meeting_media(request.meeting_id)
                if meeting_changed and request.meeting_id is not None
                else []
            )
            editorial_changed = manifest.editorial != request.editorial
            draft = self._read_draft(workspace, manifest)

            manifest_data = manifest.to_wire()
            removed_sources: list[SourceRecord] = []
            if meeting_changed:
                removed_sources = [
                    source
                    for source in manifest.sources
                    if isinstance(source.origin, MeetingLibraryOrigin)
                ]
                manifest_data["sources"] = [
                    source.to_wire()
                    for source in manifest.sources
                    if not isinstance(source.origin, MeetingLibraryOrigin)
                ]
                manifest_data["meetingId"] = request.meeting_id
                for media in meeting_media:
                    source = self._meeting_source_record(
                        manifest_data["nextMaterialNumber"],
                        media,
                    )
                    manifest_data["sources"].append(source.to_wire())
                    manifest_data["nextMaterialNumber"] += 1
            manifest_data["editorial"] = request.editorial.to_wire()
            sources_changed = self._apply_source_updates(
                manifest_data["sources"],
                request.source_updates,
            )
            if not meeting_changed and not editorial_changed and not sources_changed:
                return self._context_response(workspace_id, manifest, draft)

            if meeting_changed:
                manifest_data["draft"] = None
                updated_manifest = self._write_workspace_update(
                    workspace,
                    manifest_data,
                    manifest,
                    draft,
                )
                updated_draft = None
            else:
                updated_manifest = self._write_changed_manifest(
                    workspace,
                    manifest_data,
                    manifest.manifest_version,
                )
                updated_draft = draft
            for source in removed_sources:
                if source.workspace_ready:
                    self._remove_regular_file(
                        self._source_path(workspace / "sources", source),
                        tolerate_failure=True,
                    )

        return self._context_response(
            workspace_id,
            updated_manifest,
            updated_draft,
        )

    def list_workspaces(
        self,
        *,
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        if (
            isinstance(page, bool)
            or not isinstance(page, int)
            or page < 1
            or isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or page_size < 1
            or page_size > 100
        ):
            raise InvalidRequest(
                "workspace pagination requires page >= 1 and 1 <= page_size <= 100"
            )
        items: list[dict[str, Any]] = []
        try:
            candidates = sorted(self.inbox_root.iterdir(), key=lambda path: path.name)
        except OSError as exc:
            raise InvalidWorkspace(f"cannot list workspaces: {exc}") from exc
        for candidate in candidates:
            try:
                workspace = self._resolve_workspace(candidate.name)
                with self._workspace_lock(workspace):
                    manifest = self._read_manifest(workspace, candidate.name)
                    draft = self._read_draft(workspace, manifest)
                    items.append(self._workspace_summary(manifest, draft))
            except (WorkspaceError, OSError) as exc:
                logger.warning(
                    "Skipping unreadable WxPost workspace %s: %s",
                    candidate.name,
                    exc,
                )
        items.sort(key=lambda item: item["createdAt"], reverse=True)
        total = len(items)
        pages = (total + page_size - 1) // page_size if total > 0 else 1
        start = (page - 1) * page_size
        return {
            "items": items[start : start + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": pages,
        }

    def delete_workspace(
        self,
        workspace_id: str,
        *,
        expected_manifest_version: int,
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        with self._workspace_lock(workspace):
            manifest = self._read_manifest(workspace, workspace_id)
            self._check_manifest_version(manifest, expected_manifest_version)
            summary = self._workspace_summary(manifest)
            try:
                shutil.rmtree(workspace)
            except OSError as exc:
                raise InvalidWorkspace(f"cannot delete workspace: {exc}") from exc
        return {"workspaceId": workspace_id, "deleted": True, "workspace": summary}

    def get_context(self, workspace_id: str) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        with self._workspace_lock(workspace):
            manifest = self._read_manifest(workspace, workspace_id)
            draft = self._read_draft(workspace, manifest)
        return self._context_response(workspace_id, manifest, draft)

    def get_agent_context(self, workspace_id: str) -> dict[str, Any]:
        """Return saved workspace state plus live facts needed for authoring."""

        workspace = self._resolve_workspace(workspace_id)
        with self._workspace_lock(workspace):
            manifest = self._read_manifest(workspace, workspace_id)
            draft = self._read_draft(workspace, manifest)
        context = self._context_response(workspace_id, manifest, draft)
        context["meetingContext"] = (
            self._load_meeting_context(manifest.meeting_id)
            if manifest.meeting_id is not None
            else None
        )
        return context

    def read_source(
        self,
        workspace_id: str,
        *,
        source_id: str,
    ) -> tuple[bytes, str]:
        request = self._validate_request(
            SourceLookupRequest,
            {"sourceId": source_id},
            label="source read",
        )
        workspace = self._resolve_workspace(workspace_id)
        with self._workspace_lock(workspace):
            manifest = self._read_manifest(workspace, workspace_id)
            source = self._find_source(manifest, request.source_id)
            if not source.workspace_ready:
                raise InvalidRequest(
                    f"source is not available in the workspace: {source.id}"
                )
            source_path = self._source_path(workspace / "sources", source)
            if source_path.is_symlink() or not source_path.is_file():
                raise InvalidWorkspace(f"source file is missing: {source.id}")
            try:
                data = source_path.read_bytes()
            except OSError as exc:
                raise InvalidWorkspace(
                    f"cannot read source file {source.id}: {exc}"
                ) from exc
            if len(data) != source.size_bytes:
                raise InvalidWorkspace(f"source file size is invalid: {source.id}")
        return data, source.mime_type

    def import_source(
        self,
        workspace_id: str,
        *,
        expected_manifest_version: int,
        source_id: str,
    ) -> dict[str, Any]:
        request = self._validate_request(
            SourceActionRequest,
            {
                "expectedManifestVersion": expected_manifest_version,
                "sourceId": source_id,
            },
            label="source import",
        )
        workspace = self._resolve_workspace(workspace_id)
        with self._workspace_lock(workspace):
            manifest = self._read_manifest(workspace, workspace_id)
            self._check_manifest_version(
                manifest,
                request.expected_manifest_version,
            )
            source = self._find_source(manifest, request.source_id)
            if not isinstance(source.origin, MeetingLibraryOrigin):
                raise InvalidRequest(
                    f"source {source.id} is not a meeting-library reference"
                )
            if source.workspace_ready:
                return manifest.to_wire()
            manifest = self._materialize_meeting_source(
                workspace,
                manifest,
                source,
                include=False,
            )
        return manifest.to_wire()

    def set_source_included(
        self,
        workspace_id: str,
        *,
        expected_manifest_version: int,
        source_id: str,
        included: bool,
    ) -> dict[str, Any]:
        request = self._validate_request(
            SetSourceInclusionRequest,
            {
                "expectedManifestVersion": expected_manifest_version,
                "sourceId": source_id,
                "included": included,
            },
            label="source inclusion",
        )
        workspace = self._resolve_workspace(workspace_id)
        with self._workspace_lock(workspace):
            manifest = self._read_manifest(workspace, workspace_id)
            self._check_manifest_version(
                manifest,
                request.expected_manifest_version,
            )
            source = self._find_source(manifest, request.source_id)
            if request.included and not source.workspace_ready:
                if not isinstance(source.origin, MeetingLibraryOrigin):
                    raise InvalidWorkspace(
                        f"non-ready direct source is invalid: {source.id}"
                    )
                manifest = self._materialize_meeting_source(
                    workspace,
                    manifest,
                    source,
                    include=True,
                )
            elif source.included != request.included:
                manifest_data = manifest.to_wire()
                source_data = self._find_source_data(
                    manifest_data["sources"],
                    request.source_id,
                )
                source_data["included"] = request.included
                manifest = self._write_changed_manifest(
                    workspace,
                    manifest_data,
                    manifest.manifest_version,
                )
        return manifest.to_wire()

    def upload_source(
        self,
        workspace_id: str,
        *,
        expected_manifest_version: int,
        origin: str,
        filename: str,
        mime_type: str,
        data: bytes,
        description: str = "",
        description_source: str | None = None,
        description_status: str = "missing",
    ) -> dict[str, Any]:
        request = self._validate_request(
            UploadSourceRequest,
            {
                "expectedManifestVersion": expected_manifest_version,
                "origin": origin,
                "filename": filename,
                "mimeType": mime_type,
                "description": description,
                "descriptionSource": description_source,
                "descriptionStatus": description_status,
            },
            label="source upload",
        )
        if not isinstance(data, bytes):
            raise InvalidRequest("uploaded source must be bytes")
        if not data:
            raise InvalidRequest("uploaded source must not be empty")
        if len(data) > MAX_SOURCE_BYTES:
            raise InvalidRequest(f"uploaded source exceeds {MAX_SOURCE_BYTES} bytes")

        workspace = self._resolve_workspace(workspace_id)
        with self._workspace_lock(workspace):
            manifest = self._read_manifest(workspace, workspace_id)
            self._check_manifest_version(
                manifest,
                request.expected_manifest_version,
            )
            source_id = self._material_id(manifest.next_material_number)
            source = SourceRecord.model_validate(
                {
                    "id": source_id,
                    "kind": self._source_kind(request.mime_type),
                    "origin": {"type": request.origin},
                    "filename": request.filename,
                    "mimeType": request.mime_type,
                    "sizeBytes": len(data),
                    "workspaceReady": True,
                    "included": False,
                    "description": request.description,
                    "descriptionSource": request.description_source,
                    "descriptionStatus": request.description_status,
                }
            )
            sources_root = self._ensure_sources_directory(workspace)
            source_path = self._source_path(sources_root, source)
            self._atomic_write_bytes(source_path, data)
            manifest_data = manifest.to_wire()
            manifest_data["sources"].append(source.to_wire())
            manifest_data["nextMaterialNumber"] += 1
            try:
                manifest = self._write_changed_manifest(
                    workspace,
                    manifest_data,
                    manifest.manifest_version,
                )
            except WorkspaceError:
                self._remove_source_file_unless_claimed(
                    workspace,
                    source,
                    source_path,
                )
                raise
        return manifest.to_wire()

    def upload_source_from_path(
        self,
        workspace_id: str,
        *,
        expected_manifest_version: int,
        source_path: str,
        origin: str,
        filename: str | None = None,
        mime_type: str | None = None,
        description: str = "",
        description_source: str | None = None,
        description_status: str = "missing",
    ) -> dict[str, Any]:
        path = Path(source_path).expanduser()
        if path.is_symlink() or not path.is_file():
            raise InvalidRequest("sourcePath must be a regular file")
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise InvalidRequest(f"cannot resolve sourcePath: {exc}") from exc
        if not resolved.is_relative_to(self.workspace_root):
            raise InvalidRequest("sourcePath must be below WXPOST_WORKSPACE_ROOT")
        try:
            size = resolved.stat().st_size
            if size <= 0:
                raise InvalidRequest("uploaded source must not be empty")
            if size > MAX_SOURCE_BYTES:
                raise InvalidRequest(
                    f"uploaded source exceeds {MAX_SOURCE_BYTES} bytes"
                )
            data = resolved.read_bytes()
        except OSError as exc:
            raise InvalidRequest(f"cannot read sourcePath: {exc}") from exc
        effective_filename = filename or resolved.name
        effective_mime = (
            mime_type
            or mimetypes.guess_type(effective_filename)[0]
            or "application/octet-stream"
        )
        return self.upload_source(
            workspace_id,
            expected_manifest_version=expected_manifest_version,
            origin=origin,
            filename=effective_filename,
            mime_type=effective_mime,
            data=data,
            description=description,
            description_source=description_source,
            description_status=description_status,
        )

    def delete_source_preflight(
        self,
        workspace_id: str,
        *,
        expected_manifest_version: int,
        source_id: str,
    ) -> dict[str, Any]:
        request = self._validate_request(
            SourceActionRequest,
            {
                "expectedManifestVersion": expected_manifest_version,
                "sourceId": source_id,
            },
            label="source delete preflight",
        )
        workspace = self._resolve_workspace(workspace_id)
        with self._workspace_lock(workspace):
            manifest = self._read_manifest(workspace, workspace_id)
            self._check_manifest_version(
                manifest,
                request.expected_manifest_version,
            )
            self._find_source(manifest, request.source_id)
            draft = self._read_draft(workspace, manifest)
            references = self._draft_references(draft, request.source_id)
        return {
            "sourceId": request.source_id,
            "manifestVersion": manifest.manifest_version,
            "draftVersion": draft.draft_version if draft is not None else 0,
            "blockedByDraft": bool(references),
            "references": references,
        }

    def delete_source(
        self,
        workspace_id: str,
        *,
        expected_manifest_version: int,
        source_id: str,
    ) -> dict[str, Any]:
        request = self._validate_request(
            SourceActionRequest,
            {
                "expectedManifestVersion": expected_manifest_version,
                "sourceId": source_id,
            },
            label="source delete",
        )
        workspace = self._resolve_workspace(workspace_id)
        with self._workspace_lock(workspace):
            manifest = self._read_manifest(workspace, workspace_id)
            self._check_manifest_version(
                manifest,
                request.expected_manifest_version,
            )
            source = self._find_source(manifest, request.source_id)
            meeting_reference = isinstance(
                source.origin,
                MeetingLibraryOrigin,
            )
            if meeting_reference and not source.workspace_ready and not source.included:
                return manifest.to_wire()

            draft = self._read_draft(workspace, manifest)
            references = self._draft_references(draft, request.source_id)
            if references:
                raise SourceReferencedByDraft(request.source_id, references)

            manifest_data = manifest.to_wire()
            source_data = self._find_source_data(
                manifest_data["sources"],
                request.source_id,
            )
            if meeting_reference:
                source_data["workspaceReady"] = False
                source_data["included"] = False
            else:
                manifest_data["sources"].remove(source_data)
            manifest = self._write_changed_manifest(
                workspace,
                manifest_data,
                manifest.manifest_version,
            )
            if source.workspace_ready:
                self._remove_regular_file(
                    self._source_path(workspace / "sources", source),
                    tolerate_failure=True,
                )
        return manifest.to_wire()

    def update_sources(
        self,
        workspace_id: str,
        *,
        expected_manifest_version: int,
        updates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        request = self._validate_request(
            UpdateSourcesRequest,
            {
                "expectedManifestVersion": expected_manifest_version,
                "updates": updates,
            },
            label="source update",
        )
        with self._workspace_lock(workspace):
            manifest = self._read_manifest(workspace, workspace_id)
            actual_version = manifest.manifest_version
            if request.expected_manifest_version != actual_version:
                raise VersionConflict(
                    resource="manifest",
                    expected=request.expected_manifest_version,
                    actual=actual_version,
                )

            manifest_data = manifest.to_wire()
            if self._apply_source_updates(
                manifest_data["sources"],
                request.updates,
            ):
                manifest = self._write_changed_manifest(
                    workspace,
                    manifest_data,
                    actual_version,
                )

        return manifest.to_wire()

    def save_draft(
        self,
        workspace_id: str,
        *,
        expected_manifest_version: int,
        expected_draft_version: int,
        document: Mapping[str, Any],
        operation_id: str | None = None,
        refresh_source_snapshot: bool = False,
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        request = self._validate_request(
            SaveDraftRequest,
            {
                "expectedManifestVersion": expected_manifest_version,
                "expectedDraftVersion": expected_draft_version,
                "document": document,
                "operationId": operation_id,
            },
            label="draft save",
        )
        validated_document = self._validate_article_document(request.document)
        document_hash = self._document_sha256(validated_document)

        with self._workspace_lock(workspace):
            manifest = self._read_manifest(workspace, workspace_id)
            current = self._read_draft(workspace, manifest)
            actual_manifest_version = manifest.manifest_version
            if request.expected_manifest_version != actual_manifest_version:
                raise VersionConflict(
                    resource="manifest",
                    expected=request.expected_manifest_version,
                    actual=actual_manifest_version,
                )
            actual_version = manifest.draft.version if manifest.draft else 0
            if request.expected_draft_version != actual_version:
                raise VersionConflict(
                    resource="draft",
                    expected=request.expected_draft_version,
                    actual=actual_version,
                )

            self._validate_draft_source_snapshot(
                validated_document,
                manifest=manifest,
                current=current,
                refresh_from_materials=refresh_source_snapshot,
            )
            next_version = actual_version + 1
            manifest_data = manifest.to_wire()
            source_manifest_version = (
                actual_manifest_version
                if refresh_source_snapshot or manifest.draft is None
                else manifest.draft.source_manifest_version
            )
            draft_state = {
                "version": next_version,
                "sourceManifestVersion": source_manifest_version,
                "sha256": document_hash,
            }
            if request.operation_id is not None:
                draft_state["operationId"] = request.operation_id
            manifest_data["draft"] = draft_state
            manifest_data["updatedAt"] = datetime.now(UTC)
            updated_manifest = self._validate_manifest_data(
                manifest_data,
                label="updated source manifest",
                request_error=True,
            )
            saved = DraftEnvelope.model_validate(
                {
                    "draftVersion": next_version,
                    "document": validated_document,
                }
            )

            draft_dir = workspace / "draft"
            self._ensure_child_directory(workspace, draft_dir)
            draft_path = draft_dir / "article.json"
            pending_path = draft_dir / ".article-save-pending.json"
            self._atomic_write_json(
                pending_path,
                {
                    "previousDocument": (
                        current.document if current is not None else None
                    )
                },
            )
            try:
                self._atomic_write_json(draft_path, validated_document)
                self._atomic_write_json(
                    workspace / "source-manifest.json",
                    updated_manifest.to_wire(),
                )
            except WorkspaceError:
                persisted_manifest = self._read_manifest(workspace, workspace_id)
                self._recover_pending_draft(workspace, persisted_manifest)
                raise
            self._remove_regular_file(pending_path, tolerate_failure=True)

        return saved.to_wire()

    def save_draft_proposal(
        self,
        workspace_id: str,
        *,
        expected_manifest_version: int,
        expected_draft_version: int,
        proposal: DraftProposal | Mapping[str, Any],
        operation_id: str | None = None,
        refresh_from_materials: bool = True,
    ) -> dict[str, Any]:
        """Assemble and save a canonical document from Hermes-owned fields."""
        validated_proposal = (
            proposal
            if isinstance(proposal, DraftProposal)
            else self._validate_request(
                DraftProposal,
                proposal,
                label="draft proposal",
            )
        )
        workspace = self._resolve_workspace(workspace_id)
        with self._workspace_lock(workspace):
            manifest = self._read_manifest(workspace, workspace_id)
            self._check_manifest_version(manifest, expected_manifest_version)
            current = self._read_draft(workspace, manifest)
            if not refresh_from_materials and current is None:
                raise InvalidRequest(
                    "a Draft revision requires an existing saved Draft"
                )
            presentation = (
                current.document["presentation"]
                if current is not None
                else DEFAULT_DRAFT_PRESENTATION
            )
            document = self._article_document_from_proposal(
                workspace_id,
                validated_proposal,
                manifest,
                presentation,
                current.document if current is not None else None,
                refresh_from_materials=refresh_from_materials,
            )

        # save_draft rechecks both versions under the write lock. A Materials
        # change between assembly and save therefore rejects the stale proposal.
        return self.save_draft(
            workspace_id,
            expected_manifest_version=expected_manifest_version,
            expected_draft_version=expected_draft_version,
            document=document,
            operation_id=operation_id,
            refresh_source_snapshot=refresh_from_materials,
        )

    @staticmethod
    def _context_response(
        workspace_id: str,
        manifest: SourceManifest,
        draft: DraftEnvelope | None,
    ) -> dict[str, Any]:
        return {
            "workspaceId": workspace_id,
            "manifest": manifest.to_wire(),
            "draft": draft.to_wire() if draft is not None else None,
        }

    def _new_manifest(
        self,
        workspace_id: str,
        request: BootstrapWorkspaceRequest,
        meeting_media: list[MeetingMediaReference],
    ) -> SourceManifest:
        created_at = datetime.now(UTC)
        sources = [
            self._meeting_source_record(index, media).to_wire()
            for index, media in enumerate(meeting_media, start=1)
        ]
        return SourceManifest.model_validate(
            {
                "schemaVersion": MANIFEST_SCHEMA_VERSION,
                "workspaceId": workspace_id,
                "manifestVersion": 1,
                "nextMaterialNumber": len(sources) + 1,
                "createdBy": request.created_by.to_wire(),
                "createdAt": created_at,
                "updatedAt": created_at,
                "meetingId": request.meeting_id,
                "draft": None,
                "editorial": request.editorial.to_wire(),
                "sources": sources,
            }
        )

    def _meeting_source_record(
        self,
        material_number: int,
        media: MeetingMediaReference,
    ) -> SourceRecord:
        return SourceRecord.model_validate(
            {
                "id": self._material_id(material_number),
                "kind": self._meeting_source_kind(media.mime_type),
                "origin": {
                    "type": "meeting-library",
                    "fileKey": media.file_key,
                },
                "filename": media.filename,
                "mimeType": media.mime_type,
                "sizeBytes": media.size_bytes,
                "workspaceReady": False,
                "included": False,
                "description": "",
                "descriptionSource": None,
                "descriptionStatus": "missing",
            }
        )

    def _load_meeting_media(
        self,
        meeting_id: str,
    ) -> list[MeetingMediaReference]:
        raw_items: Any
        if self._meeting_media_loader is not None:
            try:
                raw_items = self._meeting_media_loader(meeting_id)
            except WorkspaceError:
                raise
            except Exception as exc:
                raise UpstreamUnavailable(f"cannot list meeting media: {exc}") from exc
        else:
            if not self._soarhigh_api_base_url:
                raise UpstreamUnavailable(
                    "SOARHIGH_API_BASE_URL is required to list meeting media"
                )
            headers = {}
            if self._soarhigh_service_token:
                headers["Authorization"] = f"Bearer {self._soarhigh_service_token}"
            request = Request(
                f"{self._soarhigh_api_base_url}/meetings/"
                f"{quote(meeting_id, safe='')}/media",
                headers=headers,
                method="GET",
            )
            try:
                with urlopen(request, timeout=15) as response:
                    payload = json.loads(response.read())
            except HTTPError as exc:
                if exc.code in {401, 403, 404}:
                    raise InvalidRequest(
                        "meeting is unavailable to the WxPost controller"
                    ) from exc
                raise UpstreamUnavailable(
                    f"meeting media API returned HTTP {exc.code}"
                ) from exc
            except (
                OSError,
                URLError,
                TimeoutError,
                UnicodeDecodeError,
                json.JSONDecodeError,
            ) as exc:
                raise UpstreamUnavailable(
                    f"cannot reach meeting media API: {exc}"
                ) from exc
            raw_items = payload.get("items") if isinstance(payload, dict) else None

        if not isinstance(raw_items, list):
            raise UpstreamUnavailable("meeting media API returned an invalid response")
        parsed: list[MeetingMediaReference] = []
        try:
            for item in raw_items:
                parsed.append(MeetingMediaReference.model_validate(item))
        except ValidationError as exc:
            raise UpstreamUnavailable(
                "meeting media API returned invalid media metadata: "
                f"{self._validation_message(exc)}"
            ) from exc
        file_keys = [item.file_key for item in parsed]
        if len(file_keys) != len(set(file_keys)):
            raise UpstreamUnavailable(
                "meeting media API returned duplicate fileKey values"
            )
        for media in parsed:
            self._meeting_source_kind(media.mime_type)
            parsed_url = urlparse(media.url)
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                raise UpstreamUnavailable(
                    "meeting media API returned an invalid source URL"
                )
        return sorted(parsed, key=lambda item: (item.uploaded_at, item.file_key))

    def _load_meeting_context(self, meeting_id: str) -> dict[str, Any]:
        raw: Any
        if self._meeting_context_loader is not None:
            try:
                raw = self._meeting_context_loader(meeting_id)
            except WorkspaceError:
                raise
            except Exception as exc:
                raise UpstreamUnavailable(
                    f"cannot read linked meeting context: {exc}"
                ) from exc
        else:
            if not self._soarhigh_api_base_url:
                raise UpstreamUnavailable(
                    "SOARHIGH_API_BASE_URL is required to read linked meeting context"
                )
            headers = {}
            if self._soarhigh_service_token:
                headers["Authorization"] = f"Bearer {self._soarhigh_service_token}"
            request = Request(
                f"{self._soarhigh_api_base_url}/meetings/"
                f"{quote(meeting_id, safe='')}",
                headers=headers,
                method="GET",
            )
            try:
                with urlopen(request, timeout=15) as response:
                    raw = json.loads(response.read())
            except HTTPError as exc:
                if exc.code in {401, 403, 404}:
                    raise InvalidRequest(
                        "linked meeting is unavailable to the WxPost controller"
                    ) from exc
                raise UpstreamUnavailable(
                    f"meeting API returned HTTP {exc.code}"
                ) from exc
            except (
                OSError,
                URLError,
                TimeoutError,
                UnicodeDecodeError,
                json.JSONDecodeError,
            ) as exc:
                raise UpstreamUnavailable(
                    f"cannot reach linked meeting API: {exc}"
                ) from exc

        if not isinstance(raw, Mapping):
            raise UpstreamUnavailable("meeting API returned an invalid response")

        def clean_text(value: Any) -> str:
            return value.strip() if isinstance(value, str) else ""

        manager = raw.get("manager")
        manager_name = (
            clean_text(manager.get("name")) if isinstance(manager, Mapping) else ""
        )
        agenda: list[dict[str, Any]] = []
        segments = raw.get("segments")
        if isinstance(segments, list):
            for segment in segments:
                if not isinstance(segment, Mapping):
                    continue
                role_taker = segment.get("role_taker")
                role_name = (
                    clean_text(role_taker.get("name"))
                    if isinstance(role_taker, Mapping)
                    else ""
                )
                agenda.append(
                    {
                        "type": clean_text(segment.get("type")),
                        "startTime": clean_text(segment.get("start_time")),
                        "endTime": clean_text(segment.get("end_time")),
                        "roleTaker": role_name or None,
                        "title": clean_text(segment.get("title")),
                        "content": clean_text(segment.get("content")),
                    }
                )
        awards: list[dict[str, str]] = []
        raw_awards = raw.get("awards")
        if isinstance(raw_awards, list):
            for award in raw_awards:
                if isinstance(award, Mapping):
                    awards.append(
                        {
                            "category": clean_text(award.get("category")),
                            "winner": clean_text(award.get("winner")),
                        }
                    )

        return {
            "id": clean_text(raw.get("id")) or meeting_id,
            "no": raw.get("no") if isinstance(raw.get("no"), int) else None,
            "type": clean_text(raw.get("type")),
            "theme": clean_text(raw.get("theme")),
            "manager": manager_name or None,
            "date": clean_text(raw.get("date")),
            "startTime": clean_text(raw.get("start_time")),
            "endTime": clean_text(raw.get("end_time")),
            "location": clean_text(raw.get("location")),
            "introduction": clean_text(raw.get("introduction")),
            "agenda": agenda,
            "awards": awards,
        }

    def _materialize_meeting_source(
        self,
        workspace: Path,
        manifest: SourceManifest,
        source: SourceRecord,
        *,
        include: bool,
    ) -> SourceManifest:
        if manifest.meeting_id is None or not isinstance(
            source.origin,
            MeetingLibraryOrigin,
        ):
            raise InvalidWorkspace(
                f"meeting source has invalid provenance: {source.id}"
            )
        media_by_key = {
            media.file_key: media
            for media in self._load_meeting_media(manifest.meeting_id)
        }
        media = media_by_key.get(source.origin.file_key)
        if media is None:
            raise InvalidRequest(
                f"meeting-library source is no longer available: {source.id}"
            )
        data = self._download_source(media)
        sources_root = self._ensure_sources_directory(workspace)
        updated = SourceRecord.model_validate(
            {
                **source.to_wire(),
                "kind": self._meeting_source_kind(media.mime_type),
                "filename": media.filename,
                "mimeType": media.mime_type,
                "sizeBytes": media.size_bytes,
                "workspaceReady": True,
                "included": include,
            }
        )
        old_path = self._source_path(sources_root, source)
        new_path = self._source_path(sources_root, updated)
        self._atomic_write_bytes(new_path, data)
        manifest_data = manifest.to_wire()
        source_data = self._find_source_data(
            manifest_data["sources"],
            source.id,
        )
        source_data.update(updated.to_wire())
        try:
            manifest = self._write_changed_manifest(
                workspace,
                manifest_data,
                manifest.manifest_version,
            )
        except WorkspaceError:
            self._remove_source_file_unless_claimed(
                workspace,
                updated,
                new_path,
            )
            raise
        if old_path != new_path:
            self._remove_regular_file(old_path, tolerate_failure=True)
        return manifest

    def _download_source(self, media: MeetingMediaReference) -> bytes:
        if self._source_loader is not None:
            try:
                data = self._source_loader(media.url)
            except WorkspaceError:
                raise
            except Exception as exc:
                raise UpstreamUnavailable(
                    f"cannot download meeting source: {exc}"
                ) from exc
        else:
            request = Request(media.url, method="GET")
            try:
                with urlopen(request, timeout=30) as response:
                    data = response.read(MAX_SOURCE_BYTES + 1)
            except HTTPError as exc:
                raise UpstreamUnavailable(
                    f"meeting source returned HTTP {exc.code}"
                ) from exc
            except (OSError, URLError, TimeoutError) as exc:
                raise UpstreamUnavailable(
                    f"cannot download meeting source: {exc}"
                ) from exc
        if not isinstance(data, bytes):
            raise UpstreamUnavailable("meeting source loader returned invalid bytes")
        if len(data) > MAX_SOURCE_BYTES:
            raise InvalidRequest(f"meeting source exceeds {MAX_SOURCE_BYTES} bytes")
        if len(data) != media.size_bytes:
            raise UpstreamUnavailable(
                "meeting source size does not match the current metadata"
            )
        return data

    @staticmethod
    def _source_kind(mime_type: str) -> SourceKind:
        normalized = mime_type.split(";", 1)[0].strip().lower()
        if normalized.startswith("image/"):
            return SourceKind.IMAGE
        if normalized.startswith("video/"):
            return SourceKind.VIDEO
        if normalized.startswith("audio/"):
            return SourceKind.AUDIO
        if normalized.startswith("text/"):
            return SourceKind.TRANSCRIPT
        return SourceKind.DOCUMENT

    @classmethod
    def _meeting_source_kind(cls, mime_type: str) -> SourceKind:
        kind = cls._source_kind(mime_type)
        if kind not in {SourceKind.IMAGE, SourceKind.VIDEO}:
            raise UpstreamUnavailable(
                "meeting media API returned a non-image/video source"
            )
        return kind

    @staticmethod
    def _material_id(number: int) -> str:
        return f"M{number:02d}"

    @staticmethod
    def _find_source(
        manifest: SourceManifest,
        source_id: str,
    ) -> SourceRecord:
        for source in manifest.sources:
            if source.id == source_id:
                return source
        raise InvalidRequest(f"unknown source id: {source_id}")

    @staticmethod
    def _find_source_data(
        sources: list[dict[str, Any]],
        source_id: str,
    ) -> dict[str, Any]:
        for source in sources:
            if source["id"] == source_id:
                return source
        raise InvalidRequest(f"unknown source id: {source_id}")

    @staticmethod
    def _check_manifest_version(
        manifest: SourceManifest,
        expected: int,
    ) -> None:
        if expected != manifest.manifest_version:
            raise VersionConflict(
                resource="manifest",
                expected=expected,
                actual=manifest.manifest_version,
            )

    def _write_changed_manifest(
        self,
        workspace: Path,
        manifest_data: dict[str, Any],
        previous_version: int,
    ) -> SourceManifest:
        manifest_data["manifestVersion"] = previous_version + 1
        manifest_data["updatedAt"] = datetime.now(UTC)
        manifest = self._validate_manifest_data(
            manifest_data,
            label="updated source manifest",
            request_error=True,
        )
        self._atomic_write_json(
            workspace / "source-manifest.json",
            manifest.to_wire(),
        )
        return manifest

    def _write_workspace_update(
        self,
        workspace: Path,
        manifest_data: dict[str, Any],
        previous_manifest: SourceManifest,
        draft: DraftEnvelope | None,
    ) -> SourceManifest:
        manifest_data["manifestVersion"] = previous_manifest.manifest_version + 1
        manifest_data["updatedAt"] = datetime.now(UTC)
        updated = self._validate_manifest_data(
            manifest_data,
            label="updated source manifest",
            request_error=True,
        )
        if draft is None:
            self._atomic_write_json(
                workspace / "source-manifest.json",
                updated.to_wire(),
            )
            return updated

        draft_dir = workspace / "draft"
        self._ensure_child_directory(workspace, draft_dir)
        pending_path = draft_dir / ".article-save-pending.json"
        self._atomic_write_json(
            pending_path,
            {"previousDocument": draft.document},
        )
        try:
            self._atomic_write_json(
                workspace / "source-manifest.json",
                updated.to_wire(),
            )
            self._remove_regular_file(draft_dir / "article.json")
        except WorkspaceError:
            persisted = self._read_manifest(workspace, previous_manifest.workspace_id)
            self._recover_pending_draft(workspace, persisted)
            raise
        self._remove_regular_file(pending_path, tolerate_failure=True)
        return updated

    @staticmethod
    def _workspace_summary(
        manifest: SourceManifest,
        draft: DraftEnvelope | None = None,
    ) -> dict[str, Any]:
        wire = manifest.to_wire()
        return {
            "workspaceId": manifest.workspace_id,
            "createdBy": manifest.created_by.to_wire(),
            "createdAt": wire["createdAt"],
            "updatedAt": wire["updatedAt"],
            "meetingId": manifest.meeting_id,
            "articleType": manifest.editorial.article_type.value,
            "customArticleType": manifest.editorial.custom_article_type,
            "manifestVersion": manifest.manifest_version,
            "sourceCount": len(manifest.sources),
            "readySourceCount": sum(
                source.workspace_ready for source in manifest.sources
            ),
            "includedSourceCount": sum(source.included for source in manifest.sources),
            "draftVersion": (
                manifest.draft.version if manifest.draft is not None else None
            ),
            "draftExcerpt": _draft_excerpt(draft),
        }

    @staticmethod
    def _draft_references(
        draft: DraftEnvelope | None,
        source_id: str,
    ) -> list[str]:
        if draft is None:
            return []
        document = draft.document
        references = [
            f"media.{index}"
            for index, item in enumerate(document.get("media", []))
            if isinstance(item, Mapping) and item.get("id") == source_id
        ]
        if document.get("coverMediaId") == source_id:
            references.append("coverMediaId")
        return references

    @staticmethod
    def _source_path(
        sources_root: Path,
        source: SourceRecord,
    ) -> Path:
        return sources_root / f"{source.id}{Path(source.filename).suffix}"

    def _ensure_sources_directory(self, workspace: Path) -> Path:
        sources_root = workspace / "sources"
        self._ensure_child_directory(
            workspace,
            sources_root,
            label="sources",
        )
        return sources_root

    def _remove_source_file_unless_claimed(
        self,
        workspace: Path,
        source: SourceRecord,
        path: Path,
    ) -> None:
        try:
            persisted = self._validate_manifest_data(
                self._read_json_file(
                    workspace / "source-manifest.json",
                    label="source manifest",
                ),
                label="source manifest",
            )
            persisted_source = next(
                (
                    candidate
                    for candidate in persisted.sources
                    if candidate.id == source.id
                ),
                None,
            )
            claimed = (
                persisted_source is not None
                and persisted_source.workspace_ready
                and self._source_path(
                    workspace / "sources",
                    persisted_source,
                )
                == path
            )
        except WorkspaceError:
            claimed = True
        if not claimed:
            self._remove_regular_file(path, tolerate_failure=True)

    def _resolve_workspace(
        self,
        workspace_id: str,
        *,
        create: bool = False,
    ) -> Path:
        self._validate_workspace_id(workspace_id)

        candidate = self.inbox_root / workspace_id
        if create and not candidate.exists() and not candidate.is_symlink():
            try:
                candidate.mkdir(mode=0o700)
            except FileExistsError:
                pass
            except OSError as exc:
                raise InvalidWorkspace(f"cannot create workspace: {exc}") from exc
        if not candidate.exists() or not candidate.is_dir():
            raise WorkspaceNotFound(f"workspace does not exist: {workspace_id}")
        if candidate.is_symlink():
            raise InvalidWorkspace("workspace must not be a symlink")

        resolved = candidate.resolve()
        if resolved.parent != self._resolved_inbox or resolved != candidate.absolute():
            raise InvalidWorkspace("workspace escapes the configured inbox")
        return resolved

    @staticmethod
    def _validate_workspace_id(workspace_id: str) -> None:
        if not isinstance(workspace_id, str) or not WORKSPACE_ID_PATTERN.fullmatch(
            workspace_id
        ):
            raise InvalidRequest("workspaceId must be a lowercase slug")

    @contextmanager
    def _workspace_lock(self, workspace: Path):
        lock_path = workspace / ".source-manifest.lock"
        if lock_path.is_symlink():
            raise InvalidWorkspace("workspace lock must not be a symlink")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_manifest(
        self,
        workspace: Path,
        workspace_id: str,
    ) -> SourceManifest:
        manifest = self._validate_manifest_data(
            self._read_json_file(
                workspace / "source-manifest.json",
                label="source manifest",
            ),
            label="source manifest",
        )
        if manifest.workspace_id != workspace_id:
            raise InvalidWorkspace("source manifest workspaceId does not match")
        self._validate_ready_source_files(workspace, manifest)
        return manifest

    def _read_draft(
        self,
        workspace: Path,
        manifest: SourceManifest,
    ) -> DraftEnvelope | None:
        self._recover_pending_draft(workspace, manifest)
        path = workspace / "draft" / "article.json"
        if manifest.draft is None:
            if path.exists():
                raise InvalidWorkspace(
                    "draft/article.json exists without draft metadata in the manifest"
                )
            return None
        if not path.exists():
            raise InvalidWorkspace(
                "manifest references draft/article.json but the file is missing"
            )

        document = self._read_json_file(path, label="draft")
        if self._document_sha256(document) != manifest.draft.sha256:
            raise InvalidWorkspace(
                "draft/article.json does not match its manifest hash"
            )
        return DraftEnvelope.model_validate(
            {
                "draftVersion": manifest.draft.version,
                "document": document,
            }
        )

    def _validate_ready_source_files(
        self,
        workspace: Path,
        manifest: SourceManifest,
    ) -> None:
        ready_sources = [
            source for source in manifest.sources if source.workspace_ready
        ]
        if not ready_sources:
            return

        sources_root = workspace / "sources"
        if sources_root.is_symlink() or not sources_root.is_dir():
            raise InvalidWorkspace("workspace sources path must be a regular directory")
        resolved_sources_root = sources_root.resolve()
        if resolved_sources_root.parent != workspace:
            raise InvalidWorkspace("workspace sources directory escapes the workspace")

        for source in ready_sources:
            suffix = Path(source.filename).suffix
            path = sources_root / f"{source.id}{suffix}"
            if path.is_symlink() or not path.is_file():
                raise InvalidWorkspace(
                    f"workspace-ready source file is missing: {source.id}"
                )
            try:
                resolved = path.resolve(strict=True)
            except OSError as exc:
                raise InvalidWorkspace(
                    f"cannot resolve workspace-ready source {source.id}: {exc}"
                ) from exc
            if not resolved.is_relative_to(resolved_sources_root):
                raise InvalidWorkspace(
                    f"workspace-ready source escapes sources/: {source.id}"
                )
            if path.stat().st_size != source.size_bytes:
                raise InvalidWorkspace(
                    f"workspace-ready source size does not match manifest: {source.id}"
                )

    @staticmethod
    def _read_json_file(path: Path, *, label: str) -> dict[str, Any]:
        if path.is_symlink() or not path.is_file():
            raise InvalidWorkspace(f"{label} must be a regular file")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InvalidWorkspace(f"cannot read {label}: {exc}") from exc
        if not isinstance(value, dict):
            raise InvalidWorkspace(f"{label} must contain a JSON object")
        return value

    @classmethod
    def _validate_manifest_data(
        cls,
        value: Mapping[str, Any],
        *,
        label: str,
        request_error: bool = False,
    ) -> SourceManifest:
        try:
            return SourceManifest.model_validate(value)
        except ValidationError as exc:
            error_type = InvalidRequest if request_error else InvalidWorkspace
            raise error_type(
                f"{label} does not satisfy source-manifest v4: "
                f"{cls._validation_message(exc)}"
            ) from exc

    @classmethod
    def _validate_request(
        cls,
        model: type[RequestModel],
        value: Mapping[str, Any],
        *,
        label: str,
    ) -> RequestModel:
        try:
            return model.model_validate(value)
        except ValidationError as exc:
            raise InvalidRequest(
                f"{label} does not satisfy the operation contract: "
                f"{cls._validation_message(exc)}"
            ) from exc

    @staticmethod
    def _apply_source_updates(
        sources: list[dict[str, Any]],
        updates: list[SourceUpdate],
    ) -> bool:
        changed = False
        by_id = {source["id"]: source for source in sources}
        for update in updates:
            source_id = str(update.source_id)
            source = by_id.get(source_id)
            if source is None:
                raise InvalidRequest(f"unknown source id: {source_id}")
            changes = update.to_wire(exclude_unset=True)
            changes.pop("sourceId")
            move_to_index = changes.pop("moveToIndex", None)
            for field, value in changes.items():
                if source.get(field) != value:
                    source[field] = value
                    changed = True
            if move_to_index is not None:
                if move_to_index >= len(sources):
                    raise InvalidRequest(
                        f"moveToIndex is outside the source list: {move_to_index}"
                    )
                current_index = sources.index(source)
                if current_index != move_to_index:
                    sources.insert(move_to_index, sources.pop(current_index))
                    changed = True
        return changed

    def _validate_article_document(
        self,
        document: Mapping[str, Any],
    ) -> dict[str, Any]:
        draft = dict(document)

        if self._article_validator is not None:
            try:
                normalized = self._article_validator(draft)
            except WorkspaceError:
                raise
            except Exception as exc:
                raise InvalidRequest(f"ArticleDocument is invalid: {exc}") from exc
        else:
            normalized = self._validate_article_document_with_backend(draft)
        if not isinstance(normalized, Mapping):
            raise ValidationUnavailable(
                "ArticleDocument validator did not return a normalized document"
            )
        return dict(normalized)

    def _validate_article_document_with_backend(
        self,
        document: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not self._soarhigh_api_base_url:
            raise ValidationUnavailable(
                "SOARHIGH_API_BASE_URL is required to validate ArticleDocument"
            )
        request = Request(
            f"{self._soarhigh_api_base_url}/posts/wxposts/validate",
            data=json.dumps(document, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            if exc.code == 422:
                try:
                    payload = json.loads(exc.read())
                except (UnicodeDecodeError, json.JSONDecodeError):
                    payload = None
                raise InvalidRequest(self._validation_failure_message(payload)) from exc
            raise ValidationUnavailable(
                f"SoarHigh ArticleDocument validator returned HTTP {exc.code}"
            ) from exc
        except (
            OSError,
            URLError,
            TimeoutError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise ValidationUnavailable(
                f"cannot reach SoarHigh ArticleDocument validator: {exc}"
            ) from exc
        if not isinstance(payload, dict) or payload.get("valid") is not True:
            raise ValidationUnavailable(
                "SoarHigh ArticleDocument validator returned an invalid response"
            )
        normalized = payload.get("document")
        if not isinstance(normalized, dict):
            raise ValidationUnavailable(
                "SoarHigh ArticleDocument validator omitted the normalized document"
            )
        return normalized

    @staticmethod
    def _validation_failure_message(payload: Any) -> str:
        if isinstance(payload, dict):
            errors = payload.get("errors")
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                first = errors[0]
                path = ".".join(str(part) for part in first.get("path", []))
                message = first.get("message", "ArticleDocument is invalid")
                return f"ArticleDocument is invalid at {path or 'root'}: {message}"
        return "ArticleDocument is invalid"

    @staticmethod
    def _article_document_from_proposal(
        workspace_id: str,
        proposal: DraftProposal,
        manifest: SourceManifest,
        presentation: Mapping[str, Any],
        current_document: Mapping[str, Any] | None,
        *,
        refresh_from_materials: bool,
    ) -> dict[str, Any]:
        if not refresh_from_materials and current_document is None:
            raise InvalidRequest("a Draft revision requires an existing saved Draft")
        snapshot_document = current_document or {}
        current_media = (
            {
                item["id"]: item
                for item in current_document.get("media", [])
                if isinstance(item, Mapping) and isinstance(item.get("id"), str)
            }
            if current_document is not None
            else {}
        )
        if refresh_from_materials:
            source_media = {
                source.id: {
                    "id": source.id,
                    "kind": source.kind.value,
                    "sourceUrl": (
                        "https://workspace.invalid/"
                        f"{quote(workspace_id, safe='')}/materials/{source.id}"
                    ),
                }
                for source in manifest.sources
                if source.included
                and source.kind in {SourceKind.IMAGE, SourceKind.VIDEO}
            }
        else:
            source_media = current_media
        proposal_ids = [item.id for item in proposal.media]
        unexpected = [
            source_id for source_id in proposal_ids if source_id not in source_media
        ]
        if unexpected:
            raise InvalidRequest(
                "draft proposal media contains sources outside its source snapshot: "
                + ", ".join(unexpected)
            )
        missing = [
            source_id for source_id in source_media if source_id not in proposal_ids
        ]
        if missing:
            raise InvalidRequest(
                "draft proposal media is missing sources from its source snapshot: "
                + ", ".join(missing)
            )

        media_proposals = {item.id: item for item in proposal.media}
        media: list[dict[str, Any]] = []
        for order, source_id in enumerate(
            WorkspaceController._proposal_media_order(proposal)
        ):
            item = media_proposals[source_id]
            source = source_media[source_id]
            previous = current_media.get(source_id)
            description_unchanged = (
                previous is not None and previous.get("description") == item.description
            )
            media.append(
                {
                    "id": source_id,
                    "kind": source["kind"],
                    "sourceUrl": source["sourceUrl"],
                    "description": item.description,
                    "credit": item.credit,
                    "people": item.people,
                    "include": True,
                    "order": order,
                    "descriptionSource": (
                        previous.get("descriptionSource")
                        if description_unchanged and previous is not None
                        else "ai"
                    ),
                    "descriptionStatus": (
                        previous.get("descriptionStatus")
                        if description_unchanged and previous is not None
                        else "needs_confirmation"
                    ),
                }
            )

        proposal_wire = proposal.to_wire()
        return {
            "schemaVersion": 1,
            "title": proposal_wire["title"],
            "slug": None,
            "excerpt": proposal_wire.get("excerpt"),
            "byline": proposal_wire.get("byline"),
            "articleType": (
                manifest.editorial.article_type.value
                if refresh_from_materials
                else snapshot_document["articleType"]
            ),
            "customArticleType": (
                manifest.editorial.custom_article_type
                if refresh_from_materials
                else snapshot_document.get("customArticleType")
            ),
            "sourceMeetingId": (
                manifest.meeting_id
                if refresh_from_materials
                else snapshot_document.get("sourceMeetingId")
            ),
            "bodyMarkdown": WorkspaceController._proposal_body_markdown(proposal),
            "media": media,
            "coverMediaId": proposal_wire.get("coverMediaId"),
            "presentation": dict(presentation),
        }

    @staticmethod
    def _proposal_body_markdown(proposal: DraftProposal) -> str:
        parts: list[str] = []
        for block in proposal.blocks:
            if isinstance(block, DraftMarkdownBlock):
                parts.append(block.markdown)
                continue
            if isinstance(block, DraftSectionBlock):
                parts.append(
                    "\n".join(
                        [
                            WorkspaceController._serialize_directive(
                                "section",
                                {"kicker": block.kicker},
                            ),
                            f"## {block.heading}",
                            "",
                            block.body,
                        ]
                    )
                )
                continue

            payload = block.to_wire()
            directive = str(payload.pop("type"))
            parts.append(WorkspaceController._serialize_directive(directive, payload))
        return "\n\n".join(parts)

    @staticmethod
    def _serialize_directive(name: str, payload: Mapping[str, Any]) -> str:
        return "\n".join(
            [
                f":::{name}",
                json.dumps(payload, ensure_ascii=False, indent=2),
                ":::",
            ]
        )

    @staticmethod
    def _proposal_media_order(proposal: DraftProposal) -> list[str]:
        ordered: list[str] = []
        for block in proposal.blocks:
            references: list[str]
            if isinstance(block, (DraftImageBlock, DraftVideoBlock)):
                references = [block.media]
            elif isinstance(block, DraftGalleryBlock):
                references = block.items
            elif isinstance(block, DraftPersonBlock) and block.media is not None:
                references = [block.media]
            else:
                references = []
            for source_id in references:
                if source_id not in ordered:
                    ordered.append(source_id)
        if (
            proposal.cover_media_id is not None
            and proposal.cover_media_id not in ordered
        ):
            ordered.append(proposal.cover_media_id)
        return ordered

    @staticmethod
    def _validate_draft_source_snapshot(
        document: Mapping[str, Any],
        *,
        manifest: SourceManifest,
        current: DraftEnvelope | None,
        refresh_from_materials: bool,
    ) -> None:
        if current is not None and not refresh_from_materials:
            snapshot = current.document
            for field in ("articleType", "customArticleType", "sourceMeetingId"):
                if document.get(field) != snapshot.get(field):
                    raise InvalidRequest(
                        f"ArticleDocument {field} does not match the saved Draft snapshot"
                    )
            expected_media = {
                item["id"]: (item.get("kind"), item.get("include"))
                for item in snapshot.get("media", [])
                if isinstance(item, Mapping) and isinstance(item.get("id"), str)
            }
            cover_id = document.get("coverMediaId")
            if isinstance(cover_id, str) and cover_id not in expected_media:
                cover_source = next(
                    (
                        source
                        for source in manifest.sources
                        if source.id == cover_id
                        and source.workspace_ready
                        and source.kind == SourceKind.IMAGE
                    ),
                    None,
                )
                if cover_source is None:
                    raise InvalidRequest(
                        "Draft cover must be a workspace-ready image source"
                    )
                expected_media[cover_id] = (SourceKind.IMAGE.value, True)
            WorkspaceController._validate_media_snapshot(
                document,
                expected_media,
                allow_removal=True,
            )
            return

        expected_media = {
            source.id: (source.kind.value, True)
            for source in manifest.sources
            if source.included and source.kind in {SourceKind.IMAGE, SourceKind.VIDEO}
        }
        if document.get("articleType") != manifest.editorial.article_type.value:
            raise InvalidRequest(
                "ArticleDocument articleType does not match saved Materials"
            )
        if document.get("customArticleType") != manifest.editorial.custom_article_type:
            raise InvalidRequest(
                "ArticleDocument customArticleType does not match saved Materials"
            )
        if document.get("sourceMeetingId") != manifest.meeting_id:
            raise InvalidRequest(
                "ArticleDocument sourceMeetingId does not match saved Materials"
            )
        WorkspaceController._validate_media_snapshot(document, expected_media)

    @staticmethod
    def _validate_media_snapshot(
        document: Mapping[str, Any],
        expected_media: Mapping[str, tuple[Any, Any]],
        *,
        allow_removal: bool = False,
    ) -> None:
        media = document.get("media")
        if not isinstance(media, list):
            raise InvalidRequest("ArticleDocument media must be a list")
        actual_media: dict[str, tuple[Any, Any]] = {}
        for index, item in enumerate(media):
            if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
                raise InvalidRequest(
                    f"ArticleDocument media.{index} must have a string id"
                )
            actual_media[item["id"]] = (item.get("kind"), item.get("include"))
        media_matches = (
            all(
                expected_media.get(media_id) == state
                for media_id, state in actual_media.items()
            )
            if allow_removal
            else actual_media == expected_media
        )
        if not media_matches:
            raise InvalidRequest(
                "ArticleDocument media does not match its saved source snapshot"
            )

    def _recover_pending_draft(
        self,
        workspace: Path,
        manifest: SourceManifest,
    ) -> None:
        draft_dir = workspace / "draft"
        pending_path = draft_dir / ".article-save-pending.json"
        if not pending_path.exists() and not pending_path.is_symlink():
            return

        pending = self._read_json_file(
            pending_path,
            label="pending draft recovery record",
        )
        if set(pending) != {"previousDocument"}:
            raise InvalidWorkspace(
                "pending draft recovery record has unexpected fields"
            )
        previous = pending["previousDocument"]
        if previous is not None and not isinstance(previous, dict):
            raise InvalidWorkspace(
                "pending draft recovery record has an invalid previousDocument"
            )

        draft_path = draft_dir / "article.json"
        if manifest.draft is None:
            if draft_path.exists() or draft_path.is_symlink():
                self._remove_regular_file(draft_path)
            self._remove_regular_file(pending_path, tolerate_failure=True)
            return

        if draft_path.exists() and not draft_path.is_symlink():
            current = self._read_json_file(draft_path, label="draft")
            if self._document_sha256(current) == manifest.draft.sha256:
                self._remove_regular_file(pending_path, tolerate_failure=True)
                return

        if (
            not isinstance(previous, dict)
            or self._document_sha256(previous) != manifest.draft.sha256
        ):
            raise InvalidWorkspace(
                "pending draft recovery record cannot restore the manifest draft"
            )
        self._atomic_write_json(draft_path, previous)
        self._remove_regular_file(pending_path, tolerate_failure=True)

    @staticmethod
    def _document_sha256(document: Mapping[str, Any]) -> str:
        canonical = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _validation_message(error: ValidationError) -> str:
        first = error.errors(include_url=False)[0]
        location = ".".join(str(part) for part in first["loc"]) or "root"
        return f"{location}: {first['msg']}"

    @staticmethod
    def _ensure_child_directory(
        workspace: Path,
        directory: Path,
        *,
        label: str = "draft",
    ) -> None:
        if directory.exists():
            if directory.is_symlink() or not directory.is_dir():
                raise InvalidWorkspace(f"{label} path must be a regular directory")
        else:
            directory.mkdir(mode=0o700)
        if directory.resolve().parent != workspace:
            raise InvalidWorkspace(f"{label} directory escapes the workspace")

    @staticmethod
    def _remove_regular_file(
        path: Path,
        *,
        tolerate_failure: bool = False,
    ) -> None:
        if path.is_symlink() or (path.exists() and not path.is_file()):
            if tolerate_failure:
                return
            raise InvalidWorkspace(f"refusing to remove non-file path: {path.name}")
        try:
            path.unlink(missing_ok=True)
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            if not tolerate_failure:
                raise InvalidWorkspace(f"cannot remove {path.name}: {exc}") from exc

    @staticmethod
    def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
        payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        WorkspaceController._atomic_write(path, payload.encode("utf-8"))

    @staticmethod
    def _atomic_write_bytes(path: Path, value: bytes) -> None:
        WorkspaceController._atomic_write(path, value)

    @staticmethod
    def _atomic_write(path: Path, value: bytes) -> None:
        if path.exists() and (path.is_symlink() or not path.is_file()):
            raise InvalidWorkspace(f"refusing to replace non-file path: {path.name}")
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(value)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise InvalidWorkspace(f"cannot write {path.name}: {exc}") from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
