from __future__ import annotations

import shutil

AVAILABLE: dict[str, bool] = {
    "rg": shutil.which("rg") is not None,
    "fd": shutil.which("fd") is not None,
    "bat": shutil.which("bat") is not None,
    "delta": shutil.which("delta") is not None,
    "eza": shutil.which("eza") is not None,
    "exa": shutil.which("exa") is not None,
    "zoxide": shutil.which("zoxide") is not None,
    "fzf": shutil.which("fzf") is not None,
}


def report() -> str:
    found = [name for name, enabled in AVAILABLE.items() if enabled]
    missing = [name for name, enabled in AVAILABLE.items() if not enabled]
    lines: list[str] = []
    if found:
        lines.append(f"Ecosystem tools active: {', '.join(found)}")
    if missing:
        lines.append(f"Optional (install for enhanced output): {', '.join(missing)}")
    return "\n".join(lines)
