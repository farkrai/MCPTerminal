from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class MCPCall:
    tool: str
    action: str
    params: dict[str, Any]
    raw_response: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MCPResult:
    call: MCPCall
    success: bool
    output: str
    data: Any = None
    error: str | None = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "call": self.call.to_dict(),
            "success": self.success,
            "output": self.output,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class MCPChainStep:
    tool: str
    action: str
    params: dict[str, Any]
    confidence: float = 1.0


@dataclass
class MCPChain:
    steps: list[MCPChainStep]
    description: str = ""
    continue_on_error: bool = False


class ParseError(Exception):
    pass
