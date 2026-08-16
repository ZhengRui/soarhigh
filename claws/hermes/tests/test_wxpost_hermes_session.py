from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from wxpost_controller.core import InvalidRequest, VersionConflict
from wxpost_controller.draft_store import (
    HermesDraftStore,
    read_running_operation_id,
)
from wxpost_controller.errors import (
    DraftOperationInProgress,
    DraftTurnInterrupted,
    HermesTurnFailed,
    HermesUnavailable,
)
from wxpost_controller.hermes_session import (
    HERMES_DRAFT_IDENTITY,
    HermesDescriptionService,
    HermesDraftService,
    HermesSessionClient,
    HermesTurn,
    _draft_edit_activity,
)


def _bound_operation_id(cwd: str) -> str:
    """Resolve the Controller-bound operation id exactly like the real tools:
    a read-only lookup of the running operation record."""

    workspace = Path(cwd)
    operation_id = read_running_operation_id(
        workspace.parent.parent,
        workspace.name,
    )
    assert operation_id is not None, "no running Draft operation is recorded"
    return operation_id


class _Controller:
    def __init__(self, root: Path) -> None:
        self.workspace_root = root
        self.inbox_root = root / "inbox"
        (self.inbox_root / "wxpost-test").mkdir(parents=True, exist_ok=True)
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
        self.turn_session_ids: list[str | None] = []
        self.close_on_disconnect_flags: list[bool] = []
        self.deleted_session_ids: list[str] = []
        self.live_session_ids: list[str] = []
        self.interrupted_session_ids: list[str] = []
        self.interrupt_next_turn = False

    def turn(
        self,
        *,
        title: str,
        cwd: str,
        prompt: str,
        session_id: str | None = None,
        close_on_disconnect: bool = False,
        on_event=None,
        on_session_resolved=None,
        on_live_session=None,
    ) -> HermesTurn:
        self.turn_session_ids.append(session_id)
        self.close_on_disconnect_flags.append(close_on_disconnect)
        self.prompts.append({"title": title, "cwd": cwd, "prompt": prompt})
        if on_session_resolved is not None:
            on_session_resolved("stored-session")
        if on_live_session is not None:
            on_live_session("live-session")
            self.live_session_ids.append("live-session")
        if self.interrupt_next_turn:
            self.interrupt_next_turn = False
            return HermesTurn(
                session_id="stored-session",
                reply="",
                interrupted=True,
            )
        operation_id = _bound_operation_id(cwd)
        if on_event is not None:
            on_event(
                "tool.start",
                {"toolId": "save-default", "name": "wxpost_save_draft"},
            )
        draft = self.controller.context["draft"]
        draft["draftVersion"] += 1
        self.controller.context["manifest"]["draft"] = {
            "version": draft["draftVersion"],
            "operationId": operation_id,
        }
        if on_event is not None:
            on_event(
                "tool.complete",
                {"toolId": "save-default", "name": "wxpost_save_draft"},
            )
        return HermesTurn(
            session_id="stored-session",
            reply="Draft regenerated.",
        )

    def delete(self, *, session_id: str) -> None:
        self.deleted_session_ids.append(session_id)

    def interrupt(self, *, live_session_id: str) -> bool:
        self.interrupted_session_ids.append(live_session_id)
        return True


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


def test_generate_binds_a_persistent_workspace_session_and_persists_history(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    result = service.generate(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
    )
    history = service.history("wxpost-test")

    assert result["context"]["draft"]["draftVersion"] == 3
    assert result["reply"] == "Draft regenerated.\n\nDraft version: v2 → v3"
    assert session.turn_session_ids == [None]
    assert session.close_on_disconnect_flags == [False]
    assert session.deleted_session_ids == []
    assert HermesDraftStore(tmp_path).session_binding("wxpost-test") == (
        "stored-session"
    )
    assert session.prompts[0]["title"] == "SoarHigh WxPost Draft · wxpost-test"
    assert session.prompts[0]["cwd"].endswith("/inbox/wxpost-test")
    assert "Expected manifest version: 4" in session.prompts[0]["prompt"]
    assert "Expected draft version: 2" in session.prompts[0]["prompt"]
    assert "workspace_id=" not in session.prompts[0]["prompt"]
    assert "wxpost_get_current_context" in session.prompts[0]["prompt"]
    assert "wxpost_save_current_draft" in session.prompts[0]["prompt"]
    assert "refresh_from_materials=true" in session.prompts[0]["prompt"]
    assert session.prompts[0]["prompt"].startswith(HERMES_DRAFT_IDENTITY)
    assert history["workspaceId"] == "wxpost-test"
    # The saved Draft version is reported so a mounting client can detect a
    # turn that completed while nobody was polling and reload the Draft.
    assert history["draftVersion"] == 3
    assert history["messages"][0]["text"] == (
        "Regenerate the English draft from saved Materials."
    )
    assert history["messages"][1]["text"].endswith("Draft version: v2 → v3")


def test_prompts_never_replay_controller_history(tmp_path: Path) -> None:
    """Hermes owns cross-turn context inside the persistent session; the
    Controller no longer serializes prior turns into any prompt."""

    service, session = _service(tmp_path)
    service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="Remember this instruction.",
        selected_text=None,
    )

    service.generate(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=3,
    )

    assert "PRIOR_COMPLETED_TURNS_JSON" not in session.prompts[0]["prompt"]
    assert "PRIOR_COMPLETED_TURNS_JSON" not in session.prompts[1]["prompt"]


