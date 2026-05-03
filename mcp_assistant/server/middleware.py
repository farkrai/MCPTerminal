"""FastMCP middleware: policy enforcement, timing, and tamper-evident audit logging.

PolicyMiddleware  – blocks disabled tools before execution.
TimingMiddleware  – records per-tool wall-clock duration in a session histogram.
AuditMiddleware  – appends every call/result to the SHA-256-chained JSONL log.
"""
from __future__ import annotations
import collections
import time
from typing import DefaultDict

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext

from mcp_assistant.server.state import audit, policy

class PolicyMiddleware(Middleware):
    """Enforce tool-level policy rules before a tool executes."""

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        tool_name: str = context.message.name          # e.g. "file_read"
        namespace = tool_name.split("_")[0]            # e.g. "file"

        if not policy.is_tool_allowed(namespace):
            raise ToolError(
                f"Tool '{namespace}' is disabled by policy (.mcprc)."
            )

        return await call_next(context)


class TimingMiddleware(Middleware):
    """Collect per-tool latency histograms across the session.

    Access live stats via ``TimingMiddleware.global_stats()``.
    Useful for surfacing slow tools in the TUI sidebar.
    """

    # Process-level storage (shared across all instances)
    _totals: DefaultDict[str, float] = collections.defaultdict(float)
    _counts: DefaultDict[str, int] = collections.defaultdict(int)
    _min: DefaultDict[str, float] = collections.defaultdict(lambda: float("inf"))
    _max: DefaultDict[str, float] = collections.defaultdict(float)

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        start = time.perf_counter()
        try:
            result = await call_next(context)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            tool = context.message.name
            TimingMiddleware._totals[tool] += elapsed_ms
            TimingMiddleware._counts[tool] += 1
            TimingMiddleware._min[tool] = min(TimingMiddleware._min[tool], elapsed_ms)
            TimingMiddleware._max[tool] = max(TimingMiddleware._max[tool], elapsed_ms)
        return result

    @classmethod
    def global_stats(cls) -> dict[str, dict]:
        """Return a snapshot of timing stats keyed by tool name."""
        out: dict[str, dict] = {}
        for tool, count in cls._counts.items():
            total = cls._totals[tool]
            out[tool] = {
                "calls": count,
                "avg_ms": round(total / count, 1),
                "min_ms": round(cls._min[tool], 1),
                "max_ms": round(cls._max[tool], 1),
                "total_ms": round(total, 1),
            }
        return out

    @classmethod
    def reset(cls) -> None:
        """Clear all timing data (useful in tests)."""
        cls._totals.clear()
        cls._counts.clear()
        cls._min.clear()
        cls._max.clear()


class AuditMiddleware(Middleware):
    """Log every tool call and its result to the SHA-256-chained audit log."""

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        tool_name: str = context.message.name
        arguments: dict = dict(context.message.arguments or {})
        start = time.perf_counter()

        try:
            result = await call_next(context)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            audit.log(
                tool=tool_name,
                params=arguments,
                output="",
                success=False,
                error=str(exc),
                duration_ms=round(duration_ms, 2),
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000

        # Extract text output from the MCP result content list
        output_text = ""
        if result and hasattr(result, "content"):
            for item in result.content:
                if hasattr(item, "text"):
                    output_text = item.text[:500]
                    break

        is_error = getattr(result, "isError", False) or False
        audit.log(
            tool=tool_name,
            params=arguments,
            output=output_text,
            success=not is_error,
            error=None,
            duration_ms=round(duration_ms, 2),
        )
        return result
