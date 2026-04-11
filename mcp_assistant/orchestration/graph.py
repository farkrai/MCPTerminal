from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, TypedDict, cast

from mcp_assistant.llm.client import OllamaClient
from mcp_assistant.llm.confidence import should_clarify, should_clarify_chain
from mcp_assistant.llm.inference import infer_call
from mcp_assistant.llm.model_router import ModelRouter
from mcp_assistant.llm.prompt_builder import PromptBuilder
from mcp_assistant.mcp.dispatcher import MCPDispatcher
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant.mcp.registry import ToolRegistry
from mcp_assistant.mcp.schema import (
    DirectAnswer_SCHEMA,
    FinalResponse_SCHEMA,
    MCPCall,
    MCPChain,
    MCPResult,
    OrchestratorClassification_SCHEMA,
    OrchestratorPlan_SCHEMA,
)

try:  # pragma: no cover - optional dependency
    from langgraph.graph import END, StateGraph

    _LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by fallback tests
    END = "__END__"
    StateGraph = None
    _LANGGRAPH_AVAILABLE = False

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)

NodeFn = Callable[["GraphState"], Awaitable["GraphState"]]


class GraphState(TypedDict, total=False):
    user_message: str
    context: list[dict]
    difficulty: str
    route: str
    response_mode: str
    classification: dict[str, Any]
    planner_notes: str
    specialist_notes: Dict[str, str]
    aggregate_text: str
    aggregate_payload: dict[str, Any]
    final_response: str
    tool_calls: list[dict]
    requires_confirmation: bool
    execution_plan: Any
    node_trace: list[str]
    parsed_call: Any
    dispatch_results: list[MCPResult]
    confirmed: bool
    awaiting_clarification: bool
    clarification_prompt: str
    direct_response: str
    error: str


@dataclass
class AssistantOrchestrator:
    graph: Any

    def _initial_state(
        self,
        user_message: str,
        context: list[dict] | None = None,
        parsed_call: MCPCall | MCPChain | None = None,
        confirmed: bool = False,
        extra_state: dict[str, Any] | None = None,
    ) -> GraphState:
        state: GraphState = {
            "user_message": user_message,
            "context": list(context or []),
            "specialist_notes": {},
            "node_trace": [],
            "execution_plan": {},
            "tool_calls": [],
        }
        if parsed_call is not None:
            state["parsed_call"] = parsed_call
        if confirmed:
            state["confirmed"] = True
        if extra_state:
            state.update(extra_state)
        return state

    def invoke(
        self,
        *,
        user_message: str,
        context: list[dict] | None = None,
        parsed_call: MCPCall | MCPChain | None = None,
        confirmed: bool = False,
        extra_state: dict[str, Any] | None = None,
    ) -> GraphState:
        state = self._initial_state(user_message, context, parsed_call, confirmed, extra_state)
        if hasattr(self.graph, "ainvoke"):
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return cast(GraphState, asyncio.run(self.graph.ainvoke(state)))
            raise RuntimeError(
                "Synchronous orchestrator.invoke() was called from a running event loop. "
                "Use await orchestrator.ainvoke(...) or run invoke() in a worker thread."
            )
        return cast(GraphState, self.graph.invoke(state))

    async def ainvoke(
        self,
        *,
        user_message: str,
        context: list[dict] | None = None,
        parsed_call: MCPCall | MCPChain | None = None,
        confirmed: bool = False,
        extra_state: dict[str, Any] | None = None,
    ) -> GraphState:
        state = self._initial_state(user_message, context, parsed_call, confirmed, extra_state)
        return cast(GraphState, await self.graph.ainvoke(state))


def langgraph_available() -> bool:
    return _LANGGRAPH_AVAILABLE


