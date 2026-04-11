from __future__ import annotations

import hashlib
import os
import sqlite3
import time

from mcp_assistant import config

CACHE_TTL_S: int = int(os.environ.get("MCP_CACHE_TTL", "3600"))


def _db_path():
    return config.CONTEXT_PERSIST_DIR / "llm_cache.db"


def _connect() -> sqlite3.Connection:
    config.CONTEXT_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path())
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_cache (
            key      TEXT PRIMARY KEY,
            response TEXT NOT NULL,
            ts       REAL NOT NULL,
            ttl_s    INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _key(system: str, user: str) -> str:
    return hashlib.sha256(f"{system}\n\n{user}".encode()).hexdigest()


def get(system: str, user: str) -> str | None:
    conn = _connect()
    row = conn.execute(
        "SELECT response, ts, ttl_s FROM llm_cache WHERE key = ?",
        (_key(system, user),),
    ).fetchone()
    conn.close()
    if row is None:
        return None

    response, ts, ttl_s = row
    if ttl_s > 0 and (time.time() - ts) > ttl_s:
        return None
    return response


def put(system: str, user: str, response: str, ttl_s: int = CACHE_TTL_S) -> None:
    if ttl_s == 0:
        return

    conn = _connect()
    conn.execute(
        "INSERT OR REPLACE INTO llm_cache (key, response, ts, ttl_s) VALUES (?,?,?,?)",
        (_key(system, user), response, time.time(), ttl_s),
    )
    conn.commit()
    conn.close()


def clear_expired() -> int:
    conn = _connect()
    cursor = conn.execute(
        "DELETE FROM llm_cache WHERE ttl_s > 0 AND (? - ts) > ttl_s",
        (time.time(),),
    )
    conn.commit()
    count = cursor.rowcount
    conn.close()
    return count


def clear_all() -> None:
    conn = _connect()
    conn.execute("DELETE FROM llm_cache")
    conn.commit()
    conn.close()


def _cli() -> None:
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "clear":
        clear_all()
        print("LLM cache cleared.")
    else:
        print("Usage: mcp-cache clear")
