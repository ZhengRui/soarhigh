"""Authoring and public-read routes for Hermes-authored WxPosts."""

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from postgrest.exceptions import APIError
from pydantic import BaseModel, StringConstraints, ValidationError

from ...config import (
    WXPOST_CONTROLLER_URL,
    WXPOST_HERMES_URL,
    WXPOST_PUBLIC_BASE_URL,
    WXPOST_PUBLISHER_NAME,
    WXPOST_SERVICE_TOKEN,
)
from ...db import wxpost_wechat as wxpost_wechat_store
from ...db.wxpost import (
    WxPostNotFoundError,
    WxPostRevisionConflictError,
    article_document_from_row,
    create_wxpost,
    get_public_wxpost_by_slug,
    get_wxpost_by_id,
    get_wxpost_by_workspace_id,
    get_wxposts_by_workspace_ids,
    update_wxpost,
)
from ...models.users import User
from ...models.wxpost import (
    ArticleDocument,
    WxPostCapabilities,
    WxPostCreateRequest,
    WxPostDraftEditRequest,
    WxPostMutationResult,
    WxPostPublicationDeleteRequest,
    WxPostPublicationDeleteResult,
    WxPostPublicationStatus,
    WxPostPublicationSyncRequest,
    WxPostPublicDetail,
    WxPostUpdateRequest,
    WxPostValidationFailure,
    WxPostValidationSuccess,
    WxPostWechatDraftRequest,
    WxPostWechatDraftResult,
    WxPostWechatDraftStatus,
    WxPostWechatPreviewResult,
    WxPostWechatUncertainResetRequest,
)
from ...services.wxpost_document import (
    ArticleDocumentValidationError,
    capabilities,
    pydantic_validation_issues,
    validate_and_parse,
)
from ...services.wxpost_editing import apply_draft_edits
from ...services.wxpost_hermes import (
    HermesResponseError,
    HermesUnavailableError,
    suggest_voice_tone_instruction,
)
from ...services.wxpost_publication import (
    PublicationError,
    delete_public_wxpost,
    publication_status,
    synchronize_workspace_publication,
)
from ...services.wxpost_wechat import WechatDraftError, get_preview_url, publish_wechat_draft, wechat_status
from .auth import get_current_user

wxpost_router = r = APIRouter()
service_bearer = HTTPBearer(auto_error=False)
WXPOST_MAX_SOURCE_BYTES = 50 * 1024 * 1024
workspace_source_route = re.compile(
    r"^sources/M(?:0[1-9]|[1-9][0-9]+)" r"(?:/(?:import|inclusion|content|delete-preflight|description-suggestion))?$"
)
workspace_draft_routes = {
    ("GET", "draft/session"),
    ("DELETE", "draft/session"),
    ("POST", "draft/save"),
    ("POST", "draft/generate"),
    ("POST", "draft/chat"),
}


class VoiceToneSuggestionRequest(BaseModel):
    name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
    ]


class VoiceToneSuggestionResponse(BaseModel):
    instruction: str


class DraftPreviewLinkResponse(BaseModel):
    previewUrl: str
    editorUrl: str
    workspaceId: str
    draftVersion: int
    expiresAt: int


class WorkspaceEditorLinksResponse(BaseModel):
    workspaceId: str
    materialsUrl: str
    draftUrl: str


WXPOST_DRAFT_PREVIEW_TTL_SECONDS = 24 * 60 * 60


def _workspace_editor_urls(workspace_id: str) -> tuple[str, str]:
    workspace_key = quote(workspace_id.removeprefix("wxpost-"), safe="")
    editor_url = f"{WXPOST_PUBLIC_BASE_URL}/posts/wxposts/edit/{workspace_key}"
    return editor_url, f"{editor_url}?view=edit"