def build_orchestrator_graph(nodes: Dict[str, NodeFn]):
    """Create and compile the graph."""
    if _LANGGRAPH_AVAILABLE:
        graph = StateGraph(GraphState)
        graph.add_node("classify", nodes["classify"])
        graph.add_node("planner", nodes["planner"])
        graph.add_node("router", nodes["router"])
        graph.add_node("direct", nodes["direct"])
        graph.add_node("codegen", nodes["codegen"])
        graph.add_node("review", nodes["review"])
        graph.add_node("gitops", nodes["gitops"])
        graph.add_node("sysperf", nodes["sysperf"])
        graph.add_node("mcpexec", nodes["mcpexec"])
        graph.add_node("aggregate", nodes["aggregate"])
        graph.add_node("finalize", nodes["finalize"])

        graph.set_entry_point("classify")
        graph.add_edge("classify", "planner")
        graph.add_edge("planner", "router")

        def route_selector(state: GraphState) -> str:
            return state.get("route", "mcpexec")

        graph.add_conditional_edges(
            "router",
            route_selector,
            {
                "direct": "direct",
                "codegen": "codegen",
                "review": "review",
                "gitops": "gitops",
                "sysperf": "sysperf",
                "mcpexec": "mcpexec",
                "finalize": "finalize",
            },
        )

        graph.add_edge("direct", "aggregate")
        graph.add_edge("codegen", "aggregate")
        graph.add_edge("review", "aggregate")
        graph.add_edge("gitops", "aggregate")
        graph.add_edge("sysperf", "aggregate")
        graph.add_edge("mcpexec", "aggregate")
        graph.add_edge("aggregate", "finalize")
        graph.add_edge("finalize", END)
        return _LangGraphWrapper(graph.compile())

    return _SimpleCompiledGraph(nodes)


def build_assistant_orchestrator(
    *,
    client: OllamaClient,
    prompt_builder: PromptBuilder,
    dispatcher: MCPDispatcher,
    registry: ToolRegistry,
    policy: PolicyConfig,
    model_router: ModelRouter | None = None,
) -> AssistantOrchestrator:
    nodes = _build_default_nodes(
        client=client,
        prompt_builder=prompt_builder,
        dispatcher=dispatcher,
        registry=registry,
        policy=policy,
        model_router=model_router,
    )
    return AssistantOrchestrator(build_orchestrator_graph(nodes))


class _LangGraphWrapper:
    """Wraps a compiled LangGraph so .invoke() works with async nodes."""

    def __init__(self, compiled_graph) -> None:
        self._graph = compiled_graph

    def invoke(self, state: GraphState) -> GraphState:
        return asyncio.run(self._graph.ainvoke(state))

    async def ainvoke(self, state: GraphState) -> GraphState:
        return await self._graph.ainvoke(state)


class _SimpleCompiledGraph:
    """Small fallback that preserves the orchestration contract without LangGraph."""

    def __init__(self, nodes: Dict[str, NodeFn]) -> None:
        self._nodes = nodes

    async def ainvoke(self, state: GraphState) -> GraphState:
        current = dict(state)
        for name in ("classify", "planner", "router"):
            current = await self._nodes[name](current)
        route = current.get("route", "mcpexec")
        if route != "finalize":
            current = await self._nodes.get(route, self._nodes["mcpexec"])(current)
            current = await self._nodes["aggregate"](current)
        current = await self._nodes["finalize"](current)
        return cast(GraphState, current)

    def invoke(self, state: GraphState) -> GraphState:
        return asyncio.run(self.ainvoke(state))


