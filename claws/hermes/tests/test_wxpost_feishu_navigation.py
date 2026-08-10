from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from wxpost_controller.core import (
    SOARHIGH_SERVICE_USER_AGENT,
    InvalidRequest,
    VersionConflict,
)
from wxpost_controller.feishu_navigation import FeishuNavigation
from wxpost_controller.feishu_state_store import FeishuStateStore


DM_SCOPE = "agent:wxpost:feishu:dm:oc_dm"
GROUP_MEMBER_SCOPE = "agent:wxpost:feishu:group:oc_group:ou_member"
THREAD_SCOPE = "agent:wxpost:feishu:group:oc_group:omt_thread"
RED_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjdAAAADElEQVR4nGP8zwACAAYIAQFazwZIAAAAAElFTkSuQmCC"
)
BLUE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjdAAAAD0lEQVR4nGNkYPjPwMAAAAQKAQHOAd3hAAAAAElFTkSuQmCC"
)


def _navigation(root: Path, monkeypatch: pytest.MonkeyPatch) -> FeishuNavigation:
    cache = root / "feishu-cache"
    cache.mkdir(exist_ok=True)
    monkeypatch.setenv("WXPOST_UPLOAD_CACHE_ROOTS", str(cache))
    navigation = FeishuNavigation(
        str(root),
        api_base_url="http://unused.invalid",
        service_token="test-token",
    )
    navigation._workspace_deleter = lambda workspace_id, expected_version: (
        navigation._controller.delete_workspace(
            workspace_id,
            expected_manifest_version=expected_version,
        )
    )
    return navigation


def _create_independent(
    navigation: FeishuNavigation,
    scope_key: str = DM_SCOPE,
) -> dict[str, object]:
    navigation._store.set_interaction_mode(scope_key, FeishuStateStore.EDITING)
    navigation.create_workspace(
        scope_key,
        message_id="om_create_request",
        source="independent",
        article_type="custom",
        custom_article_type="Community story",
        created_by_id="ou_member",
        created_by_name="Rui",
        confirmed=False,
    )
    return navigation.create_workspace(
        scope_key,
        message_id="om_create_confirm",
        source="independent",
        article_type="custom",
        custom_article_type="Community story",
        created_by_id="ou_member",
        created_by_name="Rui",
        confirmed=True,
    )


def test_feishu_binding_uses_durable_hermes_session_scope(tmp_path: Path) -> None:
    store = FeishuStateStore(tmp_path)
    store.bind(DM_SCOPE, "wxpost-111111111111")
    store.bind(GROUP_MEMBER_SCOPE, "wxpost-222222222222")
    store.bind(THREAD_SCOPE, "wxpost-333333333333")

    reopened = FeishuStateStore(tmp_path)
    assert reopened.active_workspace(DM_SCOPE) == "wxpost-111111111111"
    assert reopened.active_workspace(GROUP_MEMBER_SCOPE) == "wxpost-222222222222"
    assert reopened.active_workspace(THREAD_SCOPE) == "wxpost-333333333333"

    with pytest.raises(InvalidRequest, match="active Feishu conversation"):
        reopened.bind("agent:wxpost:api_server:dm:web", "wxpost-444444444444")


def test_feishu_interaction_mode_is_durable_and_defaults_to_readonly(
    tmp_path: Path,
) -> None:
    store = FeishuStateStore(tmp_path)

    assert store.interaction_mode(DM_SCOPE) == FeishuStateStore.READ_ONLY
    store.set_interaction_mode(DM_SCOPE, FeishuStateStore.EDITING)
    assert FeishuStateStore(tmp_path).interaction_mode(DM_SCOPE) == "editing"

    store.set_interaction_mode(DM_SCOPE, FeishuStateStore.READ_ONLY)
    assert FeishuStateStore(tmp_path).interaction_mode(DM_SCOPE) == "readonly"


