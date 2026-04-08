import pytest
from mcp_assistant.llm.response_parser import parse_response
from mcp_assistant.mcp.schema import MCPCall, MCPChain, ParseError


def test_parse_clean_json():
    raw = '{"tool": "FileHandler", "action": "list", "params": {"path": "."}, "confidence": 0.95}'
    result = parse_response(raw)
    assert isinstance(result, MCPCall)
    assert result.tool == "FileHandler"
    assert result.action == "list"
    assert result.confidence == 0.95


def test_parse_markdown_fenced():
    raw = '```json\n{"tool": "GitTool", "action": "status", "params": {}, "confidence": 0.9}\n```'
    result = parse_response(raw)
    assert isinstance(result, MCPCall)
    assert result.tool == "GitTool"


def test_parse_prose_wrapped():
    raw = 'Sure! Here is the answer:\n{"tool": "SystemTool", "action": "cpu_stats", "params": {}, "confidence": 0.88}'
    result = parse_response(raw)
    assert isinstance(result, MCPCall)
    assert result.tool == "SystemTool"
    assert result.confidence == pytest.approx(0.88)


def test_parse_chain():
    raw = (
        '{"chain": true, "description": "status then diff", "steps": ['
        '{"tool": "GitTool", "action": "status", "params": {}, "confidence": 0.9},'
        '{"tool": "GitTool", "action": "diff", "params": {}, "confidence": 0.85}'
        ']}'
    )
    result = parse_response(raw)
    assert isinstance(result, MCPChain)
    assert len(result.steps) == 2
    assert result.steps[0].action == "status"
    assert result.steps[1].action == "diff"


def test_parse_invalid_raises():
    with pytest.raises(ParseError):
        parse_response("this is not json at all!!!")


def test_confidence_clamped():
    raw = '{"tool": "FileHandler", "action": "list", "params": {}, "confidence": 1.5}'
    result = parse_response(raw)
    assert isinstance(result, MCPCall)
    assert result.confidence == 1.0


def test_missing_key_raises():
    raw = '{"tool": "FileHandler", "params": {}, "confidence": 0.8}'
    with pytest.raises(ParseError):
        parse_response(raw)
