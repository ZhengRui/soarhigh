"""Read-only protocol routes for validating Hermes-authored WXPosts."""

from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ...models.wxpost import (
    ArticleDocument,
    WxPostCapabilities,
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
