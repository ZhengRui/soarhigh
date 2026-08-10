#!/usr/bin/env python3
"""Backfill deterministic WeChat image renditions for ready Public Revisions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.supabase import supabase
from app.services.wxpost_publication import reconcile_publication_wechat_variants


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--wxpost-id", type=UUID)
    target.add_argument("--all-ready", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=25)
    return parser.parse_args()


def _ready_wxpost_ids(*, batch_size: int) -> list[UUID]:
    identifiers: list[UUID] = []
    start = 0
    while True:
        response = (
            supabase.table("wxposts")
            .select("id")
            .eq("status", "ready")
            .eq("is_public", True)
            .not_.is_("source_workspace_id", "null")
            .order("created_at")
            .order("id")
            .range(start, start + batch_size - 1)
            .execute()
        )
        page = response.data or []
        identifiers.extend(UUID(row["id"]) for row in page)
        if len(page) < batch_size:
            return identifiers
        start += batch_size


def main() -> None:
    args = _arguments()
    if not 1 <= args.batch_size <= 100:
        raise SystemExit("--batch-size must be between 1 and 100")
    if args.wxpost_id is not None:
        identifiers = [args.wxpost_id]
    else:
        identifiers = _ready_wxpost_ids(batch_size=args.batch_size)
    reports = [reconcile_publication_wechat_variants(identifier, dry_run=args.dry_run) for identifier in identifiers]
    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