def _encode_draft_preview_token(
    workspace_id: str,
    draft_version: int,
    expires_at: int,
) -> str:
    if not WXPOST_SERVICE_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="WxPost Draft preview signing is not configured.",
        )
    payload = json.dumps(
        {
            "workspaceId": workspace_id,
            "draftVersion": draft_version,
            "expiresAt": expires_at,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    signature = hmac.new(WXPOST_SERVICE_TOKEN.encode(), payload, hashlib.sha256).digest()
    return ".".join(base64.urlsafe_b64encode(part).decode().rstrip("=") for part in (payload, signature))


def _decode_draft_preview_token(token: str) -> tuple[str, int]:
    if not WXPOST_SERVICE_TOKEN:
        raise HTTPException(status_code=404, detail="Draft preview is unavailable.")
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        payload = base64.urlsafe_b64decode(encoded_payload + "=" * (-len(encoded_payload) % 4))
        signature = base64.urlsafe_b64decode(encoded_signature + "=" * (-len(encoded_signature) % 4))
        expected = hmac.new(WXPOST_SERVICE_TOKEN.encode(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        claims = json.loads(payload)
        workspace_id = claims["workspaceId"]
        draft_version = claims["draftVersion"]
        expires_at = claims["expiresAt"]
        if (
            not isinstance(workspace_id, str)
            or not workspace_id
            or not isinstance(draft_version, int)
            or draft_version < 1
            or not isinstance(expires_at, int)
        ):
            raise ValueError("invalid claims")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=404, detail="Draft preview is unavailable.") from error
    if expires_at < int(time.time()):
        raise HTTPException(status_code=410, detail="This Draft preview link has expired.")
    return workspace_id, draft_version


async def _load_versioned_draft_preview(
    token: str,
) -> tuple[str, int, ArticleDocument]:
    workspace_id, expected_draft_version = _decode_draft_preview_token(token)
    context = await _load_workspace_context(workspace_id)
    draft = context.get("draft")
    if not isinstance(draft, dict) or draft.get("draftVersion") != expected_draft_version:
        raise HTTPException(
            status_code=410,
            detail="This Draft preview is no longer current. Request a new preview link.",
        )
    try:
        document = ArticleDocument.model_validate(draft.get("document"))
        validate_and_parse(document)
    except (ValidationError, ArticleDocumentValidationError) as error:
        raise HTTPException(
            status_code=422,
            detail="The saved Draft cannot be previewed.",
        ) from error
    return workspace_id, expected_draft_version, document


async def require_wxpost_service(
    credentials: HTTPAuthorizationCredentials | None = Depends(service_bearer),
) -> None:
    """Authorize only the narrowly scoped Hermes ingestion credential."""

    if not WXPOST_SERVICE_TOKEN:
        raise HTTPException(status_code=503, detail="WxPost service ingestion is not configured.")
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not secrets.compare_digest(credentials.credentials, WXPOST_SERVICE_TOKEN)
    ):
        raise HTTPException(status_code=401, detail="Invalid WxPost service credential.")


async def _compile_trusted_render(
    render_document: dict[str, Any],
    presentation_override: dict[str, Any] | None = None,
) -> str:
    if not WXPOST_PUBLIC_BASE_URL or not WXPOST_SERVICE_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="WxPost canonical renderer is not configured.",
        )
    presentation = presentation_override or render_document.get("presentation")
    media = render_document.get("media")
    asset_urls = (
        {
            item["id"]: item["sourceUrl"]
            for item in media
            if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("sourceUrl"), str)
        }
        if isinstance(media, list)
        else {}
    )
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            response = await client.post(
                f"{WXPOST_PUBLIC_BASE_URL}/api/internal/wxpost/render",
                headers={
                    "Authorization": f"Bearer {WXPOST_SERVICE_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={
                    "renderDocument": render_document,
                    "presentation": presentation,
                    "context": {
                        "assetUrls": asset_urls,
                        "publisherName": WXPOST_PUBLISHER_NAME,
                    },
                },
            )
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=503,
            detail="WxPost canonical renderer is unavailable.",
        ) from error
    if response.status_code != 200:
        raise HTTPException(
            status_code=503,
            detail="WxPost canonical renderer rejected the document.",
        )
    try:
        payload = response.json()
    except ValueError as error:
        raise HTTPException(
            status_code=503,
            detail="WxPost canonical renderer returned invalid JSON.",
        ) from error
    html = payload.get("html") if isinstance(payload, dict) else None
    render_version = payload.get("renderVersion") if isinstance(payload, dict) else None
    if render_version != 1 or not isinstance(html, str) or not html:
        raise HTTPException(
            status_code=503,
            detail="WxPost canonical renderer returned an invalid result.",
        )
    return html