def test_chat_turns_share_one_persistent_workspace_session(tmp_path: Path) -> None:
    service, session = _service(tmp_path)

    service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="Tighten the opening.",
        selected_text="The original opening.",
    )
    session.controller.context["manifest"]["manifestVersion"] = 5
    service.chat(
        "wxpost-test",
        expected_manifest_version=5,
        expected_draft_version=3,
        message="Tighten the closing.",
        selected_text=None,
    )

    assert session.turn_session_ids == [None, "stored-session"]
    assert session.prompts[0]["title"] == session.prompts[1]["title"]
    assert session.deleted_session_ids == []
    assert len(service.history("wxpost-test")["messages"]) == 4
    assert "activityId" not in session.prompts[1]["prompt"]
    assert service.history("wxpost-test")["messages"][0]["selectedText"] == (
        "The original opening."
    )


def test_controller_history_survives_service_recreation(tmp_path: Path) -> None:
    controller = _Controller(tmp_path)
    first_session = _SessionClient(controller)
    first_service = HermesDraftService(
        controller=controller,  # type: ignore[arg-type]
        session_client=first_session,  # type: ignore[arg-type]
        cleanup_dispatch=lambda callback: callback(),
    )
    first_service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="Tighten the opening.",
        selected_text=None,
    )

    second_session = _SessionClient(controller)
    second_service = HermesDraftService(
        controller=controller,  # type: ignore[arg-type]
        session_client=second_session,  # type: ignore[arg-type]
        cleanup_dispatch=lambda callback: callback(),
    )

    assert second_service.history("wxpost-test")["messages"][0]["text"] == (
        "Tighten the opening."
    )
    second_service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=3,
        message="What did I just ask you to change?",
        selected_text=None,
    )
    # The workspace→session binding is durable: a recreated service resumes
    # the same persistent Hermes session (which carries the model context)
    # instead of starting a new one.
    assert second_session.turn_session_ids == ["stored-session"]


def test_startup_completes_interrupted_operation_whose_save_landed(
    tmp_path: Path,
) -> None:
    """A restart that hit after the save landed must not report failure: the
    manifest's operation-id stamp proves the Draft write succeeded."""

    controller = _Controller(tmp_path)
    store = HermesDraftStore(tmp_path)
    operation_id = "draft-44444444444444444444444444444444"
    store.start_operation(
        "wxpost-test",
        operation_id,
        request_fingerprint="fingerprint",
        member_message="Tighten the opening.",
        selected_text=None,
        expected_manifest_version=4,
        expected_draft_version=2,
    )
    store.set_steps(
        operation_id,
        [
            {
                "activityId": "save-1",
                "label": "Saving the Draft",
                "toolName": "wxpost_save_current_draft",
                "completed": True,
                "failed": False,
            },
            {
                "activityId": "verify-1",
                "label": "Verifying the saved Draft",
                "completed": False,
                "failed": False,
            },
        ],
    )
    controller.context["draft"]["draftVersion"] = 3
    controller.context["manifest"]["draft"] = {
        "version": 3,
        "operationId": operation_id,
    }

    service = HermesDraftService(
        controller=controller,  # type: ignore[arg-type]
        session_client=_SessionClient(controller),  # type: ignore[arg-type]
        cleanup_dispatch=lambda callback: callback(),
    )

    operation = store.get_operation("wxpost-test", operation_id)
    assert operation["state"] == "completed"
    assert operation["result"]["draftChanged"] is True
    assert operation["result"]["draftVersion"] == 3
    assert operation["result"]["reply"].endswith("Draft version: v2 → v3")
    # The step still in flight when the process died is dropped so history
    # never renders a forever-pending badge.
    assert [step["activityId"] for step in operation["result"]["steps"]] == ["save-1"]
    history = service.history("wxpost-test")
    assert history["messages"][1]["turnId"] == operation_id
    assert history["draftVersion"] == 3


def test_startup_fails_interrupted_operation_without_landed_save(
    tmp_path: Path,
) -> None:
    controller = _Controller(tmp_path)
    store = HermesDraftStore(tmp_path)
    stamped_elsewhere = "draft-55555555555555555555555555555555"
    orphaned = "draft-66666666666666666666666666666666"
    store.start_operation(
        "wxpost-test",
        orphaned,
        request_fingerprint="fingerprint",
        member_message="Tighten the opening.",
        selected_text=None,
        expected_manifest_version=4,
        expected_draft_version=2,
    )
    # The manifest stamp belongs to an earlier, already-settled turn — it must
    # not be mistaken for this operation's save.
    controller.context["manifest"]["draft"] = {
        "version": 2,
        "operationId": stamped_elsewhere,
    }

    HermesDraftService(
        controller=controller,  # type: ignore[arg-type]
        session_client=_SessionClient(controller),  # type: ignore[arg-type]
        cleanup_dispatch=lambda callback: callback(),
    )

    operation = store.get_operation("wxpost-test", orphaned)
    assert operation["state"] == "failed"
    assert operation["error"]["code"] == "controller_restarted"


def test_startup_fails_interrupted_operation_when_workspace_is_unreadable(
    tmp_path: Path,
) -> None:
    class _UnreadableController(_Controller):
        def get_context(self, workspace_id: str) -> dict[str, Any]:
            raise HermesTurnFailed("workspace cannot be read")

    controller = _UnreadableController(tmp_path)
    store = HermesDraftStore(tmp_path)
    operation_id = "draft-77777777777777777777777777777777"
    store.start_operation(
        "wxpost-test",
        operation_id,
        request_fingerprint="fingerprint",
        member_message="Tighten the opening.",
        selected_text=None,
        expected_manifest_version=4,
        expected_draft_version=2,
    )

    HermesDraftService(
        controller=controller,  # type: ignore[arg-type]
        session_client=_SessionClient(controller),  # type: ignore[arg-type]
        cleanup_dispatch=lambda callback: callback(),
    )

    operation = store.get_operation("wxpost-test", operation_id)
    assert operation["state"] == "failed"
    assert operation["error"]["code"] == "controller_restarted"