def test_readonly_navigation_mutations_leave_workspace_versions_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    navigation = _navigation(tmp_path, monkeypatch)
    created = _create_independent(navigation)
    workspace_id = str(created["activeWorkspaceId"])
    before = navigation._controller.get_context(workspace_id)

    with pytest.raises(InvalidRequest, match="read-only"):
        navigation.import_attachments(
            DM_SCOPE,
            message_id="om_blocked_upload",
            attachments=[{"sourcePath": str(tmp_path / "missing.jpg")}],
        )
    with pytest.raises(InvalidRequest, match="read-only"):
        navigation.delete_workspace(
            DM_SCOPE,
            message_id="om_blocked_delete",
            requested_by_user_id="ou_member",
        )

    after = navigation._controller.get_context(workspace_id)
    assert after["manifest"]["manifestVersion"] == before["manifest"]["manifestVersion"]
    assert after["draft"] == before["draft"]


def test_create_select_list_and_delete_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    navigation = _navigation(tmp_path, monkeypatch)
    navigation._controller._meeting_media_loader = lambda _meeting_id: []
    navigation._store.set_interaction_mode(DM_SCOPE, FeishuStateStore.EDITING)
    pending = navigation.create_workspace(
        DM_SCOPE,
        message_id="om_create_request",
        source="independent",
        article_type="custom",
        created_by_id="ou_member",
        created_by_name="Rui",
    )
    assert pending["confirmationRequired"] is True
    with pytest.raises(InvalidRequest, match="separate member message"):
        navigation.create_workspace(
            DM_SCOPE,
            message_id="om_create_request",
            source="independent",
            article_type="custom",
            created_by_id="ou_member",
            created_by_name="Rui",
            confirmed=True,
        )

    created = _create_independent(navigation)
    workspace_id = str(created["activeWorkspaceId"])
    assert workspace_id.startswith("wxpost-")
    assert len(workspace_id) == len("wxpost-") + 12
    assert created["interactionMode"] == FeishuStateStore.READ_ONLY
    assert (
        navigation.get_active_workspace(DM_SCOPE)["activeWorkspaceId"] == workspace_id
    )
    assert navigation.list_workspaces()["items"][0]["workspaceId"] == workspace_id

    navigation.select_workspace(GROUP_MEMBER_SCOPE, workspace_id)
    assert (
        navigation.get_active_workspace(GROUP_MEMBER_SCOPE)["interactionMode"]
        == FeishuStateStore.READ_ONLY
    )
    navigation._store.set_interaction_mode(GROUP_MEMBER_SCOPE, FeishuStateStore.EDITING)
    pending = navigation.delete_workspace(
        GROUP_MEMBER_SCOPE,
        message_id="om_delete_request",
        requested_by_user_id="ou_member",
        confirmed=False,
    )
    assert pending["confirmationRequired"] is True
    deleted = navigation.delete_workspace(
        GROUP_MEMBER_SCOPE,
        message_id="om_delete_confirm",
        requested_by_user_id="ou_member",
        confirmed=True,
    )
    assert deleted["deleted"] is True
    assert navigation.get_active_workspace(DM_SCOPE)["activeWorkspaceId"] is None
    assert (
        navigation.get_active_workspace(GROUP_MEMBER_SCOPE)["activeWorkspaceId"] is None
    )


def test_delete_workspace_is_bound_to_the_conversation_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    navigation = _navigation(tmp_path, monkeypatch)
    workspace_a = str(_create_independent(navigation, DM_SCOPE)["activeWorkspaceId"])
    workspace_b = str(
        _create_independent(navigation, GROUP_MEMBER_SCOPE)["activeWorkspaceId"]
    )

    navigation._store.set_interaction_mode(DM_SCOPE, FeishuStateStore.EDITING)
    pending = navigation.delete_workspace(
        DM_SCOPE,
        message_id="om_delete_a_request",
        requested_by_user_id="ou_member",
    )

    assert pending["workspace"]["workspaceId"] == workspace_a
    assert navigation._controller.get_context(workspace_b)["workspaceId"] == workspace_b

    deleted = navigation.delete_workspace(
        DM_SCOPE,
        message_id="om_delete_a_confirm",
        requested_by_user_id="ou_member",
        confirmed=True,
    )

    assert deleted["deleted"] is True
    assert deleted["workspaceId"] == workspace_a
    assert navigation._controller.get_context(workspace_b)["workspaceId"] == workspace_b


