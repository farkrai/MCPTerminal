from __future__ import annotations
import itertools
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
        self._spinner_cycle = itertools.cycle(["|", "/", "-", "\\"])
        self._spinner_frame = ""
        self._spinner_timer = None

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
            self.stop_spinner()
            inp.focus()

    def start_spinner(self) -> None:
        if self._spinner_timer is not None:
            return
        self._spinner_timer = self.set_interval(0.1, self._tick_spinner)

    def stop_spinner(self) -> None:
        self._spinner_frame = ""
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        if self.is_mounted:
            self.query_one("#mode-badge", Static).update(self._badge_text())

    def _tick_spinner(self) -> None:
        self._spinner_frame = next(self._spinner_cycle)
        self.query_one("#mode-badge", Static).update(self._badge_text())

    def _badge_text(self) -> str:
        base = "[DRY]" if self._dry_run else "[MCP]"
        return f"{base} {self._spinner_frame}".strip()