def _build_default_nodes(
    *,
    client: OllamaClient,
    prompt_builder: PromptBuilder,
    dispatcher: MCPDispatcher,
    registry: ToolRegistry,
    policy: PolicyConfig,
    model_router: ModelRouter | None,
) -> Dict[str, NodeFn]:
    async def classify(state: GraphState) -> GraphState:
        _trace(state, "classify")
        state.setdefault("specialist_notes", {})
        plan = dict(state.get("execution_plan") or {})
        plan.setdefault("engine", "langgraph" if _LANGGRAPH_AVAILABLE else "builtin-fallback")
        plan["context_turns"] = len(state.get("context") or [])

        classification = _classify_request(
            client=client,
            prompt_builder=prompt_builder,
            model_router=model_router,
            user_message=state.get("user_message", ""),
            context=state.get("context"),
        )
        state["classification"] = classification
        state["difficulty"] = str(classification.get("difficulty", state.get("difficulty", "low")))
        state["response_mode"] = str(classification.get("mode_hint", "mcp"))
        plan["difficulty"] = state.get("difficulty", "low")
        plan["classification_confidence"] = classification.get("confidence", 0.0)
        plan["classification_mode_hint"] = classification.get("mode_hint", "mcp")
        state["execution_plan"] = plan
        return state

    async def planner(state: GraphState) -> GraphState:
        _trace(state, "planner")
        plan_update = _plan_request(
            client=client,
            prompt_builder=prompt_builder,
            model_router=model_router,
            user_message=state.get("user_message", ""),
            classification=state.get("classification") or {},
            parsed_call=state.get("parsed_call"),
        )
        plan = dict(state.get("execution_plan") or {})
        plan.update(plan_update)
        state["execution_plan"] = plan
        state["planner_notes"] = (
            f"{plan_update.get('objective', '')} | {plan_update.get('reasoning', '')}".strip(" |")
        )
        state["response_mode"] = str(plan_update.get("mode", state.get("response_mode", "mcp")))
        return state

    async def router(state: GraphState) -> GraphState:
        _trace(state, "router")
        try:
            parsed = state.get("parsed_call")
            if (
                parsed is None
                and state.get("response_mode") == "direct"
                and not _looks_workspace_bound(state.get("user_message", ""))
            ):
                state["route"] = "direct"
                state["tool_calls"] = []
                plan = dict(state.get("execution_plan") or {})
                plan["route"] = "direct"
                state["execution_plan"] = plan
                return state

            if parsed is None:
                parsed = infer_call(
                    nl_input=state.get("user_message", ""),
                    client=client,
                    builder=prompt_builder,
                    model_router=model_router,
                    context=state.get("context"),
                )
            state["parsed_call"] = parsed

            if isinstance(parsed, MCPCall) and parsed.tool == "unknown":
                state["response_mode"] = "direct"
                state["route"] = "direct"
                state["tool_calls"] = []
                plan = dict(state.get("execution_plan") or {})
                plan["route"] = "direct"
                state["execution_plan"] = plan
                return state

            state["tool_calls"] = _tool_calls(parsed)
            state["requires_confirmation"] = _requires_confirmation(parsed, registry, policy)

            if isinstance(parsed, MCPCall):
                complexity = getattr(parsed, "_complexity", "")
                if complexity and complexity != "routing":
                    state["difficulty"] = complexity

            if _needs_clarification(parsed, policy) and not state.get("confirmed", False):
                state["awaiting_clarification"] = True
                state["route"] = "finalize"
                state["clarification_prompt"] = _clarification_prompt(
                    prompt_builder, state.get("user_message", ""), parsed
                )
                state["aggregate_text"] = state["clarification_prompt"]
                return state

            state["response_mode"] = "mcp"
            state["route"] = _specialist_route(parsed)
            plan = dict(state.get("execution_plan") or {})
            plan["route"] = state["route"]
            state["execution_plan"] = plan
            return state
        except Exception as exc:
            state["route"] = "finalize"
            state["error"] = f"Routing failed: {exc}"
            return state

    async def direct(state: GraphState) -> GraphState:
        _trace(state, "direct")
        answer = _compose_direct_response(
            client=client,
            prompt_builder=prompt_builder,
            model_router=model_router,
            user_message=state.get("user_message", ""),
            plan=cast(dict[str, Any], state.get("execution_plan") or {}),
            context=state.get("context"),
        )
        state["direct_response"] = str(answer.get("answer", ""))
        notes = dict(state.get("specialist_notes") or {})
        notes["direct"] = (
            "Answered directly without MCP tools "
            f"(confidence {float(answer.get('confidence', 0.0)):.2f})."
        )
        state["specialist_notes"] = notes
        plan = dict(state.get("execution_plan") or {})
        plan["executed_by"] = "direct"
        plan["direct_confidence"] = answer.get("confidence", 0.0)
        state["execution_plan"] = plan
        return state

    async def codegen(state: GraphState) -> GraphState:
        return _dispatch_specialist("codegen", state, dispatcher, model_router)

    async def review(state: GraphState) -> GraphState:
        return _dispatch_specialist("review", state, dispatcher, model_router)

    async def gitops(state: GraphState) -> GraphState:
        return _dispatch_specialist("gitops", state, dispatcher, model_router)

    async def sysperf(state: GraphState) -> GraphState:
        return _dispatch_specialist("sysperf", state, dispatcher, model_router)

    async def mcpexec(state: GraphState) -> GraphState:
        return _dispatch_specialist("mcpexec", state, dispatcher, model_router)

    async def aggregate(state: GraphState) -> GraphState:
        _trace(state, "aggregate")
        if state.get("awaiting_clarification"):
            payload = _fallback_aggregate_payload(
                status="clarification",
                mode=state.get("response_mode", "mcp"),
                summary=state.get("clarification_prompt", "Please confirm."),
                details=["The request needs confirmation before execution."],
                tools_used=[],
                workflow=list(state.get("node_trace") or []),
                next_step="Reply with yes to proceed, or rephrase the request.",
            )
            state["aggregate_payload"] = payload
            state["aggregate_text"] = _render_aggregate_payload(payload)
            return state

        if state.get("error"):
            payload = _fallback_aggregate_payload(
                status="error",
                mode=state.get("response_mode", "mcp"),
                summary=state["error"],
                details=["The orchestration flow could not complete successfully."],
                tools_used=[],
                workflow=list(state.get("node_trace") or []),
                next_step="Retry the request or inspect the error details.",
            )
            state["aggregate_payload"] = payload
            state["aggregate_text"] = _render_aggregate_payload(payload)
            return state

        mode = "direct" if state.get("direct_response") else "mcp"
        results = list(state.get("dispatch_results") or [])
        
        # For direct responses, skip structured formatting
        if mode == "direct":
            source_text = state.get("direct_response", "")
            state["aggregate_text"] = source_text
            # Don't set aggregate_payload for direct mode to avoid structured output
            return state
        else:
            if not results:
                payload = _fallback_aggregate_payload(
                    status="error",
                    mode="mcp",
                    summary="No execution results available.",
                    details=["The route selected MCP execution, but no tool results were produced."],
                    tools_used=[],
                    workflow=list(state.get("node_trace") or []),
                    next_step="Retry the request.",
                )
                state["aggregate_payload"] = payload
                state["aggregate_text"] = _render_aggregate_payload(payload)
                return state
            source_text = _summarize_results(results)

        payload = _aggregate_response(
            client=client,
            prompt_builder=prompt_builder,
            model_router=model_router,
            user_message=state.get("user_message", ""),
            mode=mode,
            workflow=list(state.get("node_trace") or []),
            planner_notes=state.get("planner_notes", ""),
            specialist_notes=dict(state.get("specialist_notes") or {}),
            tool_calls=list(state.get("tool_calls") or []),
            source_text=source_text,
        )
        state["aggregate_payload"] = payload
        state["aggregate_text"] = _render_aggregate_payload(payload)
        return state

    async def finalize(state: GraphState) -> GraphState:
        _trace(state, "finalize")
        plan = dict(state.get("execution_plan") or {})
        plan["node_count"] = len(state.get("node_trace") or [])
        state["execution_plan"] = plan

        if state.get("aggregate_payload"):
            state["final_response"] = state.get("aggregate_text", "")
        elif state.get("awaiting_clarification"):
            state["final_response"] = state.get("clarification_prompt", "Please confirm the action.")
        elif state.get("error"):
            state["final_response"] = state.get("aggregate_text", state["error"])
        else:
            state["final_response"] = state.get("aggregate_text", "")
        return state

    return {
        "classify": classify,
        "planner": planner,
        "router": router,
        "direct": direct,
        "codegen": codegen,
        "review": review,
        "gitops": gitops,
        "sysperf": sysperf,
        "mcpexec": mcpexec,
        "aggregate": aggregate,
        "finalize": finalize,
    }


