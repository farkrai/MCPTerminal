import pytest

fastmcp = pytest.importorskip("fastmcp")


def test_server_imports():
    from mcp_assistant import fastmcp_server

    assert fastmcp_server.mcp is not None


def test_tools_registered():
    from mcp_assistant import fastmcp_server

    names = [tool.name for tool in fastmcp_server.mcp._tools.values()]
    assert "git_status" in names
    assert "file_read" in names
