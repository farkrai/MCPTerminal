from __future__ import annotations
import dataclasses
import fnmatch
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from mcp_assistant import config


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
            sandbox_root=config.PROJECT_ROOT,
            blocked_paths=["**/.env", "**/*.pem", "**/*.key", "**/id_rsa", "**/.ssh/**"],
            max_file_size_mb=10,
            allowed_tools=[],
            disabled_tools=[],
            confirm_required={
                "file.write",
                "file.delete",
                "git.commit",
                "system.kill_process",
            },
            confirm_all_destructive=True,
            dry_run_mode=False,
            confidence_threshold=config.CONFIDENCE_THRESHOLD,
            context_window_size=config.CONTEXT_WINDOW_SIZE,
            chain_continue_on_error=False,
            audit_retention_days=30,
        )

    @classmethod
    def load(cls, path: Path) -> "PolicyConfig":
        with path.open("rb") as f:
            data = tomllib.load(f)

        security = data.get("security", {})
        tools = data.get("tools", {})
        confirmations = data.get("confirmations", {})
        behavior = data.get("behavior", {})

        sandbox = Path(security.get("sandbox_root", str(config.PROJECT_ROOT))).resolve()

        confirm_list = confirmations.get("confirm_required", [
            "file.write", "file.delete",
            "git.commit", "system.kill_process",
        ])

        return cls(
            sandbox_root=sandbox,
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

    def reload(self, path: Path) -> None:
        """Reload settings from *path* into this instance in-place.

        Mutates self so all existing import references stay valid.
        """
        fresh = PolicyConfig.load(path)
        for f in dataclasses.fields(fresh):
            setattr(self, f.name, getattr(fresh, f.name))