def _validate_persistable_document(document: ArticleDocument) -> None:
    if document.source_meeting_id is not None:
        try:
            UUID(document.source_meeting_id)
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail="sourceMeetingId must be a meeting UUID when a WxPost is stored.",
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
    timeout: int = 30,
) -> Response:
    upstream = await _request_workspace_controller(
        method,
        path,
        body=body,
        content_type=content_type,
        expected_manifest_version=expected_manifest_version,
        timeout=timeout,
    )
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


async def _workspace_creation_body(request: Request, user: User) -> bytes:
    try:
        payload = json.loads(await request.body())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=400,
            detail="Workspace creation body must be valid JSON.",
        ) from error
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400,
            detail="Workspace creation body must be a JSON object.",
        )
    payload["createdBy"] = {
        "id": user.uid,
        "name": user.full_name or user.username,
    }
    return json.dumps(payload, ensure_ascii=False).encode()


async def _stream_workspace_controller(
    method: str,
    path: str,
    *,
    body: bytes,
    content_type: str | None,
    timeout: int,
) -> Response:
    if not WXPOST_CONTROLLER_URL or not WXPOST_SERVICE_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="WxPost workspace controller is not configured.",
        )
    headers = {"Authorization": f"Bearer {WXPOST_SERVICE_TOKEN}"}
    if content_type:
        headers["Content-Type"] = content_type
    client = httpx.AsyncClient(timeout=timeout, trust_env=False)
    try:
        request = client.build_request(
            method,
            f"{WXPOST_CONTROLLER_URL}{path}",
            content=body,
            headers=headers,
        )
        upstream = await client.send(request, stream=True)
    except httpx.HTTPError as error:
        await client.aclose()
        raise HTTPException(
            status_code=503,
            detail="WxPost workspace controller is unavailable.",
        ) from error

    if upstream.status_code != 200:
        content = await upstream.aread()
        await upstream.aclose()
        await client.aclose()
        return Response(
            content=content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("Content-Type"),
        )

    async def chunks() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        chunks(),
        media_type="text/event-stream",
        headers={"Cache-Control": "private, no-store"},
    )


async def _request_workspace_controller(
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    content_type: str | None = None,
    expected_manifest_version: str | None = None,
    timeout: int = 30,
) -> httpx.Response:
    if not WXPOST_CONTROLLER_URL or not WXPOST_SERVICE_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="WxPost workspace controller is not configured.",
        )
    headers = {"Authorization": f"Bearer {WXPOST_SERVICE_TOKEN}"}
    if content_type:
        headers["Content-Type"] = content_type
    if expected_manifest_version:
        headers["X-Expected-Manifest-Version"] = expected_manifest_version
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            upstream = await client.request(
                method,
                f"{WXPOST_CONTROLLER_URL}{path}",
                content=body,
                headers=headers,
            )
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=503,
            detail="WxPost workspace controller is unavailable.",
        ) from error
    return upstream


def _upstream_error(upstream: httpx.Response) -> HTTPException:
    message = "WxPost workspace request failed."
    try:
        payload = upstream.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                message = error["message"]
            elif isinstance(payload.get("detail"), str):
                message = payload["detail"]
    except ValueError:
        pass
    return HTTPException(status_code=upstream.status_code, detail=message)


async def _load_workspace_context(workspace_id: str) -> dict[str, Any]:
    upstream = await _request_workspace_controller(
        "GET",
        f"/workspaces/{quote(workspace_id, safe='')}/context",
    )
    if upstream.status_code != 200:
        raise _upstream_error(upstream)
    try:
        payload = upstream.json()
    except ValueError as error:
        raise HTTPException(
            status_code=503,
            detail="WxPost workspace controller returned invalid context.",
        ) from error
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=503,
            detail="WxPost workspace controller returned invalid context.",
        )
    return payload


async def _load_workspace_source(
    workspace_id: str,
    source_id: str,
) -> tuple[bytes, str]:
    upstream = await _request_workspace_controller(
        "GET",
        (f"/workspaces/{quote(workspace_id, safe='')}/sources/{quote(source_id, safe='')}/content"),
    )
    if upstream.status_code != 200:
        raise _upstream_error(upstream)
    mime_type = upstream.headers.get("Content-Type", "application/octet-stream")
    return upstream.content, mime_type.split(";", 1)[0].strip()


