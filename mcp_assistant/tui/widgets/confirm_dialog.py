"""Modal yes/no confirmation dialog for destructive tool calls."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class ConfirmDialog(ModalScreen[bool]):
    """Overlay dialog that returns True (yes) or False (no)."""

    BINDINGS = [
        Binding("y", "confirm", "Yes", show=True),
        Binding("n", "cancel",  "No",  show=True),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    ConfirmDialog {
        align: center middle;
    }
    #dialog {
        width: 60;
        height: auto;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }
    #message {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
        color: $warning;
    }
    #buttons {
        width: 100%;
        align: center middle;
        height: 3;
    }
    Button {
        width: 14;
        margin: 0 2;
    }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._message, id="message")
            with Horizontal(id="buttons"):
                yield Button("Yes  [Y]", id="yes-btn", variant="success")
                yield Button("No  [N]",  id="no-btn",  variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes-btn")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
