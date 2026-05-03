"""System monitor sidebar with native Sparkline charts and animated metrics."""
from __future__ import annotations
import time
from collections import deque
import psutil
from textual.app import ComposeResult
from textual.color import Color
from textual.widget import Widget
from textual.widgets import Static, ProgressBar, Sparkline, Rule


def _severity_class(pct: float) -> str:
    if pct < 60:
        return "metric-good"
    if pct < 85:
        return "metric-warn"
    return "metric-crit"


class StatsSidebar(Widget):
    BORDER_TITLE = " ◈ System Monitor "

    def __init__(self) -> None:
        super().__init__()
        self._cpu_data: deque[float] = deque(maxlen=50)
        self._ram_data: deque[float] = deque(maxlen=50)
        self._net_rx_prev: int = 0
        self._net_tx_prev: int = 0

    def compose(self) -> ComposeResult:
        # CPU
        yield Static("  CPU", classes="section-header")
        yield ProgressBar(total=100, show_eta=False, id="cpu-bar")
        yield Static("", id="cpu-val", classes="metric-value")
        yield Sparkline([], min_color="#0d1526", max_color="#00d4ff", id="cpu-spark")

        yield Rule(line_style="heavy")

        # RAM
        yield Static("  Memory", classes="section-header")
        yield ProgressBar(total=100, show_eta=False, id="ram-bar")
        yield Static("", id="ram-val", classes="metric-value")
        yield Sparkline([], min_color="#0d1526", max_color="#00e676", id="ram-spark")

        yield Rule(line_style="heavy")

        # Disk
        yield Static("  Disk", classes="section-header")
        yield ProgressBar(total=100, show_eta=False, id="disk-bar")
        yield Static("", id="disk-val", classes="metric-value")

        yield Rule(line_style="heavy")

        # Network
        yield Static("  Network", classes="section-header")
        yield Static("", id="net-val", classes="metric-value")

        yield Rule(line_style="heavy")

        # System
        yield Static("  System", classes="section-header")
        yield Static("", id="uptime-val", classes="metric-value")
        yield Static("", id="procs-val", classes="metric-value")
        yield Static("", id="load-val", classes="metric-value")

    def on_mount(self) -> None:
        try:
            counters = psutil.net_io_counters()
            self._net_rx_prev = counters.bytes_recv
            self._net_tx_prev = counters.bytes_sent
        except Exception:
            pass
        self._refresh()
        self.set_interval(2.0, self._refresh)

    def _refresh(self) -> None:
        try:
            self._update_cpu()
            self._update_ram()
            self._update_disk()
            self._update_network()
            self._update_system()
        except Exception:
            pass

    def _update_cpu(self) -> None:
        cpu = psutil.cpu_percent(interval=None)
        self._cpu_data.append(cpu)

        bar = self.query_one("#cpu-bar", ProgressBar)
        bar.update(progress=cpu)

        val = self.query_one("#cpu-val", Static)
        cores = psutil.cpu_count()
        val.update(f"  {cpu:5.1f}%  ·  {cores} cores")
        val.remove_class("metric-good", "metric-warn", "metric-crit")
        val.add_class(_severity_class(cpu))

        spark = self.query_one("#cpu-spark", Sparkline)
        spark.data = list(self._cpu_data)

    def _update_ram(self) -> None:
        vm = psutil.virtual_memory()
        self._ram_data.append(vm.percent)

        bar = self.query_one("#ram-bar", ProgressBar)
        bar.update(progress=vm.percent)

        val = self.query_one("#ram-val", Static)
        val.update(f"  {vm.used / 1024**3:.1f} / {vm.total / 1024**3:.1f} GB")
        val.remove_class("metric-good", "metric-warn", "metric-crit")
        val.add_class(_severity_class(vm.percent))

        spark = self.query_one("#ram-spark", Sparkline)
        spark.data = list(self._ram_data)

    def _update_disk(self) -> None:
        disk = psutil.disk_usage("/")
        self.query_one("#disk-bar", ProgressBar).update(progress=disk.percent)
        val = self.query_one("#disk-val", Static)
        val.update(f"  {disk.used / 1024**3:.1f} / {disk.total / 1024**3:.1f} GB  ({disk.percent}%)")
        val.remove_class("metric-good", "metric-warn", "metric-crit")
        val.add_class(_severity_class(disk.percent))

    def _update_network(self) -> None:
        try:
            counters = psutil.net_io_counters()
        except Exception:
            return
        rx_d = counters.bytes_recv - self._net_rx_prev
        tx_d = counters.bytes_sent - self._net_tx_prev
        self._net_rx_prev = counters.bytes_recv
        self._net_tx_prev = counters.bytes_sent

        def fmt(b: int) -> str:
            r = b / 2.0
            if r > 1048576:
                return f"{r / 1048576:.1f} MB/s"
            if r > 1024:
                return f"{r / 1024:.1f} KB/s"
            return f"{r:.0f} B/s"

        self.query_one("#net-val", Static).update(f"  ↓ {fmt(rx_d)}  ↑ {fmt(tx_d)}")

    def _update_system(self) -> None:
        boot = psutil.boot_time()
        up = int(time.time() - boot)
        d, rem = divmod(up, 86400)
        h, rem = divmod(rem, 3600)
        m = rem // 60
        up_str = f"{d}d {h}h {m:02d}m" if d else f"{h}h {m:02d}m"

        self.query_one("#uptime-val", Static).update(f"  ⏱ Uptime  {up_str}")
        self.query_one("#procs-val", Static).update(f"  ⚙ Procs   {len(psutil.pids())}")

        try:
            l1, l5, l15 = psutil.getloadavg()
            self.query_one("#load-val", Static).update(f"  ⚡ Load    {l1:.2f}  {l5:.2f}  {l15:.2f}")
        except (AttributeError, OSError):
            self.query_one("#load-val", Static).update("  ⚡ Load    N/A")