def test_reset_clears_conversation_and_retires_the_workspace_session(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)
    service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="Tighten the opening.",
        selected_text=None,
    )
    before_reset = json.loads(json.dumps(session.controller.context))

    result = service.reset("wxpost-test")

    assert result == {"workspaceId": "wxpost-test", "messages": []}
    assert service.history("wxpost-test")["messages"] == []
    assert session.controller.context == before_reset
    # Reset starts a genuinely new conversation: the persistent session is
    # retired (deleted via the durable queue) and the binding is dropped, so
    # the next turn creates a fresh session with no pre-reset model context.
    assert session.deleted_session_ids == ["stored-session"]
    assert HermesDraftStore(tmp_path).session_binding("wxpost-test") is None
    assert HermesDraftStore(tmp_path).pending_deletions() == []
    service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=3,
        message="What happened before this message?",
        selected_text=None,
    )
    assert session.turn_session_ids == [None, None]


def test_workspace_delete_removes_controller_conversation(tmp_path: Path) -> None:
    service, session = _service(tmp_path)
    service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="Tighten the opening.",
        selected_text=None,
    )

    result = service.delete_workspace(
        "wxpost-test",
        expected_manifest_version=4,
    )

    assert result == {"workspaceId": "wxpost-test", "deleted": True}
    assert session.controller.deleted_workspace_ids == ["wxpost-test"]
    assert HermesDraftStore(tmp_path).history("wxpost-test") == []
    # Workspace deletion retires the persistent session so no Hermes session
    # lineage is leaked behind a deleted workspace.
    assert session.deleted_session_ids == ["stored-session"]
    assert HermesDraftStore(tmp_path).session_binding("wxpost-test") is None


def test_retire_session_still_cleans_native_feishu_sessions(tmp_path: Path) -> None:
    service, session = _service(tmp_path)

    result = service.retire_session("feishu-old-session")

    assert result == {
        "sessionId": "feishu-old-session",
        "cleanupScheduled": True,
    }
    assert session.deleted_session_ids == ["feishu-old-session"]
    assert HermesDraftStore(tmp_path).pending_deletions() == []


def test_chat_submit_runs_in_background_with_pollable_progress(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)
    release = threading.Event()
    real_turn = session.turn

    def gated_turn(**kwargs: Any) -> HermesTurn:
        kwargs["on_event"](
            "tool.start",
            {"toolId": "context-1", "name": "wxpost_get_current_context"},
        )
        assert release.wait(timeout=5)
        return real_turn(**kwargs)

    session.turn = gated_turn  # type: ignore[method-assign]
    operation_id = "draft-" + "a" * 32

    submitted = service.chat_submit(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        operation_id=operation_id,
        message="Tighten the opening.",
        selected_text=None,
    )
    assert submitted == {
        "workspaceId": "wxpost-test",
        "operationId": operation_id,
        "state": "running",
    }

    try:
        # Incremental step persistence: a polling client sees the in-progress
        # activity while the turn is still running, before any result exists.
        operation = service.operation("wxpost-test", operation_id)
        for _ in range(250):
            operation = service.operation("wxpost-test", operation_id)
            if operation["steps"]:
                break
            time.sleep(0.02)
        assert operation["state"] == "running"
        assert operation["result"] is None
        assert operation["steps"][0]["label"] == "Reading the saved Draft and media"
        assert operation["steps"][0]["completed"] is False

        # A reconnecting client (refresh, second tab) rediscovers the running
        # operation from the conversation history.
        history = service.history("wxpost-test")
        assert history["activeOperation"]["operationId"] == operation_id
        assert history["activeOperation"]["memberMessage"] == ("Tighten the opening.")

        # One in-flight turn per workspace: a concurrent submit is rejected.
        with pytest.raises(DraftOperationInProgress):
            service.chat_submit(
                "wxpost-test",
                expected_manifest_version=4,
                expected_draft_version=2,
                operation_id="draft-" + "b" * 32,
                message="Another request.",
                selected_text=None,
            )
    finally:
        release.set()

    for _ in range(250):
        operation = service.operation("wxpost-test", operation_id)
        if operation["state"] != "running":
            break
        time.sleep(0.02)
    assert operation["state"] == "completed"
    assert operation["result"]["draftChanged"] is True
    assert service.history("wxpost-test").get("activeOperation") is None


def test_generate_submit_runs_in_background_like_chat(tmp_path: Path) -> None:
    """The heaviest turn uses the same async submit + poll contract as chat."""

    service, session = _service(tmp_path)
    operation_id = "draft-" + "c" * 32

    submitted = service.generate_submit(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        operation_id=operation_id,
    )
    assert submitted == {
        "workspaceId": "wxpost-test",
        "operationId": operation_id,
        "state": "running",
    }

    for _ in range(250):
        operation = service.operation("wxpost-test", operation_id)
        if operation["state"] != "running":
            break
        time.sleep(0.02)
    assert operation["state"] == "completed"
    assert operation["result"]["draftChanged"] is True
    assert operation["result"]["draftVersion"] == 3
    assert "Regenerate the English draft" in session.prompts[0]["prompt"]


