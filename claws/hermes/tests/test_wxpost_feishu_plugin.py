from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import sys
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace

import yaml
import pytest


PLUGIN_PATH = (
    Path(__file__).parents[1]
    / "wxpost_profile"
    / "plugins"
    / "soarhigh-wxpost-navigation"
    / "__init__.py"
)
PLUGIN_MANIFEST_PATH = PLUGIN_PATH.with_name("plugin.yaml")


def _load_plugin(monkeypatch):
    gateway = ModuleType("gateway")
    session_context = ModuleType("gateway.session_context")
    session_context.get_session_env = lambda _name: ""
    monkeypatch.setitem(sys.modules, "gateway", gateway)
    monkeypatch.setitem(sys.modules, "gateway.session_context", session_context)
    spec = importlib.util.spec_from_file_location(
        "wxpost_navigation_plugin", PLUGIN_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Platform(Enum):
    FEISHU = "feishu"
    API = "api_server"


def test_plugin_manifest_declares_every_registered_tool(monkeypatch) -> None:
    plugin = _load_plugin(monkeypatch)
    manifest = yaml.safe_load(PLUGIN_MANIFEST_PATH.read_text(encoding="utf-8"))

    assert set(manifest["provides_tools"]) == set(plugin.SCHEMAS) | set(
        plugin.CURRENT_SCHEMAS
    )
    assert set(manifest["hooks"]) == {
        "pre_gateway_dispatch",
        "pre_tool_call",
        "on_session_reset",
    }


def test_session_reset_queues_only_the_old_feishu_session(
    monkeypatch,
) -> None:
    plugin = _load_plugin(monkeypatch)
    monkeypatch.setenv("WXPOST_SERVICE_TOKEN", "service-token")
    monkeypatch.setenv(
        "WXPOST_CONTROLLER_BASE_URL",
        "http://controller.internal:8787",
    )
    requests = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def open_request(request, timeout):
        requests.append((request, timeout))
        return Response()

    plugin.hermes_hooks.urlopen = open_request

    plugin.hermes_hooks.retire_reset_feishu_session(
        platform="feishu",
        reason="new_session",
        old_session_id="old-session",
        new_session_id="new-session",
    )
    plugin.hermes_hooks.retire_reset_feishu_session(
        platform="api_server",
        reason="new_session",
        old_session_id="web-old-session",
        new_session_id="web-new-session",
    )

    assert len(requests) == 1
    request, timeout = requests[0]
    assert request.full_url == "http://controller.internal:8787/sessions/retire"
    assert request.get_header("Authorization") == "Bearer service-token"
    assert json.loads(request.data) == {"sessionId": "old-session"}
    assert timeout == 3


def test_plugin_registers_the_session_reset_hook(monkeypatch) -> None:
    plugin = _load_plugin(monkeypatch)
    hooks = {}

    class Context:
        def register_hook(self, name, callback):
            hooks[name] = callback

        def register_tool(self, **_kwargs):
            return None

    plugin.register(Context())

    assert hooks == {
        "pre_gateway_dispatch": plugin.hermes_hooks.prepare_feishu_event,
        "pre_tool_call": plugin.hermes_hooks.guard_feishu_writes,
        "on_session_reset": plugin.hermes_hooks.retire_reset_feishu_session,
    }


def test_current_tools_resolve_the_exact_workspace_from_session_cwd(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plugin = _load_plugin(monkeypatch)
    monkeypatch.setenv("WXPOST_WORKSPACE_ROOT", str(tmp_path))
    controller = plugin.navigation_tools.WorkspaceController(str(tmp_path))
    context = controller.create_workspace(
        meeting_id=None,
        editorial={
            "articleType": "custom",
            "customArticleType": "Test article",
            "writingApproach": "chronological",
            "transcript": "",
            "extraNotes": "",
            "writingGuidance": "",
            "voiceTone": {"presets": [], "customProfiles": []},
        },
        created_by={"id": "member", "name": "Member"},
    )
    workspace_id = context["workspaceId"]
    runtime_cwd = ModuleType("agent.runtime_cwd")
    runtime_cwd.resolve_agent_cwd = lambda: tmp_path / "inbox" / workspace_id
    agent = ModuleType("agent")
    monkeypatch.setitem(sys.modules, "agent", agent)
    monkeypatch.setitem(sys.modules, "agent.runtime_cwd", runtime_cwd)

    report = json.loads(
        plugin.navigation_tools.handle_current(
            "wxpost_get_current_workspace_report", {}
        )
    )

    assert report["workspaceId"] == workspace_id
    assert (
        "workspace_id"
        not in plugin.CURRENT_SCHEMAS["wxpost_get_current_workspace_report"][
            "parameters"
        ]["properties"]
    )


def test_current_save_tools_do_not_expose_operation_id(monkeypatch) -> None:
    plugin = _load_plugin(monkeypatch)

    for name in ("wxpost_save_current_draft", "wxpost_edit_current_draft"):
        parameters = plugin.CURRENT_SCHEMAS[name]["parameters"]
        assert "operation_id" not in parameters["properties"]
        assert "operationId" not in parameters["properties"]
        assert "operation_id" not in parameters.get("required", [])


def _bound_workspace(plugin, tmp_path, monkeypatch) -> str:
    monkeypatch.setenv("WXPOST_WORKSPACE_ROOT", str(tmp_path))
    controller = plugin.navigation_tools.WorkspaceController(str(tmp_path))
    context = controller.create_workspace(
        meeting_id=None,
        editorial={
            "articleType": "custom",
            "customArticleType": "Test article",
            "writingApproach": "chronological",
            "transcript": "",
            "extraNotes": "",
            "writingGuidance": "",
            "voiceTone": {"presets": [], "customProfiles": []},
        },
        created_by={"id": "member", "name": "Member"},
    )
    workspace_id = context["workspaceId"]
    runtime_cwd = ModuleType("agent.runtime_cwd")
    runtime_cwd.resolve_agent_cwd = lambda: tmp_path / "inbox" / workspace_id
    monkeypatch.setitem(sys.modules, "agent", ModuleType("agent"))
    monkeypatch.setitem(sys.modules, "agent.runtime_cwd", runtime_cwd)
    return workspace_id


def test_current_edit_rejects_a_model_supplied_operation_id(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plugin = _load_plugin(monkeypatch)
    _bound_workspace(plugin, tmp_path, monkeypatch)

    with pytest.raises(RuntimeError, match="invalid current-workspace tool input"):
        plugin.navigation_tools.handle_current(
            "wxpost_edit_current_draft",
            {
                "expectedManifestVersion": 1,
                "expectedDraftVersion": 1,
                "operationId": "draft-" + "9" * 32,
                "edits": [{"type": "replaceMetadata", "field": "title", "value": "x"}],
            },
        )


def test_current_edit_requires_an_active_bound_operation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plugin = _load_plugin(monkeypatch)
    _bound_workspace(plugin, tmp_path, monkeypatch)

    with pytest.raises(RuntimeError, match="no Draft operation is active"):
        plugin.navigation_tools.handle_current(
            "wxpost_edit_current_draft",
            {
                "expectedManifestVersion": 1,
                "expectedDraftVersion": 1,
                "edits": [{"type": "replaceMetadata", "field": "title", "value": "x"}],
            },
        )


def _start_running_operation(
    workspace_root: Path,
    workspace_id: str,
    operation_id: str,
):
    from wxpost_controller.draft_store import HermesDraftStore

    store = HermesDraftStore(workspace_root)
    store.start_operation(
        workspace_id,
        operation_id,
        request_fingerprint="fingerprint",
        member_message="Tighten the opening.",
        selected_text=None,
        expected_manifest_version=1,
        expected_draft_version=0,
    )
    return store


def test_bound_operation_id_reads_the_running_operation_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plugin = _load_plugin(monkeypatch)
    workspace_id = _bound_workspace(plugin, tmp_path, monkeypatch)
    controller = plugin.navigation_tools.WorkspaceController(str(tmp_path))

    with pytest.raises(
        plugin.navigation_tools.InvalidRequest,
        match="no Draft operation is active",
    ):
        plugin.navigation_tools._bound_operation_id(controller, workspace_id)

    operation_id = "draft-" + "5" * 32
    store = _start_running_operation(tmp_path, workspace_id, operation_id)
    assert (
        plugin.navigation_tools._bound_operation_id(controller, workspace_id)
        == operation_id
    )

    # A settled operation releases the binding: no later tool call can
    # attribute a write to a finished operation.
    store.fail_operation(
        operation_id,
        error={"code": "hermes_turn_failed", "message": "stopped"},
    )
    with pytest.raises(
        plugin.navigation_tools.InvalidRequest,
        match="no Draft operation is active",
    ):
        plugin.navigation_tools._bound_operation_id(controller, workspace_id)


def test_pre_tool_guard_verifies_workspace_id_on_bound_web_sessions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A web Draft session is bound to one workspace via its cwd. Raw
    workspace-write tools must target exactly that workspace — the model's
    workspace_id argument is verified, not trusted. Reads and correctly
    targeted writes pass through unchanged."""

    plugin = _load_plugin(monkeypatch)
    workspace_id = _bound_workspace(plugin, tmp_path, monkeypatch)
    plugin.hermes_hooks.get_session_env = lambda _name: ""

    for tool_name in (
        "wxpost_save_draft",
        "mcp__soarhigh_wxpost__wxpost_edit_draft",
        "wxpost_update_sources",
    ):
        wrong = plugin.hermes_hooks.guard_feishu_writes(
            tool_name=tool_name,
            args={"workspace_id": "wxpost-somewhere-else"},
        )
        assert wrong["action"] == "block"
        assert workspace_id in wrong["message"]
        assert "No workspace data was changed" in wrong["message"]

        assert (
            plugin.hermes_hooks.guard_feishu_writes(
                tool_name=tool_name,
                args={"workspace_id": workspace_id},
            )
            is None
        )

    # Reads and the bound current tools are never intercepted.
    for tool_name in ("wxpost_get_context", "wxpost_save_current_draft"):
        assert (
            plugin.hermes_hooks.guard_feishu_writes(tool_name=tool_name, args={})
            is None
        )


def test_pre_tool_guard_ignores_web_sessions_without_a_workspace_cwd(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Non-workspace sessions (description one-shots, unrelated api
    sessions) keep full raw-tool behavior: the workspace guard only engages
    when the session cwd is a workspace directory."""

    plugin = _load_plugin(monkeypatch)
    monkeypatch.setenv("WXPOST_WORKSPACE_ROOT", str(tmp_path))
    runtime_cwd = ModuleType("agent.runtime_cwd")
    runtime_cwd.resolve_agent_cwd = lambda: tmp_path / "not-a-workspace"
    monkeypatch.setitem(sys.modules, "agent", ModuleType("agent"))
    monkeypatch.setitem(sys.modules, "agent.runtime_cwd", runtime_cwd)
    plugin.hermes_hooks.get_session_env = lambda _name: ""

    assert (
        plugin.hermes_hooks.guard_feishu_writes(
            tool_name="wxpost_save_draft",
            args={"workspace_id": "wxpost-anything"},
        )
        is None
    )


def test_raw_save_tools_prefer_the_controller_bound_operation_id(
    tmp_path: Path,
) -> None:
    """While a Controller-run Draft turn is in flight (running operation
    recorded), a raw save call is attributed to that operation — a
    model-minted id must not misattribute the write. With no running
    operation (idle Feishu workspace, or no Controller store at all) the
    model-supplied id passes through unchanged."""

    from wxpost_controller import mcp_factory

    class Controller:
        workspace_root = tmp_path
        inbox_root = tmp_path / "inbox"

    bound = "draft-" + "7" * 32
    minted = "generate-wxpost-raw-v1"
    assert (
        mcp_factory._trusted_operation_id(Controller(), "wxpost-raw", minted) == minted
    )

    store = _start_running_operation(tmp_path, "wxpost-raw", bound)
    assert (
        mcp_factory._trusted_operation_id(Controller(), "wxpost-raw", minted) == bound
    )

    # Once the operation settles, Feishu saves keep their own ids.
    store.complete_operation(
        bound,
        result={
            "reply": "Saved.",
            "draftChanged": True,
            "draftVersion": 1,
            "steps": [],
        },
    )
    assert (
        mcp_factory._trusted_operation_id(Controller(), "wxpost-raw", minted) == minted
    )


def test_current_tools_reject_a_session_cwd_outside_the_workspace_inbox(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plugin = _load_plugin(monkeypatch)
    monkeypatch.setenv("WXPOST_WORKSPACE_ROOT", str(tmp_path))
    outside = tmp_path / "not-a-workspace"
    outside.mkdir()
    runtime_cwd = ModuleType("agent.runtime_cwd")
    runtime_cwd.resolve_agent_cwd = lambda: outside
    monkeypatch.setitem(sys.modules, "agent", ModuleType("agent"))
    monkeypatch.setitem(sys.modules, "agent.runtime_cwd", runtime_cwd)

    with pytest.raises(RuntimeError, match="not bound"):
        plugin.navigation_tools.handle_current("wxpost_get_current_context", {})


def test_prepare_feishu_event_exposes_message_and_attachment_metadata(
    tmp_path,
    monkeypatch,
) -> None:
    plugin = _load_plugin(monkeypatch)
    monkeypatch.setenv("WXPOST_WORKSPACE_ROOT", str(tmp_path))
    source = SimpleNamespace(platform=Platform.FEISHU, message_id=None)
    raw_message = SimpleNamespace(
        event=SimpleNamespace(
            message=SimpleNamespace(
                content=json.dumps(
                    {"file_key": "file-key", "file_name": "club-photo.png"}
                )
            )
        )
    )
    event = SimpleNamespace(
        source=source,
        message_id="om_message",
        media_urls=["/opt/data/profiles/wxpost/cache/images/image.png"],
        media_types=["image/png"],
        raw_message=raw_message,
        text="",
    )

    plugin.hermes_hooks.prepare_feishu_event(
        event=event,
        gateway=SimpleNamespace(
            _session_key_for_source=lambda _source: ("agent:wxpost:feishu:dm:oc_chat")
        ),
    )

    assert source.message_id == "om_message"
    assert "conversation-only input" in event.text
    assert "inspect them and answer questions about them normally" in event.text
    assert "Do not import them" in event.text
    assert "enter editing mode with /editing" in event.text
    assert '"sourcePath": "/opt/data/profiles/wxpost/cache/images/image.png"' in (
        event.text
    )
    assert '"filename": "club-photo.png"' in event.text
    assert '"mimeType": "image/png"' in event.text
    assert "read-only" in event.text
    assert "read the active workspace report" in event.text

    scope_key = "agent:wxpost:feishu:dm:oc_chat"
    plugin.hermes_hooks._state_store().set_interaction_mode(scope_key, "editing")
    event.message_id = "om_second_message"
    event.text = ""
    plugin.hermes_hooks.prepare_feishu_event(
        event=event,
        gateway=SimpleNamespace(_session_key_for_source=lambda _source: scope_key),
    )

    assert "wxpost_import_feishu_attachments" in event.text
    assert "conversation-only input" not in event.text
    assert "editing mode" in event.text


def test_prepare_event_does_not_expose_navigation_metadata_on_web(
    monkeypatch,
) -> None:
    plugin = _load_plugin(monkeypatch)
    source = SimpleNamespace(platform=Platform.API, message_id=None)
    event = SimpleNamespace(
        source=source,
        message_id="web-message",
        media_urls=["/tmp/image.png"],
        media_types=["image/png"],
        raw_message=None,
        text="member text",
    )

    plugin.hermes_hooks.prepare_feishu_event(event=event)

    assert source.message_id is None
    assert event.text == "member text"


def test_feishu_mode_commands_switch_immediately_and_new_resets_readonly(
    tmp_path,
    monkeypatch,
) -> None:
    plugin = _load_plugin(monkeypatch)
    monkeypatch.setenv("WXPOST_WORKSPACE_ROOT", str(tmp_path))
    scope_key = "agent:wxpost:feishu:dm:oc_chat"
    gateway = SimpleNamespace(_session_key_for_source=lambda _source: scope_key)
    source = SimpleNamespace(
        platform=Platform.FEISHU,
        message_id=None,
        user_id="ou_member",
    )

    def dispatch(text, message_id):
        return plugin.hermes_hooks.prepare_feishu_event(
            event=SimpleNamespace(
                source=source,
                message_id=message_id,
                media_urls=[],
                media_types=[],
                raw_message=None,
                text=text,
            ),
            gateway=gateway,
        )

    switched = dispatch("/editing", "om_editing_request")
    assert "switched this Feishu conversation to editing mode" in switched["text"]
    assert plugin.hermes_hooks._state_store().interaction_mode(scope_key) == "editing"

    repeated = dispatch("/editing", "om_editing_repeat")
    assert "already in editing mode" in repeated["text"]
    assert plugin.hermes_hooks._state_store().interaction_mode(scope_key) == "editing"

    readonly = dispatch("/readonly", "om_readonly")
    assert "switched this Feishu conversation to read-only" in readonly["text"]
    assert plugin.hermes_hooks._state_store().interaction_mode(scope_key) == "readonly"

    plugin.hermes_hooks._state_store().set_interaction_mode(scope_key, "editing")
    assert dispatch("/new", "om_new") is None
    assert plugin.hermes_hooks._state_store().interaction_mode(scope_key) == "readonly"


def test_pre_tool_guard_blocks_only_feishu_writes_in_readonly_mode(
    tmp_path,
    monkeypatch,
) -> None:
    plugin = _load_plugin(monkeypatch)
    monkeypatch.setenv("WXPOST_WORKSPACE_ROOT", str(tmp_path))
    scope_key = "agent:wxpost:feishu:dm:oc_chat"
    environment = {
        "HERMES_SESSION_PLATFORM": "feishu",
        "HERMES_SESSION_KEY": scope_key,
    }
    plugin.hermes_hooks.get_session_env = lambda name: environment.get(name, "")

    assert (
        plugin.hermes_hooks.guard_feishu_writes(tool_name="wxpost_get_context", args={})
        is None
    )
    blocked = plugin.hermes_hooks.guard_feishu_writes(
        tool_name="mcp__soarhigh_wxpost__wxpost_edit_draft", args={}
    )
    assert blocked["action"] == "block"
    assert "No workspace data was changed" in blocked["message"]
    assert (
        plugin.hermes_hooks.guard_feishu_writes(
            tool_name="wxpost_describe_material", args={"confirmed": False}
        )
        is None
    )
    assert (
        plugin.hermes_hooks.guard_feishu_writes(
            tool_name="wxpost_describe_material", args={"confirmed": True}
        )["action"]
        == "block"
    )

    plugin.hermes_hooks._state_store().set_interaction_mode(scope_key, "editing")
    plugin.hermes_hooks._state_store().bind(scope_key, "wxpost-active")
    assert (
        plugin.hermes_hooks.guard_feishu_writes(
            tool_name="wxpost_edit_draft",
            args={"workspace_id": "wxpost-active"},
        )
        is None
    )
    wrong_workspace = plugin.hermes_hooks.guard_feishu_writes(
        tool_name="wxpost_edit_draft",
        args={"workspace_id": "wxpost-other"},
    )
    assert wrong_workspace["action"] == "block"
    assert "does not match" in wrong_workspace["message"]

    missing_workspace = plugin.hermes_hooks.guard_feishu_writes(
        tool_name="wxpost_update_sources",
        args={},
    )
    assert missing_workspace["action"] == "block"

    # Navigation-owned writes resolve or confirm their target themselves.
    assert (
        plugin.hermes_hooks.guard_feishu_writes(
            tool_name="wxpost_import_feishu_attachments",
            args={"attachments": []},
        )
        is None
    )

    environment["HERMES_SESSION_PLATFORM"] = "api_server"
    assert (
        plugin.hermes_hooks.guard_feishu_writes(tool_name="wxpost_edit_draft", args={})
        is None
    )


def test_pre_tool_guard_covers_every_declared_feishu_write(
    tmp_path,
    monkeypatch,
) -> None:
    plugin = _load_plugin(monkeypatch)
    monkeypatch.setenv("WXPOST_WORKSPACE_ROOT", str(tmp_path))
    environment = {
        "HERMES_SESSION_PLATFORM": "feishu",
        "HERMES_SESSION_KEY": "agent:wxpost:feishu:dm:oc_chat",
    }
    plugin.hermes_hooks.get_session_env = lambda name: environment.get(name, "")

    for tool_name in plugin.hermes_hooks.FEISHU_WRITE_TOOLS:
        blocked = plugin.hermes_hooks.guard_feishu_writes(
            tool_name=f"mcp__soarhigh_wxpost__{tool_name}",
            args={},
        )
        assert blocked is not None, tool_name
        assert blocked["action"] == "block", tool_name


def test_pre_tool_guard_scopes_every_raw_feishu_write_to_active_workspace(
    tmp_path,
    monkeypatch,
) -> None:
    plugin = _load_plugin(monkeypatch)
    monkeypatch.setenv("WXPOST_WORKSPACE_ROOT", str(tmp_path))
    scope_key = "agent:wxpost:feishu:dm:oc_chat"
    environment = {
        "HERMES_SESSION_PLATFORM": "feishu",
        "HERMES_SESSION_KEY": scope_key,
    }
    plugin.hermes_hooks.get_session_env = lambda name: environment.get(name, "")
    store = plugin.hermes_hooks._state_store()
    store.set_interaction_mode(scope_key, "editing")
    store.bind(scope_key, "wxpost-active")

    for tool_name in plugin.hermes_hooks.FEISHU_ACTIVE_WORKSPACE_WRITES:
        assert (
            plugin.hermes_hooks.guard_feishu_writes(
                tool_name=f"mcp__soarhigh_wxpost__{tool_name}",
                args={"workspace_id": "wxpost-active"},
            )
            is None
        ), tool_name
        blocked = plugin.hermes_hooks.guard_feishu_writes(
            tool_name=f"mcp__soarhigh_wxpost__{tool_name}",
            args={"workspace_id": "wxpost-other"},
        )
        assert blocked is not None, tool_name
        assert blocked["action"] == "block", tool_name


def test_feishu_destructive_tools_reject_missing_member_identity(monkeypatch) -> None:
    plugin = _load_plugin(monkeypatch)
    environment = {
        "HERMES_SESSION_PLATFORM": "feishu",
        "HERMES_SESSION_KEY": "agent:wxpost:feishu:group:oc_chat",
        "HERMES_SESSION_MESSAGE_ID": "om_message",
    }
    plugin.navigation_tools.get_session_env = lambda name: environment.get(name, "")
    plugin.navigation_tools.FeishuNavigation = lambda: object()

    with pytest.raises(RuntimeError, match="member identity is unavailable"):
        plugin.navigation_tools.handle_navigation(
            "wxpost_delete_workspace",
            {"confirmed": False},
        )


def test_navigation_workspace_errors_fail_the_tool(monkeypatch) -> None:
    plugin = _load_plugin(monkeypatch)
    environment = {
        "HERMES_SESSION_PLATFORM": "feishu",
        "HERMES_SESSION_KEY": "agent:wxpost:feishu:dm:oc_chat",
        "HERMES_SESSION_MESSAGE_ID": "om_message",
        "HERMES_SESSION_USER_ID": "ou_member",
    }
    plugin.navigation_tools.get_session_env = lambda name: environment.get(name, "")

    class Navigation:
        def get_active_workspace(self, _scope_key):
            raise plugin.navigation_tools.InvalidRequest("workspace is unavailable")

    plugin.navigation_tools.FeishuNavigation = Navigation

    with pytest.raises(RuntimeError, match="workspace is unavailable"):
        plugin.navigation_tools.handle_navigation("wxpost_get_active_workspace", {})


def test_material_library_workspace_errors_fail_the_tool(monkeypatch) -> None:
    plugin = _load_plugin(monkeypatch)
    environment = {
        "HERMES_SESSION_PLATFORM": "feishu",
        "HERMES_SESSION_KEY": "agent:wxpost:feishu:dm:oc_chat",
        "HERMES_SESSION_USER_ID": "ou_member",
        "HERMES_SESSION_CHAT_ID": "oc_chat",
    }
    plugin.navigation_tools.get_session_env = lambda name: environment.get(name, "")
    plugin.feishu_delivery.get_session_env = lambda name: environment.get(name, "")

    class Navigation:
        def get_material_library(self, _scope_key):
            raise plugin.feishu_delivery.InvalidRequest("workspace is unavailable")

    plugin.feishu_delivery.FeishuNavigation = Navigation

    with pytest.raises(RuntimeError, match="workspace is unavailable"):
        asyncio.run(plugin.feishu_delivery.show_material_library({}))


def test_show_material_library_sends_every_image_and_video_natively(
    monkeypatch,
) -> None:
    plugin = _load_plugin(monkeypatch)
    environment = {
        "HERMES_SESSION_PLATFORM": "feishu",
        "HERMES_SESSION_KEY": "agent:wxpost:feishu:dm:oc_chat",
        "HERMES_SESSION_USER_ID": "ou_member",
        "HERMES_SESSION_CHAT_ID": "oc_chat",
        "HERMES_SESSION_THREAD_ID": "omt_thread",
    }
    plugin.navigation_tools.get_session_env = lambda name: environment.get(name, "")
    plugin.feishu_delivery.get_session_env = lambda name: environment.get(name, "")
    materials = [
        {
            "id": "M01",
            "kind": "image",
            "filename": "candidate.jpg",
            "candidate": True,
            "imported": False,
            "included": False,
            "description": "A candidate image.",
            "usedInDraft": False,
            "usedAsCover": False,
        },
        {
            "id": "M02",
            "kind": "video",
            "filename": "imported.mp4",
            "candidate": False,
            "imported": True,
            "included": True,
            "description": "An imported video.",
            "usedInDraft": True,
            "usedAsCover": False,
        },
    ]

    class Navigation:
        def get_material_library(self, scope_key):
            assert scope_key == environment["HERMES_SESSION_KEY"]
            return {
                "workspaceId": "wxpost-abc",
                "report": {
                    "counts": {"total": 2, "candidates": 1, "imported": 1},
                    "materials": materials,
                },
                "media": [
                    {
                        "source": {"id": "M01"},
                        "filename": "candidate.jpg",
                        "mimeType": "image/jpeg",
                        "data": b"image",
                    },
                    {
                        "source": {"id": "M02"},
                        "filename": "imported.mp4",
                        "mimeType": "video/mp4",
                        "data": b"video",
                    },
                ],
            }

    plugin.feishu_delivery.FeishuNavigation = Navigation
    sent: list[dict] = []

    async def sender(config, chat_id, message, **kwargs):
        path = Path(kwargs["media_files"][0][0])
        assert path.is_file()
        sent.append(
            {
                "config": config,
                "chatId": chat_id,
                "message": message,
                "filename": path.name,
                "data": path.read_bytes(),
                "threadId": kwargs["thread_id"],
            }
        )
        return {"success": True}

    gateway_config = ModuleType("gateway.config")
    gateway_config.Platform = Platform
    gateway_config.load_gateway_config = lambda: SimpleNamespace(
        platforms={Platform.FEISHU: "feishu-config"}
    )
    platform_registry_module = ModuleType("gateway.platform_registry")
    platform_registry_module.platform_registry = SimpleNamespace(
        get=lambda name: SimpleNamespace(standalone_sender_fn=sender)
    )
    plugins_module = ModuleType("hermes_cli.plugins")
    plugins_module.discover_plugins = lambda: None
    monkeypatch.setitem(sys.modules, "gateway.config", gateway_config)
    monkeypatch.setitem(
        sys.modules, "gateway.platform_registry", platform_registry_module
    )
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", plugins_module)

    result = json.loads(asyncio.run(plugin.feishu_delivery.show_material_library({})))

    assert result == {
        "workspaceId": "wxpost-abc",
        "displayed": 2,
        "candidates": 1,
        "imported": 1,
    }
    assert [(item["filename"], item["data"]) for item in sent] == [
        ("candidate.jpg", b"image"),
        ("imported.mp4", b"video"),
    ]
    assert all(item["chatId"] == "oc_chat" for item in sent)
    assert all(item["threadId"] == "omt_thread" for item in sent)
    assert "Candidate" in sent[0]["message"]
    assert "Imported · Included · In Draft" in sent[1]["message"]
    assert not Path(sent[0]["filename"]).is_absolute()


def test_show_material_library_falls_back_to_a_document_for_video(
    monkeypatch,
) -> None:
    plugin = _load_plugin(monkeypatch)
    environment = {
        "HERMES_SESSION_PLATFORM": "feishu",
        "HERMES_SESSION_KEY": "agent:wxpost:feishu:dm:oc_chat",
        "HERMES_SESSION_USER_ID": "ou_member",
        "HERMES_SESSION_CHAT_ID": "oc_chat",
    }
    plugin.navigation_tools.get_session_env = lambda name: environment.get(name, "")
    plugin.feishu_delivery.get_session_env = lambda name: environment.get(name, "")

    class Navigation:
        def get_material_library(self, _scope_key):
            return {
                "workspaceId": "wxpost-abc",
                "report": {
                    "counts": {"total": 1, "candidates": 0, "imported": 1},
                    "materials": [
                        {
                            "id": "M01",
                            "kind": "video",
                            "filename": "clip.mp4",
                            "candidate": False,
                            "imported": True,
                            "included": False,
                            "description": "A short clip.",
                            "usedInDraft": False,
                            "usedAsCover": False,
                        }
                    ],
                },
                "media": [
                    {
                        "source": {"id": "M01"},
                        "filename": "clip.mp4",
                        "mimeType": "video/mp4",
                        "data": b"video",
                    }
                ],
            }

    plugin.feishu_delivery.FeishuNavigation = Navigation
    attempts: list[str] = []

    async def sender(_config, _chat_id, _message, **kwargs):
        path = Path(kwargs["media_files"][0][0])
        attempts.append(path.name)
        return (
            {"error": "native preview failed"}
            if path.suffix == ".mp4"
            else {"success": True}
        )

    gateway_config = ModuleType("gateway.config")
    gateway_config.Platform = Platform
    gateway_config.load_gateway_config = lambda: SimpleNamespace(
        platforms={Platform.FEISHU: "feishu-config"}
    )
    platform_registry_module = ModuleType("gateway.platform_registry")
    platform_registry_module.platform_registry = SimpleNamespace(
        get=lambda name: SimpleNamespace(standalone_sender_fn=sender)
    )
    plugins_module = ModuleType("hermes_cli.plugins")
    plugins_module.discover_plugins = lambda: None
    monkeypatch.setitem(sys.modules, "gateway.config", gateway_config)
    monkeypatch.setitem(
        sys.modules, "gateway.platform_registry", platform_registry_module
    )
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", plugins_module)

    result = json.loads(asyncio.run(plugin.feishu_delivery.show_material_library({})))

    assert result["displayed"] == 1
    assert attempts == ["clip.mp4", "clip.mp4.bin"]


def test_send_draft_preview_image_uses_canonical_link_and_native_feishu_media(
    monkeypatch,
) -> None:
    plugin = _load_plugin(monkeypatch)
    environment = {
        "HERMES_SESSION_PLATFORM": "feishu",
        "HERMES_SESSION_KEY": "agent:wxpost:feishu:dm:oc_chat",
        "HERMES_SESSION_USER_ID": "ou_member",
        "HERMES_SESSION_CHAT_ID": "oc_chat",
        "HERMES_SESSION_THREAD_ID": "omt_thread",
    }
    plugin.navigation_tools.get_session_env = lambda name: environment.get(name, "")
    plugin.feishu_delivery.get_session_env = lambda name: environment.get(name, "")
    requested: list[tuple[str, int | None]] = []

    class Navigation:
        def create_draft_preview_link(self, scope_key, *, draft_version=None):
            requested.append((scope_key, draft_version))
            return {
                "workspaceId": "wxpost-abc",
                "draftVersion": 8,
                "previewUrl": "https://soarhigh.example/private-token",
            }

    plugin.feishu_delivery.FeishuNavigation = Navigation

    async def capture(url, destination):
        assert url == "https://soarhigh.example/private-token"
        destination.write_bytes(b"png")

    def compress(source, destination):
        assert source.read_bytes() == b"png"
        destination.write_bytes(b"jpeg")

    monkeypatch.setattr(plugin.feishu_delivery, "capture_full_page", capture)
    monkeypatch.setattr(plugin.feishu_delivery, "compress_preview_image", compress)
    sent: list[dict] = []

    async def sender(config, chat_id, message, **kwargs):
        path = Path(kwargs["media_files"][0][0])
        sent.append(
            {
                "config": config,
                "chatId": chat_id,
                "message": message,
                "data": path.read_bytes(),
                "threadId": kwargs["thread_id"],
            }
        )
        return {"success": True}

    gateway_config = ModuleType("gateway.config")
    gateway_config.Platform = Platform
    gateway_config.load_gateway_config = lambda: SimpleNamespace(
        platforms={Platform.FEISHU: "feishu-config"}
    )
    platform_registry_module = ModuleType("gateway.platform_registry")
    platform_registry_module.platform_registry = SimpleNamespace(
        get=lambda name: SimpleNamespace(standalone_sender_fn=sender)
    )
    plugins_module = ModuleType("hermes_cli.plugins")
    plugins_module.discover_plugins = lambda: None
    monkeypatch.setitem(sys.modules, "gateway.config", gateway_config)
    monkeypatch.setitem(
        sys.modules, "gateway.platform_registry", platform_registry_module
    )
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", plugins_module)

    result = json.loads(
        asyncio.run(
            plugin.feishu_delivery.send_draft_preview_image({"draft_version": 8})
        )
    )

    assert requested == [(environment["HERMES_SESSION_KEY"], 8)]
    assert result == {
        "workspaceId": "wxpost-abc",
        "draftVersion": 8,
        "sent": True,
    }
    assert sent == [
        {
            "config": "feishu-config",
            "chatId": "oc_chat",
            "message": "Draft v8 · Full-page preview",
            "data": b"jpeg",
            "threadId": "omt_thread",
        }
    ]


def test_capture_full_page_uses_mobile_viewport_and_crops_to_article(
    tmp_path: Path, monkeypatch
) -> None:
    plugin = _load_plugin(monkeypatch)
    monkeypatch.setenv("WXPOST_CHROMIUM_PATH", "/test/chrome-headless-shell")
    calls: list[tuple[str, ...]] = []
    crops: list[tuple[int, int, int, int]] = []
    destination = tmp_path / "draft.png"

    async def run_browser(*args: str, timeout: int = 120) -> str:
        del timeout
        calls.append(args)
        if args[-1] == plugin.feishu_delivery._IMAGES_SETTLED_EXPRESSION:
            return json.dumps({"data": True})
        if args[-3:] == ("get", "box", '[data-testid="wxpost-article"]'):
            return json.dumps(
                {
                    "data": {
                        "x": 12,
                        "y": 20,
                        "width": 366,
                        "height": 800,
                    }
                }
            )
        if "screenshot" in args:
            Path(args[-1]).write_bytes(b"full-page")
        return ""

    monkeypatch.setattr(plugin.feishu_delivery, "run_browser", run_browser)

    class CroppedImage:
        def save(self, path, *, format):
            assert path == destination
            assert format == "PNG"

    class FullPageImage:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def crop(self, box):
            crops.append(box)
            return CroppedImage()

    pil_module = ModuleType("PIL")
    pil_module.Image = SimpleNamespace(open=lambda path: FullPageImage())
    monkeypatch.setitem(sys.modules, "PIL", pil_module)

    asyncio.run(
        plugin.feishu_delivery.capture_full_page(
            "https://soarhigh.example/temporary-preview", destination
        )
    )

    assert any(args[-4:] == ("set", "viewport", "390", "844") for args in calls)
    assert calls[0][2:4] == (
        "--executable-path",
        "/test/chrome-headless-shell",
    )
    assert crops == [(12, 20, 378, 820)]
    # Images are forced eager and polled to completion BEFORE the article box
    # is measured, so the crop reflects the final page height.
    eager_index = next(
        index
        for index, args in enumerate(calls)
        if "eval" in args and 'image.loading = "eager"' in args[-1]
    )
    settle_index = next(
        index
        for index, args in enumerate(calls)
        if args[-1] == plugin.feishu_delivery._IMAGES_SETTLED_EXPRESSION
    )
    box_index = next(
        index for index, args in enumerate(calls) if args[-2:-1] == ("box",)
    )
    assert eager_index < settle_index < box_index


def test_capture_full_page_polls_until_images_settle(
    tmp_path: Path, monkeypatch
) -> None:
    plugin = _load_plugin(monkeypatch)
    monkeypatch.setenv("WXPOST_CHROMIUM_PATH", "/test/chrome-headless-shell")
    monkeypatch.setattr(plugin.feishu_delivery, "_IMAGE_SETTLE_INTERVAL_SECONDS", 0)
    destination = tmp_path / "draft.png"
    settle_calls = 0

    async def run_browser(*args: str, timeout: int = 120) -> str:
        del timeout
        nonlocal settle_calls
        if args[-1] == plugin.feishu_delivery._IMAGES_SETTLED_EXPRESSION:
            settle_calls += 1
            return json.dumps({"data": settle_calls >= 3})
        if args[-3:] == ("get", "box", '[data-testid="wxpost-article"]'):
            return json.dumps({"data": {"x": 0, "y": 0, "width": 390, "height": 400}})
        if "screenshot" in args:
            Path(args[-1]).write_bytes(b"full-page")
        return ""

    monkeypatch.setattr(plugin.feishu_delivery, "run_browser", run_browser)

    class CroppedImage:
        def save(self, path, *, format):
            del path, format

    class FullPageImage:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def crop(self, box):
            del box
            return CroppedImage()

    pil_module = ModuleType("PIL")
    pil_module.Image = SimpleNamespace(open=lambda path: FullPageImage())
    monkeypatch.setitem(sys.modules, "PIL", pil_module)

    asyncio.run(
        plugin.feishu_delivery.capture_full_page(
            "https://soarhigh.example/temporary-preview", destination
        )
    )

    assert settle_calls == 3


def test_resolve_chromium_path_uses_override(monkeypatch) -> None:
    plugin = _load_plugin(monkeypatch)
    monkeypatch.setenv("WXPOST_CHROMIUM_PATH", "/custom/headless-shell")

    assert plugin.feishu_delivery.resolve_chromium_path() == "/custom/headless-shell"


def test_resolve_chromium_path_discovers_latest_hermes_browser(
    tmp_path: Path, monkeypatch
) -> None:
    plugin = _load_plugin(monkeypatch)
    monkeypatch.delenv("WXPOST_CHROMIUM_PATH", raising=False)
    monkeypatch.setenv("WXPOST_PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    old_browser = (
        tmp_path / "chromium_headless_shell-1228" / "chrome-linux" / "headless_shell"
    )
    current_browser = (
        tmp_path
        / "chromium_headless_shell-1234"
        / "chrome-headless-shell-linux64"
        / "chrome-headless-shell"
    )
    for browser in (old_browser, current_browser):
        browser.parent.mkdir(parents=True)
        browser.touch(mode=0o755)

    assert plugin.feishu_delivery.resolve_chromium_path() == str(current_browser)


def test_draft_preview_tool_sends_complete_link_without_returning_token(
    monkeypatch,
) -> None:
    plugin = _load_plugin(monkeypatch)
    environment = {
        "HERMES_SESSION_PLATFORM": "feishu",
        "HERMES_SESSION_KEY": "agent:wxpost:feishu:dm:oc_chat",
        "HERMES_SESSION_USER_ID": "ou_member",
        "HERMES_SESSION_CHAT_ID": "oc_chat",
        "HERMES_SESSION_THREAD_ID": "omt_thread",
    }
    plugin.navigation_tools.get_session_env = lambda name: environment.get(name, "")
    plugin.feishu_delivery.get_session_env = lambda name: environment.get(name, "")
    preview_url = "https://soarhigh.example/draft-preview/full.opaque.token"
    editor_url = "https://soarhigh.example/posts/wxposts/edit/abc?view=edit"

    class Navigation:
        def create_draft_preview_link(self, scope_key, *, draft_version=None):
            assert scope_key == environment["HERMES_SESSION_KEY"]
            assert draft_version == 8
            return {
                "workspaceId": "wxpost-abc",
                "draftVersion": 8,
                "previewUrl": preview_url,
                "editorUrl": editor_url,
            }

    plugin.feishu_delivery.FeishuNavigation = Navigation
    sent: list[dict] = []

    async def sender(config, chat_id, message, **kwargs):
        sent.append(
            {
                "config": config,
                "chatId": chat_id,
                "message": message,
                "threadId": kwargs["thread_id"],
            }
        )
        return {"success": True}

    gateway_config = ModuleType("gateway.config")
    gateway_config.Platform = Platform
    gateway_config.load_gateway_config = lambda: SimpleNamespace(
        platforms={Platform.FEISHU: "feishu-config"}
    )
    platform_registry_module = ModuleType("gateway.platform_registry")
    platform_registry_module.platform_registry = SimpleNamespace(
        get=lambda name: SimpleNamespace(standalone_sender_fn=sender)
    )
    plugins_module = ModuleType("hermes_cli.plugins")
    plugins_module.discover_plugins = lambda: None
    monkeypatch.setitem(sys.modules, "gateway.config", gateway_config)
    monkeypatch.setitem(
        sys.modules, "gateway.platform_registry", platform_registry_module
    )
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", plugins_module)

    result = json.loads(
        asyncio.run(
            plugin.feishu_delivery.send_draft_preview_link({"draft_version": 8})
        )
    )

    assert result == {
        "workspaceId": "wxpost-abc",
        "draftVersion": 8,
        "sent": True,
        "delivered": ["temporaryPreview", "draftEditor"],
    }
    assert sent == [
        {
            "config": "feishu-config",
            "chatId": "oc_chat",
            "message": (
                "Draft v8：\n"
                f"[临时预览]({preview_url}) · "
                f"[登录后继续编辑]({editor_url})\n"
                "提醒：网页登录后的 Draft Assistant 使用独立的 Web session，"
                "不会继承当前飞书对话；两边仍操作同一个 workspace 和 Draft。"
            ),
            "threadId": "omt_thread",
        }
    ]


@pytest.mark.parametrize(
    ("target", "url", "expected_message"),
    [
        (
            "materials",
            "https://soarhigh.example/posts/wxposts/edit/abc",
            "[在网页编辑素材](https://soarhigh.example/posts/wxposts/edit/abc)",
        ),
        (
            "draft",
            "https://soarhigh.example/posts/wxposts/edit/abc?view=edit",
            "[在网页编辑 Draft](https://soarhigh.example/posts/wxposts/edit/abc?view=edit)\n"
            "提醒：网页登录后的 Draft Assistant 使用独立的 Web session，"
            "不会继承当前飞书对话；两边仍操作同一个 workspace 和 Draft。",
        ),
    ],
)
def test_web_editor_tool_sends_the_requested_authenticated_link(
    monkeypatch, target, url, expected_message
) -> None:
    plugin = _load_plugin(monkeypatch)
    environment = {
        "HERMES_SESSION_PLATFORM": "feishu",
        "HERMES_SESSION_KEY": "agent:wxpost:feishu:dm:oc_chat",
        "HERMES_SESSION_USER_ID": "ou_member",
        "HERMES_SESSION_CHAT_ID": "oc_chat",
        "HERMES_SESSION_THREAD_ID": "omt_thread",
    }
    plugin.navigation_tools.get_session_env = lambda name: environment.get(name, "")
    plugin.feishu_delivery.get_session_env = lambda name: environment.get(name, "")

    class Navigation:
        def get_web_editor_link(self, scope_key, *, target):
            assert scope_key == environment["HERMES_SESSION_KEY"]
            return {"workspaceId": "wxpost-abc", "target": target, "url": url}

    plugin.feishu_delivery.FeishuNavigation = Navigation
    sent: list[dict] = []

    async def sender(config, chat_id, message, **kwargs):
        sent.append(
            {
                "config": config,
                "chatId": chat_id,
                "message": message,
                "threadId": kwargs["thread_id"],
            }
        )
        return {"success": True}

    gateway_config = ModuleType("gateway.config")
    gateway_config.Platform = Platform
    gateway_config.load_gateway_config = lambda: SimpleNamespace(
        platforms={Platform.FEISHU: "feishu-config"}
    )
    platform_registry_module = ModuleType("gateway.platform_registry")
    platform_registry_module.platform_registry = SimpleNamespace(
        get=lambda name: SimpleNamespace(standalone_sender_fn=sender)
    )
    plugins_module = ModuleType("hermes_cli.plugins")
    plugins_module.discover_plugins = lambda: None
    monkeypatch.setitem(sys.modules, "gateway.config", gateway_config)
    monkeypatch.setitem(
        sys.modules, "gateway.platform_registry", platform_registry_module
    )
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", plugins_module)

    result = json.loads(
        asyncio.run(plugin.feishu_delivery.send_web_editor_link({"target": target}))
    )

    assert result == {
        "workspaceId": "wxpost-abc",
        "target": target,
        "sent": True,
    }
    assert sent == [
        {
            "config": "feishu-config",
            "chatId": "oc_chat",
            "message": expected_message,
            "threadId": "omt_thread",
        }
    ]


def test_register_marks_native_material_delivery_as_async(monkeypatch) -> None:
    plugin = _load_plugin(monkeypatch)
    registrations: list[dict] = []
    ctx = SimpleNamespace(
        register_hook=lambda *_args: None,
        register_tool=lambda **kwargs: registrations.append(kwargs),
    )

    plugin.register(ctx)

    by_name = {item["name"]: item for item in registrations}
    assert by_name["wxpost_get_current_context"]["toolset"] == "wxpost_current"
    assert by_name["wxpost_list_workspaces"]["toolset"] == "wxpost_navigation"
    assert by_name["wxpost_show_material_library"]["is_async"] is True
    assert by_name["wxpost_describe_material"]["is_async"] is True
    assert by_name["wxpost_get_draft_preview"]["is_async"] is True
    assert by_name["wxpost_send_web_editor_link"]["is_async"] is True
    assert by_name["wxpost_send_draft_preview_image"]["is_async"] is True
    assert inspect.iscoroutinefunction(by_name["wxpost_describe_material"]["handler"])
    plugin.navigation_tools.handle_navigation = lambda name, args: json.dumps(
        {"name": name, "args": args}
    )
    assert json.loads(
        asyncio.run(
            by_name["wxpost_describe_material"]["handler"](
                {"source_id": "M10", "confirmed": False}
            )
        )
    ) == {
        "name": "wxpost_describe_material",
        "args": {"source_id": "M10", "confirmed": False},
    }
    assert all(
        not item.get("is_async", False)
        for name, item in by_name.items()
        if name
        not in {
            "wxpost_show_material_library",
            "wxpost_describe_material",
            "wxpost_get_draft_preview",
            "wxpost_send_web_editor_link",
            "wxpost_send_draft_preview_image",
        }
    )
