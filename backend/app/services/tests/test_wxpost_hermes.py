from __future__ import annotations

import json

import httpx
import pytest

import app.services.wxpost_hermes as wxpost_hermes


@pytest.mark.asyncio
async def test_suggest_voice_tone_instruction_uses_focused_hermes_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "Keep the humour observational and kind, using "
                                "small human details instead of punchlines."
                            )
                        }
                    }
                ]
            },
        )

    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def client_factory(*, timeout: int, trust_env: bool) -> httpx.AsyncClient:
        assert timeout == 90
        assert trust_env is False
        return real_client(transport=transport)

    monkeypatch.setattr(wxpost_hermes.httpx, "AsyncClient", client_factory)
    instruction = await wxpost_hermes.suggest_voice_tone_instruction(
        hermes_url="http://hermes",
        service_token="existing-service-token",
        profile_name="Kindly funny",
        workspace_context={
            "manifest": {
                "editorial": {
                    "articleType": "custom",
                    "customArticleType": "Event Recap",
                    "writingGuidance": "Focus on first-time guests.",
                    "voiceTone": {
                        "presets": ["encouraging"],
                        "customProfiles": [
                            {
                                "name": "Room energy",
                                "instruction": "Keep the pace lively.",
                                "selected": True,
                            }
                        ],
                    },
                }
            }
        },
    )

    assert instruction.startswith("Keep the humour observational")
    assert len(captured) == 1
    request = captured[0]
    assert str(request.url) == "http://hermes/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer existing-service-token"
    payload = json.loads(request.content)
    assert payload["stream"] is False
    assert payload["model"] == "hermes-agent"
    assert "Do not call tools" in payload["messages"][0]["content"]
    assert 'Custom profile name: "Kindly funny"' in payload["messages"][1]["content"]
    assert "Event Recap" in payload["messages"][1]["content"]
    assert "Room energy" in payload["messages"][1]["content"]


@pytest.mark.asyncio
async def test_suggest_voice_tone_instruction_rejects_failed_hermes_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            502,
            json={"error": {"message": "provider unavailable"}},
        )
    )

    def client_factory(*, timeout: int, trust_env: bool) -> httpx.AsyncClient:
        return real_client(transport=transport)

    monkeypatch.setattr(wxpost_hermes.httpx, "AsyncClient", client_factory)

    with pytest.raises(wxpost_hermes.HermesUnavailableError):
        await wxpost_hermes.suggest_voice_tone_instruction(
            hermes_url="http://hermes",
            service_token="existing-service-token",
            profile_name="Warm",
            workspace_context={},
        )


@pytest.mark.asyncio
async def test_suggest_voice_tone_instruction_rejects_non_text_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": None}}]},
        )
    )

    def client_factory(*, timeout: int, trust_env: bool) -> httpx.AsyncClient:
        return real_client(transport=transport)

    monkeypatch.setattr(wxpost_hermes.httpx, "AsyncClient", client_factory)

    with pytest.raises(wxpost_hermes.HermesResponseError):
        await wxpost_hermes.suggest_voice_tone_instruction(
            hermes_url="http://hermes",
            service_token="existing-service-token",
            profile_name="Warm",
            workspace_context={},
        )
