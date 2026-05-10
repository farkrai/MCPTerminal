"""Tests for the new tool domains: shell, docker, database, code, memory."""
from __future__ import annotations
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastmcp import Client

from mcp_assistant.server.app import create_server


@pytest_asyncio.fixture
async def client():
    async with Client(create_server()) as c:
        yield c


def _text(result) -> str:
    """Extract first text content from a tool result."""
    if hasattr(result, "content"):
        for item in result.content:
            if hasattr(item, "text"):
                return item.text
    return str(result)


# ── Shell ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_shell_which_found(client):
    result = await client.call_tool("shell_which", {"name": "python3"})
    import json
    data = json.loads(_text(result))
    assert data["found"] is True
    assert data["path"] is not None


@pytest.mark.asyncio
async def test_shell_which_missing(client):
    result = await client.call_tool("shell_which", {"name": "nonexistent_binary_xyz"})
    import json
    data = json.loads(_text(result))
    assert data["found"] is False
    assert data["path"] is None


@pytest.mark.asyncio
async def test_shell_env_all(client):
    result = await client.call_tool("shell_env", {})
    import json
    data = json.loads(_text(result))
    assert "count" in data
    assert data["count"] > 0


@pytest.mark.asyncio
async def test_shell_env_key(client):
    result = await client.call_tool("shell_env", {"key": "PATH"})
    import json
    data = json.loads(_text(result))
    assert data["key"] == "PATH"
    assert data["set"] is True


@pytest.mark.asyncio
async def test_shell_run_dry_run(client):
    result = await client.call_tool("shell_run", {"command": "echo hello", "dry_run": True})
    import json
    data = json.loads(_text(result))
    assert data["dry_run"] is True
    assert "echo hello" in data["command"]


@pytest.mark.asyncio
async def test_shell_run_simple(client):
    result = await client.call_tool("shell_run", {"command": "echo test_output"})
    import json
    data = json.loads(_text(result))
    assert data["exit_code"] == 0
    assert "test_output" in data["stdout"]


@pytest.mark.asyncio
async def test_shell_run_blocked(client):
    with pytest.raises(Exception):
        await client.call_tool("shell_run", {"command": "shutdown -h now"})


# ── Docker (mocked — docker may not be present in CI) ─────────────────────────

@pytest.mark.asyncio
async def test_docker_ps_no_docker(client):
    """When docker is not installed, tool raises a clear ToolError."""
    with patch("shutil.which", return_value=None):
        with pytest.raises(Exception, match="[Dd]ocker"):
            await client.call_tool("docker_ps", {})


@pytest.mark.asyncio
async def test_docker_stop_dry_run(client):
    """dry_run should return immediately without calling docker CLI."""
    result = await client.call_tool("docker_stop", {"container": "my_app", "dry_run": True})
    text = _text(result)
    assert "DRY RUN" in text
    assert "my_app" in text


@pytest.mark.asyncio
async def test_docker_start_dry_run(client):
    result = await client.call_tool("docker_start", {"container": "my_app", "dry_run": True})
    text = _text(result)
    assert "DRY RUN" in text


# ── Database ───────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def sqlite_db(tmp_path):
    db_file = tmp_path / "test.db"
    con = sqlite3.connect(str(db_file))
    con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)")
    con.execute("INSERT INTO users VALUES (1, 'Alice', 30)")
    con.execute("INSERT INTO users VALUES (2, 'Bob', 25)")
    con.commit()
    con.close()
    return str(db_file)


@pytest.mark.asyncio
async def test_db_tables(client, sqlite_db):
    result = await client.call_tool("db_tables", {"path": sqlite_db})
    import json
    data = json.loads(_text(result))
    names = [t["name"] for t in data["tables"]]
    assert "users" in names


@pytest.mark.asyncio
async def test_db_schema(client, sqlite_db):
    result = await client.call_tool("db_schema", {"path": sqlite_db, "table": "users"})
    import json
    data = json.loads(_text(result))
    col_names = [c["name"] for c in data["columns"]]
    assert "id" in col_names
    assert "name" in col_names
    assert "age" in col_names


@pytest.mark.asyncio
async def test_db_query(client, sqlite_db):
    result = await client.call_tool("db_query", {"path": sqlite_db, "sql": "SELECT * FROM users ORDER BY id"})
    import json
    data = json.loads(_text(result))
    assert data["count"] == 2
    assert data["rows"][0]["name"] == "Alice"


