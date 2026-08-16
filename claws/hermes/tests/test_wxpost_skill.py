import json
from pathlib import Path


SKILL_ROOT = (
    Path(__file__).resolve().parents[1] / "skills" / "soarhigh-wxpost-authoring"
)


def test_manual_review_catalog_covers_article_types_and_revision_boundaries() -> None:
    payload = json.loads((SKILL_ROOT / "manual-review" / "scenarios.json").read_text())
    scenarios = payload["scenarios"]

    assert payload["schemaVersion"] == 1
    assert payload["reviewMode"] == "manual"
    assert {scenario["articleType"] for scenario in scenarios} == {
        "meeting-recap",
        "member-story",
        "event-preview",
        "meeting-review",
        "action-guide",
        "custom",
    }
    assert (
        len(
            [
                scenario
                for scenario in scenarios
                if scenario["articleType"] == "meeting-recap"
            ]
        )
        >= 2
    )
    assert {scenario.get("operation") for scenario in scenarios} >= {
        "regenerate",
        "revise",
    }
    assert all(scenario["reviewCriteria"] for scenario in scenarios)


def test_skill_covers_semantic_vocabulary_without_presentation() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text()

    for directive in (
        "section",
        "image",
        "gallery",
        "video",
        "person",
        "takeaway",
        "info-grid",
        "timeline",
        "pull-quote",
    ):
        assert f"`{directive}`" in skill
    assert "==important phrase==" in skill
    assert "Do not submit `presentation`" in skill
    assert "When inputs disagree, use this order" in skill
    assert "the first marked `section` block" in skill
    assert "`coverMediaId` alone does not make an\n  image a body hero" in skill
    assert "Clearing a cover does not move that image into the article body" in skill
    assert "emphasize it\nonce with `==important phrase==`" in skill
    assert (
        "explicit request in `writingGuidance` for a supported semantic block" in skill
    )
    assert "replacement call with the same expected versions" in skill
    assert "Never parse or repair\n   serialized YAML" in skill
    assert "`wxpost_edit_draft`" in skill
    assert "`wxpost_edit_current_draft`" in skill
    assert (
        "body node indexes must come from the\n   current `draft.editContext`" in skill
    )
    assert (
        "does not insert that image into the body or change Materials inclusion"
        in skill
    )


def test_skill_contains_flexible_recipes_and_full_tone_instructions() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text()

    for heading in (
        "### Meeting Recap",
        "### Member Story",
        "### Event Preview",
        "### Meeting Review",
        "### Action Guide",
        "### Custom",
    ):
        assert heading in skill
    for preset in (
        "`encouraging`",
        "`lightly-humorous`",
        "`heartfelt`",
        "`documentary`",
        "`reflective`",
        "`celebratory`",
    ):
        assert preset in skill
    assert "not literal headings" in skill
    assert "`meetingContext`" in skill


def test_feishu_draft_preview_is_version_bound_and_screenshot_is_explicit() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text()

    assert "`wxpost_get_draft_preview` for the version just saved" in skill
    assert (
        "sends the\n   complete temporary preview link and authenticated web editor link"
        in skill
    )
    assert "do not repeat, shorten, or reconstruct either URL" in skill
    assert "opens the same workspace in Draft Edit" in skill
    assert "uses an independent Web session" in skill
    assert "confirm delivery without writing any URL" in skill
    assert "do not call `wxpost_send_web_editor_link` in that turn" in skill
    assert "does not create or update a public WxPost revision" in skill
    assert "Call `wxpost_send_draft_preview_image` only when" in skill
    assert "Do not send the image automatically" in skill
    assert "`wxpost_send_web_editor_link` with `target=materials`" in skill
    assert "with `target=draft`" in skill