def test_interrupt_operation_signals_the_live_hermes_session(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)
    release = threading.Event()
    real_turn = session.turn

    def gated_turn(**kwargs: Any) -> HermesTurn:
        kwargs["on_live_session"]("live-session")
        assert release.wait(timeout=5)
        kwargs["on_live_session"] = None
        return real_turn(**kwargs)

    session.turn = gated_turn  # type: ignore[method-assign]
    operation_id = "draft-" + "d" * 32
    service.chat_submit(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        operation_id=operation_id,
        message="Tighten the opening.",
        selected_text=None,
    )

    try:
        for _ in range(250):
            with service._live_turns_guard:
                if "wxpost-test" in service._live_turns:
                    break
            time.sleep(0.02)
        interrupted = service.interrupt_operation("wxpost-test", operation_id)
        assert interrupted == {
            "workspaceId": "wxpost-test",
            "operationId": operation_id,
            "interrupted": True,
        }
        assert session.interrupted_session_ids == ["live-session"]
    finally:
        release.set()

    for _ in range(250):
        operation = service.operation("wxpost-test", operation_id)
        if operation["state"] != "running":
            break
        time.sleep(0.02)
    assert operation["state"] == "completed"


def test_interrupted_turn_without_save_records_a_stopped_failure(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)
    session.interrupt_next_turn = True

    with pytest.raises(DraftTurnInterrupted):
        service.chat(
            "wxpost-test",
            expected_manifest_version=4,
            expected_draft_version=2,
            message="Tighten the opening.",
            selected_text=None,
            operation_id="draft-" + "e" * 32,
        )

    operation = service.operation("wxpost-test", "draft-" + "e" * 32)
    assert operation["state"] == "failed"
    assert operation["error"]["code"] == "draft_turn_interrupted"


def test_interrupted_turn_with_landed_save_completes_normally(
    tmp_path: Path,
) -> None:
    """Linearization: a save that landed before the interrupt is the truth."""

    service, session = _service(tmp_path)
    real_turn = session.turn

    def interrupted_after_save(**kwargs: Any) -> HermesTurn:
        turn = real_turn(**kwargs)
        return HermesTurn(
            session_id=turn.session_id,
            reply="",
            interrupted=True,
        )

    session.turn = interrupted_after_save  # type: ignore[method-assign]
    result = service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="Tighten the opening.",
        selected_text=None,
        operation_id="draft-" + "f" * 32,
    )

    assert result["draftChanged"] is True
    assert result["reply"] == "Draft version: v2 → v3"
    operation = service.operation("wxpost-test", "draft-" + "f" * 32)
    assert operation["state"] == "completed"


def test_interrupt_of_a_finished_operation_is_a_no_op(tmp_path: Path) -> None:
    service, _session = _service(tmp_path)
    operation_id = "draft-" + "1" * 32
    service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="Tighten the opening.",
        selected_text=None,
        operation_id=operation_id,
    )

    assert service.interrupt_operation("wxpost-test", operation_id) == {
        "workspaceId": "wxpost-test",
        "operationId": operation_id,
        "interrupted": False,
    }


def test_draft_turn_binding_is_scoped_to_the_running_operation(
    tmp_path: Path,
) -> None:
    """The save tools resolve the trusted operation id from the running
    operation record: present during the turn, gone once it settles, and
    never carried in prompt text the model could copy from later context."""

    service, session = _service(tmp_path)
    seen_bindings: list[str] = []
    real_turn = session.turn

    def observing_turn(**kwargs: Any) -> HermesTurn:
        seen_bindings.append(_bound_operation_id(kwargs["cwd"]))
        return real_turn(**kwargs)

    session.turn = observing_turn  # type: ignore[method-assign]
    service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="Tighten the opening.",
        selected_text=None,
    )

    assert len(seen_bindings) == 1
    assert seen_bindings[0].startswith("draft-")
    # Settled operations are not running: no later tool call can bind to one.
    assert read_running_operation_id(tmp_path, "wxpost-test") is None
    assert "operation_id=" not in session.prompts[0]["prompt"]
    assert "Draft operation ID" not in session.prompts[0]["prompt"]

    def fail_turn(**_kwargs: Any) -> HermesTurn:
        raise HermesUnavailable("Hermes web session is unavailable")

    session.turn = fail_turn  # type: ignore[method-assign]
    with pytest.raises(HermesUnavailable):
        service.chat(
            "wxpost-test",
            expected_manifest_version=4,
            expected_draft_version=3,
            message="Tighten the closing.",
            selected_text=None,
        )
    # A failed turn settles its operation too, releasing the binding.
    assert read_running_operation_id(tmp_path, "wxpost-test") is None


def test_failed_draft_turn_keeps_the_workspace_session_binding(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)
    service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="Tighten the opening.",
        selected_text=None,
    )
    operation_id = "draft-55555555555555555555555555555555"
    real_turn = session.turn

    def fail_turn(**_kwargs: Any) -> HermesTurn:
        raise HermesUnavailable("Hermes web session is unavailable")

    session.turn = fail_turn  # type: ignore[method-assign]

    with pytest.raises(HermesUnavailable):
        service.chat(
            "wxpost-test",
            expected_manifest_version=4,
            expected_draft_version=3,
            operation_id=operation_id,
            message="Tighten the closing.",
            selected_text=None,
        )

    # A failed turn no longer tears the session down: the persistent binding
    # survives so the next turn resumes the same workspace session.
    assert session.deleted_session_ids == []
    assert HermesDraftStore(tmp_path).pending_deletions() == []
    assert HermesDraftStore(tmp_path).session_binding("wxpost-test") == (
        "stored-session"
    )
    assert (
        HermesDraftStore(tmp_path).get_operation("wxpost-test", operation_id)["state"]
        == "failed"
    )
    session.turn = real_turn  # type: ignore[method-assign]
    service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=3,
        message="Tighten the closing again.",
        selected_text=None,
    )
    assert session.turn_session_ids[-1] == "stored-session"


