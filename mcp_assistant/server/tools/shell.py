"""Safe shell command execution tools.

Mounted under namespace "shell" → tool names become:
  shell_run, shell_which, shell_env

Security model
--------------
- Commands are matched against a blocklist of dangerous patterns before execution.
- CWD defaults to PROJECT_ROOT (sandboxed); callers may override to any path.
- Timeout enforced (default 30 s) to prevent runaway processes.
- dry_run=True prints the command without executing it.
"""
from __future__ import annotations
import os
import re
import shutil
import subprocess
from typing import Annotated

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from mcp_assistant import config
from mcp_assistant.server.state import policy

shell_mcp = FastMCP("ShellTools")

# Patterns that are unconditionally blocked regardless of dry_run.
_BLOCKED: list[re.Pattern] = [
    re.compile(r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s*/"),   # rm -rf /
    re.compile(r":\(\)\s*\{"),                           # fork bomb
    re.compile(r"dd\s+if=/dev/(zero|urandom|mem)"),      # dd wipe
    re.compile(r"mkfs\."),                               # filesystem format
    re.compile(r">\s*/dev/sda"),                         # raw disk write
    re.compile(r"shutdown|reboot|halt|poweroff"),        # system shutdown
    re.compile(r"curl\s+.*\|\s*(ba)?sh"),                # pipe-to-shell
    re.compile(r"wget\s+.*\|\s*(ba)?sh"),
    re.compile(r"chmod\s+[0-9]*7[0-9]*\s+/"),           # chmod 777 /
    re.compile(r"chown\s+.*\s+/\s*$"),                   # chown root /
]


def _is_blocked(cmd: str) -> str | None:
    """Return a human-readable reason if the command is blocked, else None."""
    for pattern in _BLOCKED:
        if pattern.search(cmd):
            return f"command matches blocked pattern: {pattern.pattern}"
    return None


# ── Tools ──────────────────────────────────────────────────────────────────────

@shell_mcp.tool(
    name="run",
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False),
    tags={"shell", "destructive"},
)
async def run(
    command: Annotated[str, "Shell command string to execute"],
    cwd: Annotated[str | None, "Working directory (default: project root)"] = None,
    timeout: Annotated[int, "Max seconds to wait before killing the process"] = 30,
    dry_run: Annotated[bool, "Show command without executing"] = False,
    ctx: Context = None,
) -> dict:
    """Execute a shell command and return stdout, stderr, and exit code.

    Blocked: rm -rf /, fork bombs, disk wipes, pipe-to-shell, shutdown commands.
    """
    if policy.dry_run_mode or dry_run:
        return {"dry_run": True, "command": command, "cwd": cwd or str(config.PROJECT_ROOT)}

    reason = _is_blocked(command)
    if reason:
        raise ToolError(f"Command blocked by security policy — {reason}")

    work_dir = cwd or str(config.PROJECT_ROOT)
    if ctx:
        await ctx.info(f"Running: {command!r} in {work_dir}")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=work_dir,
            timeout=timeout,
            env={**os.environ},
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout[:4000],
            "stderr": result.stderr[:2000],
            "command": command,
        }
    except subprocess.TimeoutExpired:
        raise ToolError(f"Command timed out after {timeout}s: {command!r}")


@shell_mcp.tool(
    name="which",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"shell", "read-only"},
)
async def which(
    name: Annotated[str, "Program name to locate (e.g. 'git', 'docker', 'ruff')"],
    ctx: Context = None,
) -> dict:
    """Check whether a program is installed and return its full path."""
    path = shutil.which(name)
    return {"name": name, "found": path is not None, "path": path}


@shell_mcp.tool(
    name="env",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"shell", "read-only"},
)
async def env(
    key: Annotated[str | None, "Variable name; omit to list all (values truncated)"] = None,
    ctx: Context = None,
) -> dict:
    """Read one or all environment variables (sensitive names are masked)."""
    _SENSITIVE = re.compile(
        r"(SECRET|PASSWORD|PASSWD|TOKEN|API_KEY|PRIVATE|CREDENTIALS|AUTH)",
        re.IGNORECASE,
    )
    if key:
        val = os.environ.get(key)
        if val and _SENSITIVE.search(key):
            val = "***masked***"
        return {"key": key, "value": val, "set": val is not None}

    result: dict[str, str] = {}
    for k, v in os.environ.items():
        result[k] = "***masked***" if _SENSITIVE.search(k) else v[:200]
    return {"count": len(result), "variables": result}
