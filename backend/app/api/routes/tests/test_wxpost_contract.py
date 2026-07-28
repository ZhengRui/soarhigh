import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api.routes.post as post_route
from app.api.serv import app
from app.models.wxpost import ArticleDocument

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "wxpost-meeting-recap-v1.json"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def complete_article() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def _plain_article(*, article_type: str = "custom", custom_type: str | None = "Field Reflection") -> dict:
    article = {
        "schemaVersion": 1,
        "title": "A Form the Club Has Not Named Yet",
        "articleType": article_type,
        "bodyMarkdown": (
            "This article is intentionally plain long-form Markdown.\n\n"
            "## It chooses its own shape\n\n"
            "There is no gallery, callout, prescribed ending, or required section order."
        ),
        "media": [],
        "presentation": {
            "layout": "brand-default",
            "palette": "paper-neutral",
            "appearance": "light",
            "typeface": "editorial-serif",
        },
    }
    if custom_type is not None:
        article["customArticleType"] = custom_type
    return article


def test_capabilities_describe_the_versioned_authoring_contract(client: TestClient) -> None:
    response = client.get("/posts/wxposts/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == 1
    assert payload["renderVersion"] == 1
    assert payload["articleTypes"] == [
        "meeting-recap",
        "member-story",
        "event-preview",
        "meeting-review",
        "action-guide",
        "custom",
    ]
    assert payload["directives"] == [
        "gallery",
        "video",
        "takeaway",
        "person",
        "info-grid",
        "timeline",
        "pull-quote",
    ]
    assert payload["inlineExtensions"] == ["key-point"]
    assert payload["inlineSyntax"] == {"key-point": "==important phrase=="}
    assert payload["documentSchema"]["properties"]["bodyMarkdown"]["type"] == "string"
    assert payload["documentSchema"]["properties"]["customArticleType"]["anyOf"][0]["type"] == "string"
    assert payload["renderDocumentSchema"]["properties"]["renderVersion"]["const"] == 1
    assert payload["renderDocumentSchema"]["properties"]["body"]["type"] == "array"
    assert payload["presentation"] == {
        "layouts": ["brand-default", "field-notes", "editorial-feature"],
        "palettes": ["brand-blue", "paper-neutral", "warm-terracotta"],
        "appearances": ["light", "dark"],
        "typefaces": ["modern-sans", "editorial-serif", "humanist-mix"],
    }
    assert payload["defaultPresentation"] == {
        "layout": "brand-default",
        "palette": "paper-neutral",
        "appearance": "light",
        "typeface": "editorial-serif",
    }
    assert {item["name"] for item in payload["directiveSchemas"]} == set(payload["directives"])
    assert all(item["payloadSchema"]["additionalProperties"] is False for item in payload["directiveSchemas"])


def test_complete_english_article_validates_end_to_end(
    client: TestClient,
    complete_article: dict,
) -> None:
    response = client.post("/posts/wxposts/validate", json=complete_article)

    assert response.status_code == 200
    payload = response.json()
    document = payload.pop("document")
    render_document = payload.pop("renderDocument")
    assert payload == {
        "valid": True,
        "schemaVersion": 1,
        "articleType": "meeting-recap",
        "customArticleType": None,
        "directives": [
            {"name": "info-grid", "line": 5, "mediaIds": []},
            {"name": "timeline", "line": 20, "mediaIds": []},
            {"name": "gallery", "line": 34, "mediaIds": ["M01", "M02", "M03"]},
            {"name": "pull-quote", "line": 46, "mediaIds": []},
            {"name": "person", "line": 51, "mediaIds": ["M04"]},
            {"name": "video", "line": 61, "mediaIds": ["V01"]},
            {"name": "takeaway", "line": 70, "mediaIds": []},
        ],
        "inlineExtensions": [{"name": "key-point", "count": 3}],
    }
    assert document == ArticleDocument.model_validate(complete_article).model_dump(
        by_alias=True,
        mode="json",
    )
    assert render_document["renderVersion"] == 1
    assert render_document["title"] == complete_article["title"]
    assert render_document["sourceMeetingId"] == "meeting-236"
    assert render_document["presentation"] == complete_article["presentation"]
    assert [node["kind"] for node in render_document["body"]] == [
        "markdown",
        "directive",
        "markdown",
        "directive",
        "directive",
        "markdown",
        "directive",
        "directive",
        "markdown",
        "directive",
        "markdown",
        "directive",
        "markdown",
    ]
    assert [node["name"] for node in render_document["body"] if node["kind"] == "directive"] == [
        "info-grid",
        "timeline",
        "gallery",
        "pull-quote",
        "person",
        "video",
        "takeaway",
    ]
    assert render_document["body"][0] == {
        "kind": "markdown",
        "source": (
            "The room became quiet when Maya reached the front. "
            "She had prepared an opening, but the next sentence had disappeared.\n\n"
            "What happened after that mattered more than a polished speech. "
            "==She stayed in the room and tried again.==\n"
        ),
        "line": 1,
    }
    assert render_document["body"][1] == {
        "kind": "directive",
        "name": "info-grid",
        "payload": {
            "title": "Meeting at a glance",
            "items": [
                {"label": "Theme", "value": "Learning in public"},
                {"label": "Date", "value": "July 18, 2026"},
                {"label": "Place", "value": "SoarHigh Club"},
            ],
        },
        "line": 5,
    }


def test_custom_article_accepts_plain_markdown_without_directives(client: TestClient) -> None:
    response = client.post("/posts/wxposts/validate", json=_plain_article())

    assert response.status_code == 200
    assert response.json()["articleType"] == "custom"
    assert response.json()["customArticleType"] == "Field Reflection"
    assert response.json()["directives"] == []
    assert response.json()["renderDocument"]["body"] == [
        {
            "kind": "markdown",
            "source": _plain_article()["bodyMarkdown"],
            "line": 1,
        }
    ]


def test_validation_returns_the_canonical_camel_case_document(
    client: TestClient,
    complete_article: dict,
) -> None:
    article = copy.deepcopy(complete_article)
    article["title"] = "  Canonical title  "
    article["body_markdown"] = article.pop("bodyMarkdown")
    article["media"][0]["include"] = 1
    article["media"][0]["order"] = "0"

    response = client.post("/posts/wxposts/validate", json=article)

    assert response.status_code == 200
    document = response.json()["document"]
    assert document["title"] == "Canonical title"
    assert document["bodyMarkdown"] == complete_article["bodyMarkdown"]
    assert "body_markdown" not in document
    assert document["media"][0]["include"] is True
    assert document["media"][0]["order"] == 0


def test_body_markdown_rejects_a_duplicate_level_one_title(client: TestClient) -> None:
    article = _plain_article()
    article["bodyMarkdown"] = "# A Duplicate Title\n\nThe article body begins here."

    response = client.post("/posts/wxposts/validate", json=article)

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "code": "body_h1_not_allowed",
            "path": ["bodyMarkdown"],
            "message": "ArticleDocument.title is the only title; bodyMarkdown must start with prose or H2.",
            "line": 1,
            "directive": None,
        }
    ]


