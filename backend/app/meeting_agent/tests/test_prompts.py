from app.meeting_agent.prompts import ROUTER_SYSTEM_PROMPT, SNAPSHOT_TEMPLATE


def test_router_prompt_documents_create_from_text():
    assert "create_from_text" in ROUTER_SYSTEM_PROMPT


def test_router_prompt_documents_clone_protocol():
    prompt = ROUTER_SYSTEM_PROMPT
    assert "lookup_meeting" in prompt
    assert "clone_from_meeting" in prompt
    assert "confirmation" in prompt.lower()


def test_router_prompt_documents_create_from_image():
    prompt = ROUTER_SYSTEM_PROMPT
    assert "create_from_image" in prompt
    assert "[Attachment]" in prompt


def test_router_prompt_documents_preview_meeting_path():
    """preview_meeting bridges lookup (lightweight) and clone (destructive) so
    the model can show users a historical meeting's segments BEFORE the user
    commits to clone. Pinned in prompt so future edits don't drop it."""
    prompt = ROUTER_SYSTEM_PROMPT
    assert "preview_meeting" in prompt
    # The prompt must explicitly redirect to preview_meeting when the model is
    # tempted to claim segment data is inaccessible (the bug we just fixed).
    assert "do NOT claim segment data is inaccessible" in prompt


def test_router_prompt_documents_five_creation_paths_and_gateway():
    """The agent must offer exactly five creation paths (text / image / clone
    / regular template / custom template) and refuse to fabricate a meeting
    from a vague request. This test pins the gateway rule, never-random
    rule, and both template variants so a future edit can't silently
    introduce a free-form creation backdoor or collapse Custom into
    Regular as a sub-bullet."""
    prompt = ROUTER_SYSTEM_PROMPT
    # All five paths represented.
    assert "create_from_text" in prompt
    assert "create_from_image" in prompt
    assert "clone_from_meeting" in prompt
    assert "create_from_template" in prompt
    assert '"regular_2ps"' in prompt
    assert '"custom"' in prompt
    # Path-count phrasing has migrated from "four" to "five" — guard against
    # accidental drift back.
    assert "five supported paths" in prompt
    assert "five-option menu" in prompt or "five options" in prompt
    # Gateway section guides users when no source is provided.
    assert "Creation gateway" in prompt
    # Hard rule: never invent / fabricate a meeting from a vague request.
    assert "NEVER fabricate a meeting from a vague request" in prompt
    # Push-back resistance.
    assert "do NOT cave" in prompt
    assert "Random / hallucinated meetings are out of scope" in prompt


def test_router_prompt_requires_validation_issues_to_be_surfaced():
    prompt = ROUTER_SYSTEM_PROMPT
    assert "validation_issues" in prompt
    assert "non-empty" in prompt


def test_router_prompt_delegates_creation_tables_to_route():
    """Architectural rule: the agenda meta + segment tables after a wholesale
    creation are rendered ENTIRELY by the route addendum (deterministic
    membership badges, single source of truth). The model must NOT emit
    them itself — duplicating risks bilingual-mismatched or unannotated
    tables. This test pins that delegation in the router prompt so a future
    edit can't silently add tables back to the model's output."""
    prompt = ROUTER_SYSTEM_PROMPT
    assert "After wholesale creation tools" in prompt
    # Explicit ban on the model emitting agenda tables.
    assert "Do NOT emit any meta or agenda Markdown table yourself" in prompt
    # Tool-result fields are still consultable by name so the model can
    # surface validation issues / missing fields in its short reply.
    assert "meeting_summary" in prompt
    assert "missing_required_fields" in prompt
    assert "validation_issues" in prompt
    # Bare-name role_taker contract still holds (model never sees / emits annotations).
    assert "BARE name only" in prompt
    assert "never includes a `(member)` / `(guest)` suffix" in prompt


def test_snapshot_template_supports_optional_attachment_block():
    formatted = SNAPSHOT_TEMPLATE.format(
        snapshot_json="{}",
        next_seq=1,
        tail_seq=0,
        user_message="hi",
        attachment_block="\n[Attachment]\nimage_attached: true\n",
        language_hint="",
    )
    assert "[Attachment]" in formatted
    assert "image_attached: true" in formatted


def test_snapshot_template_empty_attachment_block_renders_clean():
    formatted = SNAPSHOT_TEMPLATE.format(
        snapshot_json="{}",
        next_seq=1,
        tail_seq=0,
        user_message="hi",
        attachment_block="",
        language_hint="",
    )
    assert "[Attachment]" not in formatted


def test_snapshot_template_language_hint_renders():
    formatted = SNAPSHOT_TEMPLATE.format(
        snapshot_json="{}",
        next_seq=1,
        tail_seq=0,
        user_message="hi",
        attachment_block="",
        language_hint="[Reply language] zh\n",
    )
    assert "[Reply language] zh" in formatted


def test_router_prompt_documents_language_hint():
    from app.meeting_agent.prompts import ROUTER_SYSTEM_PROMPT

    assert "[Reply language]" in ROUTER_SYSTEM_PROMPT
    assert "default to English" in ROUTER_SYSTEM_PROMPT
