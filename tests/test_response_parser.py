import pytest
from mcp_assistant.llm.response_parser import parse_response
from mcp_assistant.server.schema import ToolCall, ToolChain, ParseError


def test_parse_clean_json():
    raw = '{"tool": "file_list", "params": {"path": "."}, "confidence": 0.95}'
    result = parse_response(raw)
    assert isinstance(result, ToolCall)
    assert result.tool == "file_list"
    assert result.confidence == 0.95


def test_parse_markdown_fenced():
    raw = '```json\n{"tool": "git_status", "params": {}, "confidence": 0.9}\n```'
    result = parse_response(raw)
    assert isinstance(result, ToolCall)
    assert result.tool == "git_status"


def test_parse_prose_wrapped():
    raw = 'Sure! Here is the answer:\n{"tool": "system_cpu_stats", "params": {}, "confidence": 0.88}'
    result = parse_response(raw)
    assert isinstance(result, ToolCall)
    assert result.tool == "system_cpu_stats"
    assert result.confidence == pytest.approx(0.88)


def test_parse_chain():
    raw = (
        '{"chain": true, "description": "status then diff", "steps": ['
        '{"tool": "git_status", "params": {}, "confidence": 0.9},'
        '{"tool": "git_diff",   "params": {}, "confidence": 0.85}'
        ']}'
    )
    result = parse_response(raw)
    assert isinstance(result, ToolChain)
    assert len(result.steps) == 2
    assert result.steps[0].tool == "git_status"
    assert result.steps[1].tool == "git_diff"
    assert result.description == "status then diff"


def test_parse_invalid_raises():
    with pytest.raises(ParseError):
        parse_response("this is not json at all!!!")


def test_confidence_clamped():
    raw = '{"tool": "file_list", "params": {}, "confidence": 1.5}'
    result = parse_response(raw)
    assert isinstance(result, ToolCall)
    assert result.confidence == 1.0


def test_missing_tool_key_raises():
    raw = '{"params": {}, "confidence": 0.8}'
    with pytest.raises(ParseError):
        parse_response(raw)


def test_chain_continue_on_error():
    raw = (
        '{"chain": true, "description": "test", "continue_on_error": true, "steps": ['
        '{"tool": "git_status", "params": {}, "confidence": 0.9}'
        ']}'
    )
    result = parse_response(raw)
    assert isinstance(result, ToolChain)
    assert result.continue_on_error is True


def test_thinking_tags_stripped():
    raw = '<think>let me think...</think>{"tool": "git_log", "params": {}, "confidence": 0.9}'
    result = parse_response(raw)
    assert isinstance(result, ToolCall)
    assert result.tool == "git_log"
