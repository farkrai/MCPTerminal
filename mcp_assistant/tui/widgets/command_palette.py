"""Command palette (Ctrl+P) — fuzzy-search tool actions and special commands."""
from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Static


# All palette-accessible commands
PALETTE_COMMANDS: list[dict] = [
    {"label": "!help", "desc": "Show help and keyboard shortcuts"},
    {"label": "!dry-run on", "desc": "Enable dry-run mode (preview before execute)"},
    {"label": "!dry-run off", "desc": "Disable dry-run mode"},
    {"label": "!context", "desc": "Show current conversation context"},
    {"label": "!context clear", "desc": "Clear conversation context"},
    {"label": "!verify", "desc": "Verify today's audit log chain integrity"},
    {"label": "!history", "desc": "Show command history"},
    {"label": "!export md", "desc": "Export session to Markdown file"},
    {"label": "!export json", "desc": "Export session to JSON file"},
    {"label": "!stats", "desc": "Show session statistics"},
    {"label": "!tools", "desc": "List available tools and actions"},
    {"label": "!clear", "desc": "Clear conversation history display"},
    # Tool quick-access
    {"label": "show git status", "desc": "GitTool.status — working tree status"},
    {"label": "show git diff", "desc": "GitTool.diff — unstaged changes"},
    {"label": "show git log", "desc": "GitTool.log — recent commits"},
    {"label": "list files", "desc": "FileHandler.list — directory listing"},
    {"label": "check cpu usage", "desc": "SystemTool.cpu_stats"},
    {"label": "check ram usage", "desc": "SystemTool.ram_stats"},
    {"label": "check disk usage", "desc": "SystemTool.disk_stats"},
    {"label": "list processes", "desc": "SystemTool.list_processes"},
    {"label": "show environment info", "desc": "SystemTool.env_info"},
    {"label": "run tests", "desc": "TestRunner.run — execute test suite"},
    {"label": "detect test framework", "desc": "TestRunner.detect"},
    {"label": "current time", "desc": "TimeTool.now — local date/time"},
    {"label": "ping host", "desc": "NetworkTool.ping — ICMP ping"},
    {"label": "dns lookup", "desc": "NetworkTool.dns_lookup — resolve hostname"},
    {"label": "check port", "desc": "NetworkTool.port_check — TCP port scan"},
    {"label": "http probe", "desc": "NetworkTool.http_probe — HTTP status check"},
]


class CommandPalette(Widget):

    class CommandSelected(Message):
        def __init__(self, command: str) -> None:
            super().__init__()
            self.command = command

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search commands…", id="palette-input")
        with Vertical(id="palette-results"):
            pass

    def on_mount(self) -> None:
        self._render_results("")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "palette-input":
            self._render_results(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "palette-input":
            results_container = self.query_one("#palette-results", Vertical)
            items = results_container.query(".palette-item")
            if items:
                label = items[0].renderable
                if isinstance(label, str):
                    self.post_message(self.CommandSelected(label.split("  ")[0].strip()))

    def _render_results(self, query: str) -> None:
        container = self.query_one("#palette-results", Vertical)
        container.remove_children()

        q = query.lower().strip()
        matches = []
        for cmd in PALETTE_COMMANDS:
            if not q or q in cmd["label"].lower() or q in cmd["desc"].lower():
                matches.append(cmd)
            if len(matches) >= 10:
                break

        for cmd in matches:
            s = Static(
                f"{cmd['label']}  [dim]{cmd['desc']}[/dim]",
                classes="palette-item",
            )
            container.mount(s)

    def focus_input(self) -> None:
        self.query_one("#palette-input", Input).focus()
        self.query_one("#palette-input", Input).value = ""