def _publication_error(error: PublicationError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        content={"error": {"code": error.code, "message": str(error)}},
    )


def _workspace_route_allowed(method: str, path: str) -> bool:
    if (method, path) in {
        ("GET", "context"),
        ("PATCH", "sources"),
        ("POST", "uploads"),
    } | workspace_draft_routes:
        return True
    if not workspace_source_route.fullmatch(path):
        return False
    leaf = path.rsplit("/", 1)[-1]
    return (method, leaf) in {
        ("POST", "import"),
        ("POST", "description-suggestion"),
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
    if controller_path == "draft/chat":
        return await _stream_workspace_controller(
            request.method,
            f"/workspaces/{quote(workspace_id, safe='')}/{controller_path}",
            body=body,
            content_type=request.headers.get("Content-Type"),
            timeout=330,
        )
    return await _proxy_workspace_controller(
        request.method,
        (f"/workspaces/{quote(workspace_id, safe='')}/{controller_path}{query}"),
        body=body,
        content_type=request.headers.get("Content-Type"),
        expected_manifest_version=request.headers.get("X-Expected-Manifest-Version"),
        timeout=(
            330
            if controller_path in {"draft/generate", "draft/chat"}
            or controller_path.endswith("/description-suggestion")
            else 30
        ),
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

    render_document = parsed.render_document(document)
    await _compile_trusted_render(render_document.model_dump(by_alias=True, mode="json"))
    return WxPostValidationSuccess(
        document=document,
        article_type=document.article_type,
        custom_article_type=document.custom_article_type,
        directives=parsed.directive_summaries(),
        inline_extensions=parsed.inline_summaries(),
        render_document=render_document,
    )


@r.post(
    "/posts/wxposts/edit",
    response_model=WxPostValidationSuccess,
    responses={422: {"model": WxPostValidationFailure}},
)
def r_edit_wxpost(payload: Any = Body(...)) -> WxPostValidationSuccess | JSONResponse:
    """Apply deterministic typed edits to an ArticleDocument without storing it."""

    try:
        request = WxPostDraftEditRequest.model_validate(payload)
        document = apply_draft_edits(request)
        parsed = validate_and_parse(document)
    except ValidationError as error:
        failure = WxPostValidationFailure(errors=pydantic_validation_issues(error))
        return JSONResponse(
            status_code=422,
            content=failure.model_dump(by_alias=True, mode="json"),
        )
    except ArticleDocumentValidationError as error:
        failure = WxPostValidationFailure(errors=error.errors)
        return JSONResponse(
            status_code=422,
            content=failure.model_dump(by_alias=True, mode="json"),
        )

    render_document = parsed.render_document(document)
    return WxPostValidationSuccess(
        document=document,
        article_type=document.article_type,
        custom_article_type=document.custom_article_type,
        directives=parsed.directive_summaries(),
        inline_extensions=parsed.inline_summaries(),
        render_document=render_document,
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
    wxpost_id: UUID = Path(..., description="The WxPost UUID to revise"),
) -> WxPostMutationResult:
    """Replace article content with compare-and-swap revision protection."""

    current = get_wxpost_by_id(wxpost_id)
    if current is None:
        raise HTTPException(status_code=404, detail="WxPost not found.")
    if current.get("source_workspace_id") is not None:
        raise HTTPException(
            status_code=409,
            detail="Workspace-linked WxPosts must be updated through publication sync.",
        )

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
        raise HTTPException(status_code=404, detail="WxPost not found.") from error
    except WxPostRevisionConflictError as error:
        raise HTTPException(
            status_code=409,
            detail="WxPost changed since the requested revision.",
        ) from error
    return _mutation_result(row)


@r.delete(
    "/posts/wxposts/{wxpost_id}/publication",
    response_model=WxPostPublicationDeleteResult,
)
async def r_delete_public_wxpost(
    request: WxPostPublicationDeleteRequest,
    wxpost_id: UUID = Path(..., description="The public WxPost UUID to delete"),
    user: User = Depends(get_current_user),
) -> WxPostPublicationDeleteResult | JSONResponse:
    del user
    try:
        workspace_id = await delete_public_wxpost(
            wxpost_id,
            expected_revision=request.expected_public_revision,
        )
    except PublicationError as error:
        return _publication_error(error)
    return WxPostPublicationDeleteResult(workspace_id=workspace_id)


@r.post(
    "/posts/wxposts/workspaces",
)
async def r_create_wxpost_workspace(
    request: Request,
    user: User = Depends(get_current_user),
) -> Response:
    return await _proxy_workspace_controller(
        "POST",
        "/workspaces",
        body=await _workspace_creation_body(request, user),
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
async def r_list_wxpost_workspaces(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> Response:
    upstream = await _request_workspace_controller(
        "GET",
        f"/workspaces?page={page}&page_size={page_size}",
    )
    if upstream.status_code != 200:
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers={"Content-Type": upstream.headers.get("Content-Type", "application/json")},
        )
    try:
        payload = upstream.json()
        items = payload["items"]
        try:
            rows = get_wxposts_by_workspace_ids([item["workspaceId"] for item in items])
        except (APIError, httpx.HTTPError):
            rows = None
        by_workspace = {row["source_workspace_id"]: row for row in rows} if rows is not None else {}
        for item in items:
            status = (
                publication_status(
                    item["workspaceId"],
                    current_draft_version=item.get("draftVersion"),
                    row=by_workspace.get(item["workspaceId"]),
                )
                if rows is not None
                else WxPostPublicationStatus(
                    state="unavailable",
                    workspace_id=item["workspaceId"],
                    current_draft_version=item.get("draftVersion"),
                )
            )
            item["publication"] = status.model_dump(by_alias=True, mode="json")
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=503,
            detail="WxPost workspace controller returned an invalid list.",
        ) from error
    return JSONResponse(content=payload)


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


@r.get(
    "/posts/wxposts/workspaces/{workspace_id}/publication",
    response_model=WxPostPublicationStatus,
)
async def r_get_wxpost_workspace_publication(
    workspace_id: str = Path(..., min_length=1),
    user: User = Depends(get_current_user),
) -> WxPostPublicationStatus:
    del user
    context = await _load_workspace_context(workspace_id)
    draft = context.get("draft")
    current_draft_version = draft.get("draftVersion") if isinstance(draft, dict) else None
    return publication_status(
        workspace_id,
        current_draft_version=current_draft_version,
        row=get_wxpost_by_workspace_id(workspace_id),
    )


@r.get(
    "/posts/wxposts/workspaces/{workspace_id}/publication/service",
    response_model=WxPostPublicationStatus,
    dependencies=[Depends(require_wxpost_service)],
)
async def r_get_wxpost_workspace_publication_for_service(
    workspace_id: str = Path(..., min_length=1),
    current_draft_version: int | None = Query(default=None, ge=1),
) -> WxPostPublicationStatus:
    """Return publication metadata without calling back into the Controller."""

    return publication_status(
        workspace_id,
        current_draft_version=current_draft_version,
        row=get_wxpost_by_workspace_id(workspace_id),
    )


@r.post(
    "/posts/wxposts/workspaces/{workspace_id}/draft-preview",
    response_model=DraftPreviewLinkResponse,
    dependencies=[Depends(require_wxpost_service)],
)
async def r_create_wxpost_draft_preview_link(
    workspace_id: str = Path(..., min_length=1),
    draft_version: int | None = Query(default=None, ge=1),
) -> DraftPreviewLinkResponse:
    """Issue a short-lived, version-bound link for one private saved Draft."""

    context = await _load_workspace_context(workspace_id)
    draft = context.get("draft")
    current_version = draft.get("draftVersion") if isinstance(draft, dict) else None
    if not isinstance(current_version, int) or current_version < 1:
        raise HTTPException(status_code=409, detail="This workspace has no saved Draft.")
    if draft_version is not None and draft_version != current_version:
        raise HTTPException(
            status_code=409,
            detail=f"Draft v{draft_version} is not the current saved Draft v{current_version}.",
        )
    expires_at = int(time.time()) + WXPOST_DRAFT_PREVIEW_TTL_SECONDS
    token = _encode_draft_preview_token(workspace_id, current_version, expires_at)
    _materials_url, draft_url = _workspace_editor_urls(workspace_id)
    return DraftPreviewLinkResponse(
        previewUrl=f"{WXPOST_PUBLIC_BASE_URL}/posts/wxposts/draft-preview/{token}",
        editorUrl=draft_url,
        workspaceId=workspace_id,
        draftVersion=current_version,
        expiresAt=expires_at,
    )


@r.get(
    "/posts/wxposts/workspaces/{workspace_id}/editor-links",
    response_model=WorkspaceEditorLinksResponse,
    dependencies=[Depends(require_wxpost_service)],
)
async def r_get_wxpost_workspace_editor_links(
    workspace_id: str = Path(..., min_length=1),
) -> WorkspaceEditorLinksResponse:
    """Return authenticated web-editor routes for a Controller workspace."""

    await _load_workspace_context(workspace_id)
    materials_url, draft_url = _workspace_editor_urls(workspace_id)
    return WorkspaceEditorLinksResponse(
        workspaceId=workspace_id,
        materialsUrl=materials_url,
        draftUrl=draft_url,
    )


@r.get("/posts/wxposts/draft-previews/{token}")
async def r_get_wxpost_draft_preview(token: str) -> dict[str, Any]:
    """Return canonical render input for a valid temporary Draft link."""

    workspace_id, draft_version, document = await _load_versioned_draft_preview(token)
    render_document = (
        validate_and_parse(document)
        .render_document(document)
        .model_dump(
            by_alias=True,
            mode="json",
        )
    )
    for media in render_document["media"]:
        source_id = media["id"]
        media["sourceUrl"] = (
            f"/posts/wxposts/draft-previews/{quote(token, safe='')}/media/" f"{quote(source_id, safe='')}"
        )
        media["posterUrl"] = None
    return {
        "workspaceId": workspace_id,
        "draftVersion": draft_version,
        "renderDocument": render_document,
    }


@r.get("/posts/wxposts/draft-previews/{token}/media/{source_id}")
async def r_get_wxpost_draft_preview_media(token: str, source_id: str) -> Response:
    """Serve only media referenced by the exact Draft bound to the link."""

    workspace_id, _draft_version, document = await _load_versioned_draft_preview(token)
    if source_id not in {media.id for media in document.media}:
        raise HTTPException(status_code=404, detail="Draft media is unavailable.")
    content, mime_type = await _load_workspace_source(workspace_id, source_id)
    return Response(
        content=content,
        media_type=mime_type,
        headers={"Cache-Control": "private, no-store"},
    )


@r.post(
    "/posts/wxposts/workspaces/{workspace_id}/publication/sync",
    response_model=WxPostPublicationStatus,
)
async def r_sync_wxpost_workspace_publication(
    request: WxPostPublicationSyncRequest,
    workspace_id: str = Path(..., min_length=1),
    user: User = Depends(get_current_user),
) -> WxPostPublicationStatus | JSONResponse:
    del user
    try:
        return await synchronize_workspace_publication(
            workspace_id,
            request,
            load_context=_load_workspace_context,
            load_source=_load_workspace_source,
            compile_render=_compile_trusted_render,
        )
    except PublicationError as error:
        return _publication_error(error)


@r.post(
    "/posts/wxposts/workspaces/{workspace_id}/voice-tone/suggestion",
    response_model=VoiceToneSuggestionResponse,
    dependencies=[Depends(get_current_user)],
)
async def r_suggest_wxpost_voice_tone(
    payload: VoiceToneSuggestionRequest,
    workspace_id: str = Path(..., min_length=1),
) -> VoiceToneSuggestionResponse | Response:
    context_response = await _proxy_workspace_controller(
        "GET",
        f"/workspaces/{quote(workspace_id, safe='')}/context",
    )
    if context_response.status_code != 200:
        return context_response
    try:
        workspace_context = json.loads(context_response.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=502,
            detail="WxPost workspace controller returned invalid context.",
        ) from error

    try:
        instruction = await suggest_voice_tone_instruction(
            hermes_url=WXPOST_HERMES_URL,
            service_token=WXPOST_SERVICE_TOKEN,
            profile_name=payload.name,
            workspace_context=workspace_context,
        )
    except HermesUnavailableError as error:
        raise HTTPException(
            status_code=503,
            detail="Hermes editorial assistant is unavailable.",
        ) from error
    except HermesResponseError as error:
        raise HTTPException(
            status_code=502,
            detail="Hermes returned an unusable voice and tone instruction.",
        ) from error
    return VoiceToneSuggestionResponse(instruction=instruction)


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


def _ready_public_wxpost(wxpost_id: UUID) -> dict:
    row = get_wxpost_by_id(wxpost_id)
    if row is None or row.get("status") != "ready" or not row.get("is_public"):
        raise HTTPException(status_code=404, detail="Public WxPost not found.")
    if not row.get("source_workspace_id"):
        raise HTTPException(status_code=422, detail="Only workspace-backed Public Revisions support WeChat Drafts.")
    return row


@r.get("/posts/wxposts/{wxpost_id}/wechat-draft", response_model=WxPostWechatDraftStatus)
async def r_get_wxpost_wechat_draft(
    wxpost_id: UUID,
    user: User = Depends(get_current_user),
) -> WxPostWechatDraftStatus:
    del user
    row = _ready_public_wxpost(wxpost_id)
    return wechat_status(row, wxpost_wechat_store.get_projection(row["source_workspace_id"]))


@r.post("/posts/wxposts/{wxpost_id}/wechat-draft", response_model=WxPostWechatDraftResult)
async def r_publish_wxpost_wechat_draft(
    request: WxPostWechatDraftRequest,
    wxpost_id: UUID,
    user: User = Depends(get_current_user),
) -> WxPostWechatDraftResult:
    del user
    row = _ready_public_wxpost(wxpost_id)
    if row["article_revision"] != request.expected_public_revision:
        raise HTTPException(status_code=409, detail="The Public Revision changed before WeChat publishing started.")
    document = article_document_from_row(row)
    render_document = validate_and_parse(document).render_document(document)
    presentation_payload = request.presentation.model_dump(by_alias=True, mode="json")
    canonical_html = await _compile_trusted_render(
        render_document.model_dump(by_alias=True, mode="json"), presentation_payload
    )
    try:
        return await publish_wechat_draft(
            row=row,
            render_document=render_document,
            presentation=request.presentation,
            canonical_html=canonical_html,
        )
    except WechatDraftError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@r.post(
    "/posts/wxposts/{wxpost_id}/wechat-draft/reset-uncertain",
    response_model=WxPostWechatDraftStatus,
)
async def r_reset_uncertain_wxpost_wechat_draft(
    request: WxPostWechatUncertainResetRequest,
    wxpost_id: UUID,
    user: User = Depends(get_current_user),
) -> WxPostWechatDraftStatus:
    del user
    row = _ready_public_wxpost(wxpost_id)
    if row["article_revision"] != request.expected_public_revision:
        raise HTTPException(status_code=409, detail="The Public Revision changed before reset was confirmed.")
    try:
        projection = wxpost_wechat_store.reset_uncertain_projection(row["source_workspace_id"])
    except RuntimeError as error:
        raise HTTPException(
            status_code=409,
            detail="The WeChat draft state is no longer eligible for reset.",
        ) from error
    return wechat_status(row, projection)


@r.post("/posts/wxposts/{wxpost_id}/wechat-draft/preview", response_model=WxPostWechatPreviewResult)
async def r_get_wxpost_wechat_preview(
    wxpost_id: UUID,
    user: User = Depends(get_current_user),
) -> WxPostWechatPreviewResult:
    del user
    row = _ready_public_wxpost(wxpost_id)
    try:
        url = await get_preview_url(row["source_workspace_id"])
    except WechatDraftError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    return WxPostWechatPreviewResult.model_validate({"previewUrl": url})


@r.get("/posts/wxposts/{slug}", response_model=WxPostPublicDetail)
async def r_get_public_wxpost(
    slug: str = Path(..., min_length=1, description="The stable public WxPost slug"),
) -> WxPostPublicDetail:
    """Return a backend-derived render document for a public WxPost."""

    detail = get_public_wxpost_by_slug(slug)
    if detail is None:
        raise HTTPException(status_code=404, detail="WxPost not found.")
    return detail