def test_controller_delete_route_is_used_for_session_aware_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    navigation = FeishuNavigation(
        str(tmp_path),
        api_base_url="http://unused.invalid",
        controller_base_url="http://controller.internal:8787",
        service_token="test-token",
    )
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"workspaceId":"wxpost-test","deleted":true}'

    def open_request(request, timeout):
        requests.append((request, timeout))
        return Response()

    monkeypatch.setattr("wxpost_controller.feishu_navigation.urlopen", open_request)

    result = navigation._delete_workspace_through_controller("wxpost-test", 7)

    assert result["deleted"] is True
    request, timeout = requests[0]
    assert request.full_url == "http://controller.internal:8787/workspaces/wxpost-test"
    assert request.method == "DELETE"
    assert request.get_header("Authorization") == "Bearer test-token"
    assert request.get_header("X-expected-manifest-version") == "7"
    assert timeout == 30


def test_confirmation_is_bound_to_requesting_member_and_expires(
    tmp_path: Path,
) -> None:
    now = [1_000.0]
    store = FeishuStateStore(tmp_path, clock=lambda: now[0])
    payload = '{"workspaceId":"wxpost-test"}'
    store.stage_confirmation(
        THREAD_SCOPE,
        action="delete",
        payload=payload,
        message_id="om_request",
        requested_by_user_id="ou_member_a",
    )

    assert not store.consume_confirmation(
        THREAD_SCOPE,
        action="delete",
        payload=payload,
        message_id="om_other_member",
        requested_by_user_id="ou_member_b",
    )
    now[0] += FeishuStateStore.CONFIRMATION_TTL_SECONDS + 1
    assert not store.consume_confirmation(
        THREAD_SCOPE,
        action="delete",
        payload=payload,
        message_id="om_expired",
        requested_by_user_id="ou_member_a",
    )


def test_confirmation_accepts_same_member_in_a_later_message(tmp_path: Path) -> None:
    store = FeishuStateStore(tmp_path, clock=lambda: 1_000.0)
    payload = '{"workspaceId":"wxpost-test"}'
    store.stage_confirmation(
        THREAD_SCOPE,
        action="delete",
        payload=payload,
        message_id="om_request",
        requested_by_user_id="ou_member",
    )

    assert store.consume_confirmation(
        THREAD_SCOPE,
        action="delete",
        payload=payload,
        message_id="om_confirm",
        requested_by_user_id="ou_member",
    )


def test_editing_confirmation_does_not_replace_a_pending_workspace_action(
    tmp_path: Path,
) -> None:
    store = FeishuStateStore(tmp_path, clock=lambda: 1_000.0)
    payload = '{"sourceId":"M01"}'
    store.stage_confirmation(
        DM_SCOPE,
        action="save_material_description",
        payload=payload,
        message_id="om_description",
        requested_by_user_id="ou_member",
    )
    store.stage_editing_confirmation(
        DM_SCOPE,
        message_id="om_editing",
        requested_by_user_id="ou_member",
    )

    assert store.consume_editing_confirmation(
        DM_SCOPE,
        message_id="om_editing_confirm",
        requested_by_user_id="ou_member",
    )
    assert store.consume_confirmation(
        DM_SCOPE,
        action="save_material_description",
        payload=payload,
        message_id="om_description_confirm",
        requested_by_user_id="ou_member",
    )