@pytest.mark.asyncio
async def test_db_query_rejects_dml(client, sqlite_db):
    with pytest.raises(Exception, match="[Ss]ELECT"):
        await client.call_tool("db_query", {"path": sqlite_db, "sql": "DELETE FROM users"})


@pytest.mark.asyncio
async def test_db_execute_dry_run(client, sqlite_db):
    result = await client.call_tool(
        "db_execute",
        {"path": sqlite_db, "sql": "DELETE FROM users WHERE id=1", "dry_run": True},
    )
    import json
    data = json.loads(_text(result))
    assert data["dry_run"] is True
    # Verify row is still there
    con = sqlite3.connect(sqlite_db)
    assert con.execute("SELECT count(*) FROM users").fetchone()[0] == 2
    con.close()


@pytest.mark.asyncio
async def test_db_execute_insert(client, sqlite_db):
    result = await client.call_tool(
        "db_execute",
        {"path": sqlite_db, "sql": "INSERT INTO users VALUES (3, 'Charlie', 22)"},
    )
    import json
    data = json.loads(_text(result))
    assert data["rowcount"] == 1


# ── Code ───────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def py_file(tmp_path):
    code = '''\
class Greeter:
    """Says hello."""

    def greet(self, name: str) -> str:
        """Return a greeting."""
        if name:
            return f"Hello, {name}"
        return "Hello, world"

def add(a, b):
    return a + b
'''
    f = tmp_path / "sample.py"
    f.write_text(code)
    return str(f)


@pytest.mark.asyncio
async def test_code_symbols(client, py_file):
    result = await client.call_tool("code_symbols", {"path": py_file})
    import json
    data = json.loads(_text(result))
    names = [s["name"] for s in data["symbols"]]
    assert "Greeter" in names
    assert any("greet" in n for n in names)
    assert "add" in names


@pytest.mark.asyncio
async def test_code_complexity(client, py_file):
    result = await client.call_tool("code_complexity", {"path": py_file})
    import json
    data = json.loads(_text(result))
    assert data["function_count"] >= 2
    func_names = [f["name"] for f in data["functions"]]
    assert any("greet" in n for n in func_names)


@pytest.mark.asyncio
async def test_code_lint(client, py_file):
    result = await client.call_tool("code_lint", {"path": py_file})
    import json
    data = json.loads(_text(result))
    assert "linter" in data
    assert "issue_count" in data


# ── Memory ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_memory_set_and_get(client):
    key = "_test_memory_key_xyz"
    await client.call_tool("memory_set", {"key": key, "value": "test_value", "tags": ["test"]})
    result = await client.call_tool("memory_get", {"key": key})
    import json
    data = json.loads(_text(result))
    assert data["key"] == key
    assert data["value"] == "test_value"
    assert "test" in data["tags"]
    # cleanup
    await client.call_tool("memory_delete", {"key": key})


@pytest.mark.asyncio
async def test_memory_list(client):
    key = "_test_list_key"
    await client.call_tool("memory_set", {"key": key, "value": "listed"})
    result = await client.call_tool("memory_list", {})
    import json
    data = json.loads(_text(result))
    keys = [e["key"] for e in data["entries"]]
    assert key in keys
    await client.call_tool("memory_delete", {"key": key})


@pytest.mark.asyncio
async def test_memory_search(client):
    key = "_test_search_key"
    await client.call_tool("memory_set", {"key": key, "value": "unique_search_term_abc123"})
    result = await client.call_tool("memory_search", {"query": "unique_search_term_abc123"})
    import json
    data = json.loads(_text(result))
    assert data["count"] >= 1
    await client.call_tool("memory_delete", {"key": key})


@pytest.mark.asyncio
async def test_memory_delete_missing(client):
    with pytest.raises(Exception, match="[Nn]ot found"):
        await client.call_tool("memory_delete", {"key": "_nonexistent_key_xyz_abc"})


@pytest.mark.asyncio
async def test_memory_get_missing(client):
    with pytest.raises(Exception, match="[Nn]ot found"):
        await client.call_tool("memory_get", {"key": "_nonexistent_key_xyz_abc"})
