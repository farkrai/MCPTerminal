"""FastMCP resources: expose live config, audit logs, and tool schemas."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError

from mcp_assistant import config
from mcp_assistant.server.state import audit, policy


def register_resources(mcp: FastMCP) -> None:
    """Register all resource endpoints on *mcp*."""

    @mcp.resource(
        "resource://config",
        name="server-config",
        description="Current policy configuration loaded from .mcprc",
        mime_type="application/json",
    )
    def get_config() -> str:
        data = {
            "sandbox_root": str(policy.sandbox_root),
            "blocked_paths": policy.blocked_paths,
            "max_file_size_mb": policy.max_file_size_mb,
            "allowed_tools": policy.allowed_tools,
            "disabled_tools": policy.disabled_tools,
            "confirm_required": sorted(policy.confirm_required),
            "confirm_all_destructive": policy.confirm_all_destructive,
            "dry_run_mode": policy.dry_run_mode,
            "confidence_threshold": policy.confidence_threshold,
            "context_window_size": policy.context_window_size,
        }
        return json.dumps(data, indent=2)

    @mcp.resource(
        "resource://audit/today",
        name="audit-log-today",
        description="Today's SHA-256-chained audit log (JSONL format)",
        mime_type="application/x-ndjson",
    )
    def get_today_audit() -> str:
        log_file: Path = (
            config.AUDIT_LOG_DIR
            / f"audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        )
        if not log_file.exists():
            return ""
        return log_file.read_text(encoding="utf-8")

    @mcp.resource(
        "resource://audit/verify",
        name="audit-chain-verify",
        description="Verify integrity of today's audit chain; returns JSON report",
        mime_type="application/json",
    )
    def verify_audit_chain() -> str:
        from mcp_assistant.audit.logger import AuditLogger
        log_file = (
            config.AUDIT_LOG_DIR
            / f"audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        )
        if not log_file.exists():
            return json.dumps({"valid": True, "errors": [], "note": "No log file yet"})
        ok, errors = AuditLogger.verify_chain(log_file)
        return json.dumps({"valid": ok, "errors": errors, "log_file": str(log_file)})

    @mcp.resource(
        "resource://session",
        name="session-info",
        description="Current session ID and audit statistics",
        mime_type="application/json",
    )
    def get_session() -> str:
        return json.dumps({
            "session_id": audit._session_id,
            "log_file": str(audit._log_file),
            "entries_this_session": audit._seq,
        })
