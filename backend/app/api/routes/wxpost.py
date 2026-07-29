"""Authoring and public-read routes for Hermes-authored WXPosts."""

import json
import re
import secrets
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

from ...config import (
    WXPOST_CONTROLLER_URL,
    WXPOST_PUBLIC_BASE_URL,
    WXPOST_SERVICE_TOKEN,
)
from ...db.wxpost import (
    WxPostNotFoundError,
    WxPostRevisionConflictError,
    create_wxpost,
    get_public_wxpost_by_slug,
    get_wxpost_by_id,
    update_wxpost,
)
from ...models.users import User
from ...models.wxpost import (
    ArticleDocument,
    WxPostCapabilities,
    WxPostCreateRequest,
    WxPostMutationResult,
    WxPostPublicDetail,
    WxPostUpdateRequest,
    WxPostValidationFailure,
    WxPostValidationSuccess,
)
from ...services.wxpost_document import (
    ArticleDocumentValidationError,
    capabilities,
    pydantic_validation_issues,
    validate_and_parse,
)
from .auth import get_current_user

wxpost_router = r = APIRouter()
service_bearer = HTTPBearer(auto_error=False)
WXPOST_MAX_SOURCE_BYTES = 50 * 1024 * 1024
workspace_source_route = re.compile(
    r"^sources/M(?:0[1-9]|[1-9][0-9]+)" r"(?:/(?:import|inclusion|content|delete-preflight))?$"
)


async def require_wxpost_service(
    credentials: HTTPAuthorizationCredentials | None = Depends(service_bearer),
) -> None:
    """Authorize only the narrowly scoped Hermes ingestion credential."""

    if not WXPOST_SERVICE_TOKEN:
        raise HTTPException(status_code=503, detail="WXPost service ingestion is not configured.")
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not secrets.compare_digest(credentials.credentials, WXPOST_SERVICE_TOKEN)
    ):
        raise HTTPException(status_code=401, detail="Invalid WXPost service credential.")


def _validate_persistable_document(document: ArticleDocument) -> None:
    if document.source_meeting_id is not None:
        try:
            UUID(document.source_meeting_id)
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail="sourceMeetingId must be a meeting UUID when a WXPost is stored.",
            ) from error
    try:
        validate_and_parse(document)
    except ArticleDocumentValidationError as error:
        raise HTTPException(
            status_code=422,
            detail=[issue.model_dump(by_alias=True, mode="json") for issue in error.errors],
        ) from error


def _mutation_result(row: dict) -> WxPostMutationResult:
    return WxPostMutationResult(
        id=row["id"],
        slug=row["slug"],
        article_revision=row["article_revision"],
        preview_url=f"{WXPOST_PUBLIC_BASE_URL}/posts/wxposts/{row['slug']}",
    )


async def _proxy_workspace_controller(
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    content_type: str | None = None,
    expected_manifest_version: str | None = None,
) -> Response:
    if not WXPOST_CONTROLLER_URL or not WXPOST_SERVICE_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="WXPost workspace controller is not configured.",
        )
    headers = {"Authorization": f"Bearer {WXPOST_SERVICE_TOKEN}"}
    if content_type:
        headers["Content-Type"] = content_type
    if expected_manifest_version:
        headers["X-Expected-Manifest-Version"] = expected_manifest_version
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            upstream = await client.request(
                method,
                f"{WXPOST_CONTROLLER_URL}{path}",
                content=body,
                headers=headers,
            )
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=503,
            detail="WXPost workspace controller is unavailable.",
        ) from error
    response_headers = {}
    if upstream_content_type := upstream.headers.get("Content-Type"):
        response_headers["Content-Type"] = upstream_content_type
    if cache_control := upstream.headers.get("Cache-Control"):
        response_headers["Cache-Control"] = cache_control
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


