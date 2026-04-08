from mcp_assistant.mcp.schema import MCPCall, MCPChain, MCPChainStep
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant import config


def test_dispatch_valid_call(dispatcher):
    call = MCPCall("SystemTool", "ram_stats", {})
    result = dispatcher.dispatch(call)
    assert result.success


def test_dispatch_unknown_tool(dispatcher):
    call = MCPCall("GhostTool", "do_something", {})
    result = dispatcher.dispatch(call)
    assert not result.success
    assert "Unknown tool" in result.output


def test_dispatch_disabled_tool(registry, audit):
    from mcp_assistant.mcp.dispatcher import MCPDispatcher
    policy = PolicyConfig.default()
    policy.disabled_tools = ["SystemTool"]
    d = MCPDispatcher(registry, policy, audit, confirm_fn=lambda _: True)
    call = MCPCall("SystemTool", "ram_stats", {})
    result = d.dispatch(call)
    assert not result.success
    assert "disabled" in result.output.lower()


def test_dispatch_param_validation(dispatcher):
    # commit requires 'message' param
    call = MCPCall("GitTool", "commit", {})
    result = dispatcher.dispatch(call)
    assert not result.success


def test_dispatch_cancelled_by_user(registry, policy, audit):
    from mcp_assistant.mcp.dispatcher import MCPDispatcher
    d = MCPDispatcher(registry, policy, audit, confirm_fn=lambda _: False)
    # FileHandler.write requires confirmation
    call = MCPCall("FileHandler", "write", {"path": "x.txt", "content": "data"})
    result = d.dispatch(call)
    assert not result.success
    assert "Cancelled" in result.output


def test_dispatch_chain(dispatcher):
    chain = MCPChain(
        steps=[
            MCPChainStep("SystemTool", "cpu_stats", {}, confidence=0.9),
            MCPChainStep("SystemTool", "ram_stats", {}, confidence=0.9),
        ],
        description="cpu then ram",
    )
    results = dispatcher.dispatch_chain(chain)
    assert len(results) == 2
    assert all(r.success for r in results)


def test_dispatch_chain_stops_on_failure(dispatcher):
    chain = MCPChain(
        steps=[
            MCPChainStep("GhostTool", "nothing", {}, confidence=0.9),   # will fail
            MCPChainStep("SystemTool", "ram_stats", {}, confidence=0.9), # should not run
        ],
        description="fail then ram",
        continue_on_error=False,
    )
    results = dispatcher.dispatch_chain(chain)
    assert len(results) == 1
    assert not results[0].success


def test_dispatch_chain_continue_on_error(dispatcher):
    chain = MCPChain(
        steps=[
            MCPChainStep("GhostTool", "nothing", {}, confidence=0.9),   # fail
            MCPChainStep("SystemTool", "ram_stats", {}, confidence=0.9), # runs anyway
        ],
        description="fail but continue",
        continue_on_error=True,
    )
    results = dispatcher.dispatch_chain(chain)
    assert len(results) == 2
    assert not results[0].success
    assert results[1].success


def test_chain_template_resolution(dispatcher):
    # step_0 output should be injectable into step_1 params via {{step_0.output}}
    from mcp_assistant.mcp.schema import MCPChain, MCPChainStep
    chain = MCPChain(
        steps=[
            MCPChainStep("SystemTool", "ram_stats", {}, confidence=0.9),
            MCPChainStep("SystemTool", "cpu_stats", {"note": "{{step_0.output}}"}, confidence=0.9),
        ],
        description="template test",
    )
    results = dispatcher.dispatch_chain(chain)
    assert len(results) == 2
    assert results[0].success
    assert results[1].success
