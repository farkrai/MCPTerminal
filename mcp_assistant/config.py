from __future__ import annotations
import os
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
AUDIT_LOG_DIR = PROJECT_ROOT / "audit_logs"
CONTEXT_PERSIST_DIR = Path.home() / ".mcp_assistant"
PLUGINS_DIR = PROJECT_ROOT / "plugins"
MCPRC_FILE = PROJECT_ROOT / ".mcprc"

# ── Ollama ────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_TIMEOUT: int = int(os.environ.get("OLLAMA_TIMEOUT", "300"))

# Temperature for structured tool-call generation (low = deterministic)
OLLAMA_TEMP_STRUCTURED: float = 0.1
# Temperature for natural language responses (explanations, clarifications)
OLLAMA_TEMP_NL: float = 0.7

# ── Behaviour ─────────────────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD: float = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.5"))
CONTEXT_WINDOW_SIZE: int = int(os.environ.get("CONTEXT_WINDOW_SIZE", "10"))
MAX_PARSE_RETRIES: int = 2


MEMORY_DB_PATH: Path = CONTEXT_PERSIST_DIR / "memory.db"


def ensure_dirs() -> None:
    AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    CONTEXT_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
