"""Dataclasses for FastMCP tool calls and results."""
from __future__ import annotations
from dataclasses import dataclass, field


class ParseError(Exception):
    """Raised when the LLM output cannot be parsed into a ToolCall."""


@dataclass
class ToolCall:
    """A single FastMCP tool invocation produced by the LLM."""
    tool: str            # FastMCP tool name, e.g. "file_read"
    params: dict         # Tool parameters dict
    confidence: float = 1.0
    raw_response: str = ""

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "params": self.params,
            "confidence": round(self.confidence, 4),
        }


@dataclass
class ToolChainStep:
    """One step in a multi-step chain."""
    tool: str
    params: dict
    confidence: float = 1.0


@dataclass
class ToolChain:
    """Ordered sequence of tool calls produced by the LLM for multi-step requests."""
    steps: list[ToolChainStep]
    description: str = ""
    continue_on_error: bool = False

    def min_confidence(self) -> float:
        if not self.steps:
            return 0.0
        return min(s.confidence for s in self.steps)


@dataclass
class ToolResult:
    """Result of a single FastMCP tool invocation (used by TUI/CLI)."""
    tool: str
    params: dict
    output: str          # raw tool output (JSON / plain text)
    success: bool
    error: str | None = None
    duration_ms: float = 0.0
    confidence: float = 1.0
    summary: str | None = None   # LLM-generated human-readable explanation
