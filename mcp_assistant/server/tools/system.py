"""System monitoring and process management tools for the FastMCP server.

Mounted under namespace "system" → tool names become:
  system_cpu_stats, system_ram_stats, system_disk_stats,
  system_list_processes, system_kill_process, system_env_info
"""
from __future__ import annotations
import os
import platform
import sys
import time
from typing import Annotated

import psutil
from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from mcp_assistant.server.state import policy

system_mcp = FastMCP("SystemTools")


# ── Tools ──────────────────────────────────────────────────────────────────────

@system_mcp.tool(
    name="cpu_stats",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=False),
    tags={"system", "monitoring"},
)
async def cpu_stats(ctx: Context = None) -> dict:
    """Get current CPU usage percentage, core count, and frequency."""
    if ctx:
        await ctx.info("Collecting CPU stats")
    pct = psutil.cpu_percent(interval=0.5)
    count_logical = psutil.cpu_count(logical=True)
    count_physical = psutil.cpu_count(logical=False)
    freq = psutil.cpu_freq()
    result = {
        "percent": pct,
        "logical_cores": count_logical,
        "physical_cores": count_physical,
    }
    if freq:
        result["freq_mhz"] = round(freq.current, 1)
    return result


@system_mcp.tool(
    name="ram_stats",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=False),
    tags={"system", "monitoring"},
)
async def ram_stats(ctx: Context = None) -> dict:
    """Get current RAM and swap usage statistics."""
    if ctx:
        await ctx.info("Collecting RAM stats")
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    gb = lambda b: round(b / 1024 ** 3, 2)
    return {
        "ram_total_gb": gb(vm.total),
        "ram_used_gb": gb(vm.used),
        "ram_available_gb": gb(vm.available),
        "ram_percent": vm.percent,
        "swap_total_gb": gb(swap.total),
        "swap_used_gb": gb(swap.used),
    }


@system_mcp.tool(
    name="disk_stats",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=False),
    tags={"system", "monitoring"},
)
async def disk_stats(ctx: Context = None) -> list[dict]:
    """Get disk usage statistics for all mounted partitions."""
    if ctx:
        await ctx.info("Collecting disk stats")
    gb = lambda b: round(b / 1024 ** 3, 2)
    partitions = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except PermissionError:
            continue
        partitions.append({
            "mount": part.mountpoint,
            "device": part.device,
            "fstype": part.fstype,
            "total_gb": gb(usage.total),
            "used_gb": gb(usage.used),
            "free_gb": gb(usage.free),
            "percent": usage.percent,
        })
    return partitions


@system_mcp.tool(
    name="list_processes",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=False),
    tags={"system", "monitoring"},
)
async def list_processes(
    n: Annotated[int, "Number of top processes to return (default: 15)"] = 15,
    ctx: Context = None,
) -> list[dict]:
    """List the top N processes sorted by CPU usage."""
    if ctx:
        await ctx.info(f"Listing top {n} processes by CPU")
    n = max(1, min(n, 100))
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "username"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
    return procs[:n]


@system_mcp.tool(
    name="kill_process",
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False),
    tags={"system", "destructive"},
)
async def kill_process(
    pid: Annotated[int | None, "Process ID to terminate"] = None,
    name: Annotated[str | None, "Process name to terminate (first match)"] = None,
    dry_run: Annotated[bool, "Preview without terminating"] = False,
    ctx: Context = None,
) -> str:
    """Send SIGTERM to a process identified by PID or name. Always requires confirmation."""
    if pid is None and name is None:
        raise ToolError("Either 'pid' or 'name' is required.")

    # Locate the process first (used for both dry-run and real kill)
    proc: psutil.Process | None = None
    if pid is not None:
        try:
            proc = psutil.Process(int(pid))
        except psutil.NoSuchProcess:
            raise ToolError(f"No process with PID {pid}")
    else:
        for p in psutil.process_iter(["name"]):
            if p.info.get("name") == name:
                proc = p
                break
        if proc is None:
            raise ToolError(f"No process named '{name}'")

    proc_name = proc.name()
    proc_pid = proc.pid

    if policy.dry_run_mode or dry_run:
        try:
            user = proc.username()
        except Exception:
            user = "unknown"
        return (
            f"[DRY RUN] Would terminate: {proc_name} "
            f"(PID {proc_pid}, user={user})"
        )

    if ctx:
        await ctx.warning(f"Terminating process: {proc_name} (PID {proc_pid})")
    proc.terminate()
    return f"SIGTERM sent to {proc_name} (PID {proc_pid})"


@system_mcp.tool(
    name="env_info",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"system", "monitoring", "read-only"},
)
async def env_info(ctx: Context = None) -> dict:
    """Get system environment information: OS, Python version, hostname, uptime."""
    if ctx:
        await ctx.info("Collecting environment info")
    boot_time = psutil.boot_time()
    uptime_s = int(time.time() - boot_time)
    h, remainder = divmod(uptime_s, 3600)
    m = remainder // 60
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "hostname": os.uname().nodename,
        "python": sys.version.split()[0],
        "uptime": f"{h}h {m}m",
        "uptime_minutes": uptime_s // 60,
    }
