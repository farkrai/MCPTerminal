"""Input bar with animated mode badge and command history recall."""
from __future__ import annotations
from collections import deque
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
        self._busy = False
        self._cmd_history: deque[str] = deque(maxlen=100)
        self._history_idx: int = -1

    def compose(self) -> ComposeResult:
        badge_cls = "mode-badge badge-dry" if self._dry_run else "mode-badge badge-mcp"
        yield Static(self._badge_text(), id="mode-badge", classes=badge_cls)
        yield Input(
            placeholder="Ask me anything in natural language…",
            id="cmd-input",
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            self._cmd_history.appendleft(text)
            self._history_idx = -1
            self.post_message(self.CommandSubmitted(text))
            self.query_one("#cmd-input", Input).clear()

    def set_dry_run(self, enabled: bool) -> None:
        self._dry_run = enabled
        self._update_badge()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        inp = self.query_one("#cmd-input", Input)
        inp.disabled = busy
        self._update_badge()
        if not busy:
            inp.focus()

    def recall_previous(self) -> None:
        if not self._cmd_history:
            return
        self._history_idx = min(self._history_idx + 1, len(self._cmd_history) - 1)
        self.query_one("#cmd-input", Input).value = self._cmd_history[self._history_idx]

    def recall_next(self) -> None:
        if self._history_idx <= 0:
            self._history_idx = -1
            self.query_one("#cmd-input", Input).value = ""
            return
        self._history_idx -= 1
        self.query_one("#cmd-input", Input).value = self._cmd_history[self._history_idx]

    def get_history(self) -> list[str]:
        return list(self._cmd_history)

    def _update_badge(self) -> None:
        badge = self.query_one("#mode-badge", Static)
        badge.update(self._badge_text())
        badge.remove_class("badge-mcp", "badge-dry", "badge-busy")
        if self._busy:
            badge.add_class("badge-busy")
        elif self._dry_run:
            badge.add_class("badge-dry")
        else:
            badge.add_class("badge-mcp")

    def _badge_text(self) -> str:
        if self._busy:
            return " ⟳ "
        return " DRY " if self._dry_run else " MCP "
