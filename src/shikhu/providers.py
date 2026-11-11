"""Opt-in Ollama Local, Ollama Cloud and native Bedrock inference backends."""

import json
import os
import time
from urllib.parse import urlsplit

import requests

PROVIDERS = frozenset({"openrouter", "ollama_local", "ollama_cloud", "bedrock"})
OLLAMA_LOCAL_URL = "http://127.0.0.1:11434"
OLLAMA_CLOUD_URL = "https://ollama.com"
REQUEST_TIMEOUT = 120


class ModelTruncatedError(RuntimeError):
    """The output limit was reached."""


def provider_name() -> str:
    name = os.environ.get("SHIKHU_PROVIDER", "openrouter").strip().lower()
    if name not in PROVIDERS:
        raise ValueError(
            f"Unsupported SHIKHU_PROVIDER={name!r}; choose {', '.join(sorted(PROVIDERS))}"
        )
    return name


def model_name() -> str:
    model = os.environ.get("SHIKHU_MODEL", "").strip()
    if not model:
        raise RuntimeError("Set SHIKHU_MODEL to a model available on the selected provider")
    return model


def validate_config() -> None:
    """Fail fast without contacting a provider."""
    provider = provider_name()
    if provider == "openrouter":
        if not os.environ.get("OPENROUTER_API_KEY"):
            raise RuntimeError("OPENROUTER_API_KEY is required for OpenRouter")
    else:
        model_name()
        if provider == "ollama_cloud" and not os.environ.get("OLLAMA_API_KEY"):
            raise RuntimeError("OLLAMA_API_KEY is required for Ollama Cloud")
        if provider == "ollama_local":
            _local_endpoint()


def _local_endpoint() -> str:
    base = os.environ.get("SHIKHU_OLLAMA_URL", OLLAMA_LOCAL_URL).rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/", "/api")
    ):
        raise ValueError(
            "SHIKHU_OLLAMA_URL must be an http(s) host[:port] without credentials or query"
        )
    return base.removesuffix("/api") + "/api/chat"


def _timeout() -> int:
    raw = os.environ.get("SHIKHU_REQUEST_TIMEOUT", str(REQUEST_TIMEOUT))
    try:
        timeout = int(raw)
    except ValueError as exc:
        raise ValueError("SHIKHU_REQUEST_TIMEOUT must be an integer number of seconds") from exc
    if not 1 <= timeout <= 3600:
        raise ValueError("SHIKHU_REQUEST_TIMEOUT must be between 1 and 3600 seconds")
    return timeout


def _ollama_chat(prompt: str, max_tokens: int, schema: dict | None, model: str) -> tuple[str, dict]:
    provider = provider_name()
    url = _local_endpoint() if provider == "ollama_local" else OLLAMA_CLOUD_URL + "/api/chat"
    headers = {"Content-Type": "application/json"}
    if provider == "ollama_cloud":
        headers["Authorization"] = f"Bearer {os.environ['OLLAMA_API_KEY']}"
    body: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    if schema is not None:
        if provider == "ollama_local":
            body["format"] = schema
        else:
            body["messages"][0]["content"] += (
                "\n\nReturn only valid JSON conforming to this schema, no Markdown:\n"
                + json.dumps(schema, separators=(",", ":"))
            )

    start = time.monotonic()
    try:
        response = requests.post(
            url, headers=headers, json=body, timeout=(5, _timeout()), allow_redirects=False
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"{provider} request failed ({type(exc).__name__})") from exc
    elapsed = time.monotonic() - start
    if response.status_code != 200:
        raise RuntimeError(f"{provider} returned HTTP {response.status_code}")
    try:
        data = response.json()
        content = data["message"]["content"]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"{provider} returned an invalid chat response") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(f"{provider} returned empty chat content")
    if data.get("done_reason") in ("length", "max_tokens"):
        raise ModelTruncatedError(f"{provider} truncated its output")
    return content, {
        "elapsed": elapsed,
        "model": data.get("model", model),
        "prompt_tokens": data.get("prompt_eval_count"),
        "completion_tokens": data.get("eval_count"),
        "cost": None,
    }


