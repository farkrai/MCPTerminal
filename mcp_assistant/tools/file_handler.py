from __future__ import annotations
import fnmatch
import time
from pathlib import Path
from mcp_assistant.mcp.base import MCPTool
from mcp_assistant.mcp.schema import MCPCall, MCPResult
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant import config


class FileHandler(MCPTool):
    TOOL_NAME = "FileHandler"
    TOOL_DESCRIPTION = "Read, write, list, search, and delete files within sandboxed paths."
    SUPPORTED_ACTIONS = {
        "read":   "Read the contents of a file. Params: path",
        "write":  "Write content to a file. Params: path, content [DESTRUCTIVE]",
        "list":   "List files in a directory. Params: path, pattern (optional glob)",
        "search": "Search for files matching a pattern. Params: path, pattern",
        "delete": "Delete a file. Params: path [DESTRUCTIVE]",
    }
    DESTRUCTIVE_ACTIONS = {"write", "delete"}

    def __init__(self, policy: PolicyConfig | None = None) -> None:
        self._policy = policy or PolicyConfig.default()

    def execute(self, call: MCPCall) -> MCPResult:
        start = time.perf_counter()
        action = call.action
        try:
            if action == "read":
                out, data = self._read(call)
            elif action == "write":
                out, data = self._write(call)
            elif action == "list":
                out, data = self._list(call)
            elif action == "search":
                out, data = self._search(call)
            elif action == "delete":
                out, data = self._delete(call)
            else:
                return self._err(call, f"Unknown action: {action}")
        except PermissionError as e:
            return self._err(call, f"Permission denied: {e}", _ms(start))
        except Exception as e:
            return self._err(call, str(e), _ms(start))

        return self._ok(call, out, data, _ms(start))

    def dry_run(self, call: MCPCall) -> str:
        action = call.action
        path = call.params.get("path", "")
        if action == "write":
            content = call.params.get("content", "")
            preview = content[:200] + ("..." if len(content) > 200 else "")
            return f"[DRY RUN] Would write {len(content)} chars to: {path}\nPreview:\n{preview}"
        if action == "delete":
            return f"[DRY RUN] Would permanently delete: {path}"
        return super().dry_run(call)

    def validate_params(self, call: MCPCall) -> list[str]:
        errors = []
        if call.action in {"read", "write", "delete", "list", "search"}:
            if not call.params.get("path"):
                errors.append("'path' param is required")
        if call.action == "write" and "content" not in call.params:
            errors.append("'content' param is required for write")
        return errors

    # ── Private actions ───────────────────────────────────────────────────────

    def _read(self, call: MCPCall) -> tuple[str, str]:
        path = self._resolve_and_check(call.params["path"])
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > self._policy.max_file_size_mb:
            raise ValueError(f"File too large ({size_mb:.1f} MB > {self._policy.max_file_size_mb} MB limit)")
        content = path.read_text(encoding="utf-8", errors="replace")
        return f"Read {path} ({len(content)} chars)", content

    def _write(self, call: MCPCall) -> tuple[str, None]:
        path = self._resolve_and_check(call.params["path"])
        content = call.params["content"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Written {len(content)} chars to {path}", None

    def _list(self, call: MCPCall) -> tuple[str, list[str]]:
        path = self._resolve_and_check(call.params["path"])
        if not path.is_dir():
            raise ValueError(f"Not a directory: {path}")
        pattern = call.params.get("pattern", "*")
        entries = sorted(path.glob(pattern))
        names = [str(e.relative_to(path)) for e in entries]
        summary = f"Found {len(names)} item(s) in {path}"
        if names:
            summary += ":\n" + "\n".join(f"  {n}" for n in names[:50])
            if len(names) > 50:
                summary += f"\n  ... and {len(names) - 50} more"
        return summary, names

    def _search(self, call: MCPCall) -> tuple[str, list[str]]:
        path = self._resolve_and_check(call.params["path"])
        pattern = call.params.get("pattern", "*")
        matches = sorted(path.rglob(pattern))
        paths = [str(m) for m in matches if m.is_file()]
        summary = f"Found {len(paths)} match(es) for '{pattern}' under {path}"
        if paths:
            summary += ":\n" + "\n".join(f"  {p}" for p in paths[:50])
        return summary, paths

    def _delete(self, call: MCPCall) -> tuple[str, None]:
        path = self._resolve_and_check(call.params["path"])
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if path.is_dir():
            raise ValueError(f"Cannot delete a directory: {path}. Only files are supported.")
        path.unlink()
        return f"Deleted: {path}", None

    def _resolve_and_check(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if not path.is_absolute():
            path = config.PROJECT_ROOT / path
        path = path.resolve()
        if not self._policy.is_path_allowed(path):
            raise PermissionError(f"Path not allowed by policy: {path}")
        return path


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)
