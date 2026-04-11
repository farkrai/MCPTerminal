from __future__ import annotations
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import RichLog, Static


class HistoryPanel(Widget):
    BORDER_TITLE = "Conversation"

    def __init__(self) -> None:
        super().__init__()
        self._stream_buffer = ""

    def compose(self) -> ComposeResult:
        yield Static("", id="streaming-line")
        yield RichLog(highlight=True, markup=True, wrap=True, id="history-log")

    def add_user(self, text: str) -> None:
        log = self.query_one("#history-log", RichLog)
        log.write(f"[bold cyan]You:[/bold cyan] {text}")

    def add_tool_call(self, tool: str, action: str, confidence: float) -> None:
        log = self.query_one("#history-log", RichLog)
        log.write(f"[dim]  → {tool}.{action}  (conf {confidence:.2f})[/dim]")

    def add_result(self, output: str, success: bool) -> None:
        log = self.query_one("#history-log", RichLog)
        style = "green" if success else "red"
        icon = "✓" if success else "✗"
        # Truncate very long outputs in history — full output is in inspector
        preview = output[:400] + ("…" if len(output) > 400 else "")
        log.write(f"[{style}]{icon}[/{style}] {preview}")
        log.write("")  # blank line between entries

    def add_chain_header(self, description: str, n_steps: int) -> None:
        log = self.query_one("#history-log", RichLog)
        log.write(f"[yellow]⛓ Chain ({n_steps} steps): {description}[/yellow]")

    def add_chain_step(self, step_n: int, tool: str, action: str, success: bool) -> None:
        log = self.query_one("#history-log", RichLog)
        icon = "✓" if success else "✗"
        color = "green" if success else "red"
        log.write(f"  [{color}]{icon}[/{color}] Step {step_n}: {tool}.{action}")

    def add_system(self, text: str) -> None:
        log = self.query_one("#history-log", RichLog)
        log.write(f"[dim italic]{text}[/dim italic]")

    def add_error(self, text: str) -> None:
        log = self.query_one("#history-log", RichLog)
        log.write(f"[bold red]Error:[/bold red] {text}")

    def start_streaming_response(self) -> None:
        self._stream_buffer = ""
        self.query_one("#streaming-line", Static).update("Thinking…")

    def append_streaming_token(self, token: str) -> None:
        self._stream_buffer += token
        self.query_one("#streaming-line", Static).update(self._stream_buffer or "Thinking…")

    def finish_streaming_response(self) -> None:
        self._stream_buffer = ""
        self.query_one("#streaming-line", Static).update("")