def test_feishu_image_description_requires_confirmation_before_materials_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    navigation = _navigation(tmp_path, monkeypatch)
    created = _create_independent(navigation)
    workspace_id = str(created["activeWorkspaceId"])
    context = navigation._controller.get_context(workspace_id)
    manifest = navigation._controller.upload_source(
        workspace_id,
        expected_manifest_version=context["manifest"]["manifestVersion"],
        origin="feishu-upload",
        filename="members.jpg",
        mime_type="image/jpeg",
        data=RED_PNG,
    )
    captured: list[dict[str, object]] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "workspaceId": workspace_id,
                    "sourceId": "M01",
                    "manifestVersion": manifest["manifestVersion"],
                    "description": "Members share an energetic moment together.",
                }
            ).encode()

    def suggest(request, timeout):
        captured.append(
            {
                "url": request.full_url,
                "authorization": request.headers["Authorization"],
                "body": json.loads(request.data),
                "timeout": timeout,
            }
        )
        return Response()

    monkeypatch.setattr("wxpost_controller.feishu_navigation.urlopen", suggest)

    proposed = navigation.describe_material(
        DM_SCOPE,
        message_id="om_description_request",
        requested_by_user_id="ou_member",
        source_id="M01",
    )

    assert proposed == {
        "confirmationRequired": True,
        "action": "save_material_description",
        "workspaceId": workspace_id,
        "sourceId": "M01",
        "suggestedDescription": "Members share an energetic moment together.",
    }
    source = navigation._controller.get_context(workspace_id)["manifest"]["sources"][0]
    assert source["description"] == ""
    assert source["descriptionStatus"] == "missing"

    with pytest.raises(InvalidRequest, match="separate member message"):
        navigation._store.set_interaction_mode(DM_SCOPE, FeishuStateStore.EDITING)
        navigation.describe_material(
            DM_SCOPE,
            message_id="om_description_request",
            requested_by_user_id="ou_member",
            source_id="M01",
            confirmed=True,
        )

    saved = navigation.describe_material(
        DM_SCOPE,
        message_id="om_description_confirm",
        requested_by_user_id="ou_member",
        source_id="M01",
        confirmed=True,
    )

    assert saved == {
        "saved": True,
        "workspaceId": workspace_id,
        "sourceId": "M01",
        "description": "Members share an energetic moment together.",
        "descriptionSource": "ai",
        "descriptionStatus": "confirmed",
        "manifestVersion": manifest["manifestVersion"] + 1,
    }
    source = navigation._controller.get_context(workspace_id)["manifest"]["sources"][0]
    assert source["description"] == "Members share an energetic moment together."
    assert source["descriptionSource"] == "ai"
    assert source["descriptionStatus"] == "confirmed"
    assert captured == [
        {
            "url": (
                "http://127.0.0.1:8787/workspaces/"
                f"{workspace_id}/sources/M01/description-suggestion"
            ),
            "authorization": "Bearer test-token",
            "body": {
                "expectedManifestVersion": manifest["manifestVersion"],
                "currentDescription": "",
            },
            "timeout": 330,
        }
    ]