def test_draft_service_accepts_a_successful_save_despite_manifest_drift(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    result = service.chat(
        "wxpost-test",
        expected_manifest_version=3,
        expected_draft_version=2,
        message="Tighten the opening.",
        selected_text=None,
    )

    assert len(session.prompts) == 1
    assert result["draftChanged"] is True
    assert result["context"]["draft"]["draftVersion"] == 3


def test_chat_rejects_a_save_attributed_to_an_earlier_turn(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)
    progress: list[dict[str, Any]] = []

    def stale_operation_turn(
        *,
        title: str,
        cwd: str,
        prompt: str,
        session_id: str | None,
        on_event,
        **_kwargs: Any,
    ) -> HermesTurn:
        session.prompts.append({"title": title, "cwd": cwd, "prompt": prompt})
        tool_name = "wxpost_edit_current_draft"
        on_event("tool.start", {"toolId": "save-1", "name": tool_name})
        session.controller.context["draft"]["draftVersion"] = 3
        session.controller.context["manifest"]["draft"] = {
            "version": 3,
            "operationId": "draft-from-an-earlier-turn",
        }
        on_event(
            "tool.complete",
            {
                "toolId": "save-1",
                "name": tool_name,
                "arguments": {
                    "edits": [
                        {
                            "type": "replaceMetadata",
                            "field": "title",
                            "value": "Updated title",
                        }
                    ]
                },
            },
        )
        return HermesTurn(session_id="stored-session", reply="Title updated.")

    session.turn = stale_operation_turn  # type: ignore[method-assign]

    with pytest.raises(VersionConflict, match="expected draft version 2"):
        service.chat(
            "wxpost-test",
            expected_manifest_version=4,
            expected_draft_version=2,
            message="Add a period to the title.",
            selected_text=None,
            on_progress=progress.append,
        )

    assert progress[0]["toolName"] == "wxpost_edit_current_draft"
    assert progress[1]["toolName"] == "wxpost_edit_current_draft"
    assert progress[1]["label"] == "Updating the Draft title"


def test_general_chat_is_not_blocked_by_unrelated_stale_page_versions(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    def answer_turn(
        *,
        title: str,
        cwd: str,
        prompt: str,
        session_id: str | None,
        on_event=None,
        **_kwargs: Any,
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
        *,
        title: str,
        cwd: str,
        prompt: str,
        session_id: str | None,
        on_event=None,
        **_kwargs: Any,
    ) -> HermesTurn:
        turn = original_turn(
            title=title,
            cwd=cwd,
            prompt=prompt,
            session_id=session_id,
            on_event=on_event,
        )
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
        *,
        title: str,
        cwd: str,
        prompt: str,
        session_id: str | None,
        on_event=None,
        **_kwargs: Any,
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
    assert (
        "wxpost_get_current_context and answer without saving. Do not load a Skill"
        in prompt
    )
    assert "wxpost_get_current_workspace_report and answer without saving" in prompt
    assert "complete workspace catalog: candidates plus" in prompt
    assert "Candidates are linked meeting/event media not yet" in prompt
    assert "Included means selected for the next Generate or Regenerate" in prompt
    assert "Only when the member explicitly asks" in prompt
    assert "create or revise Draft" in prompt
    assert "wxpost_edit_current_draft for a local title" in prompt
    assert "node indexes come from draft.editContext" in prompt
    assert "wxpost_save_current_draft only for whole-article restructuring" in prompt
    assert "take no\nworkspace ID" in prompt


def test_failed_current_workspace_read_is_not_replaced_with_stale_history(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)
    progress: list[dict[str, Any]] = []

    def failed_read_turn(
        *,
        title: str,
        cwd: str,
        prompt: str,
        session_id: str | None,
        on_event,
        **_kwargs: Any,
    ) -> HermesTurn:
        session.prompts.append({"title": title, "cwd": cwd, "prompt": prompt})
        on_event(
            "tool.start",
            {
                "toolId": "report-1",
                "name": "wxpost_get_current_workspace_report",
            },
        )
        on_event(
            "tool.complete",
            {
                "toolId": "report-1",
                "name": "wxpost_get_current_workspace_report",
                "error": True,
            },
        )
        return HermesTurn(
            session_id="stored-session",
            reply="There are 11 materials from an earlier answer.",
        )

    session.turn = failed_read_turn  # type: ignore[method-assign]

    result = service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="List the current material library.",
        selected_text=None,
        on_progress=progress.append,
    )

    assert result["reply"] == (
        "I could not read the current workspace, so I did not use older "
        "conversation data as if it were current. Please retry."
    )
    assert progress[-1] == {
        "stage": "activity_failed",
        "activityId": "report-1",
        "label": "Reading the workspace configuration",
        "toolName": "wxpost_get_current_workspace_report",
    }


def test_recovered_workspace_read_keeps_the_model_reply(tmp_path: Path) -> None:
    """A read that fails but is retried successfully saw current data, so the
    stale-data reply override must not fire."""

    service, session = _service(tmp_path)

    def retried_read_turn(
        *,
        title: str,
        cwd: str,
        prompt: str,
        session_id: str | None,
        on_event,
        **_kwargs: Any,
    ) -> HermesTurn:
        session.prompts.append({"title": title, "cwd": cwd, "prompt": prompt})
        on_event(
            "tool.complete",
            {
                "toolId": "report-1",
                "name": "wxpost_get_current_workspace_report",
                "error": True,
            },
        )
        on_event(
            "tool.complete",
            {
                "toolId": "report-2",
                "name": "wxpost_get_current_workspace_report",
                "error": False,
            },
        )
        return HermesTurn(
            session_id="stored-session",
            reply="There are 3 materials.",
        )

    session.turn = retried_read_turn  # type: ignore[method-assign]

    result = service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="List the current material library.",
        selected_text=None,
    )

    assert result["reply"] == "There are 3 materials."


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
        **_kwargs: Any,
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
                "name": "mcp__soarhigh_wxpost__wxpost_edit_draft",
            },
        )
        on_event(
            "tool.complete",
            {
                "toolId": "save-1",
                "name": "mcp__soarhigh_wxpost__wxpost_edit_draft",
                "arguments": {
                    "edits": [
                        {
                            "type": "replaceMetadata",
                            "field": "title",
                            "value": "A tighter title",
                        }
                    ]
                },
            },
        )
        on_event("message.delta", {"text": "Saved."})
        operation_id = _bound_operation_id(cwd)
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
            "toolName": "wxpost_get_context",
        },
        {
            "stage": "activity_completed",
            "activityId": "context-1",
            "label": "Reading the saved Draft and media",
            "toolName": "wxpost_get_context",
        },
        {
            "stage": "activity_started",
            "activityId": "skill-1",
            "label": "Loading the writing guidance",
            "toolName": "skill_view",
        },
        {
            "stage": "activity_completed",
            "activityId": "skill-1",
            "label": "Loading the writing guidance",
            "toolName": "skill_view",
        },
        {
            "stage": "activity_started",
            "activityId": "search-1",
            "label": "Searching the web for current club news",
            "toolName": "web_search",
        },
        {
            "stage": "activity_completed",
            "activityId": "search-1",
            "label": "Searching the web for current club news",
            "toolName": "web_search",
        },
        {
            "stage": "activity_started",
            "activityId": "search-2",
            "label": "Searching the web for Toastmasters guidance",
            "toolName": "web_search",
        },
        {
            "stage": "activity_failed",
            "activityId": "search-2",
            "label": "Searching the web for Toastmasters guidance",
            "toolName": "web_search",
        },
        {
            "stage": "activity_started",
            "activityId": "save-1",
            "label": "Saving Draft v3",
            "toolName": "wxpost_edit_draft",
        },
        {
            "stage": "activity_completed",
            "activityId": "save-1",
            "label": "Updating the Draft title",
            "toolName": "wxpost_edit_draft",
            "operationNames": ["replaceMetadata"],
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
    # The operation id no longer appears in the prompt; the manifest carries
    # the server-bound id the fake tool read from the running operation record.
    operation_id = session.controller.context["manifest"]["draft"]["operationId"]
    operation = service.operation("wxpost-test", operation_id)
    assert operation == {
        "workspaceId": "wxpost-test",
        "operationId": operation_id,
        "state": "completed",
        "result": {
            "reply": "Saved.\n\nDraft version: v2 → v3",
            "draftChanged": True,
            "draftVersion": 3,
            "steps": operation["result"]["steps"],
        },
        "error": None,
        "steps": operation["steps"],
    }
    # The live steps persisted during the turn include the in-progress
    # entries and end settled, so a polling client saw real-time progress.
    assert operation["steps"][-1]["completed"] is True
    assert operation["result"]["steps"][-2:] == [
        {
            "activityId": "save-1",
            "label": "Updating the Draft title",
            "toolName": "wxpost_edit_draft",
            "operationNames": ["replaceMetadata"],
            "completed": True,
            "failed": False,
        },
        {
            "activityId": progress[-1]["activityId"],
            "label": "Verifying the saved Draft",
            "completed": True,
            "failed": False,
        },
    ]


def test_chat_records_failed_operation_for_exact_recovery(tmp_path: Path) -> None:
    service, session = _service(tmp_path)
    operation_id = "draft-0123456789abcdef0123456789abcdef"

    def unavailable_turn(**_kwargs: Any) -> HermesTurn:
        raise HermesUnavailable("Hermes web session is unavailable")

    session.turn = unavailable_turn  # type: ignore[method-assign]

    with pytest.raises(HermesUnavailable):
        service.chat(
            "wxpost-test",
            expected_manifest_version=4,
            expected_draft_version=2,
            operation_id=operation_id,
            message="Tighten the opening.",
            selected_text=None,
        )

    assert service.operation("wxpost-test", operation_id) == {
        "workspaceId": "wxpost-test",
        "operationId": operation_id,
        "state": "failed",
        "result": None,
        "error": {
            "code": "hermes_unavailable",
            "message": "Hermes web session is unavailable",
        },
        "steps": [],
    }


def test_operation_status_remains_readable_while_turn_is_running(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)
    operation_id = "draft-fedcba9876543210fedcba9876543210"
    started = threading.Event()
    release = threading.Event()

    def slow_turn(**_kwargs: Any) -> HermesTurn:
        started.set()
        assert release.wait(timeout=5)
        return HermesTurn(session_id="stored-session", reply="No change needed.")

    session.turn = slow_turn  # type: ignore[method-assign]
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            service.chat,
            "wxpost-test",
            expected_manifest_version=4,
            expected_draft_version=2,
            operation_id=operation_id,
            message="Does this opening read clearly?",
            selected_text=None,
        )
        assert started.wait(timeout=1)
        assert service.operation("wxpost-test", operation_id)["state"] == "running"
        release.set()
        assert future.result(timeout=5)["draftChanged"] is False

    completed = service.operation("wxpost-test", operation_id)
    assert completed["state"] == "completed"
    assert completed["result"]["reply"] == "No change needed."


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
        **_kwargs: Any,
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
            "toolName": "wxpost_save_draft",
        },
        {
            "stage": "activity_failed",
            "activityId": "save-1",
            "label": "Saving Draft v3",
            "toolName": "wxpost_save_draft",
        },
    ]
    assert result["reply"] == "Unable to save."
    assert result["draftChanged"] is False
    history = service.history("wxpost-test")["messages"]
    assert history[-1]["steps"] == [
        {
            "activityId": "save-1",
            "label": "Saving Draft v3",
            "toolName": "wxpost_save_draft",
            "completed": False,
            "failed": True,
        }
    ]


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
        **_kwargs: Any,
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
        *,
        title: str,
        cwd: str,
        prompt: str,
        session_id: str | None,
        on_event=None,
        **_kwargs: Any,
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
        *,
        title: str,
        cwd: str,
        prompt: str,
        session_id: str | None,
        on_event=None,
        **_kwargs: Any,
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


