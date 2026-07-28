from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ValidationError

from .contracts import (
    DraftEnvelope,
    SaveDraftRequest,
    SourceManifest,
    SourceUpdate,
    UpdateSourcesRequest,
)

WORKSPACE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
ArticleValidator = Callable[[Mapping[str, Any]], Mapping[str, Any]]
RequestModel = TypeVar("RequestModel", bound=BaseModel)


class WorkspaceError(Exception):
    """Base error for a rejected workspace operation."""

    code = "workspace_error"

    def error_details(self) -> dict[str, Any]:
        return {}


class WorkspaceNotFound(WorkspaceError):
    """The opaque workspace identifier does not resolve to a workspace."""

    code = "workspace_not_found"


class InvalidWorkspace(WorkspaceError):
    """Stored workspace state does not satisfy the production contract."""

    code = "invalid_workspace"


class InvalidRequest(WorkspaceError):
    """A caller request does not satisfy the production operation contract."""

    code = "invalid_request"


class ValidationUnavailable(WorkspaceError):
    """The authoritative SoarHigh ArticleDocument validator is unavailable."""

    code = "validation_unavailable"


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
    """Validated, versioned, atomic access to WXPost authoring workspaces."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        article_validator: ArticleValidator | None = None,
        soarhigh_api_base_url: str | None = None,
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

    def get_context(self, workspace_id: str) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        with self._workspace_lock(workspace):
            manifest = self._read_manifest(workspace, workspace_id)
            draft = self._read_draft(workspace, manifest)
        return {
            "workspaceId": workspace_id,
            "manifest": manifest.to_wire(),
            "draft": draft.to_wire() if draft is not None else None,
        }

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
                manifest_data["manifestVersion"] = actual_version + 1
                manifest = self._validate_manifest_data(
                    manifest_data,
                    label="updated source manifest",
                    request_error=True,
                )
                self._atomic_write_json(
                    workspace / "source-manifest.json",
                    manifest.to_wire(),
                )

        return manifest.to_wire()

    def save_draft(
        self,
        workspace_id: str,
        *,
        expected_manifest_version: int,
        expected_draft_version: int,
        document: Mapping[str, Any],
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        request = self._validate_request(
            SaveDraftRequest,
            {
                "expectedManifestVersion": expected_manifest_version,
                "expectedDraftVersion": expected_draft_version,
                "document": document,
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

            self._validate_draft_against_manifest(validated_document, manifest)
            next_version = actual_version + 1
            manifest_data = manifest.to_wire()
            manifest_data["draft"] = {
                "version": next_version,
                "sourceManifestVersion": actual_manifest_version,
                "sha256": document_hash,
            }
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

    def _resolve_workspace(self, workspace_id: str) -> Path:
        if not isinstance(workspace_id, str) or not WORKSPACE_ID_PATTERN.fullmatch(
            workspace_id
        ):
            raise InvalidRequest("workspaceId must be a lowercase slug")

        candidate = self.inbox_root / workspace_id
        if not candidate.exists() or not candidate.is_dir():
            raise WorkspaceNotFound(f"workspace does not exist: {workspace_id}")
        if candidate.is_symlink():
            raise InvalidWorkspace("workspace must not be a symlink")

        resolved = candidate.resolve()
        if resolved.parent != self._resolved_inbox or resolved != candidate.absolute():
            raise InvalidWorkspace("workspace escapes the configured inbox")
        return resolved

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
                f"{label} does not satisfy source-manifest v2: "
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
    def _validate_draft_against_manifest(
        document: Mapping[str, Any],
        manifest: SourceManifest,
    ) -> None:
        expected_article_type = manifest.editorial.article_type.value
        if document.get("articleType") != expected_article_type:
            raise InvalidRequest(
                "ArticleDocument articleType does not match the source manifest"
            )
        if document.get("customArticleType") != manifest.editorial.custom_article_type:
            raise InvalidRequest(
                "ArticleDocument customArticleType does not match the source manifest"
            )

        if document.get("sourceMeetingId") != manifest.meeting_id:
            raise InvalidRequest(
                "ArticleDocument sourceMeetingId does not match the source manifest"
            )

        sources_by_id = {
            source.id: (index, source) for index, source in enumerate(manifest.sources)
        }
        media = document.get("media")
        if not isinstance(media, list):
            raise InvalidRequest("ArticleDocument media must be a list")
        media_ids: set[str] = set()
        for index, item in enumerate(media):
            if not isinstance(item, Mapping):
                raise InvalidRequest(f"ArticleDocument media.{index} must be an object")
            source_id = item.get("id")
            if not isinstance(source_id, str):
                raise InvalidRequest(
                    f"ArticleDocument media.{index}.id must be a string"
                )
            source_entry = sources_by_id.get(source_id)
            if source_entry is None:
                raise InvalidRequest(
                    f"ArticleDocument media.{index}.id is not in the source manifest: "
                    f"{source_id}"
                )
            source_index, source = source_entry
            media_ids.add(source_id)
            if item.get("kind") != source.kind.value:
                raise InvalidRequest(
                    f"ArticleDocument media.{index}.kind does not match source "
                    f"{source_id}"
                )
            snapshot_fields = {
                "include": source.included,
                "order": source_index,
                "descriptionSource": (
                    source.description_source.value
                    if source.description_source is not None
                    else None
                ),
                "descriptionStatus": source.description_status.value,
            }
            mismatches = [
                field
                for field, expected in snapshot_fields.items()
                if item.get(field) != expected
            ]
            if mismatches:
                raise InvalidRequest(
                    f"ArticleDocument media.{index} does not match source "
                    f"{source_id}: {', '.join(mismatches)}"
                )

        missing_included_media = [
            source.id
            for source in manifest.sources
            if source.included
            and source.kind.value in {"image", "video"}
            and source.id not in media_ids
        ]
        if missing_included_media:
            raise InvalidRequest(
                "ArticleDocument media is missing included manifest sources: "
                + ", ".join(missing_included_media)
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
    def _ensure_child_directory(workspace: Path, directory: Path) -> None:
        if directory.exists():
            if directory.is_symlink() or not directory.is_dir():
                raise InvalidWorkspace("draft path must be a regular directory")
        else:
            directory.mkdir(mode=0o700)
        if directory.resolve().parent != workspace:
            raise InvalidWorkspace("draft directory escapes the workspace")

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
        if path.exists() and (path.is_symlink() or not path.is_file()):
            raise InvalidWorkspace(f"refusing to replace non-file path: {path.name}")
        payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(payload)
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