def test_list_workspaces_includes_linked_meeting_title(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    navigation = _navigation(tmp_path, monkeypatch)
    navigation._controller._meeting_media_loader = lambda _meeting_id: []
    context = navigation._controller.create_workspace(
        meeting_id="meeting-463",
        editorial=navigation._editorial("meeting-recap", None),
        created_by={"id": "ou_member", "name": "Rui"},
    )
    monkeypatch.setattr(
        navigation,
        "_meeting_options_by_ids",
        lambda meeting_ids: [
            {
                "id": meeting_ids[0],
                "no": 463,
                "type": "Regular",
                "theme": "Ordinary You, Worthy of Love",
                "date": "2026-07-22",
            }
        ],
    )

    item = navigation.list_workspaces()["items"][0]

    assert item["workspaceId"] == context["workspaceId"]
    assert item["linkedSource"] == {
        "id": "meeting-463",
        "kind": "meeting",
        "number": 463,
        "title": "Ordinary You, Worthy of Love",
        "type": "Regular",
        "date": "2026-07-22",
        "unavailable": False,
    }


def test_list_workspaces_remains_available_when_linked_meeting_lookup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    navigation = _navigation(tmp_path, monkeypatch)
    navigation._controller._meeting_media_loader = lambda _meeting_id: []
    navigation._controller.create_workspace(
        meeting_id="meeting-463",
        editorial=navigation._editorial("meeting-recap", None),
        created_by={"id": "ou_member", "name": "Rui"},
    )

    def fail(_meeting_ids: list[str]) -> list[dict[str, object]]:
        from wxpost_controller.core import UpstreamUnavailable

        raise UpstreamUnavailable("meeting API unavailable")

    monkeypatch.setattr(navigation, "_meeting_options_by_ids", fail)

    item = navigation.list_workspaces()["items"][0]

    assert item["linkedSource"] == {
        "id": "meeting-463",
        "unavailable": True,
    }


def test_active_binding_is_cleared_after_workspace_is_deleted_elsewhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    navigation = _navigation(tmp_path, monkeypatch)
    created = _create_independent(navigation)
    workspace_id = str(created["activeWorkspaceId"])
    context = navigation._controller.get_context(workspace_id)
    navigation._controller.delete_workspace(
        workspace_id,
        expected_manifest_version=context["manifest"]["manifestVersion"],
    )

    assert navigation.get_active_workspace(DM_SCOPE) == {
        "activeWorkspaceId": None,
        "workspace": None,
        "interactionMode": FeishuStateStore.READ_ONLY,
    }
    with pytest.raises(InvalidRequest, match="select or create"):
        navigation.import_attachments(
            DM_SCOPE,
            message_id="om_stale_binding",
            attachments=[{"sourcePath": str(tmp_path / "missing.jpg")}],
        )


def test_active_workspace_can_request_a_version_bound_draft_preview_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    navigation = _navigation(tmp_path, monkeypatch)
    created = _create_independent(navigation)
    workspace_id = str(created["activeWorkspaceId"])
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"previewUrl":"https://preview.example/token","editorUrl":"https://preview.example/posts/wxposts/edit/test?view=edit","workspaceId":"wxpost-test","draftVersion":3,"expiresAt":1800000000}'

    def open_preview(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers["Authorization"]
        captured["method"] = request.method
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("wxpost_controller.feishu_navigation.urlopen", open_preview)

    result = navigation.create_draft_preview_link(
        DM_SCOPE,
        draft_version=3,
    )

    assert result["previewUrl"] == "https://preview.example/token"
    assert result["editorUrl"] == (
        "https://preview.example/posts/wxposts/edit/test?view=edit"
    )
    assert result["draftVersion"] == 3
    assert captured == {
        "url": (
            "http://unused.invalid/posts/wxposts/workspaces/"
            f"{workspace_id}/draft-preview?draft_version=3"
        ),
        "authorization": "Bearer test-token",
        "method": "POST",
        "timeout": 30,
    }


def test_active_workspace_can_request_materials_and_draft_web_editor_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    navigation = _navigation(tmp_path, monkeypatch)
    monkeypatch.setattr(
        navigation,
        "_active_workspace",
        lambda _scope_key: (
            "wxpost-test",
            {"workspaceId": "wxpost-test", "draft": {"draftVersion": 3}},
        ),
    )
    captured: list[dict[str, object]] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"workspaceId":"wxpost-test","materialsUrl":"https://soarhigh.example/posts/wxposts/edit/test","draftUrl":"https://soarhigh.example/posts/wxposts/edit/test?view=edit"}'

    def open_links(request, timeout):
        captured.append(
            {
                "url": request.full_url,
                "authorization": request.headers["Authorization"],
                "method": request.method,
                "timeout": timeout,
            }
        )
        return Response()

    monkeypatch.setattr("wxpost_controller.feishu_navigation.urlopen", open_links)

    materials = navigation.get_web_editor_link(DM_SCOPE, target="materials")
    draft = navigation.get_web_editor_link(DM_SCOPE, target="draft")

    assert materials == {
        "workspaceId": "wxpost-test",
        "target": "materials",
        "url": "https://soarhigh.example/posts/wxposts/edit/test",
    }
    assert draft == {
        "workspaceId": "wxpost-test",
        "target": "draft",
        "url": "https://soarhigh.example/posts/wxposts/edit/test?view=edit",
    }
    assert captured == [
        {
            "url": "http://unused.invalid/posts/wxposts/workspaces/wxpost-test/editor-links",
            "authorization": "Bearer test-token",
            "method": "GET",
            "timeout": 30,
        },
        {
            "url": "http://unused.invalid/posts/wxposts/workspaces/wxpost-test/editor-links",
            "authorization": "Bearer test-token",
            "method": "GET",
            "timeout": 30,
        },
    ]


