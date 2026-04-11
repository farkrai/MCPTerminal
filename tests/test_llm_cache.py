import pytest

from mcp_assistant import config
from mcp_assistant.llm import cache as llm_cache


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONTEXT_PERSIST_DIR", tmp_path)


def test_cache_put_and_get():
    llm_cache.clear_all()
    llm_cache.put("system", "user", '{"tool":"GitTool"}', ttl_s=60)
    assert llm_cache.get("system", "user") == '{"tool":"GitTool"}'


def test_cache_expiry():
    llm_cache.clear_all()
    llm_cache.put("system", "user", "x", ttl_s=0)
    assert llm_cache.get("system", "user") is None
