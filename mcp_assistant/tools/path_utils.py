from __future__ import annotations

import subprocess
from pathlib import Path

from mcp_assistant.llm.ecosystem import AVAILABLE


def resolve_cwd(cwd_hint: str | None) -> str:
    """Resolve a cwd hint, optionally via zoxide for fuzzy names."""
    if not cwd_hint or cwd_hint == ".":
        return "."

    hint_path = Path(cwd_hint)
    if hint_path.is_absolute() or hint_path.exists():
        return cwd_hint

    if AVAILABLE["zoxide"]:
        result = subprocess.run(
            ["zoxide", "query", "--", cwd_hint],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()

    return cwd_hint
