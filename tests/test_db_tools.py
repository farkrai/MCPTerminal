"""Tests for db_* MCP tools using test_mcp.db."""
import json
import pytest
from fastmcp import Client
from mcp_assistant.server.app import create_server


DB = "test_mcp.db"


def _text(result) -> str:
    if hasattr(result, "content"):
        for item in result.content:
            if hasattr(item, "text"):
                return item.text
    return str(result)


# ── db_tables ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_db_tables(mcp_client):
    result = await mcp_client.call_tool("db_tables", {"path": DB})
    data = json.loads(_text(result))
    names = [t["name"] for t in data["tables"]]
    assert "users" in names
    assert "projects" in names
    assert "tasks" in names


# ── db_schema ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_db_schema_users(mcp_client):
    result = await mcp_client.call_tool("db_schema", {"path": DB, "table": "users"})
    data = json.loads(_text(result))
    columns = [col["name"] for col in data["columns"]]
    assert "id" in columns
    assert "name" in columns
    assert "email" in columns


@pytest.mark.asyncio
async def test_db_schema_tasks(mcp_client):
    result = await mcp_client.call_tool("db_schema", {"path": DB, "table": "tasks"})
    data = json.loads(_text(result))
    columns = [col["name"] for col in data["columns"]]
    assert "id" in columns
    assert "title" in columns
    assert "done" in columns


# ── db_query ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_db_query_select_all(mcp_client):
    result = await mcp_client.call_tool(
        "db_query", {"path": DB, "sql": "SELECT * FROM users"}
    )
    data = json.loads(_text(result))
    assert "rows" in data
    assert data["count"] >= 3


@pytest.mark.asyncio
async def test_db_query_filter(mcp_client):
    result = await mcp_client.call_tool(
        "db_query", {"path": DB, "sql": "SELECT * FROM users WHERE id = 1"}
    )
    data = json.loads(_text(result))
    assert data["count"] == 1


@pytest.mark.asyncio
async def test_db_query_join(mcp_client):
    result = await mcp_client.call_tool(
        "db_query",
        {"path": DB, "sql": "SELECT u.name, t.title FROM users u JOIN tasks t ON u.id = t.assigned_to"},
    )
    data = json.loads(_text(result))
    assert data["count"] > 0


@pytest.mark.asyncio
async def test_db_query_count(mcp_client):
    result = await mcp_client.call_tool(
        "db_query", {"path": DB, "sql": "SELECT COUNT(*) as total FROM tasks"}
    )
    data = json.loads(_text(result))
    assert data["rows"][0]["total"] >= 3


@pytest.mark.asyncio
async def test_db_query_order_limit(mcp_client):
    result = await mcp_client.call_tool(
        "db_query", {"path": DB, "sql": "SELECT * FROM tasks ORDER BY id DESC", "limit": 2}
    )
    data = json.loads(_text(result))
    assert data["count"] <= 2


# ── db_execute ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_db_execute_insert(mcp_client):
    result = await mcp_client.call_tool(
        "db_execute",
        {"path": DB, "sql": "INSERT INTO users (name, email) VALUES ('Test User', 'test@example.com')"},
    )
    data = json.loads(_text(result))
    assert data["rowcount"] >= 1

    # cleanup
    await mcp_client.call_tool(
        "db_execute",
        {"path": DB, "sql": "DELETE FROM users WHERE email = 'test@example.com'"},
    )


@pytest.mark.asyncio
async def test_db_execute_update(mcp_client):
    result = await mcp_client.call_tool(
        "db_execute",
        {"path": DB, "sql": "UPDATE tasks SET done = 1 WHERE id = 1"},
    )
    data = json.loads(_text(result))
    assert data["rowcount"] >= 1

    # restore
    await mcp_client.call_tool(
        "db_execute",
        {"path": DB, "sql": "UPDATE tasks SET done = 0 WHERE id = 1"},
    )


@pytest.mark.asyncio
async def test_db_execute_delete(mcp_client):
    await mcp_client.call_tool(
        "db_execute",
        {"path": DB, "sql": "INSERT INTO users (name, email) VALUES ('Temp', 'temp@delete.me')"},
    )
    result = await mcp_client.call_tool(
        "db_execute",
        {"path": DB, "sql": "DELETE FROM users WHERE email = 'temp@delete.me'"},
    )
    data = json.loads(_text(result))
    assert data["rowcount"] >= 1


@pytest.mark.asyncio
async def test_db_execute_dry_run(mcp_client):
    result = await mcp_client.call_tool(
        "db_execute",
        {"path": DB, "sql": "DELETE FROM users WHERE id = 999", "dry_run": True},
    )
    data = json.loads(_text(result))
    assert data["dry_run"] is True


# ── blocked operations ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_db_query_rejects_write(mcp_client):
    """db_query must reject non-SELECT statements."""
    with pytest.raises(Exception):
        await mcp_client.call_tool(
            "db_query", {"path": DB, "sql": "DROP TABLE users"}
        )
