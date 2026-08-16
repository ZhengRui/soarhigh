from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .contracts import ArticleType
from .core import (
    InvalidRequest,
    SOARHIGH_SERVICE_USER_AGENT,
    UpstreamUnavailable,
    WorkspaceController,
    WorkspaceNotFound,
)
from .feishu_state_store import FeishuStateStore


WorkspaceDeleter = Callable[[str, int], dict[str, Any]]


class AttachmentInput(BaseModel):
    model_config = ConfigDict(
        alias_generator=lambda value: value.split("_")[0]
        + "".join(part.capitalize() for part in value.split("_")[1:]),
        populate_by_name=True,
        extra="forbid",
    )

    source_path: str
    filename: str | None = None
    mime_type: str | None = None


class StagedMaterialDescription(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    workspace_id: str = Field(alias="workspaceId", min_length=1)
    source_id: str = Field(alias="sourceId", min_length=1)
    expected_manifest_version: int = Field(
        alias="expectedManifestVersion", ge=1, strict=True
    )
    description: str = Field(min_length=1)


class FeishuNavigation:
    """Feishu-only workspace navigation using an explicit gateway scope key."""

    def __init__(
        self,
        workspace_root: str | None = None,
        *,
        api_base_url: str | None = None,
        service_token: str | None = None,
        controller_base_url: str | None = None,
        workspace_deleter: WorkspaceDeleter | None = None,
    ) -> None:
        self._root = (
            workspace_root
            if workspace_root is not None
            else os.environ.get("WXPOST_WORKSPACE_ROOT", "/workspace")
        )
        self._controller = WorkspaceController(self._root)
        self._store = FeishuStateStore(self._root)
        self._api_base_url = (
            api_base_url
            if api_base_url is not None
            else os.environ.get("SOARHIGH_API_BASE_URL", "")
        ).rstrip("/")
        self._service_token = (
            service_token
            if service_token is not None
            else os.environ.get("WXPOST_SERVICE_TOKEN", "")
        )
        self._controller_base_url = (
            controller_base_url
            if controller_base_url is not None
            else os.environ.get("WXPOST_CONTROLLER_BASE_URL", "http://127.0.0.1:8787")
        ).rstrip("/")
        self._workspace_deleter = (
            workspace_deleter or self._delete_workspace_through_controller
        )

    def list_workspaces(self, *, page: int = 1, page_size: int = 10) -> dict[str, Any]:
        result = self._controller.list_workspaces(page=page, page_size=page_size)
        linked_ids = list(
            dict.fromkeys(
                str(item["meetingId"])
                for item in result["items"]
                if item.get("meetingId")
            )
        )
        if not linked_ids:
            return result
        try:
            meetings = self._meeting_options_by_ids(linked_ids)
        except UpstreamUnavailable:
            meetings = []
        by_id = {str(item["id"]): item for item in meetings}
        for item in result["items"]:
            meeting_id = item.get("meetingId")
            if not meeting_id:
                continue
            meeting = by_id.get(str(meeting_id))
            if meeting is None:
                item["linkedSource"] = {
                    "id": meeting_id,
                    "unavailable": True,
                }
                continue
            number = meeting.get("no")
            item["linkedSource"] = {
                "id": meeting_id,
                "kind": (
                    "event"
                    if isinstance(number, int) and number >= 10000
                    else "meeting"
                ),
                "number": number,
                "title": meeting.get("theme"),
                "type": meeting.get("type"),
                "date": meeting.get("date"),
                "unavailable": False,
            }
        return result

    def get_interaction_mode(self, scope_key: str) -> dict[str, str]:
        return {"interactionMode": self._store.interaction_mode(scope_key)}

    def require_editing(self, scope_key: str) -> None:
        if self._store.interaction_mode(scope_key) != FeishuStateStore.EDITING:
            raise InvalidRequest(
                "This Feishu conversation is read-only. Send /editing and "
                "confirm the switch before changing the workspace, Materials, "
                "or Draft."
            )

    def set_read_only(self, scope_key: str) -> dict[str, str]:
        self._store.set_interaction_mode(scope_key, FeishuStateStore.READ_ONLY)
        self._store.clear_confirmation(scope_key)
        return {"interactionMode": FeishuStateStore.READ_ONLY}

    def search_meetings(
        self, *, query: str = "", page: int = 1, page_size: int = 10
    ) -> dict[str, Any]:
        if page < 1 or page_size < 1 or page_size > 50:
            raise InvalidRequest("search requires page >= 1 and pageSize from 1 to 50")
        needle = query.strip().casefold()
        matches = [
            item
            for item in self._meeting_options()
            if not needle
            or needle
            in " ".join(
                str(item.get(field, "")) for field in ("no", "theme", "type", "date")
            ).casefold()
        ]
        start = (page - 1) * page_size
        return {
            "items": matches[start : start + page_size],
            "total": len(matches),
            "page": page,
            "pageSize": page_size,
            "pages": max(1, (len(matches) + page_size - 1) // page_size),
        }

    def get_active_workspace(self, scope_key: str) -> dict[str, Any]:
        workspace_id, context = self._active_workspace(scope_key)
        return {
            "activeWorkspaceId": workspace_id,
            "workspace": context,
            "interactionMode": self._store.interaction_mode(scope_key),
        }

    def get_active_workspace_report(self, scope_key: str) -> dict[str, Any]:
        workspace_id, context = self._active_workspace(scope_key)
        if workspace_id is None or context is None:
            raise InvalidRequest("select or create a workspace first")
        report = self._controller.get_workspace_report(workspace_id)
        report["interactionMode"] = self._store.interaction_mode(scope_key)
        return report

    def get_material_library(self, scope_key: str) -> dict[str, Any]:
        workspace_id, context = self._active_workspace(scope_key)
        if workspace_id is None or context is None:
            raise InvalidRequest("select or create a workspace first")
        report = self._controller.get_workspace_report(workspace_id)
        return {
            "workspaceId": workspace_id,
            "report": report,
            "media": self._controller.read_materials_for_display(
                workspace_id,
                expected_manifest_version=report["manifestVersion"],
            ),
        }

    def describe_material(
        self,
        scope_key: str,
        *,
        message_id: str,
        requested_by_user_id: str,
        source_id: str,
        confirmed: bool = False,
        guidance: str = "",
    ) -> dict[str, Any]:
        """Generate, then explicitly confirm, one Materials image description."""

        workspace_id, context = self._active_workspace(scope_key)
        if workspace_id is None or context is None:
            raise InvalidRequest("select or create a workspace first")
        action = "save_material_description"
        if not confirmed:
            manifest = context["manifest"]
            source = next(
                (item for item in manifest["sources"] if item["id"] == source_id),
                None,
            )
            if source is None:
                raise InvalidRequest(f"unknown source id: {source_id}")
            suggestion = self._suggest_material_description(
                workspace_id,
                source_id=source_id,
                expected_manifest_version=manifest["manifestVersion"],
                current_description=source["description"],
                guidance=guidance,
            )
            confirmation = StagedMaterialDescription(
                workspaceId=workspace_id,
                sourceId=source_id,
                expectedManifestVersion=manifest["manifestVersion"],
                description=suggestion,
            ).model_dump_json(by_alias=True)
            self._store.stage_confirmation(
                scope_key,
                action=action,
                payload=confirmation,
                message_id=message_id,
                requested_by_user_id=requested_by_user_id,
            )
            return {
                "confirmationRequired": True,
                "action": action,
                "workspaceId": workspace_id,
                "sourceId": source_id,
                "suggestedDescription": suggestion,
            }

        self.require_editing(scope_key)

        staged_confirmation = self._store.consume_staged_confirmation(
            scope_key,
            action=action,
            message_id=message_id,
            requested_by_user_id=requested_by_user_id,
        )
        if staged_confirmation is None:
            raise InvalidRequest(
                "generate an image-description suggestion first, then confirm it "
                "in a separate member message"
            )
        try:
            staged = StagedMaterialDescription.model_validate_json(staged_confirmation)
        except ValidationError as exc:  # pragma: no cover - SQLite is private
            raise InvalidRequest("the staged image description is invalid") from exc
        if staged.workspace_id != workspace_id or staged.source_id != source_id:
            raise InvalidRequest(
                "the pending image description belongs to a different workspace "
                "or source; generate a new suggestion"
            )
        manifest = self._controller.update_sources(
            workspace_id,
            expected_manifest_version=staged.expected_manifest_version,
            updates=[
                {
                    "sourceId": source_id,
                    "description": staged.description,
                    "descriptionSource": "ai",
                    "descriptionStatus": "confirmed",
                }
            ],
        )
        return {
            "saved": True,
            "workspaceId": workspace_id,
            "sourceId": source_id,
            "description": staged.description,
            "descriptionSource": "ai",
            "descriptionStatus": "confirmed",
            "manifestVersion": manifest["manifestVersion"],
        }

    def _suggest_material_description(
        self,
        workspace_id: str,
        *,
        source_id: str,
        expected_manifest_version: int,
        current_description: str,
        guidance: str = "",
    ) -> str:
        if not self._controller_base_url or not self._service_token:
            raise UpstreamUnavailable(
                "Controller image descriptions are not configured"
            )
        request = Request(
            f"{self._controller_base_url}/workspaces/"
            f"{quote(workspace_id, safe='')}/sources/"
            f"{quote(source_id, safe='')}/description-suggestion",
            data=json.dumps(
                {
                    "expectedManifestVersion": expected_manifest_version,
                    "currentDescription": current_description,
                    "guidance": guidance,
                }
            ).encode(),
            headers={
                "Authorization": f"Bearer {self._service_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=330) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            try:
                error_payload = json.loads(exc.read())
                detail = error_payload.get("error", {}).get("message")
            except (AttributeError, json.JSONDecodeError):
                detail = None
            message = str(detail) if detail else f"Controller returned HTTP {exc.code}"
            if 400 <= exc.code < 500:
                raise InvalidRequest(message) from exc
            raise UpstreamUnavailable(message) from exc
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise UpstreamUnavailable(
                f"cannot generate the Materials image description: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise UpstreamUnavailable(
                "Controller image-description service returned invalid data"
            )
        description = payload.get("description")
        if (
            payload.get("workspaceId") != workspace_id
            or payload.get("sourceId") != source_id
            or payload.get("manifestVersion") != expected_manifest_version
            or not isinstance(description, str)
            or not description.strip()
        ):
            raise UpstreamUnavailable(
                "Controller image-description service returned invalid data"
            )
        return description.strip()

    def create_draft_preview_link(
        self,
        scope_key: str,
        *,
        draft_version: int | None = None,
    ) -> dict[str, Any]:
        workspace_id, context = self._active_workspace(scope_key)
        if workspace_id is None or context is None:
            raise InvalidRequest("select or create a workspace first")
        if not self._api_base_url or not self._service_token:
            raise UpstreamUnavailable("Draft preview service is not configured")
        query = (
            f"?{urlencode({'draft_version': draft_version})}"
            if draft_version is not None
            else ""
        )
        request = Request(
            f"{self._api_base_url}/posts/wxposts/workspaces/"
            f"{quote(workspace_id, safe='')}/draft-preview{query}",
            data=b"",
            headers={
                "Authorization": f"Bearer {self._service_token}",
                "User-Agent": SOARHIGH_SERVICE_USER_AGENT,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read()).get("detail")
            except (AttributeError, json.JSONDecodeError):
                detail = None
            raise UpstreamUnavailable(
                str(detail) if detail else f"Draft preview API returned HTTP {exc.code}"
            ) from exc
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise UpstreamUnavailable(
                f"cannot create Draft preview link: {exc}"
            ) from exc
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("previewUrl"), str)
            or not isinstance(payload.get("editorUrl"), str)
            or not isinstance(payload.get("draftVersion"), int)
        ):
            raise UpstreamUnavailable("Draft preview API returned invalid data")
        return payload

    def get_web_editor_link(
        self,
        scope_key: str,
        *,
        target: Literal["materials", "draft"],
    ) -> dict[str, Any]:
        workspace_id, context = self._active_workspace(scope_key)
        if workspace_id is None or context is None:
            raise InvalidRequest("select or create a workspace first")
        if target == "draft" and context.get("draft") is None:
            raise InvalidRequest("the selected workspace has no saved Draft")
        if not self._api_base_url or not self._service_token:
            raise UpstreamUnavailable("web editor links are not configured")
        request = Request(
            f"{self._api_base_url}/posts/wxposts/workspaces/"
            f"{quote(workspace_id, safe='')}/editor-links",
            headers={
                "Authorization": f"Bearer {self._service_token}",
                "User-Agent": SOARHIGH_SERVICE_USER_AGENT,
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read()).get("detail")
            except (AttributeError, json.JSONDecodeError):
                detail = None
            raise UpstreamUnavailable(
                str(detail) if detail else f"web editor API returned HTTP {exc.code}"
            ) from exc
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise UpstreamUnavailable(f"cannot create web editor link: {exc}") from exc
        url_key = "materialsUrl" if target == "materials" else "draftUrl"
        if (
            not isinstance(payload, dict)
            or payload.get("workspaceId") != workspace_id
            or not isinstance(payload.get(url_key), str)
        ):
            raise UpstreamUnavailable("web editor API returned invalid data")
        return {
            "workspaceId": workspace_id,
            "target": target,
            "url": payload[url_key],
        }

    def select_workspace(self, scope_key: str, workspace_id: str) -> dict[str, Any]:
        context = self._controller.get_context(workspace_id)
        self._store.bind(scope_key, workspace_id)
        self.set_read_only(scope_key)
        return {
            "activeWorkspaceId": workspace_id,
            "workspace": context,
            "interactionMode": FeishuStateStore.READ_ONLY,
        }

    def create_workspace(
        self,
        scope_key: str,
        *,
        message_id: str,
        source: Literal["independent", "meeting", "event"],
        article_type: str,
        created_by_id: str,
        created_by_name: str,
        meeting_id: str | None = None,
        custom_article_type: str | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        self.require_editing(scope_key)
        if source == "independent" and meeting_id is not None:
            raise InvalidRequest("independent workspaces cannot link a meeting")
        if source != "independent" and meeting_id is None:
            raise InvalidRequest("linked workspaces require meetingId")
        if meeting_id is not None:
            meeting = next(
                (
                    item
                    for item in self._meeting_options()
                    if item.get("id") == meeting_id
                ),
                None,
            )
            if meeting is None:
                raise InvalidRequest("selected meeting/event is unavailable")
            meeting_number = meeting.get("no")
            is_event = isinstance(meeting_number, int) and meeting_number >= 10000
            if (source == "event") != is_event:
                raise InvalidRequest(
                    "selected meeting does not match the requested source type"
                )
        confirmation = json.dumps(
            {
                "source": source,
                "articleType": article_type,
                "meetingId": meeting_id,
                "customArticleType": custom_article_type,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        if not confirmed:
            self._store.stage_confirmation(
                scope_key,
                action="create",
                payload=confirmation,
                message_id=message_id,
                requested_by_user_id=created_by_id,
            )
            return {
                "confirmationRequired": True,
                "action": "create",
                "setup": json.loads(confirmation),
            }
        if not self._store.consume_confirmation(
            scope_key,
            action="create",
            payload=confirmation,
            message_id=message_id,
            requested_by_user_id=created_by_id,
        ):
            self._store.stage_confirmation(
                scope_key,
                action="create",
                payload=confirmation,
                message_id=message_id,
                requested_by_user_id=created_by_id,
            )
            raise InvalidRequest(
                "workspace creation must be confirmed in a separate member message"
            )
        context = self._controller.create_workspace(
            meeting_id=meeting_id,
            editorial=self._editorial(article_type, custom_article_type),
            created_by={"id": created_by_id, "name": created_by_name},
        )
        self._store.bind(scope_key, context["workspaceId"])
        self.set_read_only(scope_key)
        return {
            "activeWorkspaceId": context["workspaceId"],
            "workspace": context,
            "interactionMode": FeishuStateStore.READ_ONLY,
        }

    def delete_workspace(
        self,
        scope_key: str,
        *,
        message_id: str,
        requested_by_user_id: str,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        self.require_editing(scope_key)
        workspace_id, context = self._active_workspace(scope_key)
        if workspace_id is None or context is None:
            raise InvalidRequest("select or create a workspace first")
        confirmation = json.dumps(
            {"workspaceId": workspace_id}, ensure_ascii=False, sort_keys=True
        )
        if not confirmed:
            self._store.stage_confirmation(
                scope_key,
                action="delete",
                payload=confirmation,
                message_id=message_id,
                requested_by_user_id=requested_by_user_id,
            )
            return {
                "confirmationRequired": True,
                "action": "delete",
                "workspace": {
                    "workspaceId": workspace_id,
                    "title": context.get("displayTitle"),
                },
            }
        if not self._store.consume_confirmation(
            scope_key,
            action="delete",
            payload=confirmation,
            message_id=message_id,
            requested_by_user_id=requested_by_user_id,
        ):
            self._store.stage_confirmation(
                scope_key,
                action="delete",
                payload=confirmation,
                message_id=message_id,
                requested_by_user_id=requested_by_user_id,
            )
            raise InvalidRequest(
                "workspace deletion must be confirmed in a separate member message"
            )
        result = self._workspace_deleter(
            workspace_id,
            context["manifest"]["manifestVersion"],
        )
        self._store.clear_workspace(workspace_id)
        return {
            **result,
            "activeWorkspaceId": self._store.active_workspace(scope_key),
        }

    def _delete_workspace_through_controller(
        self,
        workspace_id: str,
        expected_manifest_version: int,
    ) -> dict[str, Any]:
        if not self._controller_base_url or not self._service_token:
            raise UpstreamUnavailable("Controller workspace deletion is not configured")
        request = Request(
            f"{self._controller_base_url}/workspaces/{quote(workspace_id, safe='')}",
            headers={
                "Authorization": f"Bearer {self._service_token}",
                "X-Expected-Manifest-Version": str(expected_manifest_version),
            },
            method="DELETE",
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            try:
                error_payload = json.loads(exc.read())
                detail = error_payload.get("error", {}).get("message")
            except (AttributeError, json.JSONDecodeError):
                detail = None
            raise UpstreamUnavailable(
                str(detail)
                if detail
                else f"Controller workspace deletion returned HTTP {exc.code}"
            ) from exc
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise UpstreamUnavailable(
                f"cannot delete workspace through Controller: {exc}"
            ) from exc
        if not isinstance(payload, dict) or payload.get("deleted") is not True:
            raise UpstreamUnavailable(
                "Controller workspace deletion returned invalid data"
            )
        return payload

    def import_attachments(
        self,
        scope_key: str,
        *,
        message_id: str,
        attachments: list[dict[str, Any]],
        include: bool = False,
    ) -> dict[str, Any]:
        workspace_id, context = self._active_workspace(scope_key)
        if workspace_id is None or context is None:
            raise InvalidRequest(
                "select or create a workspace, then resend the attachments"
            )
        self.require_editing(scope_key)
        try:
            parsed = [AttachmentInput.model_validate(item) for item in attachments]
        except ValidationError as exc:
            raise InvalidRequest("invalid Feishu attachment metadata") from exc
        result = self._controller.upload_sources_from_paths(
            workspace_id,
            expected_manifest_version=context["manifest"]["manifestVersion"],
            message_id=message_id,
            attachments=[item.model_dump(by_alias=True) for item in parsed],
            include=include,
        )
        return {
            "workspaceId": workspace_id,
            "manifestVersion": result["manifest"]["manifestVersion"],
            "importedSourceIds": result["sourceIds"],
            "existingSourceIds": result["existingSourceIds"],
        }

    def _active_workspace(
        self,
        scope_key: str,
    ) -> tuple[str | None, dict[str, Any] | None]:
        workspace_id = self._store.active_workspace(scope_key)
        if workspace_id is None:
            return None, None
        try:
            return workspace_id, self._controller.get_context(workspace_id)
        except WorkspaceNotFound:
            self._store.clear_workspace(workspace_id)
            return None, None

    @staticmethod
    def _editorial(
        article_type: str, custom_article_type: str | None
    ) -> dict[str, Any]:
        try:
            parsed_type = ArticleType(article_type)
        except ValueError as exc:
            raise InvalidRequest(f"unsupported articleType: {article_type}") from exc
        custom = custom_article_type.strip() if custom_article_type else None
        if parsed_type != ArticleType.CUSTOM and custom is not None:
            raise InvalidRequest("customArticleType is only valid for custom articles")
        return {
            "articleType": parsed_type.value,
            "customArticleType": custom,
            "writingApproach": "chronological",
            "transcript": "",
            "extraNotes": "",
            "writingGuidance": "",
            "voiceTone": {"presets": [], "customProfiles": []},
        }

    def _meeting_options(self) -> list[dict[str, Any]]:
        if not self._api_base_url:
            raise UpstreamUnavailable("SOARHIGH_API_BASE_URL is required")
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            query = urlencode({"page": page, "page_size": 100})
            request = Request(
                f"{self._api_base_url}/meetings/options?{query}",
                headers={
                    "User-Agent": SOARHIGH_SERVICE_USER_AGENT,
                    **(
                        {"Authorization": f"Bearer {self._service_token}"}
                        if self._service_token
                        else {}
                    ),
                },
            )
            try:
                with urlopen(request, timeout=15) as response:
                    payload = json.loads(response.read())
            except HTTPError as exc:
                raise UpstreamUnavailable(
                    f"meeting options API returned HTTP {exc.code}"
                ) from exc
            except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise UpstreamUnavailable(
                    f"cannot list meeting options: {exc}"
                ) from exc
            page_items = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(page_items, list):
                raise UpstreamUnavailable("meeting options API returned invalid data")
            items.extend(item for item in page_items if isinstance(item, dict))
            if page >= int(payload.get("pages", page)):
                return items
            page += 1

    def _meeting_options_by_ids(self, meeting_ids: list[str]) -> list[dict[str, Any]]:
        if not self._api_base_url:
            raise UpstreamUnavailable("SOARHIGH_API_BASE_URL is required")
        request = Request(
            f"{self._api_base_url}/meetings/options/batch",
            data=json.dumps({"ids": meeting_ids}).encode(),
            headers={
                "Content-Type": "application/json",
                "User-Agent": SOARHIGH_SERVICE_USER_AGENT,
                **(
                    {"Authorization": f"Bearer {self._service_token}"}
                    if self._service_token
                    else {}
                ),
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            raise UpstreamUnavailable(
                f"meeting options API returned HTTP {exc.code}"
            ) from exc
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise UpstreamUnavailable(f"cannot resolve linked meetings: {exc}") from exc
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise UpstreamUnavailable("meeting options API returned invalid data")
        return [item for item in items if isinstance(item, dict)]
