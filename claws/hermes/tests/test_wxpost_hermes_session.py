from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from wxpost_controller.core import InvalidRequest, VersionConflict
from wxpost_controller.hermes_session import (
    HermesDescriptionService,
    HermesDraftService,
    HermesSessionClient,
    HermesSessionHistory,
    HermesTurn,
    HermesTurnFailed,
)


class _Controller:
    def __init__(self, root: Path) -> None:
        self.inbox_root = root / "inbox"
        self.source_revision = "source-revision-1"
        self.context: dict[str, Any] = {
            "workspaceId": "wxpost-test",
            "manifest": {"manifestVersion": 4},
            "draft": {"draftVersion": 2},
        }

    def get_context(self, workspace_id: str) -> dict[str, Any]:
        assert workspace_id == "wxpost-test"
        return self.context

    def get_source_description_context(
        self,
        workspace_id: str,
        *,
        expected_manifest_version: int,
        source_id: str,
    ) -> dict[str, Any]:
        assert workspace_id == "wxpost-test"
        actual_version = self.context["manifest"]["manifestVersion"]
        if expected_manifest_version != actual_version:
            raise VersionConflict(
                resource="manifest",
                expected=expected_manifest_version,
                actual=actual_version,
            )
        return {
            "workspaceId": workspace_id,
            "manifestVersion": actual_version,
            "source": {
                "id": source_id,
                "filename": "meeting-room.jpg",
                "mimeType": "image/jpeg",
                "path": f"sources/{source_id}.jpg",
            },
            "sourceRevision": self.source_revision,
            "meetingContext": {
                "theme": "Culture in Every Voice",
                "introduction": "A meeting about belonging.",
                "agenda": [{"title": "Table Topics"}],
                "internalNote": "This must not enter the image prompt.",
            },
        }

    def assert_source_description_target(
        self,
        workspace_id: str,
        *,
        expected_manifest_version: int,
        source_id: str,
        expected_source_revision: str,
    ) -> None:
        assert workspace_id == "wxpost-test"
        assert source_id == "M01"
        if expected_source_revision != self.source_revision:
            raise VersionConflict(
                resource="manifest",
                expected=expected_manifest_version,
                actual=self.context["manifest"]["manifestVersion"],
            )


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


def test_description_service_polishes_any_language_into_local_english_suggestion(
    tmp_path: Path,
) -> None:
    controller = _Controller(tmp_path)
    session = _SessionClient(controller)
    session.turn = (
        lambda **kwargs: (  # type: ignore[method-assign]
            session.prompts.append(kwargs)
            or HermesTurn(
                session_id="description-session",
                reply=(
                    '{"description":"Members exchange ideas around a table '
                    'before the meeting begins."}'
                ),
            )
        )
    )
    service = HermesDescriptionService(
        controller=controller,  # type: ignore[arg-type]
        session_client=session,  # type: ignore[arg-type]
    )

    result = service.suggest(
        "wxpost-test",
        expected_manifest_version=4,
        source_id="M01",
        current_description="会员们在会议开始前围坐交流。",
    )

    assert result == {
        "workspaceId": "wxpost-test",
        "sourceId": "M01",
        "description": (
            "Members exchange ideas around a table before the meeting begins."
        ),
    }
    prompt = session.prompts[0]["prompt"]
    assert "sources/M01.jpg" in prompt
    assert "translating, compressing, and polishing" in prompt
    assert "editorial caption" in prompt
    assert "not an inventory of objects" in prompt
    assert "visible mood" in prompt
    assert "Culture in Every Voice" in prompt
    assert "internalNote" not in prompt
    assert "会员们在会议开始前围坐交流。" in prompt
    assert "Do not save or update the workspace" in prompt


