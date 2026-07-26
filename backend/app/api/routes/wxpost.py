"""Authoring and public-read routes for Hermes-authored WXPosts."""

import secrets
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

from ...config import WXPOST_PUBLIC_BASE_URL, WXPOST_SERVICE_TOKEN
from ...db.wxpost import (
    WxPostNotFoundError,
    WxPostRevisionConflictError,
    create_wxpost,
    get_public_wxpost_by_slug,
    get_wxpost_by_id,
    update_wxpost,
)
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

wxpost_router = r = APIRouter()
service_bearer = HTTPBearer(auto_error=False)


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


@r.get("/posts/wxposts/{slug}", response_model=WxPostPublicDetail)
async def r_get_public_wxpost(
    slug: str = Path(..., min_length=1, description="The stable public WXPost slug"),
) -> WxPostPublicDetail:
    """Return a backend-derived render document for a public WXPost."""

    detail = get_public_wxpost_by_slug(slug)
    if detail is None:
        raise HTTPException(status_code=404, detail="WXPost not found.")
    return detail
