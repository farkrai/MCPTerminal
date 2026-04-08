from __future__ import annotations
import json
import re
from mcp_assistant.mcp.schema import MCPCall, MCPChain, MCPChainStep, ParseError

_REQUIRED_CALL_KEYS = {"tool", "action", "params", "confidence"}
_REQUIRED_CHAIN_KEYS = {"chain", "steps"}

# Matches the outermost {...} block even if surrounded by prose or markdown fences
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_response(raw: str) -> MCPCall | MCPChain:
    """
    Parse raw LLM output into either an MCPCall or MCPChain.
    Raises ParseError if the output cannot be interpreted.
    """
    text = _strip_markdown_fences(raw).strip()
    data = _extract_json(text)

    if data.get("chain") is True:
        return _build_chain(data, raw)
    return _build_call(data, raw)


def _strip_markdown_fences(text: str) -> str:
    # Remove ```json ... ``` or ``` ... ``` wrappers that phi3 sometimes adds
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    return text


def _extract_json(text: str) -> dict:
    # First try direct parse (happy path)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: find the first {...} block via regex
    match = _JSON_BLOCK_RE.search(text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ParseError(
        f"Could not extract valid JSON from LLM response.\nRaw output:\n{text[:500]}"
    )


def _build_call(data: dict, raw: str) -> MCPCall:
    missing = _REQUIRED_CALL_KEYS - data.keys()
    if missing:
        raise ParseError(f"LLM response missing required keys: {missing}\nGot: {data}")

    confidence = float(data.get("confidence", 1.0))
    confidence = max(0.0, min(1.0, confidence))

    return MCPCall(
        tool=str(data["tool"]),
        action=str(data["action"]),
        params=dict(data.get("params") or {}),
        raw_response=raw,
        confidence=confidence,
    )


def _build_chain(data: dict, raw: str) -> MCPChain:
    steps_raw = data.get("steps")
    if not steps_raw or not isinstance(steps_raw, list):
        raise ParseError(f"Chain response missing 'steps' list.\nGot: {data}")

    steps: list[MCPChainStep] = []
    for i, s in enumerate(steps_raw):
        if not isinstance(s, dict):
            raise ParseError(f"Chain step {i} is not a dict: {s}")
        missing = {"tool", "action"} - s.keys()
        if missing:
            raise ParseError(f"Chain step {i} missing keys {missing}: {s}")
        steps.append(
            MCPChainStep(
                tool=str(s["tool"]),
                action=str(s["action"]),
                params=dict(s.get("params") or {}),
                confidence=float(s.get("confidence", 1.0)),
            )
        )

    return MCPChain(
        steps=steps,
        description=str(data.get("description", "")),
        continue_on_error=bool(data.get("continue_on_error", False)),
    )


# ── CLI smoke test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    samples = [
        # Clean JSON
        '{"tool": "FileHandler", "action": "list", "params": {"path": "."}, "confidence": 0.95}',
        # Wrapped in markdown fence
        '```json\n{"tool": "GitTool", "action": "status", "params": {}, "confidence": 0.9}\n```',
        # With surrounding prose (common phi3 behaviour)
        'Sure! Here is the JSON:\n{"tool": "SystemTool", "action": "cpu_stats", "params": {}, "confidence": 0.88}',
        # Chain
        '{"chain": true, "description": "status then diff", "steps": ['
        '{"tool": "GitTool", "action": "status", "params": {}, "confidence": 0.9},'
        '{"tool": "GitTool", "action": "diff", "params": {}, "confidence": 0.88}]}',
    ]
    for s in samples:
        try:
            result = parse_response(s)
            print(f"OK  → {result}")
        except ParseError as e:
            print(f"ERR → {e}")
