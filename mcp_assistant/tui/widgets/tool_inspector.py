from __future__ import annotations
import json
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import RichLog
from mcp_assistant.mcp.schema import MCPCall, MCPResult


class ToolInspector(Widget):
    BORDER_TITLE = "Tool Inspector"

    def compose(self) -> ComposeResult:
        yield RichLog(highlight=True, markup=True, wrap=True, id="inspector-log")

    def show_call(self, call: MCPCall, result: MCPResult) -> None:
        log = self.query_one("#inspector-log", RichLog)
        log.clear()

        status_style = "bold green" if result.success else "bold red"
        status_text = "SUCCESS" if result.success else "FAILURE"

        log.write(f"[{status_style}]{status_text}[/{status_style}]  [{result.duration_ms:.0f}ms]")
        log.write("")

        log.write("[bold cyan]CALL[/bold cyan]")
        log.write(f"  [cyan]tool   :[/cyan] {call.tool}")
        log.write(f"  [cyan]action :[/cyan] {call.action}")
        log.write(f"  [cyan]conf   :[/cyan] {call.confidence:.2f}")
        if result.model_used:
            log.write(f"  [cyan]model  :[/cyan] {result.model_used}")

        if call.params:
            params_str = json.dumps(call.params, indent=4)
            log.write(f"  [cyan]params :[/cyan]")
            for line in params_str.splitlines():
                log.write(f"    {line}")

        log.write("")
        log.write("[bold cyan]OUTPUT[/bold cyan]")
        for line in result.output.splitlines():
            log.write(f"  {line}")

        if result.error:
            log.write("")
            log.write(f"[bold red]ERROR[/bold red]: {result.error}")

    def show_chain(self, results: list[MCPResult]) -> None:
        log = self.query_one("#inspector-log", RichLog)
        log.clear()

        log.write(f"[bold yellow]CHAIN RESULT[/bold yellow]  ({len(results)} steps)")
        log.write("")

        for i, result in enumerate(results, 1):
            call = result.call
            status_style = "green" if result.success else "red"
            icon = "✓" if result.success else "✗"
            log.write(f"[{status_style}]{icon}[/{status_style}] Step {i}: [cyan]{call.tool}.{call.action}[/cyan]  [{result.duration_ms:.0f}ms]")
            if result.output:
                preview = result.output[:200] + ("…" if len(result.output) > 200 else "")
                for line in preview.splitlines():
                    log.write(f"    {line}")
            log.write("")

        last_data = results[-1].data if results else None
        if isinstance(last_data, dict) and "chain_summary" in last_data:
            summary = last_data["chain_summary"]
            log.write("[bold cyan]CHAIN SUMMARY[/bold cyan]")
            log.write(f"  {summary.get('summary', '')}")

    def show_clarification(self, tool: str, action: str, confidence: float) -> None:
        log = self.query_one("#inspector-log", RichLog)
        log.clear()
        log.write("[bold yellow]LOW CONFIDENCE[/bold yellow]")
        log.write("")
        log.write(f"  [cyan]tool   :[/cyan] {tool}")
        log.write(f"  [cyan]action :[/cyan] {action}")
        log.write(f"  [cyan]conf   :[/cyan] {confidence:.2f}")
        log.write("")
        log.write("[dim]Waiting for confirmation…[/dim]")

    def show_idle(self) -> None:
        log = self.query_one("#inspector-log", RichLog)
        log.clear()
        log.write("[dim]No tool called yet.[/dim]")
        log.write("")
        log.write("[dim]Type a natural language command[/dim]")
        log.write("[dim]in the input bar to get started.[/dim]")
