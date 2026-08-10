"""One-time, offline source-manifest v4 to v5 migration."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from .contracts import SourceKind, SourceManifest
from .source_metadata import inspect_source_bytes


class MigrationError(RuntimeError):
    """A manifest cannot be migrated without changing its meaning."""


@dataclass(frozen=True)
class PreparedManifest:
    path: Path
    original: bytes
    migrated: bytes | None


def _source_path(workspace: Path, source: dict[str, Any]) -> Path:
    filename = source.get("filename")
    source_id = source.get("id")
    if not isinstance(filename, str) or not isinstance(source_id, str):
        raise MigrationError(f"{workspace.name}: source identity is invalid")
    path = workspace / "sources" / f"{source_id}{Path(filename).suffix}"
    try:
        path.resolve(strict=False).relative_to(workspace.resolve())
    except ValueError as error:
        raise MigrationError(
            f"{workspace.name}: source path escapes workspace"
        ) from error
    return path


def prepare_manifest(path: Path) -> PreparedManifest:
    original = path.read_bytes()
    try:
        payload = json.loads(original)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MigrationError(f"{path}: invalid JSON") from error
    if not isinstance(payload, dict):
        raise MigrationError(f"{path}: manifest must be an object")
    schema_version = payload.get("schemaVersion")
    if schema_version == 5:
        try:
            SourceManifest.model_validate(payload)
        except ValueError as error:
            raise MigrationError(f"{path}: invalid v5 manifest") from error
        return PreparedManifest(path=path, original=original, migrated=None)
    if schema_version != 4:
        raise MigrationError(f"{path}: expected schemaVersion 4 or 5")

    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise MigrationError(f"{path}: sources must be a list")
    workspace = path.parent
    for source in sources:
        if not isinstance(source, dict):
            raise MigrationError(f"{path}: source must be an object")
        if source.get("workspaceReady") is not True:
            source["contentSha256"] = None
            source["dimensions"] = None
            continue
        source_path = _source_path(workspace, source)
        if source_path.is_symlink() or not source_path.is_file():
            raise MigrationError(f"{path}: source file is unavailable")
        try:
            data = source_path.read_bytes()
            kind = SourceKind(source.get("kind"))
            metadata = inspect_source_bytes(data, kind=kind)
        except (OSError, ValueError) as error:
            raise MigrationError(
                f"{path}: cannot inspect {source_path.name}"
            ) from error
        if source.get("sizeBytes") != len(data):
            raise MigrationError(f"{path}: size mismatch for {source_path.name}")
        source.update(metadata.to_wire())

    payload["schemaVersion"] = 5
    try:
        manifest = SourceManifest.model_validate(payload)
    except ValueError as error:
        raise MigrationError(f"{path}: migrated manifest is invalid") from error
    migrated = (
        json.dumps(manifest.to_wire(), ensure_ascii=False, indent=2) + "\n"
    ).encode()
    return PreparedManifest(path=path, original=original, migrated=migrated)


def prepare_all(workspace_root: Path) -> list[PreparedManifest]:
    paths = sorted((workspace_root / "inbox").glob("*/source-manifest.json"))
    return [prepare_manifest(path) for path in paths]


def _atomic_write(path: Path, data: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def apply_all(
    workspace_root: Path,
    prepared: Sequence[PreparedManifest],
    backup_root: Path,
) -> int:
    changed = [item for item in prepared if item.migrated is not None]
    for item in changed:
        relative = item.path.relative_to(workspace_root)
        backup = backup_root / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item.path, backup)
    for item in changed:
        assert item.migrated is not None
        _atomic_write(item.path, item.migrated)
    return len(changed)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-root", type=Path)
    args = parser.parse_args(argv)

    prepared = prepare_all(args.workspace_root)
    changed = sum(item.migrated is not None for item in prepared)
    if args.apply:
        backup_root = args.backup_root or (
            args.workspace_root
            / ".wxpost-manifest-backups"
            / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        )
        changed = apply_all(args.workspace_root, prepared, backup_root)
        print(f"Migrated {changed} manifest(s); backups: {backup_root}")
    else:
        print(f"Validated {len(prepared)} manifest(s); {changed} require migration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
