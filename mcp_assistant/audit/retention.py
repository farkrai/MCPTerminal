from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path


def cleanup_old_logs(log_dir: Path, retention_days: int) -> list[str]:
    """
    Delete audit log files older than retention_days.
    Returns list of deleted file names.
    If retention_days is 0, no files are deleted.
    """
    if retention_days <= 0:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted: list[str] = []

    for log_file in log_dir.glob("audit_*.jsonl"):
        # Parse date from filename: audit_YYYY-MM-DD.jsonl
        try:
            date_str = log_file.stem.replace("audit_", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        if file_date < cutoff:
            log_file.unlink()
            deleted.append(log_file.name)

    return deleted