def test_draft_web_editor_link_requires_a_saved_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    navigation = _navigation(tmp_path, monkeypatch)
    monkeypatch.setattr(
        navigation,
        "_active_workspace",
        lambda _scope_key: (
            "wxpost-test",
            {"workspaceId": "wxpost-test", "draft": None},
        ),
    )

    with pytest.raises(InvalidRequest, match="no saved Draft"):
        navigation.get_web_editor_link(DM_SCOPE, target="draft")


def test_linked_workspace_requires_matching_meeting_or_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    navigation = _navigation(tmp_path, monkeypatch)
    navigation._controller._meeting_media_loader = lambda _meeting_id: []
    monkeypatch.setattr(
        navigation,
        "_meeting_options",
        lambda: [
            {"id": "meeting-462", "no": 462, "theme": "Belonging"},
            {"id": "event-10001", "no": 10001, "theme": "Member Day"},
        ],
    )
    navigation._store.set_interaction_mode(DM_SCOPE, FeishuStateStore.EDITING)

    with pytest.raises(InvalidRequest, match="does not match"):
        navigation.create_workspace(
            DM_SCOPE,
            message_id="om_event_mismatch",
            source="event",
            meeting_id="meeting-462",
            article_type="custom",
            created_by_id="ou_member",
            created_by_name="Rui",
            confirmed=True,
        )

    navigation.create_workspace(
        DM_SCOPE,
        message_id="om_event_request",
        source="event",
        meeting_id="event-10001",
        article_type="custom",
        custom_article_type="Event Recap",
        created_by_id="ou_member",
        created_by_name="Rui",
        confirmed=False,
    )
    created = navigation.create_workspace(
        DM_SCOPE,
        message_id="om_event_confirm",
        source="event",
        meeting_id="event-10001",
        article_type="custom",
        custom_article_type="Event Recap",
        created_by_id="ou_member",
        created_by_name="Rui",
        confirmed=True,
    )
    assert created["workspace"]["manifest"]["meetingId"] == "event-10001"


def test_meeting_api_requests_identify_the_controller_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    navigation = _navigation(tmp_path, monkeypatch)
    captured = []

    class Response:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self._payload).encode()

    def open_request(request, timeout):
        captured.append((request, timeout))
        payload = (
            {"items": [], "pages": 1}
            if request.get_method() == "GET"
            else {"items": []}
        )
        return Response(payload)

    monkeypatch.setattr("wxpost_controller.feishu_navigation.urlopen", open_request)

    assert navigation._meeting_options() == []
    assert navigation._meeting_options_by_ids(["meeting-464"]) == []

    assert [request.get_header("User-agent") for request, _timeout in captured] == [
        SOARHIGH_SERVICE_USER_AGENT,
        SOARHIGH_SERVICE_USER_AGENT,
    ]
    assert [request.get_header("Authorization") for request, _timeout in captured] == [
        "Bearer test-token",
        "Bearer test-token",
    ]


