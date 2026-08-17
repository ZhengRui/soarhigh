from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .core import SOARHIGH_SERVICE_USER_AGENT, InvalidRequest
from .errors import PublicationOperationNotFound
from .publication_store import PublicationStore

logger = logging.getLogger(__name__)

_OPERATION_ID_PATTERN = re.compile(r"^publish-[0-9a-f]{32}$")

# HTTPError is a URLError subclass, but the default backend_call always
# converts it into PublicationBackendError before it can propagate here, so
# anything caught by this tuple is a genuine connectivity failure.
_NETWORK_ERRORS = (URLError, TimeoutError, OSError)

BackendCall = Callable[[str, str, dict[str, Any] | None], dict[str, Any]]


class PublicationBackendError(Exception):
    """A backend response carrying a typed ``{code, message}`` error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _BackendUnreachable(Exception):
    """Both attempts at a backend call failed at the network level."""


def _fingerprint(plan: dict[str, Any]) -> str:
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_backend_error(exc: HTTPError) -> tuple[str, str]:
    try:
        payload = json.loads(exc.read())
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message")
            if isinstance(code, str) and isinstance(message, str):
                return code, message
    return "backend_error", f"backend request failed with status {exc.code}"


class PublicationService:
    """Runs an async WxPost publication: asset ensures, then finalize.

    Mirrors the Draft Assistant's submit/poll shape (``generate_submit`` in
    ``hermes_session.py``): ``submit`` durably admits the operation and hands
    the run to a background thread, callers poll ``operation``/``current``.
    """

    def __init__(
        self,
        store: PublicationStore,
        *,
        api_base_url: str,
        service_token: str,
        backend_call: BackendCall | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._store = store
        self._api_base_url = api_base_url.rstrip("/")
        self._service_token = service_token
        self._backend_call = backend_call or self._call_backend
        self._sleep = sleep

    def submit(
        self,
        workspace_id: str,
        *,
        operation_id: str,
        plan: dict[str, Any],
        _defer_thread: bool = False,
    ) -> dict[str, Any]:
        if not _OPERATION_ID_PATTERN.fullmatch(operation_id):
            raise InvalidRequest("Publication operation identifier is invalid")
        self._store.start_operation(
            workspace_id,
            operation_id,
            request_fingerprint=_fingerprint(plan),
            plan_json=json.dumps(plan, ensure_ascii=False),
        )
        if not _defer_thread:
            threading.Thread(
                target=self._run,
                args=(workspace_id, operation_id),
                name="wxpost-publication",
                daemon=True,
            ).start()
        return {
            "workspaceId": workspace_id,
            "operationId": operation_id,
            "state": "running",
        }

    def operation(self, workspace_id: str, operation_id: str) -> dict[str, Any]:
        result = self._store.get_operation(workspace_id, operation_id)
        if result is None:
            raise PublicationOperationNotFound("Publication operation does not exist")
        return result

    def current(self, workspace_id: str) -> dict[str, Any]:
        return {"running": self._store.running_operation(workspace_id)}

    def _run(self, workspace_id: str, operation_id: str) -> None:
        try:
            self._run_operation(workspace_id, operation_id)
        except Exception:
            logger.exception("Publication operation %s crashed", operation_id)
            try:
                self._store.fail_operation(
                    operation_id,
                    error={
                        "code": "publication_runner_error",
                        "message": "The publication runner failed unexpectedly.",
                    },
                )
            except Exception:
                logger.exception(
                    "Publication operation %s could not be marked failed",
                    operation_id,
                )

    def _run_operation(self, workspace_id: str, operation_id: str) -> None:
        plan = self._store.plan(operation_id)
        if plan is None:
            raise RuntimeError(f"publication plan missing for {operation_id}")
        items = plan.get("items") or []
        steps: list[dict[str, Any]] = [
            {
                "activityId": f"asset-{item['sourceId']}",
                "label": f"Preparing {item['sourceId']}",
                "completed": False,
                "failed": False,
            }
            for item in items
        ] + [
            {
                "activityId": "finalize",
                "label": "Publishing the article",
                "completed": False,
                "failed": False,
            }
        ]
        self._store.set_steps(operation_id, steps)

        for index, item in enumerate(items):
            if not self._perform_step(
                operation_id,
                steps,
                index,
                lambda item=item: self._call_with_retry(
                    "POST",
                    f"/posts/wxposts/workspaces/{workspace_id}"
                    "/publication/assets/ensure",
                    {"wxpostId": plan.get("wxpostId"), "item": item},
                ),
            ):
                return

        finalize_index = len(items)
        result = self._perform_step(
            operation_id,
            steps,
            finalize_index,
            lambda: self._call_with_retry(
                "POST",
                f"/posts/wxposts/workspaces/{workspace_id}/publication/finalize",
                {
                    "wxpostId": plan.get("wxpostId"),
                    "expectedManifestVersion": plan.get("manifestVersion"),
                    "expectedDraftVersion": plan.get("draftVersion"),
                    "bundleSha256": plan.get("bundleSha256"),
                },
            ),
            return_response=True,
        )
        if result is False:
            return
        self._store.complete_operation(operation_id, result=result)

    def _perform_step(
        self,
        operation_id: str,
        steps: list[dict[str, Any]],
        index: int,
        call: Callable[[], dict[str, Any]],
        *,
        return_response: bool = False,
    ) -> Any:
        """Run one backend call, updating ``steps`` and the store either way.

        Returns the backend response (when ``return_response``) or ``True``
        on success; returns ``False`` once the operation has already been
        failed, so the caller stops without touching the store again.
        """

        try:
            response = call()
        except PublicationBackendError as exc:
            self._fail_step(operation_id, steps, index, exc.code, exc.message)
            return False
        except _BackendUnreachable as exc:
            self._fail_step(operation_id, steps, index, "backend_unreachable", str(exc))
            return False
        steps[index]["completed"] = True
        self._store.set_steps(operation_id, steps)
        return response if return_response else True

    def _fail_step(
        self,
        operation_id: str,
        steps: list[dict[str, Any]],
        index: int,
        code: str,
        message: str,
    ) -> None:
        steps[index]["failed"] = True
        self._store.set_steps(operation_id, steps)
        self._store.fail_operation(
            operation_id, error={"code": code, "message": message}
        )

    def _call_with_retry(
        self,
        method: str,
        path: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self._backend_call(method, path, body)
        except PublicationBackendError:
            raise
        except _NETWORK_ERRORS:
            self._sleep(2)
            try:
                return self._backend_call(method, path, body)
            except PublicationBackendError:
                raise
            except _NETWORK_ERRORS as retry_exc:
                raise _BackendUnreachable(
                    f"backend unreachable after retry: {retry_exc}"
                ) from retry_exc

    def _call_backend(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None,
    ) -> dict[str, Any]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
        request = Request(
            f"{self._api_base_url}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._service_token}",
                "Content-Type": "application/json",
                "User-Agent": SOARHIGH_SERVICE_USER_AGENT,
            },
        )
        try:
            with urlopen(request, timeout=90) as response:
                raw = response.read()
        except HTTPError as exc:
            code, message = _parse_backend_error(exc)
            raise PublicationBackendError(code, message) from exc
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise PublicationBackendError(
                "backend_error", "backend response was not valid JSON"
            ) from exc