def test_canonical_markdown_whitespace_is_not_normalized_during_validation(client: TestClient) -> None:
    article = _plain_article()
    article["bodyMarkdown"] = "\n:::takeaway\ntext: Leading whitespace remains part of the source.\n:::\n"

    response = client.post("/posts/wxposts/validate", json=article)

    assert response.status_code == 200
    assert response.json()["directives"][0]["line"] == 2


def test_article_types_do_not_impose_modules_or_order(
    client: TestClient,
    complete_article: dict,
) -> None:
    custom = _plain_article(custom_type="Photo Essay with Practical Notes")
    custom["media"] = complete_article["media"]
    custom["bodyMarkdown"] = (
        ":::takeaway\n"
        "text: Begin with the conclusion when that serves the reader.\n"
        ":::\n\n"
        "The prose may come after a rich block.\n\n"
        ":::gallery\n"
        "items:\n"
        "  - M03\n"
        "  - M01\n"
        ":::\n\n"
        "A custom article can end without a prescribed closing module."
    )

    custom_response = client.post("/posts/wxposts/validate", json=custom)
    standard_response = client.post(
        "/posts/wxposts/validate",
        json=_plain_article(article_type="member-story", custom_type=None),
    )

    assert custom_response.status_code == 200
    assert [item["name"] for item in custom_response.json()["directives"]] == ["takeaway", "gallery"]
    assert standard_response.status_code == 200
    assert standard_response.json()["directives"] == []