def _workspace_route_allowed(method: str, path: str) -> bool:
    if (method, path) in {
        ("GET", "context"),
        ("PATCH", "sources"),
        ("POST", "uploads"),
    }:
        return True
    if not workspace_source_route.fullmatch(path):
        return False
    leaf = path.rsplit("/", 1)[-1]
    return (method, leaf) in {
        ("POST", "import"),
        ("PUT", "inclusion"),
        ("GET", "content"),
        ("GET", "delete-preflight"),
    } or (method == "DELETE" and leaf.startswith("M"))


async def _proxy_workspace_request(
    request: Request,
    workspace_id: str,
    controller_path: str,
) -> Response:
    if not _workspace_route_allowed(request.method, controller_path):
        raise HTTPException(status_code=404, detail="Workspace route not found.")
    query = f"?{request.url.query}" if controller_path == "uploads" else ""
    body = await _read_limited_workspace_upload(request) if controller_path == "uploads" else await request.body()
    return await _proxy_workspace_controller(
        request.method,
        (f"/workspaces/{quote(workspace_id, safe='')}/" f"{controller_path}{query}"),
        body=body,
        content_type=request.headers.get("Content-Type"),
        expected_manifest_version=request.headers.get("X-Expected-Manifest-Version"),
    )


async def _read_limited_workspace_upload(request: Request) -> bytes:
    raw_length = request.headers.get("Content-Length")
    if raw_length:
        try:
            content_length = int(raw_length)
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail="Upload Content-Length must be an integer.",
            ) from error
        if content_length > WXPOST_MAX_SOURCE_BYTES:
            raise HTTPException(status_code=413, detail="Upload exceeds 50 MiB.")

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > WXPOST_MAX_SOURCE_BYTES:
            raise HTTPException(status_code=413, detail="Upload exceeds 50 MiB.")
        body.extend(chunk)
    return bytes(body)


@r.get("/posts/wxposts/capabilities", response_model=WxPostCapabilities)
async def r_get_wxpost_capabilities() -> WxPostCapabilities:
    """Return the versioned authoring vocabulary owned by SoarHigh."""

    return capabilities()


@r.post(
    "/posts/wxposts/validate",
    response_model=WxPostValidationSuccess,
    responses={422: {"model": WxPostValidationFailure}},
)
async def r_validate_wxpost(payload: Any = Body(...)) -> WxPostValidationSuccess | JSONResponse:
    """Validate and parse an ArticleDocument without storing or publishing it."""

    try:
        document = ArticleDocument.model_validate(payload)
    except ValidationError as error:
        failure = WxPostValidationFailure(errors=pydantic_validation_issues(error))
        return JSONResponse(status_code=422, content=failure.model_dump(by_alias=True, mode="json"))

    try:
        parsed = validate_and_parse(document)
    except ArticleDocumentValidationError as error:
        failure = WxPostValidationFailure(errors=error.errors)
        return JSONResponse(status_code=422, content=failure.model_dump(by_alias=True, mode="json"))

    return WxPostValidationSuccess(
        document=document,
        article_type=document.article_type,
        custom_article_type=document.custom_article_type,
        directives=parsed.directive_summaries(),
        inline_extensions=parsed.inline_summaries(),
        render_document=parsed.render_document(document),
    )


@r.post(
    "/posts/wxposts",
    response_model=WxPostMutationResult,
    status_code=201,
    dependencies=[Depends(require_wxpost_service)],
)
async def r_create_wxpost(request: WxPostCreateRequest) -> WxPostMutationResult:
    """Persist one validated canonical source document."""

    _validate_persistable_document(request.document)
    return _mutation_result(create_wxpost(request.document))


