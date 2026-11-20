"""Guard the optional providers against changes to the upstream chat API."""

from unittest.mock import Mock

import pytest

from shikhu import generator, providers


def test_model_selection_follows_upstream_default(monkeypatch):
    monkeypatch.delenv("SHIKHU_MODEL", raising=False)
    assert generator.get_model() == generator.DEFAULT_MODEL


@pytest.mark.parametrize("provider", ["ollama_local", "ollama_cloud", "bedrock"])
def test_provider_dispatch_survives_upstream_changes(monkeypatch, provider):
    monkeypatch.setenv("SHIKHU_PROVIDER", provider)
    monkeypatch.setenv("SHIKHU_MODEL", "test-model")
    result = ('{"questions":[]}', {"model": "test-model", "elapsed": 0.2, "cost": None})
    backend = Mock(return_value=result)
    monkeypatch.setattr(providers, "chat", backend)
    monkeypatch.setattr(
        generator.requests,
        "post",
        Mock(side_effect=AssertionError("unexpected OpenRouter request")),
    )
    content, stats = generator._chat("Check source", 500, response_format={"type": "json_schema"})
    assert (content, stats) == result
    backend.assert_called_once_with(
        "Check source", 500, response_format={"type": "json_schema"}
    )


def test_provider_truncation_keeps_generator_retry_contract(monkeypatch):
    monkeypatch.setenv("SHIKHU_PROVIDER", "ollama_local")
    monkeypatch.setattr(
        providers,
        "chat",
        Mock(side_effect=providers.ModelTruncatedError("output limit")),
    )
    with pytest.raises(generator.TruncatedResponse, match="output limit"):
        generator._chat("Prompt", 10)
