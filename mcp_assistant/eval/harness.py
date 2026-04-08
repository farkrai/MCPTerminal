from __future__ import annotations
import sys
import time
from pathlib import Path
from mcp_assistant import config
from mcp_assistant.eval.dataset import load_dataset, EvalItem
from mcp_assistant.eval.metrics import EvalReport, EvalResult, build_eval_result
from mcp_assistant.eval.report import generate_report
from mcp_assistant.llm.client import OllamaClient
from mcp_assistant.llm.prompt_builder import PromptBuilder
from mcp_assistant.llm.response_parser import parse_response, ParseError


class EvalHarness:
    def __init__(
        self,
        dataset_path: Path,
        context_window: int = 0,
        confidence_threshold: float = 0.5,
        ablation_label: str = "default",
        verbose: bool = False,
    ) -> None:
        self._dataset = load_dataset(dataset_path)
        self._dataset_path = str(dataset_path)
        self._context_window = context_window
        self._confidence_threshold = confidence_threshold
        self._ablation_label = ablation_label
        self._verbose = verbose

        self._client = OllamaClient()
        self._builder = PromptBuilder()
        self._system = self._builder.system_prompt()

    def run_all(self) -> EvalReport:
        results: list[EvalResult] = []
        context: list[dict] = []
        total = len(self._dataset)

        print(f"\n[eval] Ablation: '{self._ablation_label}'  "
              f"context={self._context_window}  "
              f"conf_thresh={self._confidence_threshold}  "
              f"n={total}")
        print(f"[eval] Model: {self._client.model}")
        print("-" * 60)

        for i, item in enumerate(self._dataset, 1):
            result = self._run_single(item, context)
            results.append(result)

            # Rolling context (only if context_window > 0)
            if self._context_window > 0:
                context.append({"role": "user", "content": item.nl_input})
                context.append({"role": "assistant", "content": f"{result.pred_tool}.{result.pred_action}"})
                if len(context) > self._context_window * 2:
                    context = context[-(self._context_window * 2):]

            # Progress
            status = "✓" if result.action_match else ("P" if result.parse_failed else "✗")
            if self._verbose or not result.action_match:
                gt = f"{result.gt_tool}.{result.gt_action}"
                pred = f"{result.pred_tool}.{result.pred_action}"
                match_str = f"{gt}" if result.action_match else f"{gt} ← got {pred}"
                print(f"  [{i:>2}/{total}] {status}  {item.difficulty:<6}  {match_str}  ({result.latency_ms:.0f}ms)")
            else:
                print(f"  [{i:>2}/{total}] {status}  {item.difficulty:<6}  {result.gt_tool}.{result.gt_action}  ({result.latency_ms:.0f}ms)")

        report = EvalReport(
            results=results,
            model=self._client.model,
            dataset_path=self._dataset_path,
            context_window=self._context_window,
            confidence_threshold=self._confidence_threshold,
            ablation_label=self._ablation_label,
        )

        print("-" * 60)
        print(f"[eval] Tool Accuracy  : {report.tool_accuracy():.1%}")
        print(f"[eval] Action Accuracy: {report.action_accuracy():.1%}")
        print(f"[eval] Parse Failures : {report.parse_failure_rate():.1%}")
        print(f"[eval] Hallucinations : {report.hallucination_rate():.1%}")
        print(f"[eval] Mean Latency   : {report.mean_latency_ms():.0f} ms")
        print(f"[eval] P95 Latency    : {report.p95_latency_ms():.0f} ms")

        return report

    def _run_single(self, item: EvalItem, context: list[dict]) -> EvalResult:
        ctx = context[-(self._context_window * 2):] if self._context_window > 0 else []
        prompt = self._builder.user_prompt(item.nl_input, ctx)

        start = time.perf_counter()
        parsed = None
        error = None

        for attempt in range(config.MAX_PARSE_RETRIES + 1):
            try:
                p = prompt if attempt == 0 else prompt + "\n\nREMINDER: Respond ONLY with valid JSON."
                raw = self._client.generate(p, system=self._system)
                parsed = parse_response(raw)
                break
            except ParseError as e:
                error = str(e)
                if attempt == config.MAX_PARSE_RETRIES:
                    latency = (time.perf_counter() - start) * 1000
                    return build_eval_result(item, None, latency, parse_failed=True, error=error)
            except Exception as e:
                error = str(e)
                latency = (time.perf_counter() - start) * 1000
                return build_eval_result(item, None, latency, parse_failed=True, error=error)

        latency = (time.perf_counter() - start) * 1000
        return build_eval_result(item, parsed, latency, parse_failed=False, error=None)


def run_ablation_study(
    dataset_path: Path,
    output_dir: Path,
    verbose: bool = False,
) -> list[EvalReport]:
    """
    Run 4 ablation conditions and save a report for each.
    Returns all EvalReport objects.
    """
    conditions = [
        {"context_window": 0,  "confidence_threshold": 1.0, "label": "no_context_no_conf_gate"},
        {"context_window": 5,  "confidence_threshold": 1.0, "label": "ctx5_no_conf_gate"},
        {"context_window": 10, "confidence_threshold": 1.0, "label": "ctx10_no_conf_gate"},
        {"context_window": 10, "confidence_threshold": 0.5, "label": "ctx10_with_conf_gate"},
    ]

    reports = []
    for cond in conditions:
        harness = EvalHarness(
            dataset_path=dataset_path,
            context_window=cond["context_window"],
            confidence_threshold=cond["confidence_threshold"],
            ablation_label=cond["label"],
            verbose=verbose,
        )
        report = harness.run_all()
        json_p, md_p = generate_report(report, output_dir)
        print(f"  Saved: {md_p.name}")
        reports.append(report)

    _print_ablation_summary(reports)
    return reports


def _print_ablation_summary(reports: list[EvalReport]) -> None:
    print("\n" + "=" * 70)
    print("ABLATION SUMMARY")
    print("=" * 70)
    print(f"{'Label':<35} {'Tool%':>6} {'Action%':>8} {'Hal%':>6} {'MeanMs':>8}")
    print("-" * 70)
    for r in reports:
        print(
            f"{r.ablation_label:<35} "
            f"{r.tool_accuracy():>6.1%} "
            f"{r.action_accuracy():>8.1%} "
            f"{r.hallucination_rate():>6.1%} "
            f"{r.mean_latency_ms():>8.0f}"
        )
    print("=" * 70)


def cli_main(args: list[str] | None = None) -> None:
    import argparse
    parser = argparse.ArgumentParser(description="MCP Assistant Evaluation Harness")
    parser.add_argument("--dataset", type=Path,
                        default=config.PROJECT_ROOT / "eval_data" / "eval_dataset.json")
    parser.add_argument("--output", type=Path,
                        default=config.PROJECT_ROOT / "eval_results")
    parser.add_argument("--ablation", action="store_true",
                        help="Run all 4 ablation conditions")
    parser.add_argument("--context", type=int, default=0,
                        help="Context window size (turns)")
    parser.add_argument("--label", type=str, default="single_run")
    parser.add_argument("--verbose", action="store_true")
    ns = parser.parse_args(args)

    if ns.ablation:
        run_ablation_study(ns.dataset, ns.output, verbose=ns.verbose)
    else:
        harness = EvalHarness(
            dataset_path=ns.dataset,
            context_window=ns.context,
            ablation_label=ns.label,
            verbose=ns.verbose,
        )
        report = harness.run_all()
        json_p, md_p = generate_report(report, ns.output)
        print(f"\nReport saved: {md_p}")
        print(f"JSON saved  : {json_p}")


if __name__ == "__main__":
    cli_main()
