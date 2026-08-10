import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from scripts import backfill_wxpost_wechat_variants as backfill


def test_script_is_directly_runnable_from_backend_root() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, str(backend_root / "scripts/backfill_wxpost_wechat_variants.py"), "--help"],
        cwd=backend_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--all-ready" in result.stdout


def test_all_ready_paginates_until_the_last_partial_page(monkeypatch) -> None:
    identifiers = [
        UUID("00000000-0000-4000-8000-000000000001"),
        UUID("00000000-0000-4000-8000-000000000002"),
        UUID("00000000-0000-4000-8000-000000000003"),
    ]
    ranges: list[tuple[int, int]] = []
    orders: list[str] = []

    class Query:
        def select(self, *args):
            return self

        def eq(self, *args):
            return self

        @property
        def not_(self):
            return self

        def is_(self, *args):
            return self

        def order(self, field):
            orders.append(field)
            return self

        def range(self, start, end):
            ranges.append((start, end))
            self.start = start
            self.end = end
            return self

        def execute(self):
            page = identifiers[self.start : self.end + 1]
            return SimpleNamespace(data=[{"id": str(identifier)} for identifier in page])

    class Supabase:
        def table(self, name):
            assert name == "wxposts"
            return Query()

    monkeypatch.setattr(backfill, "supabase", Supabase())

    assert backfill._ready_wxpost_ids(batch_size=2) == identifiers
    assert ranges == [(0, 1), (2, 3)]
    assert orders == ["created_at", "id", "created_at", "id"]
