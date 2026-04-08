from __future__ import annotations
import time
from mcp_assistant.mcp.base import MCPTool
from mcp_assistant.mcp.registry import ToolRegistry
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant.mcp.schema import MCPCall, MCPChain, MCPResult
from mcp_assistant.audit.logger import AuditLogger


class PolicyViolation(Exception):
    pass


class MCPDispatcher:
    def __init__(
        self,
        registry: ToolRegistry,
        policy: PolicyConfig,
        audit_logger: AuditLogger,
        confirm_fn=None,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._audit = audit_logger
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
            self._audit.log(call, result)
            return result

        # 2. Tool must be allowed by policy
        if not self._policy.is_tool_allowed(call.tool):
            result = MCPResult(
                call=call, success=False,
                output=f"Tool '{call.tool}' is disabled by policy.",
                error="PolicyViolation: tool disabled",
            )
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
            self._audit.log(call, result)
            return result

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
                self._audit.log(call, result)
                return result

        # 5. Execute
        result = tool.execute(call)
        elapsed = (time.perf_counter() - start) * 1000
        result.duration_ms = round(elapsed, 2)

        # 6. Audit
        self._audit.log(call, result)
        return result

    def dispatch_chain(self, chain: MCPChain) -> list[MCPResult]:
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
            result = self.dispatch(call)
            results.append(result)
            if not result.success and not chain.continue_on_error:
                break
        return results


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