def _dispatch_specialist(
    name: str,
    state: GraphState,
    dispatcher: MCPDispatcher,
    model_router: ModelRouter | None,
) -> GraphState:
    _trace(state, name)
    if state.get("awaiting_clarification"):
        return state

    parsed = state.get("parsed_call")
    if parsed is None:
        state["error"] = "No parsed tool call available for execution."
        return state

    if isinstance(parsed, MCPChain):
        results = dispatcher.dispatch_chain(parsed, model_router=model_router)
    else:
        results = [dispatcher.dispatch(parsed)]

    notes = dict(state.get("specialist_notes") or {})
    notes[name] = _specialist_note(name, parsed, results)
    state["specialist_notes"] = notes
    state["dispatch_results"] = results
    plan = dict(state.get("execution_plan") or {})
    plan["executed_by"] = name
    state["execution_plan"] = plan
    return state


def _trace(state: GraphState, node_name: str) -> None:
    trace = list(state.get("node_trace") or [])
    trace.append(node_name)
    state["node_trace"] = trace


def _classify_difficulty(message: str) -> str:
    text = message.lower()
    if any(token in text for token in ("explain", "summarize", "analyse", "analyze", "review", "why")):
        return "high"
    if _looks_multi_step(text) or any(token in text for token in ("compare", "debug", "investigate")):
        return "medium"
    return "low"


