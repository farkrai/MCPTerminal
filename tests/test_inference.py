from __future__ import annotations

import pytest
import requests

from mcp_assistant import config
from mcp_assistant.llm.inference import infer_call
from mcp_assistant.llm.prompt_builder import PromptBuilder
from mcp_assistant.llm.client import OllamaClient, _normalize_keep_alive
from mcp_assistant.mcp.schema import ParseError


class _FakeClient:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.calls = []
        self.model = config.OLLAMA_MODEL

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        model: str | None = None,
        format_schema: dict | None = None,
    ):
        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "temperature": temperature,
                "model": model,
                "format_schema": format_schema,
            }
        )
        response = next(self._responses)
        if isinstance(response, Exception):
            raise response
        return response


def test_infer_call_retries_parse_errors():
    client = _FakeClient([
        "not json",
        '{"tool": "GitTool", "action": "status", "params": {}, "confidence": 0.9}',
    ])

    result = infer_call("show git status", client, PromptBuilder(), use_cache=False)

    assert result.tool == "GitTool"
    assert len(client.calls) == 2
    assert "REMINDER: Respond ONLY with a single valid JSON object. No prose." in client.calls[1]["prompt"]


def test_infer_call_raises_after_exhausting_parse_retries():
    client = _FakeClient(["bad", "still bad", "nope"])

    with pytest.raises(ParseError):
        infer_call(
            "show git status",
            client,
            PromptBuilder(),
            max_parse_retries=2,
            use_cache=False,
        )


def test_client_generate_retries_transient_failures(monkeypatch):
    client = OllamaClient()
    attempts = {"count": 0}

    def fake_do_generate(prompt, system, temperature, model=None, format_schema=None):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise requests.Timeout("temporary timeout")
        return "ok"

    monkeypatch.setattr(client, "_do_generate", fake_do_generate)
    monkeypatch.setattr("mcp_assistant.llm.client.time.sleep", lambda _: None)
    monkeypatch.setattr("mcp_assistant.llm.client.random.uniform", lambda _a, _b: 0.0)

    assert client.generate("hello", max_retries=3) == "ok"
    assert attempts["count"] == 3


def test_normalize_keep_alive_numeric_string():
    assert _normalize_keep_alive("-1") == -1
    assert _normalize_keep_alive("300") == 300


def test_normalize_keep_alive_duration_string():
    assert _normalize_keep_alive("5m") == "5m"