@pytest.mark.parametrize(
    "article_type",
    [
        "meeting-recap",
        "member-story",
        "event-preview",
        "meeting-review",
        "action-guide",
    ],
)
def test_every_standard_article_type_accepts_freeform_markdown(
    client: TestClient,
    article_type: str,
) -> None:
    response = client.post(
        "/posts/wxposts/validate",
        json=_plain_article(article_type=article_type, custom_type=None),
    )

    assert response.status_code == 200
    assert response.json()["articleType"] == article_type
    assert response.json()["directives"] == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("layout", "brand-default"),
        ("layout", "field-notes"),
        ("layout", "editorial-feature"),
        ("palette", "brand-blue"),
        ("palette", "paper-neutral"),
        ("palette", "warm-terracotta"),
        ("appearance", "light"),
        ("appearance", "dark"),
        ("typeface", "modern-sans"),
        ("typeface", "editorial-serif"),
        ("typeface", "humanist-mix"),
    ],
)
def test_every_advertised_presentation_value_is_accepted(
    client: TestClient,
    field: str,
    value: str,
) -> None:
    article = _plain_article()
    article["presentation"][field] = value

    response = client.post("/posts/wxposts/validate", json=article)

    assert response.status_code == 200


def test_custom_article_requires_a_meaningful_label(client: TestClient) -> None:
    response = client.post(
        "/posts/wxposts/validate",
        json=_plain_article(custom_type=None),
    )

    assert response.status_code == 422
    assert response.json() == {
        "valid": False,
        "errors": [
            {
                "code": "custom_article_type_required",
                "path": ["customArticleType"],
                "message": "customArticleType is required when articleType is custom.",
                "line": None,
                "directive": None,
            }
        ],
    }


