from __future__ import annotations

import copy
import fcntl
import json
import os
import re
import tempfile
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

WORKSPACE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SOURCE_FIELDS = frozenset({"description", "included", "order"})
SOURCE_KINDS = frozenset({"image", "video", "transcript", "note"})


class WorkspaceError(Exception):
    """Base error for a rejected workspace operation."""


class WorkspaceNotFound(WorkspaceError):
    """The opaque workspace identifier does not resolve to a workspace."""


class InvalidWorkspace(WorkspaceError):
    """The workspace or requested document does not satisfy the contract."""


class VersionConflict(WorkspaceError):
    """The caller attempted to update a stale workspace version."""

    def __init__(self, *, expected: int, actual: int) -> None:
        super().__init__(f"expected version {expected}, current version is {actual}")
        self.expected = expected
        self.actual = actual


class WorkspaceController:
    """Validated, versioned, atomic access to WXPost authoring workspaces."""

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.inbox_root = self.workspace_root / "inbox"
        self.inbox_root.mkdir(parents=True, exist_ok=True)
        if self.inbox_root.is_symlink():
            raise InvalidWorkspace("workspace inbox must not be a symlink")
        self._resolved_inbox = self.inbox_root.resolve()

    def get_context(self, workspace_id: str) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        with self._workspace_lock(workspace, shared=True):
            manifest = self._read_manifest(workspace, workspace_id)
            draft = self._read_draft(workspace)
        return {"workspaceId": workspace_id, "manifest": manifest, "draft": draft}

    def update_sources(
        self,
        workspace_id: str,
        *,
        expected_version: int,
        updates: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        expected_version = self._validate_expected_version(expected_version)
        normalized_updates = self._validate_updates(updates)
        with self._workspace_lock(workspace):
            manifest = self._read_manifest(workspace, workspace_id)
            actual_version = manifest["version"]
            if expected_version != actual_version:
                raise VersionConflict(expected=expected_version, actual=actual_version)

            changed = self._apply_source_updates(
                manifest["sources"], normalized_updates
            )
            if changed:
                manifest["version"] = actual_version + 1
                self._atomic_write_json(workspace / "source-manifest.json", manifest)

        return copy.deepcopy(manifest)

    def save_draft(
        self,
        workspace_id: str,
        *,
        expected_version: int,
        document: Mapping[str, Any],
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        expected_version = self._validate_expected_version(expected_version)
        validated_document = self._validate_draft_document(document)
        with self._workspace_lock(workspace):
            current = self._read_draft(workspace)
            actual_version = current["workspaceVersion"] if current else 0
            if expected_version != actual_version:
                raise VersionConflict(expected=expected_version, actual=actual_version)

            saved = copy.deepcopy(validated_document)
            saved["workspaceVersion"] = actual_version + 1
            draft_dir = workspace / "draft"
            self._ensure_child_directory(workspace, draft_dir)
            self._atomic_write_json(draft_dir / "article.json", saved)

        return copy.deepcopy(saved)

    def _resolve_workspace(self, workspace_id: str) -> Path:
        if not isinstance(workspace_id, str) or not WORKSPACE_ID_PATTERN.fullmatch(
            workspace_id
        ):
            raise InvalidWorkspace("workspaceId must be a lowercase slug")

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
    def _workspace_lock(self, workspace: Path, *, shared: bool = False):
        lock_path = workspace / ".source-manifest.lock"
        if lock_path.is_symlink():
            raise InvalidWorkspace("workspace lock must not be a symlink")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
            fcntl.flock(lock_file.fileno(), mode)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_manifest(self, workspace: Path, workspace_id: str) -> dict[str, Any]:
        path = workspace / "source-manifest.json"
        manifest = self._read_json_file(path, label="source manifest")
        if manifest.get("schemaVersion") != 1:
            raise InvalidWorkspace("source manifest schemaVersion must be 1")
        if manifest.get("workspaceId") != workspace_id:
            raise InvalidWorkspace("source manifest workspaceId does not match")
        version = manifest.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise InvalidWorkspace("source manifest version must be a positive integer")

        sources = manifest.get("sources")
        if not isinstance(sources, list):
            raise InvalidWorkspace("source manifest sources must be a list")
        self._validate_sources(sources)
        return manifest

    def _read_draft(self, workspace: Path) -> dict[str, Any] | None:
        path = workspace / "draft" / "article.json"
        if not path.exists():
            return None
        draft = self._read_json_file(path, label="draft")
        workspace_version = draft.get("workspaceVersion")
        if (
            not isinstance(workspace_version, int)
            or isinstance(workspace_version, bool)
            or workspace_version < 1
        ):
            raise InvalidWorkspace("draft workspaceVersion must be a positive integer")
        self._validate_draft_document(draft)
        return draft

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

    @staticmethod
    def _validate_sources(sources: list[Any]) -> None:
        source_ids: set[str] = set()
        for source in sources:
            if not isinstance(source, dict):
                raise InvalidWorkspace("each source must be an object")
            source_id = source.get("id")
            if not isinstance(source_id, str) or not source_id:
                raise InvalidWorkspace("each source must have a non-empty id")
            if source_id in source_ids:
                raise InvalidWorkspace(f"duplicate source id: {source_id}")
            source_ids.add(source_id)
            if source.get("kind") not in SOURCE_KINDS:
                raise InvalidWorkspace(f"unsupported source kind for {source_id}")
            if not isinstance(source.get("included"), bool):
                raise InvalidWorkspace(f"included must be boolean for {source_id}")
            description = source.get("description")
            if description is not None and not isinstance(description, str):
                raise InvalidWorkspace(
                    f"description must be text or null for {source_id}"
                )
            order = source.get("order")
            if not isinstance(order, int) or isinstance(order, bool) or order < 0:
                raise InvalidWorkspace(
                    f"order must be a non-negative integer for {source_id}"
                )

    @staticmethod
    def _validate_expected_version(expected_version: Any) -> int:
        if (
            not isinstance(expected_version, int)
            or isinstance(expected_version, bool)
            or expected_version < 0
        ):
            raise InvalidWorkspace("expectedVersion must be a non-negative integer")
        return expected_version

    @staticmethod
    def _validate_updates(
        updates: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        if not isinstance(updates, Iterable) or isinstance(
            updates, (str, bytes, Mapping)
        ):
            raise InvalidWorkspace("updates must be a list")
        normalized: list[dict[str, Any]] = []
        for raw_update in updates:
            if not isinstance(raw_update, Mapping):
                raise InvalidWorkspace("each source update must be an object")
            update = dict(raw_update)
            source_id = update.pop("sourceId", None)
            if not isinstance(source_id, str) or not source_id:
                raise InvalidWorkspace("each source update requires sourceId")
            unknown = set(update) - SOURCE_FIELDS
            if unknown:
                raise InvalidWorkspace(
                    f"unsupported source update fields: {', '.join(sorted(unknown))}"
                )
            if not update:
                raise InvalidWorkspace("source update must change at least one field")
            if "included" in update and not isinstance(update["included"], bool):
                raise InvalidWorkspace("included must be boolean")
            if "description" in update and not isinstance(update["description"], str):
                raise InvalidWorkspace("description must be text")
            if "order" in update and (
                not isinstance(update["order"], int)
                or isinstance(update["order"], bool)
                or update["order"] < 0
            ):
                raise InvalidWorkspace("order must be a non-negative integer")
            normalized.append({"sourceId": source_id, **update})
        if not normalized:
            raise InvalidWorkspace("updates must not be empty")
        return normalized

    @staticmethod
    def _apply_source_updates(
        sources: list[dict[str, Any]], updates: list[dict[str, Any]]
    ) -> bool:
        by_id = {source["id"]: source for source in sources}
        changed = False
        for update in updates:
            source_id = update["sourceId"]
            source = by_id.get(source_id)
            if source is None:
                raise InvalidWorkspace(f"unknown source id: {source_id}")
            for field in SOURCE_FIELDS:
                if field in update and source.get(field) != update[field]:
                    source[field] = update[field]
                    changed = True
        return changed

    @staticmethod
    def _validate_draft_document(document: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(document, Mapping):
            raise InvalidWorkspace("draft document must be an object")
        draft = copy.deepcopy(dict(document))
        if draft.get("schemaVersion") != 1:
            raise InvalidWorkspace("draft schemaVersion must be 1")
        for field in ("title", "articleType", "bodyMarkdown"):
            value = draft.get(field)
            if not isinstance(value, str) or not value.strip():
                raise InvalidWorkspace(f"draft {field} must be non-empty text")
        if "workspaceVersion" in draft:
            version = draft["workspaceVersion"]
            if not isinstance(version, int) or isinstance(version, bool) or version < 1:
                raise InvalidWorkspace(
                    "draft workspaceVersion must be a positive integer"
                )
        media = draft.get("media", [])
        if not isinstance(media, list):
            raise InvalidWorkspace("draft media must be a list")
        return draft

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
                temporary_path.unlink(missing_ok=True)
