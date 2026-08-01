from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from wxpost_controller.core import InvalidRequest, VersionConflict
from wxpost_controller.hermes_session import (
    HermesDraftService,
    HermesSessionClient,
    HermesSessionHistory,
    HermesTurn,
    HermesTurnFailed,
)


class _Controller:
    def __init__(self, root: Path) -> None:
        self.inbox_root = root / "inbox"
        self.context: dict[str, Any] = {
            "workspaceId": "wxpost-test",
            "manifest": {"manifestVersion": 4},
            "draft": {"draftVersion": 2},
        }

    def get_context(self, workspace_id: str) -> dict[str, Any]:
        assert workspace_id == "wxpost-test"
        return self.context


class _SessionClient:
    def __init__(self, controller: _Controller) -> None:
        self.controller = controller
        self.prompts: list[dict[str, str]] = []

    def history(self, *, title: str) -> HermesSessionHistory:
        assert title == "SoarHigh WxPost authoring v3 · wxpost-test"
        return HermesSessionHistory(
            session_id="stored-session",
            messages=[
                {"role": "user", "text": "Tighten the opening."},
                {"role": "assistant", "text": "Opening tightened."},
            ],
        )

    def turn(self, *, title: str, cwd: str, prompt: str) -> HermesTurn:
        self.prompts.append({"title": title, "cwd": cwd, "prompt": prompt})
        operation_id = prompt.split('operation_id="', 1)[1].split('"', 1)[0]
        draft = self.controller.context["draft"]
        draft["draftVersion"] += 1
        self.controller.context["manifest"]["draft"] = {
            "version": draft["draftVersion"],
            "operationId": operation_id,
        }
        return HermesTurn(
            session_id="stored-session",
            reply="Draft regenerated.",
        )


def _service(tmp_path: Path) -> tuple[HermesDraftService, _SessionClient]:
    controller = _Controller(tmp_path)
    session = _SessionClient(controller)
    return (
        HermesDraftService(
            controller=controller,  # type: ignore[arg-type]
            session_client=session,  # type: ignore[arg-type]
        ),
        session,
    )


def test_draft_service_resumes_history_and_runs_one_versioned_turn(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    history = service.history("wxpost-test")
    result = service.generate(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
    )

    assert history == {
        "workspaceId": "wxpost-test",
        "sessionId": "stored-session",
        "messages": [
            {"role": "user", "text": "Tighten the opening."},
            {"role": "assistant", "text": "Opening tightened."},
        ],
    }
    assert result["context"]["draft"]["draftVersion"] == 3
    assert result["reply"] == "Draft regenerated."
    assert len(session.prompts) == 1
    assert session.prompts[0]["title"] == "SoarHigh WxPost authoring v3 · wxpost-test"
    assert session.prompts[0]["cwd"].endswith("/inbox/wxpost-test")
    assert "Expected manifest version: 4" in session.prompts[0]["prompt"]
    assert "Expected draft version: 2" in session.prompts[0]["prompt"]
    assert 'workspace_id="wxpost-test"' in session.prompts[0]["prompt"]
    assert "expected_manifest_version=4" in session.prompts[0]["prompt"]
    assert "expected_draft_version=2" in session.prompts[0]["prompt"]
    assert 'operation_id="draft-' in session.prompts[0]["prompt"]
    assert "refresh_from_materials=true" in session.prompts[0]["prompt"]
    assert "Re-read and follow the current" in session.prompts[0]["prompt"]
    assert (
        "rather than preserving the prior Draft's structure"
        in (session.prompts[0]["prompt"])
    )
    assert (
        "make one replacement save call with the same versions"
        in (session.prompts[0]["prompt"])
    )


def test_draft_service_rejects_stale_versions_before_calling_hermes(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    with pytest.raises(VersionConflict, match="expected manifest version 3"):
        service.revise(
            "wxpost-test",
            expected_manifest_version=3,
            expected_draft_version=2,
            message="Tighten the opening.",
            selected_text=None,
        )

    assert session.prompts == []


def test_focused_revision_keeps_the_saved_draft_source_snapshot(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    service.revise(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="Tighten the opening.",
        selected_text=None,
    )

    assert "refresh_from_materials=false" in session.prompts[0]["prompt"]


def test_draft_service_rejects_invalid_revision_inputs_before_hermes(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    with pytest.raises(InvalidRequest, match="must be text"):
        service.revise(
            "wxpost-test",
            expected_manifest_version=4,
            expected_draft_version=2,
            message=None,  # type: ignore[arg-type]
            selected_text=None,
        )

    assert session.prompts == []


def test_draft_service_does_not_adopt_an_unrelated_save(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    def unrelated_turn(*, title: str, cwd: str, prompt: str) -> HermesTurn:
        session.prompts.append({"title": title, "cwd": cwd, "prompt": prompt})
        session.controller.context["draft"]["draftVersion"] = 3
        session.controller.context["manifest"]["draft"] = {"version": 3}
        return HermesTurn(session_id="stored-session", reply="Draft regenerated.")

    session.turn = unrelated_turn  # type: ignore[method-assign]

    with pytest.raises(VersionConflict, match="expected draft version 2"):
        service.generate(
            "wxpost-test",
            expected_manifest_version=4,
            expected_draft_version=2,
        )


def test_draft_service_reports_a_manifest_change_during_the_turn_as_a_conflict(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    def changed_materials_turn(*, title: str, cwd: str, prompt: str) -> HermesTurn:
        session.prompts.append({"title": title, "cwd": cwd, "prompt": prompt})
        session.controller.context["manifest"]["manifestVersion"] = 5
        return HermesTurn(session_id="stored-session", reply="Materials changed.")

    session.turn = changed_materials_turn  # type: ignore[method-assign]

    with pytest.raises(VersionConflict, match="expected manifest version 4"):
        service.generate(
            "wxpost-test",
            expected_manifest_version=4,
            expected_draft_version=2,
        )


def test_draft_service_keeps_a_no_save_turn_as_a_hermes_failure(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    def no_save_turn(*, title: str, cwd: str, prompt: str) -> HermesTurn:
        session.prompts.append({"title": title, "cwd": cwd, "prompt": prompt})
        return HermesTurn(session_id="stored-session", reply="Unable to save.")

    session.turn = no_save_turn  # type: ignore[method-assign]

    with pytest.raises(HermesTurnFailed, match="Unable to save"):
        service.generate(
            "wxpost-test",
            expected_manifest_version=4,
            expected_draft_version=2,
        )


def test_draft_service_serializes_only_turns_for_the_same_workspace(
    tmp_path: Path,
) -> None:
    service, _ = _service(tmp_path)

    assert service._turn_lock("workspace-a") is service._turn_lock("workspace-a")
    assert service._turn_lock("workspace-a") is not service._turn_lock("workspace-b")


def test_visible_history_accepts_serve_text_messages_and_hides_tools() -> None:
    assert HermesSessionClient._visible_messages(
        [
            {
                "role": "user",
                "text": 'hidden prompt\nMEMBER_REQUEST_JSON:"Tighten it."',
            },
            {"role": "tool", "name": "wxpost_get_context"},
            {"role": "assistant", "text": "Draft tightened."},
        ]
    ) == [
        {"role": "user", "text": "Tighten it."},
        {"role": "assistant", "text": "Draft tightened."},
    ]