def _looks_multi_step(message: str) -> bool:
    text = message.lower()
    return any(token in text for token in (" then ", "after that", "followed by", "and also", "first "))


def _tool_calls(parsed: MCPCall | MCPChain) -> list[dict]:
    if isinstance(parsed, MCPChain):
        return [
            {
                "tool": step.tool,
                "action": step.action,
                "params": dict(step.params),
                "confidence": step.confidence,
            }
            for step in parsed.steps
        ]
    return [parsed.to_dict()]


def _specialist_route(parsed: MCPCall | MCPChain) -> str:
    if isinstance(parsed, MCPChain):
        return "mcpexec"
    if parsed.tool == "GitTool":
        return "gitops"
    if parsed.tool == "SystemTool":
        return "sysperf"
    if parsed.tool == "FileHandler":
        return "codegen"
    if parsed.tool == "TestRunner" and parsed.action == "explain_failures":
        return "review"
    return "mcpexec"


def _needs_clarification(parsed: MCPCall | MCPChain, policy: PolicyConfig) -> bool:
    if isinstance(parsed, MCPChain):
        return should_clarify_chain(parsed, policy.confidence_threshold)
    return should_clarify(parsed, policy.confidence_threshold)


def _clarification_prompt(
    prompt_builder: PromptBuilder,
    user_message: str,
    parsed: MCPCall | MCPChain,
) -> str:
    if isinstance(parsed, MCPCall):
        return prompt_builder.clarification_prompt(user_message, parsed.tool, parsed.action)
    steps_desc = " -> ".join(f"{step.tool}.{step.action}" for step in parsed.steps)
    return (
        f"I wasn't fully confident about your request: '{user_message}'\n"
        f"I interpreted it as the chain: {steps_desc}\n"
        "Could you rephrase or confirm? (or type 'yes' to proceed)"
    )


def _requires_confirmation(
    parsed: MCPCall | MCPChain,
    registry: ToolRegistry,
    policy: PolicyConfig,
) -> bool:
    calls: list[tuple[str, str]]
    if isinstance(parsed, MCPChain):
        calls = [(step.tool, step.action) for step in parsed.steps]
    else:
        calls = [(parsed.tool, parsed.action)]

    for tool_name, action in calls:
        tool = registry.get(tool_name)
        if tool is None:
            continue
        if (
            policy.requires_confirmation(tool_name, action)
            or (policy.confirm_all_destructive and action in tool.DESTRUCTIVE_ACTIONS)
            or action in tool.ALWAYS_CONFIRM_ACTIONS
        ):
            return True
    return False


def _specialist_note(
    name: str,
    parsed: MCPCall | MCPChain,
    results: list[MCPResult],
) -> str:
    if isinstance(parsed, MCPChain):
        return f"{name} executed {len(parsed.steps)} step(s); {sum(r.success for r in results)} succeeded."
    status = "succeeded" if results and results[0].success else "failed"
    return f"{name} handled {parsed.tool}.{parsed.action} and {status}."


def _classify_request(
    *,
    client: OllamaClient,
    prompt_builder: PromptBuilder,
    model_router: ModelRouter | None,
    user_message: str,
    context: list[dict] | None,
) -> dict[str, Any]:
    fallback = _fallback_classification(user_message)
    try:
        data = _generate_structured_json(
            client=client,
            prompt=prompt_builder.orchestrator_classify_prompt(user_message, context),
            system=prompt_builder.orchestrator_classify_system_prompt(),
            model=model_router.classifier_model() if model_router else None,
            format_schema=(
                OrchestratorClassification_SCHEMA
                if model_router and model_router.supports_structured_output()
                else None
            ),
        )
        return {
            "intent": str(data.get("intent", fallback["intent"])),
            "difficulty": str(data.get("difficulty", fallback["difficulty"])),
            "mode_hint": str(data.get("mode_hint", fallback["mode_hint"])),
            "confidence": _coerce_confidence(data.get("confidence", fallback["confidence"])),
            "reasoning": str(data.get("reasoning", fallback["reasoning"])),
        }
    except Exception:
        return fallback


