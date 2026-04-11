from __future__ import annotations

from mcp_assistant.llm.prompt_builder import PromptBuilder
from mcp_assistant.mcp.base import MCPTool
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant.mcp.registry import ToolRegistry
from mcp_assistant.mcp.schema import MCPCall, MCPChain, MCPChainStep, MCPResult
from mcp_assistant.orchestration.graph import (
    build_assistant_orchestrator,
    build_orchestrator_graph,
)


def _trace_node(name: str, route: str | None = None):
    async def _node(state):
        trace = list(state.get("node_trace") or [])
        trace.append(name)
        state["node_trace"] = trace
        if route is not None:
            state["route"] = route
        return state

    return _node


class _DummyTool(MCPTool):
    TOOL_NAME = ""
    DESTRUCTIVE_ACTIONS: set[str] = set()

    def __init__(self, tool_name: str, destructive_actions: set[str] | None = None) -> None:
        self.TOOL_NAME = tool_name
        self.DESTRUCTIVE_ACTIONS = destructive_actions or set()

    def execute(self, call: MCPCall) -> MCPResult:
        return self._ok(call, f"{call.tool}.{call.action}")


class _FakeClient:
    model = "fake-model"

    def __init__(self, responses=None) -> None:
        self._responses = iter(responses or [])

    def generate(self, *args, **kwargs):
        return next(self._responses)


class _FakeDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def dispatch(self, call: MCPCall) -> MCPResult:
        self.calls.append(("single", call.tool, call.action))
        return MCPResult(call=call, success=True, output=f"{call.tool}.{call.action} OK")

    def dispatch_chain(self, chain: MCPChain, model_router=None) -> list[MCPResult]:
        self.calls.append(("chain", "MCPChain", str(len(chain.steps))))
        return [
            MCPResult(
                call=MCPCall(tool=step.tool, action=step.action, params=step.params),
                success=True,
                output=f"{step.tool}.{step.action} OK",
            )
            for step in chain.steps
        ]


def test_build_orchestrator_graph_executes_selected_branch():
    graph = build_orchestrator_graph(
        {
            "classify": _trace_node("classify"),
            "planner": _trace_node("planner"),
            "router": _trace_node("router", route="gitops"),
            "direct": _trace_node("direct"),
            "codegen": _trace_node("codegen"),
            "review": _trace_node("review"),
            "gitops": _trace_node("gitops"),
            "sysperf": _trace_node("sysperf"),
            "mcpexec": _trace_node("mcpexec"),
            "aggregate": _trace_node("aggregate"),
            "finalize": _trace_node("finalize"),
        }
    )

    state = graph.invoke({"user_message": "show git status", "node_trace": []})

    assert state["node_trace"] == [
        "classify",
        "planner",
        "router",
        "gitops",
        "aggregate",
        "finalize",
    ]


def test_build_orchestrator_graph_executes_direct_branch():
    graph = build_orchestrator_graph(
        {
            "classify": _trace_node("classify"),
            "planner": _trace_node("planner"),
            "router": _trace_node("router", route="direct"),
            "direct": _trace_node("direct"),
            "codegen": _trace_node("codegen"),
            "review": _trace_node("review"),
            "gitops": _trace_node("gitops"),
            "sysperf": _trace_node("sysperf"),
            "mcpexec": _trace_node("mcpexec"),
            "aggregate": _trace_node("aggregate"),
            "finalize": _trace_node("finalize"),
        }
    )

    state = graph.invoke({"user_message": "explain unit testing", "node_trace": []})

    assert state["node_trace"] == [
        "classify",
        "planner",
        "router",
        "direct",
        "aggregate",
        "finalize",
    ]