def test_chat_does_not_misreport_a_materials_change_as_a_draft_conflict(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    def changed_materials_turn(
        *,
        title: str,
        cwd: str,
        prompt: str,
        session_id: str | None,
        on_event=None,
        **_kwargs: Any,
    ) -> HermesTurn:
        session.prompts.append({"title": title, "cwd": cwd, "prompt": prompt})
        session.controller.context["manifest"]["manifestVersion"] = 5
        return HermesTurn(
            session_id="stored-session",
            reply="Materials changed; no Draft was saved.",
        )

    session.turn = changed_materials_turn  # type: ignore[method-assign]

    result = service.chat(
        "wxpost-test",
        expected_manifest_version=4,
        expected_draft_version=2,
        message="Change the Materials description for M02.",
        selected_text=None,
    )

    assert result["draftChanged"] is False
    assert result["context"]["manifest"]["manifestVersion"] == 5
    assert result["context"]["draft"]["draftVersion"] == 2


def test_draft_service_keeps_a_no_save_turn_as_a_hermes_failure(
    tmp_path: Path,
) -> None:
    service, session = _service(tmp_path)

    def no_save_turn(
        *,
        title: str,
        cwd: str,
        prompt: str,
        session_id: str | None,
        on_event=None,
        **_kwargs: Any,
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
                            "args": {"private": "context arguments"},
                            "summary": "private result",
                        },
                    },
                },
                {
                    "method": "event",
                    "params": {
                        "session_id": "live-session",
                        "type": "tool.complete",
                        "payload": {
                            "tool_id": "tool-2",
                            "name": "mcp__soarhigh_wxpost__wxpost_edit_draft",
                            "error": False,
                            "args": {
                                "edits": [
                                    {
                                        "type": "clearCover",
                                    }
                                ]
                            },
                            "summary": "private result",
                        },
                    },
                },
                {
                    "method": "event",
                    "params": {
                        "session_id": "live-session",
                        "type": "tool.complete",
                        "payload": {
                            "tool_id": "tool-3",
                            "name": "mcp__soarhigh_wxpost__wxpost_save_draft",
                            "args": {"private": "save arguments"},
                            # Hermes reports MCP-level failures only through
                            # the result payload; the event carries no error
                            # flag of its own.
                            "result": {
                                "error": (
                                    "Error executing tool wxpost_save_draft: "
                                    "1 validation error"
                                ),
                            },
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

    reply, interrupted = client._wait_for_completion(  # type: ignore[arg-type]
        Messages(),
        "live-session",
        on_event=lambda event, payload: events.append((event, payload)),
    )

    assert reply == "Done."
    assert interrupted is False
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
        (
            "tool.complete",
            {
                "toolId": "tool-2",
                "name": "mcp__soarhigh_wxpost__wxpost_edit_draft",
                "error": False,
                "arguments": {"edits": [{"type": "clearCover"}]},
            },
        ),
        (
            "tool.complete",
            {
                "toolId": "tool-3",
                "name": "mcp__soarhigh_wxpost__wxpost_save_draft",
                "error": True,
            },
        ),
    ]


@pytest.mark.parametrize(
    ("edit", "expected_label"),
    [
        (
            {"type": "replaceMetadata", "field": "title", "value": "New"},
            "Updating the Draft title",
        ),
        (
            {"type": "insertImage", "sourceId": "M03", "index": 2},
            "Adding M03 to the Draft",
        ),
        (
            {"type": "removeMediaFromBody", "sourceId": "M02"},
            "Removing M02 from the Draft",
        ),
        ({"type": "clearCover"}, "Clearing the Draft cover"),
    ],
)
def test_draft_edit_activity_uses_typed_operation_details(
    edit: dict[str, Any],
    expected_label: str,
) -> None:
    result = _draft_edit_activity({"edits": [edit]})

    assert result == (expected_label, [edit["type"]])


def _description_service(
    controller: _Controller,
    session: _SessionClient,
    *,
    retired_sessions: list[str] | None = None,
) -> HermesDescriptionService:
    def retire(session_id: str) -> None:
        if retired_sessions is not None:
            retired_sessions.append(session_id)

    return HermesDescriptionService(
        controller=controller,  # type: ignore[arg-type]
        session_client=session,  # type: ignore[arg-type]
        retire_session=retire,
    )


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
                    '{"status":"ok","description":"Members exchange ideas around a table '
                    'before the meeting begins."}'
                ),
            )
        )
    )
    retired_sessions: list[str] = []
    service = _description_service(
        controller,
        session,
        retired_sessions=retired_sessions,
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
        "manifestVersion": 4,
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
    # No guidance was given, so the member-guidance framing must be absent.
    assert "MEMBER_GUIDANCE_JSON" not in prompt
    assert retired_sessions == ["description-session"]


def test_description_service_threads_member_guidance_into_the_prompt(
    tmp_path: Path,
) -> None:
    controller = _Controller(tmp_path)
    session = _SessionClient(controller)
    session.turn = lambda **kwargs: (  # type: ignore[method-assign]
        session.prompts.append(kwargs)
        or HermesTurn(
            session_id="description-session",
            reply='{"status":"ok","description":"大家在会前围坐交流。"}',
        )
    )
    service = _description_service(controller, session)

    result = service.suggest(
        "wxpost-test",
        expected_manifest_version=4,
        source_id="M01",
        current_description="",
        guidance="写中文，简洁，提到会议主题",
    )

    assert result["description"] == "大家在会前围坐交流。"
    prompt = session.prompts[0]["prompt"]
    assert "MEMBER_GUIDANCE_JSON:" + '"写中文，简洁，提到会议主题"' in prompt
    assert "take precedence over the default" in prompt
    # Guidance steers style only; the image stays the factual authority.
    assert "never override what the" in prompt
    # The fixed English framing disappears whenever guidance exists — a loud
    # early "English" otherwise outweighs the later precedence note.
    assert "suggest one English" not in prompt
    assert "natural English editorial caption" not in prompt
    assert "following the member guidance below" in prompt
    assert "in the language" in prompt

    with pytest.raises(InvalidRequest, match="at most 500 characters"):
        service.suggest(
            "wxpost-test",
            expected_manifest_version=4,
            source_id="M01",
            current_description="",
            guidance="x" * 501,
        )


def test_description_service_uses_image_first_generation_for_empty_text(
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
                    '{"status":"ok","description":'
                    '"A speaker addresses seated members."}'
                ),
            )
        )
    )
    service = _description_service(controller, session)

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
        '{"description":"Old response contract"}',
        '{"status":"ok","description":""}',
        '{"status":"ok","description":"Useful","extra":true}',
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
    service = _description_service(controller, session)

    with pytest.raises(HermesTurnFailed, match="invalid image description"):
        service.suggest(
            "wxpost-test",
            expected_manifest_version=4,
            source_id="M01",
            current_description="",
        )


