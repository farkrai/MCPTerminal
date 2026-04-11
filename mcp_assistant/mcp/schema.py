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
    model_used: str = ""

    def to_dict(self) -> dict:
        return {
            "call": self.call.to_dict(),
            "success": self.success,
            "output": self.output,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "model_used": self.model_used,
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


MCPCall_SCHEMA = {
    "type": "object",
    "required": ["tool", "action", "params", "confidence", "complexity"],
    "properties": {
        "tool": {"type": "string"},
        "action": {"type": "string"},
        "params": {"type": "object"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "complexity": {"type": "string", "enum": ["routing", "low", "medium", "high"]},
    },
    "additionalProperties": False,
}

ChainSummary_SCHEMA = {
    "type": "object",
    "required": ["summary", "steps_succeeded", "steps_failed", "overall_status"],
    "properties": {
        "summary": {"type": "string"},
        "steps_succeeded": {"type": "integer"},
        "steps_failed": {"type": "integer"},
        "overall_status": {"type": "string", "enum": ["success", "partial", "failure"]},
    },
    "additionalProperties": False,
}

OrchestratorClassification_SCHEMA = {
    "type": "object",
    "required": ["intent", "difficulty", "mode_hint", "confidence", "reasoning"],
    "properties": {
        "intent": {"type": "string"},
        "difficulty": {"type": "string", "enum": ["low", "medium", "high"]},
        "mode_hint": {"type": "string", "enum": ["direct", "mcp"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reasoning": {"type": "string"},
    },
    "additionalProperties": False,
}

OrchestratorPlan_SCHEMA = {
    "type": "object",
    "required": ["mode", "objective", "steps", "specialist", "reasoning"],
    "properties": {
        "mode": {"type": "string", "enum": ["direct", "mcp"]},
        "objective": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {"type": "string"},
        },
        "specialist": {
            "type": "string",
            "enum": ["direct", "codegen", "review", "gitops", "sysperf", "mcpexec"],
        },
        "reasoning": {"type": "string"},
    },
    "additionalProperties": False,
}

DirectAnswer_SCHEMA = {
    "type": "object",
    "required": ["answer", "confidence"],
    "properties": {
        "answer": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "additionalProperties": False,
}

FinalResponse_SCHEMA = {
    "type": "object",
    "required": [
        "status",
        "mode",
        "summary",
        "details",
        "tools_used",
        "workflow",
        "next_step",
    ],
    "properties": {
        "status": {"type": "string", "enum": ["success", "clarification", "error"]},
        "mode": {"type": "string", "enum": ["direct", "mcp"]},
        "summary": {"type": "string"},
        "details": {
            "type": "array",
            "items": {"type": "string"},
        },
        "tools_used": {
            "type": "array",
            "items": {"type": "string"},
        },
        "workflow": {
            "type": "array",
            "items": {"type": "string"},
        },
        "next_step": {"type": "string"},
    },
    "additionalProperties": False,
}