def test_orchestrator_requests_clarification_before_execution():
    registry = ToolRegistry()
    registry.register(_DummyTool("FileHandler", {"write", "delete"}))
    dispatcher = _FakeDispatcher()
    orchestrator = build_assistant_orchestrator(
        client=_FakeClient(),
        prompt_builder=PromptBuilder(),
        dispatcher=dispatcher,
        registry=registry,
        policy=PolicyConfig.default(),
        model_router=None,
    )

    state = orchestrator.invoke(
        user_message="delete config.py",
        parsed_call=MCPCall(
            tool="FileHandler",
            action="delete",
            params={"path": "config.py"},
            confidence=0.2,
        ),
    )

    assert state["awaiting_clarification"] is True
    assert state["requires_confirmation"] is True
    assert "FileHandler.delete" in state["final_response"]
    assert dispatcher.calls == []
    assert state["node_trace"][-1] == "finalize"


def test_orchestrator_routes_and_dispatches_specialist():
    registry = ToolRegistry()
    registry.register(_DummyTool("GitTool"))
    dispatcher = _FakeDispatcher()
    orchestrator = build_assistant_orchestrator(
        client=_FakeClient(),
        prompt_builder=PromptBuilder(),
        dispatcher=dispatcher,
        registry=registry,
        policy=PolicyConfig.default(),
        model_router=None,
    )

    state = orchestrator.invoke(
        user_message="show git status",
        parsed_call=MCPCall(
            tool="GitTool",
            action="status",
            params={},
            confidence=0.95,
        ),
    )

    assert state["route"] == "gitops"
    assert dispatcher.calls == [("single", "GitTool", "status")]
    assert state["dispatch_results"][0].output == "GitTool.status OK"
    assert "gitops" in state["specialist_notes"]
    assert state["node_trace"] == [
        "classify",
        "planner",
        "router",
        "gitops",
        "aggregate",
        "finalize",
    ]


def test_orchestrator_routes_chain_to_mcpexec():
    registry = ToolRegistry()
    registry.register(_DummyTool("GitTool"))
    registry.register(_DummyTool("SystemTool"))
    dispatcher = _FakeDispatcher()
    orchestrator = build_assistant_orchestrator(
        client=_FakeClient(),
        prompt_builder=PromptBuilder(),
        dispatcher=dispatcher,
        registry=registry,
        policy=PolicyConfig.default(),
        model_router=None,
    )

    chain = MCPChain(
        steps=[
            MCPChainStep(tool="GitTool", action="status", params={}, confidence=0.9),
            MCPChainStep(tool="SystemTool", action="cpu_stats", params={}, confidence=0.9),
        ],
        description="status then cpu stats",
    )

    state = orchestrator.invoke(
        user_message="show git status then cpu stats",
        parsed_call=chain,
    )

    assert state["route"] == "mcpexec"
    assert dispatcher.calls == [("chain", "MCPChain", "2")]
    assert len(state["dispatch_results"]) == 2


def test_orchestrator_can_answer_directly_without_mcp():
    registry = ToolRegistry()
    dispatcher = _FakeDispatcher()
    client = _FakeClient(
        [
            '{"intent":"greeting","difficulty":"low","mode_hint":"direct","confidence":0.95,"reasoning":"No local state needed."}',
            '{"mode":"direct","objective":"Answer the greeting","steps":["Answer directly","Aggregate the result"],"specialist":"direct","reasoning":"The request is conversational."}',
            '{"answer":"Hello! I can help with code, files, git, and system tasks.","confidence":0.93}',
            '{"status":"success","mode":"direct","summary":"Hello! I can help with code, files, git, and system tasks.","details":["Answered directly without MCP tools."],"tools_used":[],"workflow":["classify","planner","router","direct","aggregate"],"next_step":"Ask a workspace or coding question when ready."}',
        ]
    )
    orchestrator = build_assistant_orchestrator(
        client=client,
        prompt_builder=PromptBuilder(),
        dispatcher=dispatcher,
        registry=registry,
        policy=PolicyConfig.default(),
        model_router=None,
    )

    state = orchestrator.invoke(user_message="hi")

    assert state["route"] == "direct"
    assert "Hello! I can help" in state["final_response"]
    assert state.get("aggregate_payload") is None
    assert state.get("direct_response", "").startswith("Hello!")
    assert dispatcher.calls == []
