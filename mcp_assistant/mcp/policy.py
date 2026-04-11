from __future__ import annotations
import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from mcp_assistant import config

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - compatibility for Python < 3.11
    import tomli as tomllib


@dataclass
class PolicyConfig:
    sandbox_root: Path
    blocked_paths: list[str]
    max_file_size_mb: int
    allowed_tools: list[str]
    disabled_tools: list[str]
    confirm_required: set[str]        # "ToolName.action" strings
    confirm_all_destructive: bool
    dry_run_mode: bool
    confidence_threshold: float
    context_window_size: int
    chain_continue_on_error: bool
    audit_retention_days: int = 30

    # ── Path safety ───────────────────────────────────────────────────────────

    def is_path_allowed(self, path: str | Path) -> bool:
        p = Path(path).resolve()

        # Must be under sandbox_root
        try:
            p.relative_to(self.sandbox_root)
        except ValueError:
            return False

        # Must not match any blocked pattern
        path_str = str(p)
        for pattern in self.blocked_paths:
            if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(p.name, pattern):
                return False

        return True

    def is_tool_allowed(self, tool_name: str) -> bool:
        if tool_name in self.disabled_tools:
            return False
        if self.allowed_tools:
            return tool_name in self.allowed_tools
        return True

    def requires_confirmation(self, tool_name: str, action: str) -> bool:
        return f"{tool_name}.{action}" in self.confirm_required

    # ── Factories ─────────────────────────────────────────────────────────────

    @classmethod
    def default(cls) -> "PolicyConfig":
        return cls(
            sandbox_root=config.WORKSPACE_DIR,
            blocked_paths=["**/.env", "**/*.pem", "**/*.key", "**/id_rsa", "**/.ssh/**"],
            max_file_size_mb=10,
            allowed_tools=[],
            disabled_tools=[],
            confirm_required={
                "FileHandler.write",
                "FileHandler.delete",
                "GitTool.commit",
                "SystemTool.kill_process",
            },
            confirm_all_destructive=True,
            dry_run_mode=False,
            confidence_threshold=config.CONFIDENCE_THRESHOLD,
            context_window_size=config.CONTEXT_WINDOW_SIZE,
            chain_continue_on_error=False,
            audit_retention_days=30,
        )

    @classmethod
    def load(cls, mcprc_path: Path) -> "PolicyConfig":
        with mcprc_path.open("rb") as f:
            data = tomllib.load(f)

        security = data.get("security", {})
        tools = data.get("tools", {})
        confirmations = data.get("confirmations", {})
        behavior = data.get("behavior", {})

        sandbox = str(security.get("sandbox_root", "") or "").strip()
        if not sandbox:
            sandbox_root = config.WORKSPACE_DIR
        else:
            sandbox_path = Path(sandbox).expanduser()
            if sandbox_path.is_absolute():
                sandbox_root = sandbox_path.resolve()
            else:
                sandbox_root = (mcprc_path.parent / sandbox_path).resolve()

        confirm_list = confirmations.get("confirm_required", [
            "FileHandler.write", "FileHandler.delete",
            "GitTool.commit", "SystemTool.kill_process",
        ])

        return cls(
            sandbox_root=sandbox_root,
            blocked_paths=security.get("blocked_paths", ["**/.env", "**/*.pem", "**/*.key"]),
            max_file_size_mb=int(security.get("max_file_size_mb", 10)),
            allowed_tools=tools.get("allowed_tools", []),
            disabled_tools=tools.get("disabled_tools", []),
            confirm_required=set(confirm_list),
            confirm_all_destructive=bool(confirmations.get("confirm_all_destructive", True)),
            dry_run_mode=bool(behavior.get("dry_run_mode", False)),
            confidence_threshold=float(behavior.get("confidence_threshold", config.CONFIDENCE_THRESHOLD)),
            context_window_size=int(behavior.get("context_window_size", config.CONTEXT_WINDOW_SIZE)),
            chain_continue_on_error=bool(behavior.get("chain_continue_on_error", False)),
            audit_retention_days=int(data.get("audit", {}).get("retention_days", 30)),
        )

    @classmethod
    def load_or_default(cls, path: Path) -> "PolicyConfig":
        if path.exists():
            return cls.load(path)
        return cls.default()
