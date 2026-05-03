"""Tool inspector panel — shows last call details with rich formatting."""
from __future__ import annotations
import json
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import RichLog
from mcp_assistant.server.schema import ToolResult


class ToolInspector(Widget):
    BORDER_TITLE = " ◈ Inspector "

    def __init__(self) -> None:
        super().__init__()
        self._call_count = 0
        self._total_ms = 0.0

    def compose(self) -> ComposeResult:
        yield RichLog(highlight=True, markup=True, wrap=True, id="inspector-log")

    # ── Single call ──────────────────────────────────────────────────────────

    def show_call(self, result: ToolResult) -> None:
        self._call_count += 1
        self._total_ms += result.duration_ms
        log = self.query_one("#inspector-log", RichLog)
        log.clear()

        # Status banner
        if result.success:
            log.write("[bold #00e676 on #0a1a10]  ✓  SUCCESS  [/bold #00e676 on #0a1a10]")
        else:
            log.write("[bold #ff1744 on #1a0a0a]  ✗  FAILURE  [/bold #ff1744 on #1a0a0a]")

        # Timing
        avg = self._total_ms / self._call_count if self._call_count else 0
        log.write(
            f"[#3a5070]  {result.duration_ms:.0f}ms  ·  "
            f"#{self._call_count}  ·  avg {avg:.0f}ms[/#3a5070]"
        )
        log.write("")

        # Call details
        log.write("[bold #00d4ff]  ── Call ──[/bold #00d4ff]")
        log.write(f"  [#3a5070]tool  [/#3a5070] [bold #c8d6e5]{result.tool}[/bold #c8d6e5]")

        if result.confidence >= 0.7:
            cc = "#00e676"
        elif result.confidence >= 0.5:
            cc = "#ffab00"
        else:
            cc = "#ff1744"
        log.write(f"  [#3a5070]conf  [/#3a5070] [{cc}]{result.confidence:.0%}[/{cc}]")

        if result.params:
            log.write(f"  [#3a5070]params[/#3a5070]")
            for line in json.dumps(result.params, indent=2).splitlines():
                log.write(f"    [#5a6a8a]{line}[/#5a6a8a]")

        # Output
        log.write("")
        log.write("[bold #00d4ff]  ── Output ──[/bold #00d4ff]")
        preview = result.output[:800]
        for line in preview.splitlines():
            log.write(f"  [#c8d6e5]{line}[/#c8d6e5]")
        if len(result.output) > 800:
            log.write(f"  [#3a5070]… {len(result.output) - 800} more chars[/#3a5070]")

        if result.error:
            log.write("")
            log.write(f"[bold #ff1744]  ── Error ──[/bold #ff1744]")
            log.write(f"  [#ff1744]{result.error}[/#ff1744]")

    # ── Chain result ─────────────────────────────────────────────────────────

    def show_chain(self, results: list[ToolResult]) -> None:
        log = self.query_one("#inspector-log", RichLog)
        log.clear()

        total_ms = sum(r.duration_ms for r in results)
        ok = sum(1 for r in results if r.success)
        self._call_count += len(results)
        self._total_ms += total_ms

        log.write("[bold #ffab00 on #1a1500]  ⛓  CHAIN  [/bold #ffab00 on #1a1500]")
        log.write(f"[#3a5070]  {len(results)} steps  ·  {ok} ok  ·  {total_ms:.0f}ms[/#3a5070]")
        log.write("")

        for i, result in enumerate(results, 1):
            icon = "[#00e676]●[/#00e676]" if result.success else "[#ff1744]●[/#ff1744]"
            log.write(
                f"  {icon} [bold #c8d6e5]Step {i}[/bold #c8d6e5]  "
                f"[#00d4ff]{result.tool}[/#00d4ff]  "
                f"[#3a5070]{result.duration_ms:.0f}ms[/#3a5070]"
            )
            if result.output:
                preview = result.output[:200] + ("…" if len(result.output) > 200 else "")
                for line in preview.splitlines()[:4]:
                    log.write(f"    [#5a6a8a]{line}[/#5a6a8a]")
            if result.error:
                log.write(f"    [#ff1744]{result.error}[/#ff1744]")
            log.write("")

    # ── Clarification ────────────────────────────────────────────────────────

    def show_clarification(self, tool_name: str, confidence: float) -> None:
        log = self.query_one("#inspector-log", RichLog)
        log.clear()
        log.write("[bold #ffab00 on #1a1500]  ⚠  LOW CONFIDENCE  [/bold #ffab00 on #1a1500]")
        log.write("")
        log.write(f"  [#3a5070]tool  [/#3a5070] {tool_name}")
        log.write(f"  [#3a5070]conf  [/#3a5070] [#ff1744]{confidence:.0%}[/#ff1744]")
        log.write("")
        log.write("[italic #3a5070]  Type 'yes' to confirm or rephrase…[/italic #3a5070]")

    # ── Idle ─────────────────────────────────────────────────────────────────

    def show_idle(self) -> None:
        log = self.query_one("#inspector-log", RichLog)
        log.clear()
        log.write("[bold #00d4ff]  ◈  Ready[/bold #00d4ff]")
        log.write("")
        log.write("[#3a5070]  No tool called yet.[/#3a5070]")
        log.write("")
        log.write("[#3a5070]  Try typing:[/#3a5070]")
        log.write("[italic #445566]    show git status[/italic #445566]")
        log.write("[italic #445566]    list files in src/[/italic #445566]")
        log.write("[italic #445566]    check cpu usage[/italic #445566]")
        log.write("[italic #445566]    ping google.com[/italic #445566]")
        log.write("[italic #445566]    run tests[/italic #445566]")

    def get_stats(self) -> dict:
        return {
            "call_count": self._call_count,
            "total_ms": round(self._total_ms, 2),
            "avg_ms": round(self._total_ms / self._call_count, 2) if self._call_count else 0,
        }
