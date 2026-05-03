from mcp_assistant.server.schema import ToolCall, ToolChain, ToolChainStep, ToolResult, ParseError


def test_tool_call_to_dict():
    call = ToolCall(tool="file_read", params={"path": "README.md"}, confidence=0.95)
    d = call.to_dict()
    assert d["tool"] == "file_read"
    assert d["params"] == {"path": "README.md"}
    assert d["confidence"] == 0.95


def test_tool_call_defaults():
    call = ToolCall(tool="git_status", params={})
    assert call.confidence == 1.0
    assert call.raw_response == ""


def test_tool_result_success():
    result = ToolResult(
        tool="git_status", params={},
        output="On branch main", success=True,
    )
    assert result.success
    assert "main" in result.output
    assert result.error is None
    assert result.duration_ms == 0.0


def test_tool_result_failure():
    result = ToolResult(
        tool="file_read", params={"path": "/etc/shadow"},
        output="", success=False,
        error="Path not allowed by policy",
        duration_ms=1.5,
    )
    assert not result.success
    assert result.error == "Path not allowed by policy"
    assert result.duration_ms == 1.5


def test_tool_chain():
    chain = ToolChain(
        steps=[
            ToolChainStep(tool="git_status", params={}, confidence=0.9),
            ToolChainStep(tool="git_diff",   params={}, confidence=0.88),
        ],
        description="status then diff",
    )
    assert len(chain.steps) == 2
    assert chain.steps[0].tool == "git_status"
    assert chain.steps[1].tool == "git_diff"
    assert chain.min_confidence() == pytest.approx(0.88)


def test_tool_chain_min_confidence_empty():
    chain = ToolChain(steps=[])
    assert chain.min_confidence() == 0.0


def test_parse_error_is_exception():
    err = ParseError("bad json")
    assert isinstance(err, Exception)
    assert "bad json" in str(err)


import pytest
