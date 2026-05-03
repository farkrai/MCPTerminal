import json
from pathlib import Path
from mcp_assistant.audit.logger import AuditLogger
from mcp_assistant.audit.retention import cleanup_old_logs


def _log(logger: AuditLogger, tool="file_read", success=True):
    logger.log(
        tool=tool,
        params={"path": "."},
        output="ok",
        success=success,
        error=None if success else "something went wrong",
        duration_ms=5.0,
    )


def test_log_creates_file(tmp_path):
    logger = AuditLogger(tmp_path)
    _log(logger)
    logs = list(tmp_path.glob("audit_*.jsonl"))
    assert len(logs) == 1


def test_log_entry_has_required_fields(tmp_path):
    logger = AuditLogger(tmp_path)
    _log(logger)
    log_file = list(tmp_path.glob("audit_*.jsonl"))[0]
    entry = json.loads(log_file.read_text().strip())
    for field in ("seq", "session_id", "ts", "tool", "params", "result", "prev_hash", "entry_hash"):
        assert field in entry, f"Missing field: {field}"


def test_log_entry_tool_and_params(tmp_path):
    logger = AuditLogger(tmp_path)
    logger.log(tool="git_status", params={"cwd": None}, output="On branch main",
               success=True, error=None, duration_ms=12.5)
    log_file = list(tmp_path.glob("audit_*.jsonl"))[0]
    entry = json.loads(log_file.read_text().strip())
    assert entry["tool"] == "git_status"
    assert entry["params"] == {"cwd": None}
    assert entry["result"]["success"] is True


def test_audit_chain_valid(tmp_path):
    logger = AuditLogger(tmp_path)
    for i in range(5):
        _log(logger, tool=f"tool_{i}")
    log_file = list(tmp_path.glob("audit_*.jsonl"))[0]
    ok, errors = AuditLogger.verify_chain(log_file)
    assert ok, f"Chain invalid: {errors}"


def test_audit_chain_detects_tampering(tmp_path):
    logger = AuditLogger(tmp_path)
    _log(logger)
    _log(logger)

    log_file = list(tmp_path.glob("audit_*.jsonl"))[0]
    lines = log_file.read_text().splitlines()

    entry = json.loads(lines[0])
    entry["result"]["output"] = "TAMPERED"
    lines[0] = json.dumps(entry)
    log_file.write_text("\n".join(lines) + "\n")

    ok, errors = AuditLogger.verify_chain(log_file)
    assert not ok
    assert len(errors) > 0


def test_seq_increments(tmp_path):
    logger = AuditLogger(tmp_path)
    for _ in range(3):
        _log(logger)
    log_file = list(tmp_path.glob("audit_*.jsonl"))[0]
    seqs = [json.loads(l)["seq"] for l in log_file.read_text().splitlines()]
    assert seqs == [1, 2, 3]


def test_retention_cleanup(tmp_path):
    from datetime import datetime, timedelta
    old_date = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")
    recent_date = datetime.now().strftime("%Y-%m-%d")
    (tmp_path / f"audit_{old_date}.jsonl").write_text('{"seq":1}\n')
    (tmp_path / f"audit_{recent_date}.jsonl").write_text('{"seq":1}\n')

    removed = cleanup_old_logs(tmp_path, retention_days=30)
    assert len(removed) == 1
    assert f"audit_{old_date}.jsonl" in removed
    assert (tmp_path / f"audit_{recent_date}.jsonl").exists()


def test_retention_zero_keeps_all(tmp_path):
    from datetime import datetime, timedelta
    old_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
    (tmp_path / f"audit_{old_date}.jsonl").write_text('{"seq":1}\n')
    removed = cleanup_old_logs(tmp_path, retention_days=0)
    assert removed == []
