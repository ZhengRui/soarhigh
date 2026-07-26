"""Read-only protocol routes for validating Hermes-authored WePosts."""

from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ...models.wepost import (
    ArticleDocument,
    WePostCapabilities,
    WePostValidationFailure,
    WePostValidationSuccess,
)
from ...services.wepost_document import (
    ArticleDocumentValidationError,
    capabilities,
    pydantic_validation_issues,
    validate_and_parse,
)

wepost_router = r = APIRouter()


@r.get("/posts/weposts/capabilities", response_model=WePostCapabilities)
async def r_get_wepost_capabilities() -> WePostCapabilities:
    """Return the versioned authoring vocabulary owned by SoarHigh."""

    return capabilities()


@r.post(
    "/posts/weposts/validate",
    response_model=WePostValidationSuccess,
    responses={422: {"model": WePostValidationFailure}},
)
async def r_validate_wepost(payload: Any = Body(...)) -> WePostValidationSuccess | JSONResponse:
    """Validate and parse an ArticleDocument without storing or publishing it."""

    try:
        document = ArticleDocument.model_validate(payload)
    except ValidationError as error:
        failure = WePostValidationFailure(errors=pydantic_validation_issues(error))
        return JSONResponse(status_code=422, content=failure.model_dump(by_alias=True, mode="json"))

    try:
        parsed = validate_and_parse(document)
    except ArticleDocumentValidationError as error:
        failure = WePostValidationFailure(errors=error.errors)
        return JSONResponse(status_code=422, content=failure.model_dump(by_alias=True, mode="json"))

    return WePostValidationSuccess(
        article_type=document.article_type,
        custom_article_type=document.custom_article_type,
        directives=parsed.directive_summaries(),
        inline_extensions=parsed.inline_summaries(),
    )
