from __future__ import annotations
from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Static


class InputBar(Widget):

    class CommandSubmitted(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__()
        self._dry_run = dry_run

    def compose(self) -> ComposeResult:
        yield Static(self._badge_text(), id="mode-badge", classes="mode-badge")
        yield Input(placeholder="Type a command in natural language…", id="cmd-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            self.post_message(self.CommandSubmitted(text))
            self.query_one("#cmd-input", Input).clear()

    def set_dry_run(self, enabled: bool) -> None:
        self._dry_run = enabled
        self.query_one("#mode-badge", Static).update(self._badge_text())

    def set_busy(self, busy: bool) -> None:
        inp = self.query_one("#cmd-input", Input)
        inp.disabled = busy
        if not busy:
            inp.focus()

    def _badge_text(self) -> str:
        return "[DRY]" if self._dry_run else "[MCP]"
