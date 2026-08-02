from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from wxpost_controller.core import InvalidRequest, VersionConflict
from wxpost_controller.hermes_session import (
    HERMES_DRAFT_IDENTITY,
    HERMES_DRAFT_PROTOCOL_VERSION,
    HermesDescriptionService,
    HermesDraftService,
    HermesDraftSessionRegistry,
    HermesSessionClient,
    HermesSessionHistory,
    HermesTurn,
    HermesTurnFailed,
)


class _Controller:
    def __init__(self, root: Path) -> None:
        self.workspace_root = root
        self.inbox_root = root / "inbox"
        self.source_revision = "source-revision-1"
        self.deleted_workspace_ids: list[str] = []
        self.context: dict[str, Any] = {
            "workspaceId": "wxpost-test",
            "manifest": {"manifestVersion": 4},
            "draft": {"draftVersion": 2},
        }

    def get_context(self, workspace_id: str) -> dict[str, Any]:
        assert workspace_id == "wxpost-test"
        return self.context

    def delete_workspace(
        self,
        workspace_id: str,
        *,
        expected_manifest_version: int,
    ) -> dict[str, Any]:
        assert workspace_id == "wxpost-test"
        assert expected_manifest_version == self.context["manifest"]["manifestVersion"]
        self.deleted_workspace_ids.append(workspace_id)
        return {"workspaceId": workspace_id, "deleted": True}

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
        self.history_session_ids: list[str | None] = []
        self.turn_session_ids: list[str | None] = []
        self.deleted_session_ids: list[str] = []

    def history(
        self,
        *,
        title: str,
        session_id: str | None = None,
    ) -> HermesSessionHistory:
        assert title == "SoarHigh WxPost authoring v6 · wxpost-test"
        self.history_session_ids.append(session_id)
        return HermesSessionHistory(
            session_id=session_id or "stored-session",
            messages=[
                {"role": "user", "text": "Tighten the opening."},
                {"role": "assistant", "text": "Opening tightened."},
            ],
        )

    def turn(
        self,
        *,
        title: str,
        cwd: str,
        prompt: str,
        session_id: str | None = None,
    ) -> HermesTurn:
        self.turn_session_ids.append(session_id)
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

    def delete(self, *, session_id: str) -> None:
        self.deleted_session_ids.append(session_id)
        self.prompts.append({"title": session_id, "cwd": "", "prompt": "DELETE"})


