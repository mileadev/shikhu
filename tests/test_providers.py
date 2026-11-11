"""Offline provider contract tests: no network or cloud credentials required."""

import json
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from shikhu import judgments, providers


@pytest.fixture(autouse=True)
def _reset_provider(monkeypatch):
    for name in ("SHIKHU_PROVIDER", "SHIKHU_MODEL", "SHIKHU_JUDGMENT_MODEL", "SHIKHU_OLLAMA_URL", "OLLAMA_API_KEY", "AWS_PROFILE"):
        monkeypatch.delenv(name, raising=False)


def _response(content='{"questions": []}', status=200):
    return SimpleNamespace(
        status_code=status,
        json=lambda: {
            "message": {"content": content},
            "model": "test",
            "prompt_eval_count": 8,
            "eval_count": 4,
        },
    )


def test_local_does_not_forward_cloud_key(monkeypatch):
    monkeypatch.setenv("SHIKHU_PROVIDER", "ollama_local")
    monkeypatch.setenv("SHIKHU_MODEL", "qwen3:14b")
    monkeypatch.setenv("OLLAMA_API_KEY", "secret")
    monkeypatch.setenv("SHIKHU_OLLAMA_URL", "http://100.99.98.97:11434")
    post = MagicMock(return_value=_response())
    monkeypatch.setattr(providers.requests, "post", post)
    content, usage = providers.chat("hello", 128)
    assert post.call_args.args[0] == "http://100.99.98.97:11434/api/chat"
    assert "Authorization" not in post.call_args.kwargs["headers"]
    assert post.call_args.kwargs["allow_redirects"] is False
    assert content == '{"questions": []}'
    assert usage["cost"] is None


def test_cloud_is_pinned_to_ollama(monkeypatch):
    monkeypatch.setenv("SHIKHU_PROVIDER", "ollama_cloud")
    monkeypatch.setenv("SHIKHU_MODEL", "model")
    monkeypatch.setenv("OLLAMA_API_KEY", "cloud-key")
    monkeypatch.setenv("SHIKHU_OLLAMA_URL", "http://wrong.example")
    post = MagicMock(return_value=_response())
    monkeypatch.setattr(providers.requests, "post", post)
    providers.chat("hello", 128)
    assert post.call_args.args[0] == "https://ollama.com/api/chat"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer cloud-key"


def test_local_schema(monkeypatch):
    monkeypatch.setenv("SHIKHU_PROVIDER", "ollama_local")
    monkeypatch.setenv("SHIKHU_MODEL", "qwen")
    post = MagicMock(return_value=_response())
    monkeypatch.setattr(providers.requests, "post", post)
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    providers.chat("hello", 128, {"json_schema": {"schema": schema}})
    assert post.call_args.kwargs["json"]["format"] == schema


def test_cloud_schema_prompt_fallback(monkeypatch):
    monkeypatch.setenv("SHIKHU_PROVIDER", "ollama_cloud")
    monkeypatch.setenv("SHIKHU_MODEL", "model")
    monkeypatch.setenv("OLLAMA_API_KEY", "key")
    post = MagicMock(return_value=_response())
    monkeypatch.setattr(providers.requests, "post", post)
    providers.chat("hello", 128, {"json_schema": {"schema": {"type": "object"}}})
    body = post.call_args.kwargs["json"]
    assert "format" not in body
    assert "valid JSON" in body["messages"][0]["content"]


@pytest.mark.parametrize("base", [
    "file:///etc/passwd",
    "http://foo?api_key=x",
    "http://me:pwd@host",
    "http://host/other",
])
def test_invalid_local_endpoint(monkeypatch, base):
    monkeypatch.setenv("SHIKHU_PROVIDER", "ollama_local")
    monkeypatch.setenv("SHIKHU_MODEL", "qwen")
    monkeypatch.setenv("SHIKHU_OLLAMA_URL", base)
    with pytest.raises(ValueError, match="OLLAMA_URL"):
        providers.validate_config()


def test_cloud_requires_key(monkeypatch):
    monkeypatch.setenv("SHIKHU_PROVIDER", "ollama_cloud")
    monkeypatch.setenv("SHIKHU_MODEL", "model")
    with pytest.raises(RuntimeError, match="OLLAMA_API_KEY"):
        providers.validate_config()


def test_bedrock_uses_native_converse(monkeypatch):
    monkeypatch.setenv("SHIKHU_PROVIDER", "bedrock")
    monkeypatch.setenv("SHIKHU_MODEL", "us.amazon.nova-micro-v1:0")
    monkeypatch.setenv("AWS_REGION", "eu-central-1")
    client = MagicMock()
    client.converse.return_value = {
        "output": {"message": {"content": [{"text": '{"ok":true}'}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 22, "outputTokens": 7},
    }
    session = MagicMock()
    session.client.return_value = client
    stub = ModuleType("boto3")
    stub.Session = lambda **kw: session
    botocore_stub = ModuleType("botocore")
    config_stub = ModuleType("botocore.config")
    config_stub.Config = lambda **kw: kw
    monkeypatch.setitem(sys.modules, "boto3", stub)
    monkeypatch.setitem(sys.modules, "botocore", botocore_stub)
    monkeypatch.setitem(sys.modules, "botocore.config", config_stub)
    content, stats = providers.chat("prompt", 120, {"json_schema": {"schema": {"type": "object"}}})
    assert content == '{"ok":true}'
    payload = client.converse.call_args.kwargs
    assert payload["modelId"] == "us.amazon.nova-micro-v1:0"
    assert "outputConfig" in payload
    schema = json.loads(payload["outputConfig"]["textFormat"]["structure"]["jsonSchema"]["schema"])
    assert schema["type"] == "object"
    assert stats["prompt_tokens"] == 22


def test_heuristic_scores_are_not_calibrated(monkeypatch):
    monkeypatch.setenv("SHIKHU_PROVIDER", "ollama_local")
    monkeypatch.setenv("SHIKHU_MODEL", "qwen")
    monkeypatch.setattr(providers, "chat", lambda *a, **k: ('{"scores":{"q":0.8}}', {"elapsed": 0.1, "model": "qwen"}))
    answer, stats = judgments.ask("state", {"q": {"type": "noul"}})
    assert answer["q"]["noul"] == pytest.approx(0.8)
    assert stats["judgment_kind"] == "uncalibrated_heuristic"


@pytest.mark.parametrize("text", [
    '{"scores":{"q":1.5}}', '{"scores":{}}',
    '{"scores":{"q":true}}', '{"scores":{"q":"0.5"}}',
    '{"scores":{"q":0.8,"q":0.7}}',
])
def test_invalid_heuristic_scores(monkeypatch, text):
    monkeypatch.setenv("SHIKHU_PROVIDER", "ollama_local")
    monkeypatch.setenv("SHIKHU_MODEL", "qwen")
    monkeypatch.setattr(providers, "chat", lambda *a, **k: (text, {"elapsed": 0.1, "model": "qwen"}))
    with pytest.raises(judgments.JudgmentProtocolError):
        judgments.ask("state", {"q": {"type": "noul"}})


def test_non_noul_rejected():
    with pytest.raises(NotImplementedError, match="Noul"):
        judgments.ask("state", {"q": {"type": "choice"}})
