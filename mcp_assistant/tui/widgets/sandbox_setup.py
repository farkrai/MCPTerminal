"""First-run modal screen: prompts the user to choose their sandbox directory."""
from __future__ import annotations
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class SandboxSetupScreen(ModalScreen[Path | None]):
    """Shown on first launch (no .mcprc). Returns the chosen sandbox Path."""

    BINDINGS = [Binding("escape", "skip", "Use default", show=True)]

    DEFAULT_CSS = """
    SandboxSetupScreen {
        align: center middle;
    }
    #setup-dialog {
        width: 72;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 3;
    }
    #setup-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        width: 100%;
        margin-bottom: 1;
    }
    #setup-body {
        width: 100%;
        color: $text-muted;
        margin-bottom: 1;
    }
    #setup-error {
        width: 100%;
        color: $error;
        height: 1;
        margin-bottom: 1;
    }
    #sandbox-input {
        width: 100%;
        margin-bottom: 1;
    }
    #setup-hint {
        width: 100%;
        color: $text-muted;
        text-style: italic;
        margin-bottom: 1;
    }
    #setup-buttons {
        width: 100%;
        align: center middle;
        height: 3;
    }
    #setup-confirm {
        width: 20;
        margin: 0 2;
    }
    #setup-skip {
        width: 20;
        margin: 0 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="setup-dialog"):
            yield Label("Welcome to MCP Terminal Assistant", id="setup-title")
            yield Static(
                "This assistant controls your machine through natural language.\n"
                "First, tell it which directory it is allowed to work in.\n"
                "It will never read or write anything outside this boundary.",
                id="setup-body",
            )
            yield Input(
                value=str(Path.cwd()),
                placeholder="/path/to/your/project",
                id="sandbox-input",
            )
            yield Static(
                "Tip: use your project root, e.g. /home/you/myproject",
                id="setup-hint",
            )
            yield Static("", id="setup-error")
            with Horizontal(id="setup-buttons"):
                yield Button("Set Workspace", id="setup-confirm", variant="success")
                yield Button("Use Default",   id="setup-skip",    variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "setup-skip":
            self.dismiss(None)
            return
        self._try_confirm()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._try_confirm()

    def _try_confirm(self) -> None:
        raw = self.query_one("#sandbox-input", Input).value.strip()
        path = Path(raw).expanduser().resolve()
        error = self.query_one("#setup-error", Static)
        if not raw:
            error.update("Please enter a directory path.")
            return
        if not path.exists():
            error.update(f"Directory does not exist: {path}")
            return
        if not path.is_dir():
            error.update(f"Not a directory: {path}")
            return
        error.update("")
        self.dismiss(path)

    def action_skip(self) -> None:
        self.dismiss(None)
