from __future__ import annotations
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from mcp_assistant.mcp.schema import MCPCall, MCPResult

_GENESIS_HASH = "0" * 64


class AuditLogger:
    def __init__(self, log_dir: Path) -> None:
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._session_id = uuid.uuid4().hex[:8]
        self._seq = 0
        self._prev_hash = _GENESIS_HASH
        self._log_file = self._log_dir / f"audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"

    # ── Public API ────────────────────────────────────────────────────────────

    def log(self, call: MCPCall, result: MCPResult) -> None:
        self._seq += 1
        entry = {
            "seq": self._seq,
            "session_id": self._session_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "user": os.getenv("USER", "unknown"),
            "hostname": os.uname().nodename,
            "call": call.to_dict(),
            "result": {
                "success": result.success,
                "output": result.output[:500],
                "error": result.error,
                "duration_ms": round(result.duration_ms, 2),
                "model_used": result.model_used,
            },
            "prev_hash": self._prev_hash,
        }
        entry_hash = _compute_hash(entry)
        entry["entry_hash"] = entry_hash
        self._prev_hash = entry_hash

        with self._log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=True) + "\n")

    # ── Chain verification ────────────────────────────────────────────────────

    @staticmethod
    def verify_chain(log_file: Path) -> tuple[bool, list[str]]:
        errors: list[str] = []
        entries: list[dict] = []

        with log_file.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    errors.append(f"Line {lineno}: invalid JSON")

        prev_hash = _GENESIS_HASH
        for i, entry in enumerate(entries):
            stored_hash = entry.get("entry_hash", "")
            entry_without_hash = {k: v for k, v in entry.items() if k != "entry_hash"}
            expected_hash = _compute_hash(entry_without_hash)

            if stored_hash != expected_hash:
                errors.append(f"Entry {i+1} (seq={entry.get('seq')}): hash mismatch — entry was tampered")

            if entry.get("prev_hash") != prev_hash:
                errors.append(f"Entry {i+1} (seq={entry.get('seq')}): chain broken — prev_hash mismatch")

            prev_hash = stored_hash

        return len(errors) == 0, errors


def _compute_hash(entry: dict) -> str:
    canonical = json.dumps(entry, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


# ── CLI ───────────────────────────────────────────────────────────────────────
def cli_verify(args: list[str] | None = None) -> None:
    import sys
    argv = args if args is not None else sys.argv[1:]
    if not argv:
        print("Usage: mcp-verify <audit_log_file.jsonl>")
        sys.exit(1)
    log_file = Path(argv[0])
    if not log_file.exists():
        print(f"File not found: {log_file}")
        sys.exit(1)
    ok, errors = AuditLogger.verify_chain(log_file)
    if ok:
        print(f"Audit chain OK — {log_file}")
    else:
        print(f"Audit chain INVALID — {len(errors)} error(s):")
        for e in errors:
            print(f"  {e}")
        sys.exit(2)


if __name__ == "__main__":
    cli_verify()