def test_description_service_surfaces_inspection_errors_without_a_suggestion(
    tmp_path: Path,
) -> None:
    controller = _Controller(tmp_path)
    session = _SessionClient(controller)
    session.turn = (
        lambda **kwargs: HermesTurn(  # type: ignore[method-assign]
            session_id="description-session",
            reply=('{"status":"error","error":' '"sources/M01.jpg was unavailable"}'),
        )
    )
    retired_sessions: list[str] = []
    service = _description_service(
        controller,
        session,
        retired_sessions=retired_sessions,
    )

    with pytest.raises(HermesTurnFailed, match="could not inspect the image"):
        service.suggest(
            "wxpost-test",
            expected_manifest_version=4,
            source_id="M01",
            current_description="",
        )
    assert retired_sessions == ["description-session"]


def test_description_service_retires_a_session_when_the_turn_fails(
    tmp_path: Path,
) -> None:
    controller = _Controller(tmp_path)
    session = _SessionClient(controller)

    def failing_turn(*, on_session_resolved, **_kwargs) -> HermesTurn:
        on_session_resolved("description-session")
        raise HermesUnavailable("connection lost")

    session.turn = failing_turn  # type: ignore[method-assign]
    retired_sessions: list[str] = []
    service = _description_service(
        controller,
        session,
        retired_sessions=retired_sessions,
    )

    with pytest.raises(HermesUnavailable, match="connection lost"):
        service.suggest(
            "wxpost-test",
            expected_manifest_version=4,
            source_id="M01",
            current_description="",
        )

    assert retired_sessions == ["description-session"]


