from __future__ import annotations
import subprocess
import time
from pathlib import Path
from mcp_assistant.mcp.base import MCPTool
from mcp_assistant.mcp.schema import MCPCall, MCPResult
from mcp_assistant import config


class GitTool(MCPTool):
    TOOL_NAME = "GitTool"
    TOOL_DESCRIPTION = "Git repository operations: status, diff, log, commit, and branch management."
    SUPPORTED_ACTIONS = {
        "status":        "Show working tree status. Params: cwd (optional)",
        "diff":          "Show unstaged or staged diff. Params: cwd, staged (bool, optional)",
        "log":           "Show recent commit log. Params: cwd, n (int, optional, default 10)",
        "add":           "Stage files. Params: cwd, path (file or '.' for all)",
        "commit":        "Commit staged changes. Params: cwd, message [DESTRUCTIVE]",
        "branch_list":   "List all branches. Params: cwd (optional)",
        "branch_switch": "Switch branch. Params: cwd, branch [DESTRUCTIVE]",
    }
    DESTRUCTIVE_ACTIONS = {"commit", "branch_switch"}

    def execute(self, call: MCPCall) -> MCPResult:
        start = time.perf_counter()
        action = call.action
        cwd = self._resolve_cwd(call.params.get("cwd"))
        try:
            if action == "status":
                out = self._run(["git", "status"], cwd)
            elif action == "diff":
                staged = call.params.get("staged", False)
                cmd = ["git", "diff", "--cached"] if staged else ["git", "diff"]
                out = self._run(cmd, cwd)
                if not out.strip():
                    out = "(No changes)" if not staged else "(Nothing staged)"
            elif action == "log":
                n = int(call.params.get("n", 10))
                out = self._run(["git", "log", f"--oneline", f"-{n}"], cwd)
            elif action == "add":
                path = call.params.get("path", ".")
                out = self._run(["git", "add", path], cwd)
                out = out or f"Staged: {path}"
            elif action == "commit":
                message = call.params.get("message", "")
                if not message:
                    return self._err(call, "'message' param is required for commit", _ms(start))
                out = self._run(["git", "commit", "-m", message], cwd)
            elif action == "branch_list":
                out = self._run(["git", "branch", "-a"], cwd)
            elif action == "branch_switch":
                branch = call.params.get("branch", "")
                if not branch:
                    return self._err(call, "'branch' param is required for branch_switch", _ms(start))
                out = self._run(["git", "checkout", branch], cwd)
            else:
                return self._err(call, f"Unknown action: {action}", _ms(start))
        except subprocess.CalledProcessError as e:
            return self._err(call, e.stderr or str(e), _ms(start))
        except Exception as e:
            return self._err(call, str(e), _ms(start))

        return self._ok(call, out.strip() or "(empty output)", duration_ms=_ms(start))

    def dry_run(self, call: MCPCall) -> str:
        action = call.action
        cwd = self._resolve_cwd(call.params.get("cwd"))
        if action == "commit":
            message = call.params.get("message", "(no message)")
            try:
                staged = self._run(["git", "diff", "--cached", "--stat"], cwd)
            except Exception:
                staged = "(could not get staged diff)"
            return (
                f"[DRY RUN] Would commit with message: \"{message}\"\n"
                f"Staged changes:\n{staged or '(nothing staged)'}"
            )
        if action == "branch_switch":
            return f"[DRY RUN] Would switch to branch: {call.params.get('branch')}"
        return super().dry_run(call)

    # ── Private ───────────────────────────────────────────────────────────────

    def _run(self, cmd: list[str], cwd: Path) -> str:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )
        return result.stdout

    def _resolve_cwd(self, cwd: str | None) -> Path:
        if cwd:
            p = Path(cwd)
            return p if p.is_absolute() else config.PROJECT_ROOT / p
        return config.PROJECT_ROOT


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)