def _plan_request(
    *,
    client: OllamaClient,
    prompt_builder: PromptBuilder,
    model_router: ModelRouter | None,
    user_message: str,
    classification: dict[str, Any],
    parsed_call: MCPCall | MCPChain | None,
) -> dict[str, Any]:
    fallback = _fallback_plan(user_message, classification, parsed_call)
    try:
        data = _generate_structured_json(
            client=client,
            prompt=prompt_builder.orchestrator_plan_prompt(user_message, classification),
            system=prompt_builder.orchestrator_plan_system_prompt(),
            model=model_router.planner_model() if model_router else None,
            format_schema=(
                OrchestratorPlan_SCHEMA if model_router and model_router.supports_structured_output() else None
            ),
        )
        steps = [str(step) for step in data.get("steps", fallback["steps"]) if str(step).strip()]
        return {
            "mode": str(data.get("mode", fallback["mode"])),
            "objective": str(data.get("objective", fallback["objective"])),
            "steps": steps or fallback["steps"],
            "specialist": str(data.get("specialist", fallback["specialist"])),
            "reasoning": str(data.get("reasoning", fallback["reasoning"])),
        }
    except Exception:
        return fallback


def _compose_direct_response(
    *,
    client: OllamaClient,
    prompt_builder: PromptBuilder,
    model_router: ModelRouter | None,
    user_message: str,
    plan: dict[str, Any],
    context: list[dict] | None,
) -> dict[str, Any]:
    fallback = {
        "answer": (
            "This request does not appear to need MCP tools. "
            "Please retry once the local model is available for a full direct response."
        ),
        "confidence": 0.4,
    }
    try:
        data = _generate_structured_json(
            client=client,
            prompt=prompt_builder.direct_response_prompt(user_message, plan, context),
            system=prompt_builder.direct_response_system_prompt(),
            model=model_router.router_model() if model_router else None,
            format_schema=(
                DirectAnswer_SCHEMA if model_router and model_router.supports_structured_output() else None
            ),
        )
        return {
            "answer": str(data.get("answer", fallback["answer"])),
            "confidence": _coerce_confidence(data.get("confidence", fallback["confidence"])),
        }
    except Exception:
        return fallback


def _aggregate_response(
    *,
    client: OllamaClient,
    prompt_builder: PromptBuilder,
    model_router: ModelRouter | None,
    user_message: str,
    mode: str,
    workflow: list[str],
    planner_notes: str,
    specialist_notes: dict[str, str],
    tool_calls: list[dict],
    source_text: str,
) -> dict[str, Any]:
    fallback = _fallback_aggregate_payload(
        status="success",
        mode=mode,
        summary=source_text.splitlines()[0][:240] if source_text else "Completed request.",
        details=[line.strip() for line in source_text.splitlines() if line.strip()][:4] or [source_text[:240]],
        tools_used=[
            f"{item.get('tool', 'unknown')}.{item.get('action', 'unknown')}" for item in tool_calls
        ],
        workflow=workflow,
        next_step="None.",
    )
    try:
        data = _generate_structured_json(
            client=client,
            prompt=prompt_builder.aggregator_prompt(
                user_message=user_message,
                mode=mode,
                workflow=workflow,
                planner_notes=planner_notes,
                specialist_notes=specialist_notes,
                tool_calls=tool_calls,
                source_text=source_text,
            ),
            system=prompt_builder.aggregator_system_prompt(),
            model=model_router.aggregator_model() if model_router else None,
            format_schema=(
                FinalResponse_SCHEMA if model_router and model_router.supports_structured_output() else None
            ),
        )
        return {
            "status": str(data.get("status", "success")),
            "mode": str(data.get("mode", mode)),
            "summary": str(data.get("summary", fallback["summary"])),
            "details": [str(item) for item in data.get("details", fallback["details"]) if str(item).strip()]
            or fallback["details"],
            "tools_used": [
                str(item) for item in data.get("tools_used", fallback["tools_used"]) if str(item).strip()
            ],
            "workflow": [str(item) for item in data.get("workflow", workflow) if str(item).strip()] or workflow,
            "next_step": str(data.get("next_step", fallback["next_step"])),
        }
    except Exception:
        return fallback