@r.patch(
    "/posts/wxposts/{wxpost_id}",
    response_model=WxPostMutationResult,
    dependencies=[Depends(require_wxpost_service)],
)
async def r_update_wxpost(
    request: WxPostUpdateRequest,
    wxpost_id: UUID = Path(..., description="The WXPost UUID to revise"),
) -> WxPostMutationResult:
    """Replace article content with compare-and-swap revision protection."""

    current = get_wxpost_by_id(wxpost_id)
    if current is None:
        raise HTTPException(status_code=404, detail="WXPost not found.")

    document_payload = request.document.model_dump(by_alias=True, mode="json")
    if request.document.presentation is None:
        document_payload["presentation"] = current["default_presentation"]
    document = ArticleDocument.model_validate(document_payload)
    _validate_persistable_document(document)

    try:
        row = update_wxpost(
            wxpost_id,
            expected_revision=request.expected_revision,
            document=document,
        )
    except WxPostNotFoundError as error:
        raise HTTPException(status_code=404, detail="WXPost not found.") from error
    except WxPostRevisionConflictError as error:
        raise HTTPException(
            status_code=409,
            detail="WXPost changed since the requested revision.",
        ) from error
    return _mutation_result(row)


@r.put(
    "/posts/wxposts/workspaces/{workspace_id}",
)
async def r_bootstrap_wxpost_workspace(
    request: Request,
    workspace_id: str = Path(..., min_length=1),
    user: User = Depends(get_current_user),
) -> Response:
    try:
        payload = json.loads(await request.body())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=400,
            detail="Workspace bootstrap body must be valid JSON.",
        ) from error
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400,
            detail="Workspace bootstrap body must be a JSON object.",
        )
    payload["createdBy"] = {
        "id": user.uid,
        "name": user.full_name or user.username,
    }
    return await _proxy_workspace_controller(
        "PUT",
        f"/workspaces/{quote(workspace_id, safe='')}",
        body=json.dumps(payload, ensure_ascii=False).encode(),
        content_type="application/json",
    )


@r.patch(
    "/posts/wxposts/workspaces/{workspace_id}",
    dependencies=[Depends(get_current_user)],
)
async def r_update_wxpost_workspace(
    request: Request,
    workspace_id: str = Path(..., min_length=1),
) -> Response:
    return await _proxy_workspace_controller(
        "PATCH",
        f"/workspaces/{quote(workspace_id, safe='')}",
        body=await request.body(),
        content_type=request.headers.get("Content-Type"),
    )


@r.get(
    "/posts/wxposts/workspaces",
    dependencies=[Depends(get_current_user)],
)
async def r_list_wxpost_workspaces() -> Response:
    return await _proxy_workspace_controller("GET", "/workspaces")


@r.delete(
    "/posts/wxposts/workspaces/{workspace_id}",
    dependencies=[Depends(get_current_user)],
)
async def r_delete_wxpost_workspace(
    request: Request,
    workspace_id: str = Path(..., min_length=1),
) -> Response:
    return await _proxy_workspace_controller(
        "DELETE",
        f"/workspaces/{quote(workspace_id, safe='')}",
        expected_manifest_version=request.headers.get("X-Expected-Manifest-Version"),
    )


@r.api_route(
    "/posts/wxposts/workspaces/{workspace_id}/{controller_path:path}",
    methods=["GET", "PATCH", "POST", "PUT", "DELETE"],
    dependencies=[Depends(get_current_user)],
)
async def r_proxy_wxpost_workspace_operation(
    request: Request,
    workspace_id: str = Path(..., min_length=1),
    controller_path: str = Path(..., min_length=1),
) -> Response:
    return await _proxy_workspace_request(request, workspace_id, controller_path)


@r.get("/posts/wxposts/{slug}", response_model=WxPostPublicDetail)
async def r_get_public_wxpost(
    slug: str = Path(..., min_length=1, description="The stable public WXPost slug"),
) -> WxPostPublicDetail:
    """Return a backend-derived render document for a public WXPost."""

    detail = get_public_wxpost_by_slug(slug)
    if detail is None:
        raise HTTPException(status_code=404, detail="WXPost not found.")
    return detail
