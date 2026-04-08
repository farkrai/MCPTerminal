from mcp_assistant.mcp.schema import MCPCall, MCPResult, MCPChain, MCPChainStep


def test_mcp_call_to_dict():
    call = MCPCall(tool="FileHandler", action="list", params={"path": "."}, confidence=0.9)
    d = call.to_dict()
    assert d["tool"] == "FileHandler"
    assert d["action"] == "list"
    assert d["confidence"] == 0.9


def test_mcp_result_success():
    call = MCPCall(tool="GitTool", action="status", params={})
    result = MCPResult(call=call, success=True, output="On branch main")
    assert result.success
    assert "main" in result.output
    assert result.error is None


def test_mcp_result_failure():
    call = MCPCall(tool="GitTool", action="commit", params={})
    result = MCPResult(call=call, success=False, output="Error: no message", error="no message")
    assert not result.success
    assert result.error == "no message"


def test_mcp_chain():
    chain = MCPChain(
        steps=[
            MCPChainStep(tool="GitTool", action="status", params={}, confidence=0.9),
            MCPChainStep(tool="GitTool", action="diff", params={}, confidence=0.88),
        ],
        description="status then diff",
    )
    assert len(chain.steps) == 2
    assert chain.steps[0].tool == "GitTool"
    assert chain.steps[1].action == "diff"