def _generate_structured_json(
    *,
    client: OllamaClient,
    prompt: str,
    system: str,
    model: str | None,
    format_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    raw = client.generate(
        prompt=prompt,
        system=system,
        temperature=0.1,
        model=model,
        format_schema=format_schema,
    )
    return _extract_json_object(raw)


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(text)
        if not match:
            raise
        data = json.loads(match.group())
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object from LLM response.")
    return data


def _fallback_classification(user_message: str) -> dict[str, Any]:
    mode_hint = "mcp" if _looks_workspace_bound(user_message) else "direct"
    return {
        "intent": user_message[:120] or "unknown",
        "difficulty": _classify_difficulty(user_message),
        "mode_hint": mode_hint,
        "confidence": 0.75 if mode_hint == "mcp" else 0.6,
        "reasoning": (
            "The request appears to depend on local workspace or system state."
            if mode_hint == "mcp"
            else "The request can likely be answered directly without inspecting the local machine."
        ),
    }


def _fallback_plan(
    user_message: str,
    classification: dict[str, Any],
    parsed_call: MCPCall | MCPChain | None,
) -> dict[str, Any]:
    mode = "mcp" if parsed_call is not None else str(classification.get("mode_hint", "mcp"))
    specialist = "direct" if mode == "direct" else _hint_specialist(user_message)
    if mode == "direct":
        steps = ["Answer from general reasoning.", "Hand response to aggregator for structured output."]
    else:
        steps = ["Resolve the right MCP tool or chain.", "Execute the request.", "Send results to aggregator."]
    return {
        "mode": mode,
        "objective": user_message[:120] or "Handle the user request.",
        "steps": steps,
        "specialist": specialist,
        "reasoning": str(classification.get("reasoning", "Plan derived from classifier output.")),
    }


def _fallback_aggregate_payload(
    *,
    status: str,
    mode: str,
    summary: str,
    details: list[str],
    tools_used: list[str],
    workflow: list[str],
    next_step: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "mode": mode,
        "summary": summary.strip() or "Completed request.",
        "details": [item.strip() for item in details if item and item.strip()] or ["No extra details."],
        "tools_used": [item for item in tools_used if item],
        "workflow": workflow,
        "next_step": next_step.strip() or "None.",
    }


def _render_aggregate_payload(payload: dict[str, Any]) -> str:
    parts = [
        f"Status: {payload.get('status', 'success')}",
        f"Mode: {payload.get('mode', 'mcp')}",
        f"Summary: {payload.get('summary', '')}",
    ]

    details = [str(item) for item in payload.get("details", []) if str(item).strip()]
    if details:
        parts.append("Details:")
        parts.extend(f"- {item}" for item in details)

    tools_used = [str(item) for item in payload.get("tools_used", []) if str(item).strip()]
    if tools_used:
        parts.append(f"Tools: {', '.join(tools_used)}")

    workflow = [str(item) for item in payload.get("workflow", []) if str(item).strip()]
    if workflow:
        parts.append(f"Workflow: {' -> '.join(workflow)}")

    next_step = str(payload.get("next_step", "")).strip()
    if next_step:
        parts.append(f"Next: {next_step}")

    return "\n".join(parts)


def _summarize_results(results: list[MCPResult]) -> str:
    if len(results) == 1:
        return results[0].output

    last_data = results[-1].data if results else None
    if isinstance(last_data, dict) and "chain_summary" in last_data:
        chain_summary = last_data["chain_summary"]
        if isinstance(chain_summary, dict):
            summary = str(chain_summary.get("summary", "")).strip()
            if summary:
                return summary
        if isinstance(chain_summary, str) and chain_summary.strip():
            return chain_summary

    return "\n".join(
        f"Step {i + 1}: {result.call.tool}.{result.call.action} -> {result.output[:200]}"
        for i, result in enumerate(results)
    )


def _hint_specialist(user_message: str) -> str:
    text = user_message.lower()
    if "git" in text or any(token in text for token in ("commit", "branch", "diff", "status")):
        return "gitops"
    if any(token in text for token in ("cpu", "ram", "memory", "disk", "process", "uptime")):
        return "sysperf"
    if any(token in text for token in ("test", "pytest", "jest", "failure")):
        return "review"
    if any(token in text for token in ("file", "directory", "folder", "read", "write", "list", "search")):
        return "codegen"
    return "mcpexec"


def _looks_workspace_bound(message: str) -> bool:
    text = message.lower()
    workspace_tokens = (
        "git",
        "repo",
        "repository",
        "branch",
        "commit",
        "diff",
        "status",
        "file",
        "files",
        "folder",
        "directory",
        "read",
        "write",
        "delete",
        "list",
        "search",
        "find",
        "run tests",
        "test",
        "cpu",
        "ram",
        "memory",
        "disk",
        "process",
        "uptime",
        "/",
        "~/",
        ".py",
        ".md",
    )
    return _looks_multi_step(text) or any(token in text for token in workspace_tokens)


def _coerce_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