def test_description_service_uses_image_first_generation_for_empty_text(
    tmp_path: Path,
) -> None:
    controller = _Controller(tmp_path)
    session = _SessionClient(controller)
    session.turn = lambda **kwargs: (  # type: ignore[method-assign]
        session.prompts.append(kwargs)
        or HermesTurn(
            session_id="description-session",
            reply='{"description":"A speaker addresses seated members."}',
        )
    )
    service = HermesDescriptionService(
        controller=controller,  # type: ignore[arg-type]
        session_client=session,  # type: ignore[arg-type]
    )

    service.suggest(
        "wxpost-test",
        expected_manifest_version=4,
        source_id="M01",
        current_description="",
    )

    prompt = session.prompts[0]["prompt"]
    assert "No current description was provided" in prompt
    assert "Create the caption from the image and supporting context" in prompt


@pytest.mark.parametrize(
    "reply",
    [
        "A plain sentence without the response contract.",
        '{"description":""}',
        '{"description":"Useful","extra":true}',
    ],
)
def test_description_service_rejects_non_contract_replies(
    tmp_path: Path,
    reply: str,
) -> None:
    controller = _Controller(tmp_path)
    session = _SessionClient(controller)
    session.turn = lambda **kwargs: HermesTurn(  # type: ignore[method-assign]
        session_id="description-session",
        reply=reply,
    )
    service = HermesDescriptionService(
        controller=controller,  # type: ignore[arg-type]
        session_client=session,  # type: ignore[arg-type]
    )

    with pytest.raises(HermesTurnFailed, match="invalid image description"):
        service.suggest(
            "wxpost-test",
            expected_manifest_version=4,
            source_id="M01",
            current_description="",
        )


def test_description_service_keeps_a_snapshot_suggestion_when_manifest_changes(
    tmp_path: Path,
) -> None:
    controller = _Controller(tmp_path)
    session = _SessionClient(controller)

    def changed_turn(**kwargs: str) -> HermesTurn:
        controller.context["manifest"]["manifestVersion"] = 5
        return HermesTurn(
            session_id="description-session",
            reply='{"description":"A meeting room."}',
        )

    session.turn = changed_turn  # type: ignore[method-assign]
    service = HermesDescriptionService(
        controller=controller,  # type: ignore[arg-type]
        session_client=session,  # type: ignore[arg-type]
    )

    suggestion = service.suggest(
        "wxpost-test",
        expected_manifest_version=4,
        source_id="M01",
        current_description="",
    )

    assert suggestion["description"] == "A meeting room."


def test_description_service_rejects_a_suggestion_when_its_source_changes(
    tmp_path: Path,
) -> None:
    controller = _Controller(tmp_path)
    session = _SessionClient(controller)

    def changed_turn(**kwargs: str) -> HermesTurn:
        controller.context["manifest"]["manifestVersion"] = 5
        controller.source_revision = "source-revision-2"
        return HermesTurn(
            session_id="description-session",
            reply='{"description":"A meeting room."}',
        )

    session.turn = changed_turn  # type: ignore[method-assign]
    service = HermesDescriptionService(
        controller=controller,  # type: ignore[arg-type]
        session_client=session,  # type: ignore[arg-type]
    )

    with pytest.raises(VersionConflict, match="current manifest version is 5"):
        service.suggest(
            "wxpost-test",
            expected_manifest_version=4,
            source_id="M01",
            current_description="",
        )


def test_description_service_serializes_only_turns_for_the_same_source(
    tmp_path: Path,
) -> None:
    controller = _Controller(tmp_path)
    session = _SessionClient(controller)
    service = HermesDescriptionService(
        controller=controller,  # type: ignore[arg-type]
        session_client=session,  # type: ignore[arg-type]
    )

    assert service._turn_lock("workspace-a", "M01") is service._turn_lock(
        "workspace-a", "M01"
    )
    assert service._turn_lock("workspace-a", "M01") is not service._turn_lock(
        "workspace-a", "M02"
    )
    assert service._turn_lock("workspace-a", "M01") is not service._turn_lock(
        "workspace-b", "M01"
    )
