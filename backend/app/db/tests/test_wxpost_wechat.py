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

    def in_(self, column: str, value: object):
        self.filters.append(("in", column, value))
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


def test_clear_confirmed_missing_projection_is_guarded_by_remote_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = FakeQuery([{"source_workspace_id": "wxpost-test", "state": "idle"}])
    monkeypatch.setattr(wxpost_wechat, "supabase", FakeSupabase(query))

    result = wxpost_wechat.clear_confirmed_missing_projection(
        "wxpost-test",
        media_id="missing-media-id",
        projection_sha256="a" * 64,
        asset_mappings={"body:digest": "https://mmbiz.qpic.cn/body.jpg"},
    )

    assert result == {"source_workspace_id": "wxpost-test", "state": "idle"}
    assert query.filters == [
        ("eq", "source_workspace_id", "wxpost-test"),
        ("in", "state", ["idle", "ready"]),
        ("eq", "wechat_media_id", "missing-media-id"),
        ("eq", "projection_sha256", "a" * 64),
    ]
    assert query.values["state"] == "idle"
    assert query.values["wechat_media_id"] is None
    assert query.values["asset_mappings"] == {"body:digest": "https://mmbiz.qpic.cn/body.jpg"}
