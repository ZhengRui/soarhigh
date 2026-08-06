from types import SimpleNamespace

import pytest

from app.db import wxpost_wechat


class FakeQuery:
    def __init__(self, data: list[dict]) -> None:
        self.data = data
        self.values: dict = {}
        self.filters: list[tuple[str, str, object]] = []

    def update(self, values: dict):
        self.values = values
        return self

    def eq(self, column: str, value: object):
        self.filters.append(("eq", column, value))
        return self

    def is_(self, column: str, value: object):
        self.filters.append(("is", column, value))
        return self

    def execute(self):
        return SimpleNamespace(data=self.data)


class FakeSupabase:
    def __init__(self, query: FakeQuery) -> None:
        self.query = query

    def table(self, name: str) -> FakeQuery:
        assert name == "wxpost_wechat_drafts"
        return self.query


def test_reset_uncertain_projection_is_scoped_and_preserves_asset_mappings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = FakeQuery([{"source_workspace_id": "wxpost-test", "state": "idle"}])
    monkeypatch.setattr(wxpost_wechat, "supabase", FakeSupabase(query))

    result = wxpost_wechat.reset_uncertain_projection("wxpost-test")

    assert result["state"] == "idle"
    assert ("eq", "source_workspace_id", "wxpost-test") in query.filters
    assert ("eq", "state", "uncertain") in query.filters
    assert ("is", "wechat_media_id", "null") in query.filters
    assert query.values["state"] == "idle"
    assert query.values["operation_id"] is None
    assert "asset_mappings" not in query.values


def test_reset_uncertain_projection_rejects_a_changed_or_linked_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = FakeQuery([])
    monkeypatch.setattr(wxpost_wechat, "supabase", FakeSupabase(query))

    with pytest.raises(RuntimeError, match="could not be reset"):
        wxpost_wechat.reset_uncertain_projection("wxpost-test")
