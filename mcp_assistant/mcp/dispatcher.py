from __future__ import annotations
import json
import logging
import time
from mcp_assistant.mcp.base import MCPTool
from mcp_assistant.mcp import tool_cache
from mcp_assistant.mcp.registry import ToolRegistry
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant.mcp.schema import MCPCall, MCPChain, MCPResult
from mcp_assistant.audit.logger import AuditLogger
from mcp_assistant import config

log = logging.getLogger(__name__)


class PolicyViolation(Exception):
    pass


class MCPDispatcher:
    def __init__(
        self,
        registry: ToolRegistry,
        policy: PolicyConfig,
        audit_logger: AuditLogger,
        confirm_fn=None,
        client=None,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._audit = audit_logger
        self._client = client
        # confirm_fn(prompt: str) -> bool — injected so TUI/CLI can handle differently
        self._confirm_fn = confirm_fn or _default_confirm

    # ── Public API ────────────────────────────────────────────────────────────

    def dispatch(self, call: MCPCall) -> MCPResult:
        start = time.perf_counter()

        # 1. Tool must exist
        tool = self._registry.get(call.tool)
        if tool is None:
            result = MCPResult(
                call=call, success=False,
                output=f"Unknown tool: '{call.tool}'. Available: {sorted(self._registry.tool_names())}",
                error=f"Unknown tool: {call.tool}",
            )
            result.model_used = getattr(call, "_model_used", "")
            self._audit.log(call, result)
            return result

        # 2. Tool must be allowed by policy
        if not self._policy.is_tool_allowed(call.tool):
            result = MCPResult(
                call=call, success=False,
                output=f"Tool '{call.tool}' is disabled by policy.",
                error="PolicyViolation: tool disabled",
            )
            result.model_used = getattr(call, "_model_used", "")
            self._audit.log(call, result)
            return result

        # 3. Validate params
        errors = tool.validate_params(call)
        if errors:
            result = MCPResult(
                call=call, success=False,
                output=f"Invalid params: {'; '.join(errors)}",
                error="Param validation failed",
            )
            result.model_used = getattr(call, "_model_used", "")
            self._audit.log(call, result)
            return result

        cached = tool_cache.get(call)
        if cached is not None:
            cached.call = call
            cached.model_used = getattr(call, "_model_used", cached.model_used)
            cached.duration_ms = round((time.perf_counter() - start) * 1000, 2)
            if isinstance(cached.data, dict):
                cached.data["from_tool_cache"] = True
            self._audit.log(call, cached)
            return cached

        # 4. Dry-run / confirmation for destructive or policy-flagged actions
        needs_confirm = (
            self._policy.dry_run_mode
            or self._policy.requires_confirmation(call.tool, call.action)
            or (self._policy.confirm_all_destructive and call.action in tool.DESTRUCTIVE_ACTIONS)
            or call.action in tool.ALWAYS_CONFIRM_ACTIONS
        )
        if needs_confirm:
            preview = tool.dry_run(call)
            if not self._confirm_fn(f"{preview}\nProceed? (y/n): "):
                result = MCPResult(
                    call=call, success=False,
                    output="Cancelled by user.",
                    error="User cancelled",
                )
                result.model_used = getattr(call, "_model_used", "")
                self._audit.log(call, result)
                return result

        # 5. Execute
        result = tool.execute(call)
        elapsed = (time.perf_counter() - start) * 1000
        result.duration_ms = round(elapsed, 2)
        result.model_used = getattr(call, "_model_used", "")
        tool_cache.put(call, result)

        # 6. Audit
        self._audit.log(call, result)
        return result

    def dispatch_chain(self, chain: MCPChain, model_router=None) -> list[MCPResult]:
        results: list[MCPResult] = []
        for i, step in enumerate(chain.steps):
            # Resolve {{step_N.output}} templates in params
            params = _resolve_templates(step.params, results)
            call = MCPCall(
                tool=step.tool,
                action=step.action,
                params=params,
                confidence=step.confidence,
            )
            setattr(call, "_model_used", getattr(chain, "_model_used", ""))
            result = self.dispatch(call)
            results.append(result)
            if not result.success and not chain.continue_on_error:
                break
        if model_router and len(results) >= 2:
            self._aggregate_chain(chain, results, model_router)
        return results

    def _aggregate_chain(self, chain: MCPChain, results: list[MCPResult], model_router) -> None:
        if self._client is None:
            return

        from mcp_assistant.mcp.schema import ChainSummary_SCHEMA

        steps_text = "\n".join(
            f"Step {i + 1} ({r.call.tool}.{r.call.action}): "
            f"{'OK' if r.success else 'FAILED'} - {r.output[:200]}"
            for i, r in enumerate(results)
        )
        prompt = (
            "Summarise the following multi-step operation results.\n"
            f"Chain description: {chain.description}\n\n{steps_text}"
        )
        try:
            raw = self._client.generate(
                prompt=prompt,
                system="You are a terminal assistant. Summarise chain results concisely.",
                temperature=config.OLLAMA_TEMP_STRUCTURED,
                model=model_router.aggregator_model(),
                format_schema=ChainSummary_SCHEMA if model_router.supports_structured_output() else None,
            )
            try:
                summary = json.loads(raw)
            except json.JSONDecodeError:
                summary = {
                    "summary": raw,
                    "steps_succeeded": sum(r.success for r in results),
                    "steps_failed": sum(not r.success for r in results),
                    "overall_status": "success" if all(r.success for r in results) else "partial",
                }

            if not isinstance(results[-1].data, dict):
                results[-1].data = {"result_data": results[-1].data}
            results[-1].data["chain_summary"] = summary
        except Exception as exc:
            log.warning("Chain aggregation failed: %s", exc)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _default_confirm(prompt: str) -> bool:
    ans = input(prompt).strip().lower()
    return ans in {"y", "yes"}


def _resolve_templates(params: dict, prior_results: list[MCPResult]) -> dict:
    resolved = {}
    for k, v in params.items():
        if isinstance(v, str):
            for i, r in enumerate(prior_results):
                v = v.replace(f"{{{{step_{i}.output}}}}", r.output)
        resolved[k] = v
    return resolved
