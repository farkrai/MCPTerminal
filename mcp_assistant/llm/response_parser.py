"""Parse raw LLM output into ToolCall / ToolChain objects.

Expected LLM output formats
----------------------------
Single call::

    {"tool": "file_read", "params": {"path": "README.md"}, "confidence": 0.95}

Chain::

    {
      "chain": true,
      "description": "check status then show diff",
      "steps": [
        {"tool": "git_status", "params": {}, "confidence": 0.92},
        {"tool": "git_diff",   "params": {}, "confidence": 0.90}
      ]
    }
"""
from __future__ import annotations
import json
import re

from mcp_assistant.server.schema import ParseError, ToolCall, ToolChain, ToolChainStep

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_response(raw: str) -> ToolCall | ToolChain:
    """Parse raw LLM text into a ``ToolCall`` or ``ToolChain``.

    Raises :class:`ParseError` if the output is unparseable.
    """
    text = _strip_thinking_tags(_strip_markdown_fences(raw)).strip()
    data = _extract_json(text)

    if data.get("chain") is True:
        return _build_chain(data, raw)
    return _build_call(data, raw)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _strip_markdown_fences(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    return text


def _strip_thinking_tags(text: str) -> str:
    """Remove <think>...</think> blocks emitted by reasoning models (deepseek-r1)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = _JSON_BLOCK_RE.search(text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ParseError(
        f"Could not extract valid JSON from LLM response.\nRaw:\n{text[:500]}"
    )


def _build_call(data: dict, raw: str) -> ToolCall:
    if "tool" not in data:
        raise ParseError(f"Missing 'tool' key in LLM response.\nGot: {data}")
    confidence = float(data.get("confidence", 1.0))
    confidence = max(0.0, min(1.0, confidence))
    return ToolCall(
        tool=str(data["tool"]),
        params=dict(data.get("params") or {}),
        confidence=confidence,
        raw_response=raw,
    )


def _build_chain(data: dict, raw: str) -> ToolChain:
    steps_raw = data.get("steps")
    if not steps_raw or not isinstance(steps_raw, list):
        raise ParseError(f"Chain missing 'steps' list.\nGot: {data}")

    steps: list[ToolChainStep] = []
    for i, s in enumerate(steps_raw):
        if not isinstance(s, dict) or "tool" not in s:
            raise ParseError(f"Chain step {i} invalid: {s}")
        steps.append(
            ToolChainStep(
                tool=str(s["tool"]),
                params=dict(s.get("params") or {}),
                confidence=float(s.get("confidence", 1.0)),
            )
        )

    return ToolChain(
        steps=steps,
        description=str(data.get("description", "")),
        continue_on_error=bool(data.get("continue_on_error", False)),
    )
