"""Inline yes/no confirmation bar shown above the text input."""
from __future__ import annotations
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Static


class ConfirmBar(Widget):
    """A narrow bar with Yes/No buttons that appears above the input box."""

    BINDINGS = [
        Binding("y", "accept", "Yes", show=True),
        Binding("n", "reject", "No",  show=True),
        Binding("escape", "reject", "Cancel", show=False),
    ]

    class Confirmed(Message):
        def __init__(self, accepted: bool) -> None:
            super().__init__()
            self.accepted = accepted

    def compose(self) -> ComposeResult:
        yield Static("", id="confirm-label")
        with Horizontal(id="confirm-buttons"):
            yield Button("Yes  [Y]", id="confirm-yes", variant="success")
            yield Button("No   [N]", id="confirm-no",  variant="error")

    def show(self, message: str) -> None:
        self.remove_class("hidden")
        self.query_one("#confirm-label", Static).update(message)
        self.focus()

    def hide(self) -> None:
        self.add_class("hidden")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.hide()
        self.post_message(self.Confirmed(event.button.id == "confirm-yes"))

    def action_accept(self) -> None:
        self.hide()
        self.post_message(self.Confirmed(True))

    def action_reject(self) -> None:
        self.hide()
        self.post_message(self.Confirmed(False))
