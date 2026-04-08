from __future__ import annotations
from dataclasses import dataclass, field
from mcp_assistant.mcp.schema import MCPCall, MCPChain

_KNOWN_TOOLS = {"FileHandler", "GitTool", "SystemTool", "TestRunner"}


@dataclass
class EvalResult:
    item_id: int
    nl_input: str
    category: str
    difficulty: str
    is_chain: bool

    # Ground truth
    gt_tool: str
    gt_action: str

    # Prediction
    pred_tool: str
    pred_action: str
    pred_confidence: float
    is_chain_response: bool     # LLM returned a chain
    chain_step_count: int       # 0 if not a chain

    # Outcome flags
    tool_match: bool            # pred_tool == gt_tool
    action_match: bool          # tool_match AND pred_action == gt_action
    parse_failed: bool          # LLM output could not be parsed
    hallucinated: bool          # pred_tool not in known tools

    # Performance
    latency_ms: float
    error: str | None = None


@dataclass
class EvalReport:
    results: list[EvalResult]
    model: str
    dataset_path: str
    context_window: int
    confidence_threshold: float
    ablation_label: str = "default"

    # ── Aggregate metrics ─────────────────────────────────────────────────────

    def tool_accuracy(self) -> float:
        valid = [r for r in self.results if not r.parse_failed]
        if not valid:
            return 0.0
        return sum(r.tool_match for r in valid) / len(valid)

    def action_accuracy(self) -> float:
        valid = [r for r in self.results if not r.parse_failed]
        if not valid:
            return 0.0
        return sum(r.action_match for r in valid) / len(valid)

    def parse_failure_rate(self) -> float:
        return sum(r.parse_failed for r in self.results) / len(self.results)

    def hallucination_rate(self) -> float:
        valid = [r for r in self.results if not r.parse_failed]
        if not valid:
            return 0.0
        return sum(r.hallucinated for r in valid) / len(valid)

    def mean_latency_ms(self) -> float:
        lats = [r.latency_ms for r in self.results]
        return sum(lats) / len(lats) if lats else 0.0

    def p95_latency_ms(self) -> float:
        lats = sorted(r.latency_ms for r in self.results)
        if not lats:
            return 0.0
        idx = int(0.95 * len(lats))
        return lats[min(idx, len(lats) - 1)]

    def per_category(self) -> dict[str, dict]:
        categories: dict[str, list[EvalResult]] = {}
        for r in self.results:
            categories.setdefault(r.category, []).append(r)
        out = {}
        for cat, items in categories.items():
            valid = [r for r in items if not r.parse_failed]
            out[cat] = {
                "count": len(items),
                "tool_accuracy": sum(r.tool_match for r in valid) / len(valid) if valid else 0.0,
                "action_accuracy": sum(r.action_match for r in valid) / len(valid) if valid else 0.0,
                "mean_latency_ms": sum(r.latency_ms for r in items) / len(items),
            }
        return out

    def per_difficulty(self) -> dict[str, dict]:
        difficulties: dict[str, list[EvalResult]] = {}
        for r in self.results:
            difficulties.setdefault(r.difficulty, []).append(r)
        out = {}
        for diff, items in difficulties.items():
            valid = [r for r in items if not r.parse_failed]
            out[diff] = {
                "count": len(items),
                "tool_accuracy": sum(r.tool_match for r in valid) / len(valid) if valid else 0.0,
                "action_accuracy": sum(r.action_match for r in valid) / len(valid) if valid else 0.0,
            }
        return out

    def failures(self) -> list[EvalResult]:
        return [r for r in self.results if not r.action_match or r.parse_failed]

    def to_dict(self) -> dict:
        return {
            "ablation_label": self.ablation_label,
            "model": self.model,
            "dataset": self.dataset_path,
            "context_window": self.context_window,
            "confidence_threshold": self.confidence_threshold,
            "summary": {
                "total": len(self.results),
                "tool_accuracy": round(self.tool_accuracy(), 4),
                "action_accuracy": round(self.action_accuracy(), 4),
                "parse_failure_rate": round(self.parse_failure_rate(), 4),
                "hallucination_rate": round(self.hallucination_rate(), 4),
                "mean_latency_ms": round(self.mean_latency_ms(), 1),
                "p95_latency_ms": round(self.p95_latency_ms(), 1),
            },
            "per_category": self.per_category(),
            "per_difficulty": self.per_difficulty(),
            "results": [
                {
                    "id": r.item_id,
                    "nl_input": r.nl_input,
                    "category": r.category,
                    "difficulty": r.difficulty,
                    "gt": f"{r.gt_tool}.{r.gt_action}",
                    "pred": f"{r.pred_tool}.{r.pred_action}",
                    "tool_match": r.tool_match,
                    "action_match": r.action_match,
                    "parse_failed": r.parse_failed,
                    "hallucinated": r.hallucinated,
                    "confidence": round(r.pred_confidence, 3),
                    "latency_ms": round(r.latency_ms, 1),
                    "error": r.error,
                }
                for r in self.results
            ],
        }


def build_eval_result(
    item,
    parsed,
    latency_ms: float,
    parse_failed: bool,
    error: str | None,
) -> EvalResult:
    gt = item.ground_truth

    if parse_failed or parsed is None:
        return EvalResult(
            item_id=item.id, nl_input=item.nl_input,
            category=item.category, difficulty=item.difficulty,
            is_chain=item.is_chain,
            gt_tool=gt["tool"], gt_action=gt["action"],
            pred_tool="(parse_error)", pred_action="(parse_error)",
            pred_confidence=0.0, is_chain_response=False, chain_step_count=0,
            tool_match=False, action_match=False,
            parse_failed=True, hallucinated=False,
            latency_ms=latency_ms, error=error,
        )

    if isinstance(parsed, MCPChain):
        # For chain responses, evaluate first step against ground truth
        first = parsed.steps[0] if parsed.steps else None
        pred_tool = first.tool if first else "unknown"
        pred_action = first.action if first else "unknown"
        pred_conf = first.confidence if first else 0.0
        is_chain_resp = True
        step_count = len(parsed.steps)
    else:
        pred_tool = parsed.tool
        pred_action = parsed.action
        pred_conf = parsed.confidence
        is_chain_resp = False
        step_count = 0

    tool_match = pred_tool == gt["tool"]
    action_match = tool_match and pred_action == gt["action"]
    hallucinated = pred_tool not in _KNOWN_TOOLS and pred_tool != "unknown"

    return EvalResult(
        item_id=item.id, nl_input=item.nl_input,
        category=item.category, difficulty=item.difficulty,
        is_chain=item.is_chain,
        gt_tool=gt["tool"], gt_action=gt["action"],
        pred_tool=pred_tool, pred_action=pred_action,
        pred_confidence=pred_conf,
        is_chain_response=is_chain_resp, chain_step_count=step_count,
        tool_match=tool_match, action_match=action_match,
        parse_failed=False, hallucinated=hallucinated,
        latency_ms=latency_ms, error=error,
    )