def _bedrock_schema(value):
    """Remove unsupported Bedrock Converse JSON-Schema constraints; validate responses locally."""
    unsupported = {
        "minimum", "maximum", "multipleOf", "exclusiveMinimum", "exclusiveMaximum",
        "minLength", "maxLength", "maxItems", "minProperties", "maxProperties", "uniqueItems",
    }
    if isinstance(value, list):
        return [_bedrock_schema(v) for v in value]
    if isinstance(value, dict):
        clean = {}
        for key, val in value.items():
            if key in unsupported or (key == "minItems" and val not in (0, 1)):
                continue
            clean[key] = _bedrock_schema(val)
        return clean
    return value


def _bedrock_chat(
    prompt: str, max_tokens: int, schema: dict | None, model: str
) -> tuple[str, dict]:
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise RuntimeError(
            "Bedrock needs boto3: install with uv tool install --with boto3 ."
        ) from exc

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE") or None, region_name=region)
    client = session.client(
        "bedrock-runtime",
        config=Config(
            connect_timeout=5,
            read_timeout=max(120, _timeout()),
            retries={"mode": "standard", "max_attempts": 3},
        ),
    )
    request: dict = {
        "modelId": model,
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": max_tokens},
    }
    if schema is not None:
        if os.environ.get("SHIKHU_BEDROCK_STRUCTURED", "on").lower() == "off":
            request["messages"][0]["content"][0]["text"] += (
                "\n\nReturn only valid JSON matching this schema, with no Markdown:\n"
                + json.dumps(schema, separators=(",", ":"))
            )
        else:
            request["outputConfig"] = {
                "textFormat": {
                    "type": "json_schema",
                    "structure": {
                        "jsonSchema": {
                            "name": "shikhu_result",
                            "description": "Validated Shikhu model response",
                            "schema": json.dumps(_bedrock_schema(schema), separators=(",", ":")),
                        }
                    },
                }
            }
    start = time.monotonic()
    response = client.converse(**request)
    elapsed = time.monotonic() - start
    if response.get("stopReason") == "max_tokens":
        raise ModelTruncatedError("Bedrock truncated its output")
    if response.get("stopReason") in (
        "guardrail_intervened",
        "content_filtered",
        "malformed_model_output",
        "model_context_window_exceeded",
    ):
        raise RuntimeError(f"Bedrock stopped generation: {response['stopReason']}")
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    content = "".join(block.get("text", "") for block in blocks if isinstance(block, dict))
    if not content.strip():
        raise RuntimeError("Bedrock returned no text content")
    usage = response.get("usage") or {}
    return content, {
        "elapsed": elapsed,
        "model": model,
        "prompt_tokens": usage.get("inputTokens"),
        "completion_tokens": usage.get("outputTokens"),
        "cost": None,
    }


def chat(
    prompt: str, max_tokens: int, response_format: dict | None = None, model: str | None = None
) -> tuple[str, dict]:
    """Return (text, usage) using the configured non-OpenRouter backend."""
    provider = provider_name()
    if provider == "openrouter":
        raise ValueError("OpenRouter requests are handled by shikhu.generator")
    validate_config()
    selected_model = model or model_name()
    if max_tokens < 1:
        raise ValueError("max_tokens must be positive")
    schema = response_format.get("json_schema", {}).get("schema") if response_format else None
    if response_format is not None and not isinstance(schema, dict):
        raise ValueError("Unsupported response_format: expected a JSON schema")
    if provider in ("ollama_local", "ollama_cloud"):
        return _ollama_chat(prompt, max_tokens, schema, selected_model)
    return _bedrock_chat(prompt, max_tokens, schema, selected_model)
