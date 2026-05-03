"""Conversation history with rich formatting and timestamp badges."""
from __future__ import annotations
from datetime import datetime
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import RichLog


class HistoryPanel(Widget):
    BORDER_TITLE = " ◈ Conversation "

    def __init__(self) -> None:
        super().__init__()
        self._entries: list[dict] = []

    def compose(self) -> ComposeResult:
        yield RichLog(highlight=True, markup=True, wrap=True, id="history-log")

    def _ts(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    # ── User message ─────────────────────────────────────────────────────────

    def add_user(self, text: str) -> None:
        log = self.query_one("#history-log", RichLog)
        ts = self._ts()
        log.write(
            f"[#3a5070]{ts}[/#3a5070]  "
            f"[bold #00d4ff]▸ You[/bold #00d4ff]  "
            f"[#e0e6f0]{text}[/#e0e6f0]"
        )
        self._entries.append({"role": "user", "content": text, "ts": ts})

    # ── Tool call indicator ──────────────────────────────────────────────────

    def add_tool_call(self, tool_name: str, confidence: float) -> None:
        log = self.query_one("#history-log", RichLog)
        if confidence >= 0.7:
            conf_style = "#00e676"
        elif confidence >= 0.5:
            conf_style = "#ffab00"
        else:
            conf_style = "#ff1744"
        log.write(
            f"          [#3a5070]╰─►[/#3a5070] "
            f"[bold #c8d6e5]{tool_name}[/bold #c8d6e5]  "
            f"[{conf_style}]●[/{conf_style}] "
            f"[#3a5070]{confidence:.0%}[/#3a5070]"
        )

    # ── Result output ────────────────────────────────────────────────────────

    def add_result(self, output: str, success: bool) -> None:
        log = self.query_one("#history-log", RichLog)
        ts = self._ts()

        if success:
            badge = "[bold #00e676 on #0a1a10] ✓ OK [/bold #00e676 on #0a1a10]"
        else:
            badge = "[bold #ff1744 on #1a0a0a] ✗ ERR [/bold #ff1744 on #1a0a0a]"

        log.write(f"[#3a5070]{ts}[/#3a5070]  {badge}")

        preview = output[:600] + ("…" if len(output) > 600 else "")
        for line in preview.splitlines():
            log.write(f"          [#c8d6e5]{line}[/#c8d6e5]")
        log.write("")  # spacing
        self._entries.append({"role": "assistant", "content": output[:200], "ts": ts})

    # ── Chain ────────────────────────────────────────────────────────────────

    def add_chain_header(self, description: str, n_steps: int) -> None:
        log = self.query_one("#history-log", RichLog)
        log.write(
            f"[#3a5070]{self._ts()}[/#3a5070]  "
            f"[bold #ffab00 on #1a1500] ⛓ CHAIN [/bold #ffab00 on #1a1500] "
            f"[#ffab00]{n_steps} steps › {description}[/#ffab00]"
        )

    def add_chain_step(self, step_n: int, tool_name: str, success: bool) -> None:
        log = self.query_one("#history-log", RichLog)
        icon = "[#00e676]●[/#00e676]" if success else "[#ff1744]●[/#ff1744]"
        log.write(
            f"          {icon} [bold #c8d6e5]Step {step_n}[/bold #c8d6e5]  "
            f"[#00d4ff]{tool_name}[/#00d4ff]"
        )

    # ── System / info ────────────────────────────────────────────────────────

    def add_system(self, text: str) -> None:
        log = self.query_one("#history-log", RichLog)
        for line in text.splitlines():
            log.write(f"[italic #3a5070]  {line}[/italic #3a5070]")

    def add_error(self, text: str) -> None:
        log = self.query_one("#history-log", RichLog)
        log.write(
            f"[#3a5070]{self._ts()}[/#3a5070]  "
            f"[bold #ff1744 on #1a0a0a] ERROR [/bold #ff1744 on #1a0a0a] "
            f"[#ff1744]{text}[/#ff1744]"
        )

    def add_success_toast(self, text: str) -> None:
        log = self.query_one("#history-log", RichLog)
        log.write(
            f"[#3a5070]{self._ts()}[/#3a5070]  "
            f"[bold #00e676 on #0a1a10] OK [/bold #00e676 on #0a1a10] "
            f"[#00e676]{text}[/#00e676]"
        )

    # ── Data access ──────────────────────────────────────────────────────────

    def get_entries(self) -> list[dict]:
        return list(self._entries)

    def clear_log(self) -> None:
        self.query_one("#history-log", RichLog).clear()
        self._entries.clear()
