from __future__ import annotations
import time
import psutil
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static, ProgressBar
from textual.reactive import reactive


class StatsSidebar(Widget):
    BORDER_TITLE = "System Stats"

    _cpu: reactive[float] = reactive(0.0)
    _ram_pct: reactive[float] = reactive(0.0)
    _ram_used: reactive[str] = reactive("0 GB")
    _ram_total: reactive[str] = reactive("0 GB")
    _disk_pct: reactive[float] = reactive(0.0)
    _context_tokens: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        yield Static("CPU", classes="stats-label")
        yield ProgressBar(total=100, show_eta=False, id="cpu-bar")
        yield Static("", id="cpu-val", classes="stats-value")

        yield Static(" ", classes="stats-label")
        yield Static("RAM", classes="stats-label")
        yield ProgressBar(total=100, show_eta=False, id="ram-bar")
        yield Static("", id="ram-val", classes="stats-value")

        yield Static(" ", classes="stats-label")
        yield Static("DISK /", classes="stats-label")
        yield ProgressBar(total=100, show_eta=False, id="disk-bar")
        yield Static("", id="disk-val", classes="stats-value")

        yield Static(" ", classes="stats-label")
        yield Static("UPTIME", classes="stats-label")
        yield Static("", id="uptime-val", classes="stats-value")

        yield Static(" ", classes="stats-label")
        yield Static("PROCS", classes="stats-label")
        yield Static("", id="procs-val", classes="stats-value")

        yield Static(" ", classes="stats-label")
        yield Static("CTX", classes="stats-label")
        yield Static("", id="ctx-val", classes="stats-value")

    def on_mount(self) -> None:
        self.refresh_stats()
        self.set_interval(2.0, self.refresh_stats)

    def refresh_stats(self) -> None:
        try:
            cpu = psutil.cpu_percent(interval=None)
            vm = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            boot = psutil.boot_time()
            uptime_s = int(time.time() - boot)
            h, rem = divmod(uptime_s, 3600)
            m = rem // 60
            n_procs = len(psutil.pids())

            self._cpu = cpu
            self._ram_pct = vm.percent
            self._ram_used = f"{vm.used / 1024**3:.1f}"
            self._ram_total = f"{vm.total / 1024**3:.1f}"
            self._disk_pct = disk.percent

            self.query_one("#cpu-bar", ProgressBar).advance(cpu - self._cpu if False else 0)
            self.query_one("#cpu-bar", ProgressBar).update(progress=cpu)
            self.query_one("#cpu-val", Static).update(f"{cpu:.1f}%")

            self.query_one("#ram-bar", ProgressBar).update(progress=vm.percent)
            self.query_one("#ram-val", Static).update(
                f"{vm.used / 1024**3:.1f} / {vm.total / 1024**3:.1f} GB  ({vm.percent:.0f}%)"
            )

            self.query_one("#disk-bar", ProgressBar).update(progress=disk.percent)
            self.query_one("#disk-val", Static).update(
                f"{disk.used / 1024**3:.1f} / {disk.total / 1024**3:.1f} GB  ({disk.percent:.0f}%)"
            )

            self.query_one("#uptime-val", Static).update(f"{h}h {m:02d}m")
            self.query_one("#procs-val", Static).update(str(n_procs))

        except Exception:
            pass

    def set_context_tokens(self, tokens: int) -> None:
        self._context_tokens = tokens
        if self.is_mounted:
            self.query_one("#ctx-val", Static).update(f"{tokens} tok")
