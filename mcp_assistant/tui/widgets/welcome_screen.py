"""Animated welcome banner — fades out on first interaction or after timeout."""
from __future__ import annotations
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


_BANNER = r"""
 ╔══════════════════════════════════════════════════════════════╗
 ║                                                              ║
 ║    ███╗   ███╗ ██████╗██████╗    ████████╗███████╗██████╗    ║
 ║    ████╗ ████║██╔════╝██╔══██╗   ╚══██╔══╝██╔════╝██╔══██╗   ║
 ║    ██╔████╔██║██║     ██████╔╝      ██║   █████╗  ██████╔╝   ║
 ║    ██║╚██╔╝██║██║     ██╔═══╝       ██║   ██╔══╝  ██╔══██╗   ║
 ║    ██║ ╚═╝ ██║╚██████╗██║           ██║   ███████╗██║  ██║   ║
 ║    ╚═╝     ╚═╝ ╚═════╝╚═╝           ╚═╝   ╚══════╝╚═╝  ╚═╝   ║
 ║                                                              ║
 ╚══════════════════════════════════════════════════════════════╝
""".strip("\n")


class WelcomeScreen(Widget):

    def compose(self) -> ComposeResult:
        yield Static(_BANNER, id="welcome-title")
        yield Static(
            "Offline AI-Powered Terminal  ·  Model Context Protocol  ·  Ollama",
            id="welcome-subtitle",
        )
        yield Static(
            "Ctrl+P Palette  ·  Ctrl+D Dry-Run  ·  Ctrl+E Export  ·  "
            "Ctrl+L Clear  ·  F1 Help  ·  Ctrl+Q Quit",
            id="welcome-info",
        )
