from __future__ import annotations
import subprocess
import time
from pathlib import Path
from mcp_assistant.mcp.base import MCPTool
from mcp_assistant.mcp.schema import MCPCall, MCPResult
from mcp_assistant import config
from mcp_assistant.llm.ecosystem import AVAILABLE
from mcp_assistant.tools.path_utils import resolve_cwd


class GitTool(MCPTool):
    TOOL_NAME = "GitTool"
    TOOL_DESCRIPTION = "Git repository operations: status, diff, log, commit, and branch management."
    SUPPORTED_ACTIONS = {
        "status":        "Show high-level summary of staged/unstaged changes (like 'git status'). Use when user asks about current state, modified files, or what branch they're on.",
        "diff":          "Show line-level diff of changes. Use when the user asks WHAT CHANGED, what the differences are, or what is STAGED. Params: staged (bool, optional)",
        "log":           "Show recent commit history. Params: n (int, default 10)",
        "add":           "Stage files for commit. Params: path (str)",
        "commit":        "Commit staged changes. DESTRUCTIVE. Params: message (str)",
        "branch_list":   "List all branches.",
        "branch_switch": "Switch to a branch. DESTRUCTIVE. Params: branch (str)",
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
                raw = subprocess.run(cmd, capture_output=True, cwd=cwd)
                if raw.returncode != 0:
                    raise subprocess.CalledProcessError(raw.returncode, cmd, raw.stdout, raw.stderr)
                if AVAILABLE["delta"] and raw.stdout:
                    enhanced = subprocess.run(
                        ["delta", "--color-only"],
                        input=raw.stdout,
                        capture_output=True,
                    )
                    out = enhanced.stdout.decode("utf-8", errors="replace")
                else:
                    out = raw.stdout.decode("utf-8", errors="replace")
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
            p = Path(resolve_cwd(cwd))
            return p if p.is_absolute() else config.WORKSPACE_DIR / p
        return config.WORKSPACE_DIR


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)