def test_standard_article_rejects_a_custom_type_label(client: TestClient) -> None:
    response = client.post(
        "/posts/wxposts/validate",
        json=_plain_article(article_type="event-preview", custom_type="Should not be present"),
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "custom_article_type_not_allowed"
    assert response.json()["errors"][0]["path"] == ["customArticleType"]


@pytest.mark.parametrize(
    ("body", "expected_code"),
    [
        (
            ":::hero\ntext: This directive is not registered.\n:::",
            "unknown_directive",
        ),
        (
            ":::takeaway\ntext: [an unfinished YAML value\n:::",
            "malformed_directive_yaml",
        ),
        (
            ":::takeaway\ntext: Never closed",
            "unclosed_directive",
        ),
        (
            "A safe paragraph.\n\n<script>alert('no')</script>",
            "unsafe_html",
        ),
    ],
)
def test_markdown_failures_return_repairable_errors(
    client: TestClient,
    body: str,
    expected_code: str,
) -> None:
    article = _plain_article()
    article["bodyMarkdown"] = body

    response = client.post("/posts/wxposts/validate", json=article)

    assert response.status_code == 422
    assert response.json()["valid"] is False
    assert expected_code in {error["code"] for error in response.json()["errors"]}
    matching = next(error for error in response.json()["errors"] if error["code"] == expected_code)
    assert matching["path"][0] == "bodyMarkdown"
    assert matching["line"] is not None


@pytest.mark.parametrize(
    ("body", "expected_code", "expected_path_tail"),
    [
        (
            ":::takeaway\ntext: Keep the constraint small.\ncolor: orange\n:::",
            "invalid_directive_payload",
            ["color"],
        ),
        (
            ":::takeaway\n- This is a list, not a mapping.\n:::",
            "directive_payload_not_mapping",
            ["directive:takeaway"],
        ),
        (
            ":::pull-quote\ntext: <strong>Untrusted HTML</strong>\n:::",
            "unsafe_html",
            ["text"],
        ),
    ],
)
def test_directive_payload_failures_identify_the_repair_location(
    client: TestClient,
    body: str,
    expected_code: str,
    expected_path_tail: list[str],
) -> None:
    article = _plain_article()
    article["bodyMarkdown"] = body

    response = client.post("/posts/wxposts/validate", json=article)

    assert response.status_code == 422
    matching = next(error for error in response.json()["errors"] if error["code"] == expected_code)
    assert matching["path"][-len(expected_path_tail) :] == expected_path_tail
    expected_directive = "takeaway" if "takeaway" in body else "pull-quote"
    assert matching["directive"] == expected_directive


def test_directive_media_must_exist_be_included_and_have_the_right_kind(
    client: TestClient,
    complete_article: dict,
) -> None:
    article = copy.deepcopy(complete_article)
    article["bodyMarkdown"] = (
        ":::gallery\n" "items:\n" "  - MISSING\n" "  - V01\n" "  - M02\n" ":::\n\n" ":::video\n" "media: M01\n" ":::"
    )
    article["media"][1]["include"] = False

    response = client.post("/posts/wxposts/validate", json=article)

    assert response.status_code == 422
    errors = response.json()["errors"]
    assert [error["code"] for error in errors] == [
        "unknown_media_reference",
        "media_kind_mismatch",
        "media_not_included",
        "media_kind_mismatch",
    ]
    assert errors[0]["path"] == ["bodyMarkdown", "directive:gallery", "items", 0]
    assert errors[-1]["path"] == ["bodyMarkdown", "directive:video", "media"]


def test_media_manifest_and_cover_failures_are_structured(
    client: TestClient,
    complete_article: dict,
) -> None:
    article = copy.deepcopy(complete_article)
    article["media"][1]["id"] = "M01"
    article["media"][2]["order"] = 0
    article["coverMediaId"] = "V01"

    response = client.post("/posts/wxposts/validate", json=article)

    assert response.status_code == 422
    errors = response.json()["errors"]
    assert {error["code"] for error in errors} >= {
        "duplicate_media_id",
        "duplicate_media_order",
        "cover_media_kind_mismatch",
    }
    assert next(error for error in errors if error["code"] == "duplicate_media_id")["path"] == [
        "media",
        1,
        "id",
    ]
    assert next(error for error in errors if error["code"] == "cover_media_kind_mismatch")["path"] == ["coverMediaId"]


def test_document_contract_rejects_invalid_presentation_and_unknown_fields(client: TestClient) -> None:
    article = _plain_article()
    article["presentation"]["palette"] = "neon-rainbow"
    article["modules"] = []

    response = client.post("/posts/wxposts/validate", json=article)

    assert response.status_code == 422
    errors = response.json()["errors"]
    assert {tuple(error["path"]) for error in errors} == {
        ("presentation", "palette"),
        ("modules",),
    }
    assert all(error["line"] is None for error in errors)


def test_document_contract_rejects_an_unsupported_schema_version(client: TestClient) -> None:
    article = _plain_article()
    article["schemaVersion"] = 2

    response = client.post("/posts/wxposts/validate", json=article)

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "literal_error"
    assert response.json()["errors"][0]["path"] == ["schemaVersion"]


def test_ordinary_post_route_remains_available(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        post_route,
        "get_post_by_slug",
        lambda slug, user_id: {
            "id": "post-1",
            "title": "An Ordinary Post",
            "slug": slug,
            "content": "Ordinary Markdown remains unchanged.",
            "is_public": True,
        },
    )
    app.dependency_overrides[post_route.get_optional_user] = lambda: None
    try:
        response = client.get("/posts/an-ordinary-post")
    finally:
        app.dependency_overrides.pop(post_route.get_optional_user, None)

    assert response.status_code == 200
    assert response.json()["slug"] == "an-ordinary-post"
    assert response.json()["content"] == "Ordinary Markdown remains unchanged."
