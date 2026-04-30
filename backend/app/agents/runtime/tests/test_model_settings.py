from app.agents.runtime.model_settings import build_model_settings


def test_gemini_3x_uses_thinking_level():
    settings = build_model_settings("google-gla:gemini-3.1-flash-lite-preview", thinking_level="HIGH")
    assert settings is not None
    cfg = settings["google_thinking_config"]
    assert cfg["thinking_level"] == "HIGH"
    assert cfg["include_thoughts"] is True
    assert "thinking_budget" not in cfg


def test_gemini_3x_uppercases_lowercase_input():
    settings = build_model_settings("google-gla:gemini-3-pro", thinking_level="medium")
    assert settings["google_thinking_config"]["thinking_level"] == "MEDIUM"


def test_gemini_25_full_uses_thinking_budget_dynamic():
    settings = build_model_settings("google-gla:gemini-2.5-pro", thinking_level="HIGH")
    assert settings is not None
    cfg = settings["google_thinking_config"]
    assert cfg["thinking_budget"] == -1
    assert "thinking_level" not in cfg


def test_gemini_25_flash_lite_returns_none():
    assert build_model_settings("google-gla:gemini-2.5-flash-lite") is None


def test_openai_o_series_uses_reasoning_effort():
    settings = build_model_settings("openai:o4-mini", thinking_level="MEDIUM")
    assert settings is not None
    assert settings["openai_reasoning_effort"] == "medium"


def test_openai_gpt5_uses_reasoning_effort():
    settings = build_model_settings("openai:gpt-5", thinking_level="LOW")
    assert settings is not None
    assert settings["openai_reasoning_effort"] == "low"


def test_openai_non_reasoning_returns_none():
    assert build_model_settings("openai:gpt-4o") is None
    assert build_model_settings("openai:gpt-3.5-turbo") is None


def test_unknown_provider_returns_none():
    assert build_model_settings("anthropic:claude-haiku-4-5") is None
