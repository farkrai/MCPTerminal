from __future__ import annotations
import os
import time
import psutil
from mcp_assistant.mcp.base import MCPTool
from mcp_assistant.mcp.schema import MCPCall, MCPResult


class SystemTool(MCPTool):
    TOOL_NAME = "SystemTool"
    TOOL_DESCRIPTION = "System resource monitoring and process management."
    SUPPORTED_ACTIONS = {
        "cpu_stats":      "CPU usage and core count. Params: (none)",
        "ram_stats":      "RAM usage and availability. Params: (none)",
        "disk_stats":     "Disk usage for all mounted partitions. Params: (none)",
        "list_processes": "List top N processes by CPU. Params: n (int, default 15)",
        "kill_process":   "Kill a process by PID or name. Params: pid OR name [DESTRUCTIVE]",
        "env_info":       "Show OS, Python version, hostname, uptime. Params: (none)",
    }
    DESTRUCTIVE_ACTIONS = {"kill_process"}
    ALWAYS_CONFIRM_ACTIONS = {"kill_process"}

    def execute(self, call: MCPCall) -> MCPResult:
        start = time.perf_counter()
        action = call.action
        try:
            if action == "cpu_stats":
                out, data = self._cpu_stats()
            elif action == "ram_stats":
                out, data = self._ram_stats()
            elif action == "disk_stats":
                out, data = self._disk_stats()
            elif action == "list_processes":
                n = int(call.params.get("n", 15))
                out, data = self._list_processes(n)
            elif action == "kill_process":
                out, data = self._kill_process(call)
            elif action == "env_info":
                out, data = self._env_info()
            else:
                return self._err(call, f"Unknown action: {action}", _ms(start))
        except Exception as e:
            return self._err(call, str(e), _ms(start))

        return self._ok(call, out, data, _ms(start))

    def dry_run(self, call: MCPCall) -> str:
        if call.action == "kill_process":
            pid = call.params.get("pid")
            name = call.params.get("name")
            target = f"PID {pid}" if pid else f"name '{name}'"
            try:
                proc = self._find_process(call)
                info = f"{proc.name()} (PID {proc.pid}, user={proc.username()})"
            except Exception:
                info = target
            return f"[DRY RUN] Would terminate process: {info}"
        return super().dry_run(call)

    # ── Private actions ───────────────────────────────────────────────────────

    def _cpu_stats(self) -> tuple[str, dict]:
        pct = psutil.cpu_percent(interval=0.5)
        count = psutil.cpu_count(logical=True)
        phys = psutil.cpu_count(logical=False)
        freq = psutil.cpu_freq()
        data = {"percent": pct, "logical_cores": count, "physical_cores": phys}
        out = (
            f"CPU Usage : {pct}%\n"
            f"Cores     : {phys} physical, {count} logical\n"
        )
        if freq:
            out += f"Frequency : {freq.current:.0f} MHz"
            data["freq_mhz"] = round(freq.current, 1)
        return out, data

    def _ram_stats(self) -> tuple[str, dict]:
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()

        def fmt(b: int) -> str:
            return f"{b / (1024**3):.2f} GB"

        data = {
            "total_gb": round(vm.total / 1024**3, 2),
            "used_gb": round(vm.used / 1024**3, 2),
            "available_gb": round(vm.available / 1024**3, 2),
            "percent": vm.percent,
        }
        out = (
            f"RAM Total     : {fmt(vm.total)}\n"
            f"RAM Used      : {fmt(vm.used)} ({vm.percent}%)\n"
            f"RAM Available : {fmt(vm.available)}\n"
            f"Swap Used     : {fmt(swap.used)} / {fmt(swap.total)}"
        )
        return out, data

    def _disk_stats(self) -> tuple[str, list[dict]]:
        lines = []
        data = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except PermissionError:
                continue
            gb = lambda b: round(b / 1024**3, 2)
            lines.append(
                f"{part.mountpoint:<20} {gb(usage.used):.1f}/{gb(usage.total):.1f} GB "
                f"({usage.percent}% used)"
            )
            data.append({
                "mount": part.mountpoint,
                "total_gb": gb(usage.total),
                "used_gb": gb(usage.used),
                "percent": usage.percent,
            })
        return "Disk Usage:\n" + "\n".join(lines), data

    def _list_processes(self, n: int) -> tuple[str, list[dict]]:
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "username"]):
            try:
                procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
        top = procs[:n]
        lines = [f"{'PID':>7}  {'CPU%':>5}  {'MEM%':>5}  {'USER':<12}  NAME"]
        lines.append("-" * 55)
        for p in top:
            lines.append(
                f"{p['pid']:>7}  {p['cpu_percent'] or 0:>5.1f}  "
                f"{p['memory_percent'] or 0:>5.1f}  "
                f"{(p['username'] or '')[:12]:<12}  {p['name']}"
            )
        return "\n".join(lines), top

    def _kill_process(self, call: MCPCall) -> tuple[str, dict]:
        proc = self._find_process(call)
        name = proc.name()
        pid = proc.pid
        proc.terminate()
        return f"Sent SIGTERM to {name} (PID {pid})", {"pid": pid, "name": name}

    def _env_info(self) -> tuple[str, dict]:
        import platform, sys
        boot = psutil.boot_time()
        uptime_s = int(time.time() - boot)
        h, m = divmod(uptime_s // 60, 60)
        data = {
            "os": platform.system(),
            "os_version": platform.version(),
            "hostname": os.uname().nodename,
            "python": sys.version,
            "uptime_min": uptime_s // 60,
        }
        out = (
            f"OS       : {platform.system()} {platform.release()}\n"
            f"Hostname : {data['hostname']}\n"
            f"Python   : {sys.version.split()[0]}\n"
            f"Uptime   : {h}h {m}m"
        )
        return out, data

    def _find_process(self, call: MCPCall) -> psutil.Process:
        pid = call.params.get("pid")
        name = call.params.get("name")
        if pid:
            return psutil.Process(int(pid))
        if name:
            for p in psutil.process_iter(["name"]):
                if p.info["name"] == name:
                    return p
            raise ProcessLookupError(f"No process named '{name}'")
        raise ValueError("Either 'pid' or 'name' param is required for kill_process")


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)