def _service(tmp_path: Path) -> tuple[HermesDraftService, _SessionClient]:
    controller = _Controller(tmp_path)
    session = _SessionClient(controller)
    return (
        HermesDraftService(
            controller=controller,  # type: ignore[arg-type]
            session_client=session,  # type: ignore[arg-type]
            cleanup_dispatch=lambda callback: callback(),
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
    assert result["reply"] == ("Draft regenerated.\n\nDraft version: v2 → v3")
    assert result["draftChanged"] is True
    assert len(session.prompts) == 1
    assert session.prompts[0]["title"] == "SoarHigh WxPost authoring v6 · wxpost-test"
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
    assert "Draft version: v2 → v3" in session.prompts[0]["prompt"]
    assert session.prompts[0]["prompt"].startswith(HERMES_DRAFT_IDENTITY)
    assert session.history_session_ids == [None]
    assert session.turn_session_ids == ["stored-session"]


def test_draft_session_registry_survives_service_recreation(tmp_path: Path) -> None:
    controller = _Controller(tmp_path)
    first_session = _SessionClient(controller)
    first_service = HermesDraftService(
        controller=controller,  # type: ignore[arg-type]
        session_client=first_session,  # type: ignore[arg-type]
        cleanup_dispatch=lambda callback: callback(),
    )

    first_service.history("wxpost-test")

    second_session = _SessionClient(controller)
    second_service = HermesDraftService(
        controller=controller,  # type: ignore[arg-type]
        session_client=second_session,  # type: ignore[arg-type]
        cleanup_dispatch=lambda callback: callback(),
    )
    second_service.history("wxpost-test")

    assert first_session.history_session_ids == [None]
    assert second_session.history_session_ids == ["stored-session"]


def test_draft_session_registry_retires_an_older_protocol_session(
    tmp_path: Path,
) -> None:
    registry_directory = tmp_path / ".wxpost-controller"
    registry_directory.mkdir()
    (registry_directory / "draft-sessions.json").write_text(
        json.dumps(
            {
                "version": 1,
                "draftProtocolVersion": 5,
                "sessions": {"wxpost-test": "protocol-5-session"},
                "pendingDeletions": [],
            }
        ),
        encoding="utf-8",
    )
    service, session = _service(tmp_path)

    history = service.history("wxpost-test")

    assert session.deleted_session_ids == ["protocol-5-session"]
    assert session.history_session_ids == [None]
    assert history["sessionId"] == "stored-session"
    registry = HermesDraftSessionRegistry(tmp_path)
    assert registry.get("wxpost-test") == "stored-session"
    assert registry.pending_deletions() == []


def test_history_schedules_session_cleanup_without_blocking_the_request(
    tmp_path: Path,
) -> None:
    registry_directory = tmp_path / ".wxpost-controller"
    registry_directory.mkdir()
    (registry_directory / "draft-sessions.json").write_text(
        json.dumps(
            {
                "version": 1,
                "draftProtocolVersion": HERMES_DRAFT_PROTOCOL_VERSION,
                "sessions": {},
                "pendingDeletions": ["stale-session"],
            }
        ),
        encoding="utf-8",
    )
    controller = _Controller(tmp_path)
    session = _SessionClient(controller)
    scheduled: list[Callable[[], None]] = []
    service = HermesDraftService(
        controller=controller,  # type: ignore[arg-type]
        session_client=session,  # type: ignore[arg-type]
        cleanup_dispatch=scheduled.append,
    )

    history = service.history("wxpost-test")

    assert history["sessionId"] == "stored-session"
    assert session.deleted_session_ids == []
    assert len(scheduled) == 1

    scheduled.pop()()

    assert session.deleted_session_ids == ["stale-session"]
    assert HermesDraftSessionRegistry(tmp_path).pending_deletions() == []


def test_cleanup_dispatch_failure_does_not_fail_history(tmp_path: Path) -> None:
    controller = _Controller(tmp_path)
    session = _SessionClient(controller)

    def unavailable_dispatch(_callback: Callable[[], None]) -> None:
        raise RuntimeError("cannot start cleanup worker")

    service = HermesDraftService(
        controller=controller,  # type: ignore[arg-type]
        session_client=session,  # type: ignore[arg-type]
        cleanup_dispatch=unavailable_dispatch,
    )

    history = service.history("wxpost-test")

    assert history["sessionId"] == "stored-session"


def test_reset_replaces_only_the_active_draft_conversation(tmp_path: Path) -> None:
    service, session = _service(tmp_path)
    before = json.loads(json.dumps(session.controller.context))

    service.history("wxpost-test")
    result = service.reset("wxpost-test")

    assert result == {
        "workspaceId": "wxpost-test",
        "sessionId": None,
        "messages": [],
    }
    assert session.deleted_session_ids == ["stored-session"]
    assert session.controller.context == before
    service.history("wxpost-test")
    assert "conversation-" in (session.history_session_ids[-1] or "")


def test_reset_keeps_fresh_pointer_when_old_session_cleanup_fails(
    tmp_path: Path,
) -> None:
    controller = _Controller(tmp_path)

    class CleanupFailureSession(_SessionClient):
        def delete(self, *, session_id: str) -> None:
            raise HermesTurnFailed("cleanup failed")

    session = CleanupFailureSession(controller)
    registry = HermesDraftSessionRegistry(tmp_path)
    service = HermesDraftService(
        controller=controller,  # type: ignore[arg-type]
        session_client=session,  # type: ignore[arg-type]
        session_registry=registry,
        cleanup_dispatch=lambda callback: callback(),
    )

    result = service.reset("wxpost-test")

    assert result["sessionId"] is None
    assert "conversation-" in (registry.get("wxpost-test") or "")
    legacy_title = "SoarHigh WxPost authoring v6 · wxpost-test"
    assert registry.pending_deletions() == [legacy_title]

    retry_session = _SessionClient(controller)
    retry_service = HermesDraftService(
        controller=controller,  # type: ignore[arg-type]
        session_client=retry_session,  # type: ignore[arg-type]
        session_registry=registry,
        cleanup_dispatch=lambda callback: callback(),
    )
    retry_service.history("wxpost-test")

    assert retry_session.deleted_session_ids == [legacy_title]
    assert registry.pending_deletions() == []


def test_workspace_delete_retires_its_persisted_draft_session(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    service.history("wxpost-test")
    result = service.delete_workspace(
        "wxpost-test",
        expected_manifest_version=4,
    )

    assert result == {"workspaceId": "wxpost-test", "deleted": True}
    assert session.controller.deleted_workspace_ids == ["wxpost-test"]
    assert session.deleted_session_ids == ["stored-session"]
    registry = HermesDraftSessionRegistry(tmp_path)
    assert registry.get("wxpost-test") is None
    assert registry.pending_deletions() == []


def test_workspace_delete_retires_a_legacy_title_only_session(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    result = service.delete_workspace(
        "wxpost-test",
        expected_manifest_version=4,
    )

    assert result == {"workspaceId": "wxpost-test", "deleted": True}
    assert session.deleted_session_ids == ["SoarHigh WxPost authoring v6 · wxpost-test"]
    registry = HermesDraftSessionRegistry(tmp_path)
    assert registry.get("wxpost-test") is None
    assert registry.pending_deletions() == []


def test_draft_service_rejects_a_stale_editorial_save_after_calling_hermes(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    with pytest.raises(VersionConflict, match="expected manifest version 3"):
        service.chat(
            "wxpost-test",
            expected_manifest_version=3,
            expected_draft_version=2,
            message="Tighten the opening.",
            selected_text=None,
        )

    assert len(session.prompts) == 1


def test_general_chat_is_not_blocked_by_unrelated_stale_page_versions(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    def answer_turn(
        *, title: str, cwd: str, prompt: str, session_id: str | None
    ) -> HermesTurn:
        session.prompts.append({"title": title, "cwd": cwd, "prompt": prompt})
        return HermesTurn(session_id="stored-session", reply="It is sunny today.")

    session.turn = answer_turn  # type: ignore[method-assign]

    result = service.chat(
        "wxpost-test",
        expected_manifest_version=3,
        expected_draft_version=1,
        message="What is today's weather?",
        selected_text=None,
    )

    assert result["reply"] == "It is sunny today."
    assert result["draftChanged"] is False
    assert result["context"] == session.controller.context


def test_focused_revision_keeps_the_saved_draft_source_snapshot(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    result = service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="Tighten the opening.",
        selected_text=None,
    )

    assert "refresh_from_materials=false" in session.prompts[0]["prompt"]
    assert "include media_changes" in session.prompts[0]["prompt"]
    assert "Do not include a Draft version line" in session.prompts[0]["prompt"]
    assert result["draftChanged"] is True
    assert result["reply"].endswith("Draft version: v2 → v3")


def test_chat_turn_always_uses_the_member_facing_product_identity(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="你是谁？你从哪里来？要到哪里去？",
        selected_text=None,
    )

    prompt = session.prompts[0]["prompt"]
    assert prompt.startswith(HERMES_DRAFT_IDENTITY)
    assert "SoarHigh Club's AI Assistant" in prompt
    assert "SoarHigh 俱乐部的 AI 助手" in prompt
    assert "Do not present yourself as Hermes Agent" in prompt


def test_chat_turn_preserves_unicode_member_request_in_prompt(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="我前面5轮的消息是什么？",
        selected_text=None,
    )

    prompt = session.prompts[0]["prompt"]
    assert 'MEMBER_REQUEST_JSON:"我前面5轮的消息是什么？"' in prompt
    assert r"\u97625" not in prompt


def test_draft_service_does_not_duplicate_hermes_version_transition(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    original_turn = session.turn

    def versioned_turn(
        *, title: str, cwd: str, prompt: str, session_id: str | None
    ) -> HermesTurn:
        turn = original_turn(title=title, cwd=cwd, prompt=prompt, session_id=session_id)
        return HermesTurn(
            session_id=turn.session_id,
            reply="Opening tightened.\n\nDraft version: v2 → v3",
        )

    session.turn = versioned_turn  # type: ignore[method-assign]

    result = service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="Tighten the opening.",
        selected_text=None,
    )

    assert result["reply"] == "Opening tightened.\n\nDraft version: v2 → v3"


def test_draft_service_rejects_invalid_revision_inputs_before_hermes(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    with pytest.raises(InvalidRequest, match="must be text"):
        service.chat(
            "wxpost-test",
            expected_manifest_version=4,
            expected_draft_version=2,
            message=None,  # type: ignore[arg-type]
            selected_text=None,
        )

    assert session.prompts == []


def test_chat_can_answer_a_read_only_draft_question_without_saving(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    def answer_turn(
        *, title: str, cwd: str, prompt: str, session_id: str | None
    ) -> HermesTurn:
        session.prompts.append({"title": title, "cwd": cwd, "prompt": prompt})
        return HermesTurn(session_id="stored-session", reply="There are four parts.")

    session.turn = answer_turn  # type: ignore[method-assign]

    result = service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="How many parts are in this article?",
        selected_text=None,
    )

    assert result["reply"] == "There are four parts."
    assert result["draftChanged"] is False
    assert result["context"]["draft"]["draftVersion"] == 2
    prompt = session.prompts[0]["prompt"]
    assert "Choose exactly one mode before calling a tool" in prompt
    assert "Do not read the workspace and do not load a Skill" in prompt
    assert "wxpost_get_context and answer without saving. Do not load a Skill" in prompt
    assert "imported workspaceReady images" in prompt
    assert "Never count workspaceReady=false" in prompt
    assert "Only when the member explicitly asks" in prompt
    assert "create or revise Draft" in prompt


def test_chat_maps_only_genuine_hermes_events_to_product_progress(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)
    progress: list[dict[str, Any]] = []

    def streamed_turn(
        *,
        title: str,
        cwd: str,
        prompt: str,
        session_id: str | None,
        on_event,
    ) -> HermesTurn:
        session.prompts.append({"title": title, "cwd": cwd, "prompt": prompt})
        on_event(
            "tool.start",
            {
                "toolId": "context-1",
                "name": "mcp__soarhigh_wxpost__wxpost_get_context",
            },
        )
        on_event(
            "tool.complete",
            {
                "toolId": "context-1",
                "name": "mcp__soarhigh_wxpost__wxpost_get_context",
            },
        )
        on_event(
            "tool.start",
            {"toolId": "internal-1", "name": "unrelated_internal_tool"},
        )
        on_event("reasoning.delta", {})
        on_event("tool.start", {"toolId": "skill-1", "name": "skill_view"})
        on_event("tool.complete", {"toolId": "skill-1", "name": "skill_view"})
        on_event(
            "tool.start",
            {
                "toolId": "search-1",
                "name": "web_search",
                "context": "Searching the web for current club news",
            },
        )
        on_event("tool.complete", {"toolId": "search-1", "name": "web_search"})
        on_event(
            "tool.start",
            {
                "toolId": "search-2",
                "name": "web_search",
                "context": "Searching the web for Toastmasters guidance",
            },
        )
        on_event(
            "tool.complete",
            {"toolId": "search-2", "name": "web_search", "error": True},
        )
        on_event(
            "tool.start",
            {
                "toolId": "save-1",
                "name": "mcp__soarhigh_wxpost__wxpost_save_draft",
            },
        )
        on_event(
            "tool.complete",
            {
                "toolId": "save-1",
                "name": "mcp__soarhigh_wxpost__wxpost_save_draft",
            },
        )
        on_event("message.delta", {"text": "Saved."})
        operation_id = prompt.split('operation_id="', 1)[1].split('"', 1)[0]
        session.controller.context["draft"]["draftVersion"] = 3
        session.controller.context["manifest"]["draft"] = {
            "version": 3,
            "operationId": operation_id,
        }
        return HermesTurn(session_id="stored-session", reply="Saved.")

    session.turn = streamed_turn  # type: ignore[method-assign]

    result = service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="Tighten the opening.",
        selected_text=None,
        on_progress=progress.append,
    )

    assert progress[:-2] == [
        {
            "stage": "activity_started",
            "activityId": "context-1",
            "label": "Reading the saved Draft and media",
        },
        {
            "stage": "activity_completed",
            "activityId": "context-1",
            "label": "Reading the saved Draft and media",
        },
        {
            "stage": "activity_started",
            "activityId": "skill-1",
            "label": "Loading the writing guidance",
        },
        {
            "stage": "activity_completed",
            "activityId": "skill-1",
            "label": "Loading the writing guidance",
        },
        {
            "stage": "activity_started",
            "activityId": "search-1",
            "label": "Searching the web for current club news",
        },
        {
            "stage": "activity_completed",
            "activityId": "search-1",
            "label": "Searching the web for current club news",
        },
        {
            "stage": "activity_started",
            "activityId": "search-2",
            "label": "Searching the web for Toastmasters guidance",
        },
        {
            "stage": "activity_failed",
            "activityId": "search-2",
            "label": "Searching the web for Toastmasters guidance",
        },
        {
            "stage": "activity_started",
            "activityId": "save-1",
            "label": "Saving Draft v3",
        },
        {
            "stage": "activity_completed",
            "activityId": "save-1",
            "label": "Saving Draft v3",
        },
    ]
    assert progress[-2]["stage"] == "activity_started"
    assert progress[-2]["label"] == "Verifying the saved Draft"
    assert progress[-2]["activityId"].startswith("verify-draft-")
    assert progress[-1] == {
        "stage": "activity_completed",
        "activityId": progress[-2]["activityId"],
        "label": "Verifying the saved Draft",
    }
    assert result["draftChanged"] is True


def test_failed_draft_save_does_not_report_verification_success(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)
    progress: list[dict[str, Any]] = []

    def failed_save_turn(
        *,
        title: str,
        cwd: str,
        prompt: str,
        session_id: str | None,
        on_event,
    ) -> HermesTurn:
        session.prompts.append({"title": title, "cwd": cwd, "prompt": prompt})
        on_event(
            "tool.start",
            {
                "toolId": "save-1",
                "name": "mcp__soarhigh_wxpost__wxpost_save_draft",
            },
        )
        on_event(
            "tool.complete",
            {
                "toolId": "save-1",
                "name": "mcp__soarhigh_wxpost__wxpost_save_draft",
                "error": True,
            },
        )
        return HermesTurn(session_id="stored-session", reply="Unable to save.")

    session.turn = failed_save_turn  # type: ignore[method-assign]

    result = service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="Tighten the opening.",
        selected_text=None,
        on_progress=progress.append,
    )

    assert progress == [
        {
            "stage": "activity_started",
            "activityId": "save-1",
            "label": "Saving Draft v3",
        },
        {
            "stage": "activity_failed",
            "activityId": "save-1",
            "label": "Saving Draft v3",
        },
    ]
    assert result["reply"] == "Unable to save."
    assert result["draftChanged"] is False


def test_failed_draft_save_without_start_event_does_not_report_verification(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)
    progress: list[dict[str, Any]] = []

    def failed_save_turn(
        *,
        title: str,
        cwd: str,
        prompt: str,
        session_id: str | None,
        on_event,
    ) -> HermesTurn:
        session.prompts.append({"title": title, "cwd": cwd, "prompt": prompt})
        on_event(
            "tool.complete",
            {
                "toolId": "save-1",
                "name": "mcp__soarhigh_wxpost__wxpost_save_draft",
                "error": True,
            },
        )
        return HermesTurn(session_id="stored-session", reply="Unable to save.")

    session.turn = failed_save_turn  # type: ignore[method-assign]

    result = service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="Tighten the opening.",
        selected_text=None,
        on_progress=progress.append,
    )

    assert progress == []
    assert result["reply"] == "Unable to save."
    assert result["draftChanged"] is False


def test_draft_service_does_not_adopt_an_unrelated_save(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    def unrelated_turn(
        *, title: str, cwd: str, prompt: str, session_id: str | None
    ) -> HermesTurn:
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

    def changed_materials_turn(
        *, title: str, cwd: str, prompt: str, session_id: str | None
    ) -> HermesTurn:
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

    def no_save_turn(
        *, title: str, cwd: str, prompt: str, session_id: str | None
    ) -> HermesTurn:
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


def test_session_client_deletes_the_resolved_stored_session_id() -> None:
    class Socket:
        def __enter__(self) -> Socket:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    client = HermesSessionClient(
        serve_url="ws://hermes.invalid/api/ws",
        token="secret",
    )
    sockets = [Socket(), Socket()]
    calls: list[tuple[str, dict[str, str]]] = []
    client._connect = lambda: sockets.pop(0)  # type: ignore[method-assign,return-value]
    client._resume = lambda websocket, identifier: {  # type: ignore[method-assign]
        "session_id": "live-session",
        "stored_session_id": "stored-session",
    }
    client._rpc = lambda websocket, method, params: (  # type: ignore[method-assign]
        calls.append((method, params)) or {}
    )

    client.delete(session_id="legacy session title")

    assert calls == [
        ("session.close", {"session_id": "live-session"}),
        ("session.delete", {"session_id": "stored-session"}),
    ]


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


def test_session_client_forwards_only_safe_lifecycle_events() -> None:
    class Messages:
        def __init__(self) -> None:
            self.items = [
                {
                    "method": "event",
                    "params": {
                        "session_id": "live-session",
                        "type": "reasoning.delta",
                        "payload": {"text": "private reasoning"},
                    },
                },
                {
                    "method": "event",
                    "params": {
                        "session_id": "live-session",
                        "type": "tool.start",
                        "payload": {
                            "tool_id": "tool-1",
                            "name": "wxpost_get_context",
                            "context": "Reading the saved Draft",
                            "args_text": "private arguments",
                        },
                    },
                },
                {
                    "method": "event",
                    "params": {
                        "session_id": "live-session",
                        "type": "tool.complete",
                        "payload": {
                            "tool_id": "tool-1",
                            "name": "wxpost_get_context",
                            "error": False,
                            "summary": "private result",
                        },
                    },
                },
                {
                    "method": "event",
                    "params": {
                        "session_id": "live-session",
                        "type": "message.complete",
                        "payload": {"text": "Done."},
                    },
                },
            ]

        def recv(self, *, timeout: float) -> str:
            assert timeout == 300
            return json.dumps(self.items.pop(0))

    events: list[tuple[str, dict[str, Any]]] = []
    client = HermesSessionClient(
        serve_url="ws://hermes.invalid/api/ws",
        token="secret",
    )

    reply = client._wait_for_completion(  # type: ignore[arg-type]
        Messages(),
        "live-session",
        on_event=lambda event, payload: events.append((event, payload)),
    )

    assert reply == "Done."
    assert events == [
        (
            "tool.start",
            {
                "toolId": "tool-1",
                "name": "wxpost_get_context",
                "context": "Reading the saved Draft",
            },
        ),
        (
            "tool.complete",
            {"toolId": "tool-1", "name": "wxpost_get_context", "error": False},
        ),
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
