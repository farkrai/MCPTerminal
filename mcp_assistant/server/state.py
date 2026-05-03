"""Global server-side singletons – policy and audit logger.

Loaded once at import time from .mcprc / default values.
All tool modules import from here to avoid re-loading config on every call.
"""
from __future__ import annotations
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant.audit.logger import AuditLogger
from mcp_assistant import config

config.ensure_dirs()

policy: PolicyConfig = PolicyConfig.load_or_default(config.MCPRC_FILE)
audit: AuditLogger = AuditLogger(config.AUDIT_LOG_DIR)

__all__ = ["policy", "audit"]
