from __future__ import annotations
import os
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
WORKSPACE_DIR = Path(os.environ.get("MCP_WORKSPACE", str(Path.cwd()))).expanduser().resolve()
AUDIT_LOG_DIR = PROJECT_ROOT / "audit_logs"
CONTEXT_PERSIST_DIR = Path.home() / ".mcp_assistant"
PLUGINS_DIR = PROJECT_ROOT / "plugins"
MCPRC_FILE = PROJECT_ROOT / ".mcprc"

# ── Ollama ────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "dolphin-mistral:latest")
OLLAMA_TIMEOUT: int = int(os.environ.get("OLLAMA_TIMEOUT", "120"))
OLLAMA_MAX_RETRIES: int = int(os.environ.get("OLLAMA_MAX_RETRIES", "3"))
OLLAMA_KEEP_ALIVE: str = os.environ.get("OLLAMA_KEEP_ALIVE", "-1")

# Temperature for structured tool-call generation (low = deterministic)
OLLAMA_TEMP_STRUCTURED: float = 0.1
# Temperature for natural language responses (explanations, clarifications)
OLLAMA_TEMP_NL: float = 0.7

# ── Behaviour ─────────────────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD: float = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.5"))
CONTEXT_WINDOW_SIZE: int = int(os.environ.get("CONTEXT_WINDOW_SIZE", "10"))
MAX_CONTEXT_TOKENS: int = int(os.environ.get("MAX_CONTEXT_TOKENS", "3000"))
MAX_PARSE_RETRIES: int = 2

# Multi-tier model routing
CLASSIFIER_MODEL: str = os.environ.get("CLASSIFIER_MODEL", OLLAMA_MODEL)
PLANNER_MODEL: str = os.environ.get("PLANNER_MODEL", OLLAMA_MODEL)
ROUTER_MODEL: str = os.environ.get("ROUTER_MODEL", OLLAMA_MODEL)
EXECUTOR_MODEL_LOW: str = os.environ.get("EXECUTOR_MODEL_LOW", OLLAMA_MODEL)
EXECUTOR_MODEL_MEDIUM: str = os.environ.get("EXECUTOR_MODEL_MEDIUM", EXECUTOR_MODEL_LOW)
EXECUTOR_MODEL_HIGH: str = os.environ.get("EXECUTOR_MODEL_HIGH", EXECUTOR_MODEL_MEDIUM)
AGGREGATOR_MODEL: str = os.environ.get("AGGREGATOR_MODEL", EXECUTOR_MODEL_HIGH)


def ensure_dirs() -> None:
    AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    CONTEXT_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