def test_feishu_attachment_import_is_idempotent_per_message_and_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    navigation = _navigation(tmp_path, monkeypatch)
    cache = tmp_path / "feishu-cache"
    first_path = cache / "photo.jpg"
    first_path.write_bytes(RED_PNG)
    second_path = cache / "same-name.jpg"
    second_path.write_bytes(BLUE_PNG)

    with pytest.raises(InvalidRequest, match="select or create"):
        navigation.import_attachments(
            DM_SCOPE,
            message_id="om_before_select",
            attachments=[{"sourcePath": str(first_path)}],
        )

    created = _create_independent(navigation)
    workspace_id = str(created["activeWorkspaceId"])
    navigation._store.set_interaction_mode(DM_SCOPE, FeishuStateStore.EDITING)
    first = navigation.import_attachments(
        DM_SCOPE,
        message_id="om_1",
        attachments=[{"sourcePath": str(first_path), "filename": "photo.jpg"}],
    )
    repeated = navigation.import_attachments(
        DM_SCOPE,
        message_id="om_1",
        attachments=[{"sourcePath": str(first_path), "filename": "photo.jpg"}],
    )
    different = navigation.import_attachments(
        DM_SCOPE,
        message_id="om_1",
        attachments=[{"sourcePath": str(second_path), "filename": "photo.jpg"}],
    )

    assert first["importedSourceIds"] == ["M01"]
    assert repeated["importedSourceIds"] == []
    assert repeated["existingSourceIds"] == ["M01"]
    assert different["importedSourceIds"] == ["M02"]
    sources = navigation.get_active_workspace(DM_SCOPE)["workspace"]["manifest"][
        "sources"
    ]
    assert [source["id"] for source in sources] == ["M01", "M02"]
    assert all(source["workspaceReady"] is True for source in sources)
    assert all(source["included"] is False for source in sources)
    assert (
        navigation.get_active_workspace(DM_SCOPE)["activeWorkspaceId"] == workspace_id
    )


def test_feishu_attachment_import_validates_metadata_and_scopes_deduplication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    navigation = _navigation(tmp_path, monkeypatch)
    cache = tmp_path / "feishu-cache"
    source_path = cache / "photo.jpg"
    source_path.write_bytes(RED_PNG)
    _create_independent(navigation)
    navigation._store.set_interaction_mode(DM_SCOPE, FeishuStateStore.EDITING)

    with pytest.raises(InvalidRequest, match="attachment metadata"):
        navigation.import_attachments(
            DM_SCOPE,
            message_id="om_invalid",
            attachments=[{"filename": "photo.jpg"}],
        )

    first = navigation.import_attachments(
        DM_SCOPE,
        message_id="om_first",
        attachments=[{"sourcePath": str(source_path)}],
    )
    second_message = navigation.import_attachments(
        DM_SCOPE,
        message_id="om_second",
        attachments=[{"sourcePath": str(source_path)}],
    )

    assert first["importedSourceIds"] == ["M01"]
    assert second_message["importedSourceIds"] == ["M02"]


def test_material_library_rejects_a_report_and_media_version_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    navigation = _navigation(tmp_path, monkeypatch)
    created = _create_independent(navigation)
    workspace_id = str(created["activeWorkspaceId"])
    navigation._store.set_interaction_mode(DM_SCOPE, FeishuStateStore.EDITING)
    source_path = tmp_path / "feishu-cache" / "concurrent.jpg"
    source_path.write_bytes(RED_PNG)
    original_get_report = navigation._controller.get_workspace_report

    def get_report_then_change_manifest(target_workspace_id: str) -> dict[str, object]:
        report = original_get_report(target_workspace_id)
        navigation.import_attachments(
            DM_SCOPE,
            message_id="om_concurrent_change",
            attachments=[{"sourcePath": str(source_path)}],
        )
        return report

    monkeypatch.setattr(
        navigation._controller,
        "get_workspace_report",
        get_report_then_change_manifest,
    )

    with pytest.raises(VersionConflict, match="expected manifest version"):
        navigation.get_material_library(DM_SCOPE)

    assert (
        navigation.get_active_workspace(DM_SCOPE)["activeWorkspaceId"] == workspace_id
    )