def test_description_service_keeps_a_snapshot_suggestion_when_manifest_changes(
    tmp_path: Path,
) -> None:
    controller = _Controller(tmp_path)
    session = _SessionClient(controller)

    def changed_turn(**kwargs: str) -> HermesTurn:
        controller.context["manifest"]["manifestVersion"] = 5
        return HermesTurn(
            session_id="description-session",
            reply='{"status":"ok","description":"A meeting room."}',
        )

    session.turn = changed_turn  # type: ignore[method-assign]
    service = _description_service(controller, session)

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
            reply='{"status":"ok","description":"A meeting room."}',
        )

    session.turn = changed_turn  # type: ignore[method-assign]
    service = _description_service(controller, session)

    with pytest.raises(VersionConflict, match="current manifest version is 5"):
        service.suggest(
            "wxpost-test",
            expected_manifest_version=4,
            source_id="M01",
            current_description="",
        )


def test_description_service_uses_one_turn_lock_per_source(
    tmp_path: Path,
) -> None:
    controller = _Controller(tmp_path)
    session = _SessionClient(controller)
    service = _description_service(controller, session)

    assert service._turn_lock("workspace-a", "M01") is service._turn_lock(
        "workspace-a", "M01"
    )
    assert service._turn_lock("workspace-a", "M01") is not service._turn_lock(
        "workspace-a", "M02"
    )


def test_description_service_rejects_a_duplicate_turn_for_the_same_source(
    tmp_path: Path,
) -> None:
    controller = _Controller(tmp_path)
    session = _SessionClient(controller)
    service = _description_service(controller, session)
    turn_lock = service._turn_lock("wxpost-test", "M01")
    turn_lock.acquire()
    try:
        with pytest.raises(InvalidRequest, match="already being generated"):
            service.suggest(
                "wxpost-test",
                expected_manifest_version=4,
                source_id="M01",
                current_description="",
            )
    finally:
        turn_lock.release()
    assert service._turn_lock("workspace-a", "M01") is not service._turn_lock(
        "workspace-b", "M01"
    )
