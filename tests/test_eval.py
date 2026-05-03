import json
import pytest
from pathlib import Path
from mcp_assistant.eval.dataset import load_dataset, EvalItem
from mcp_assistant.eval.metrics import EvalReport, EvalResult, build_eval_result
from mcp_assistant.eval.report import generate_report
from mcp_assistant.server.schema import ToolCall, ToolChain, ToolChainStep
from mcp_assistant import config

DATASET_PATH = config.PROJECT_ROOT / "eval_data" / "eval_dataset.json"


# ── Dataset ───────────────────────────────────────────────────────────────────

def test_dataset_loads():
    items = load_dataset(DATASET_PATH)
    assert len(items) == 60


def test_dataset_categories():
    items = load_dataset(DATASET_PATH)
    cats = {i.category for i in items}
    assert "file_ops" in cats
    assert "git_ops" in cats
    assert "system_ops" in cats
    assert "test_ops" in cats
    assert "chaining" in cats


def test_dataset_difficulties():
    items = load_dataset(DATASET_PATH)
    diffs = {i.difficulty for i in items}
    assert {"easy", "medium", "hard"} == diffs


def test_dataset_chain_items():
    items = load_dataset(DATASET_PATH)
    chains = [i for i in items if i.is_chain]
    assert len(chains) == 5
    for c in chains:
        assert len(c.chain_steps) >= 2


def test_dataset_counts_per_category():
    items = load_dataset(DATASET_PATH)
    counts = {}
    for i in items:
        counts[i.category] = counts.get(i.category, 0) + 1
    assert counts["file_ops"] == 15
    assert counts["git_ops"] == 15
    assert counts["system_ops"] == 15
    assert counts["test_ops"] == 10
    assert counts["chaining"] == 5


# ── Metrics ───────────────────────────────────────────────────────────────────

def _make_item(id=1, gt_tool="file_list", gt_action="", category="file_ops", difficulty="easy"):
    return EvalItem(
        id=id, nl_input="test", ground_truth={"tool": gt_tool, "action": gt_action, "params": {}},
        category=category, difficulty=difficulty,
    )


def _make_call(tool="file_list", conf=0.9):
    return ToolCall(tool=tool, params={}, confidence=conf)


def test_build_eval_result_correct():
    item = _make_item()
    call = _make_call("file_list")
    result = build_eval_result(item, call, latency_ms=500, parse_failed=False, error=None)
    assert result.tool_match
    assert result.action_match
    assert not result.parse_failed
    assert not result.hallucinated


def test_build_eval_result_wrong_tool():
    item = _make_item(gt_tool="file_list")
    call = _make_call("git_status")
    result = build_eval_result(item, call, latency_ms=500, parse_failed=False, error=None)
    assert not result.tool_match
    assert not result.action_match


def test_build_eval_result_parse_failed():
    item = _make_item()
    result = build_eval_result(item, None, latency_ms=100, parse_failed=True, error="bad json")
    assert result.parse_failed
    assert not result.tool_match
    assert result.error == "bad json"


def test_build_eval_result_hallucination():
    item = _make_item()
    call = _make_call(tool="GhostTool_xyz")
    result = build_eval_result(item, call, latency_ms=200, parse_failed=False, error=None)
    assert result.hallucinated


def test_build_eval_result_chain():
    item = _make_item(gt_tool="git_status")
    chain = ToolChain(steps=[
        ToolChainStep(tool="git_status", params={}, confidence=0.9),
        ToolChainStep(tool="git_diff",   params={}, confidence=0.88),
    ])
    result = build_eval_result(item, chain, latency_ms=800, parse_failed=False, error=None)
    assert result.is_chain_response
    assert result.chain_step_count == 2
    assert result.tool_match   # first step matches gt


# ── EvalReport ────────────────────────────────────────────────────────────────

def _make_report(results):
    return EvalReport(
        results=results, model="phi3:latest",
        dataset_path="test", context_window=0,
        confidence_threshold=0.5, ablation_label="test",
    )


def test_report_tool_accuracy():
    item = _make_item()
    r1 = build_eval_result(item, _make_call("file_list"), 100, False, None)
    r2 = build_eval_result(item, _make_call("git_status"), 100, False, None)
    report = _make_report([r1, r2])
    assert report.tool_accuracy() == pytest.approx(0.5)


def test_report_action_accuracy_full_match():
    item = _make_item()
    results = [build_eval_result(item, _make_call("file_list"), 100, False, None) for _ in range(4)]
    report = _make_report(results)
    assert report.action_accuracy() == pytest.approx(1.0)


def test_report_parse_failure_rate():
    item = _make_item()
    r_ok = build_eval_result(item, _make_call(), 100, False, None)
    r_fail = build_eval_result(item, None, 100, True, "err")
    report = _make_report([r_ok, r_fail])
    assert report.parse_failure_rate() == pytest.approx(0.5)


def test_report_hallucination_rate():
    item = _make_item()
    r_ok = build_eval_result(item, _make_call("file_list"), 100, False, None)
    r_hal = build_eval_result(item, _make_call("GhostTool_xyz"), 100, False, None)
    report = _make_report([r_ok, r_hal])
    assert report.hallucination_rate() == pytest.approx(0.5)


def test_report_latency():
    item = _make_item()
    results = [build_eval_result(item, _make_call(), ms, False, None) for ms in [100, 200, 300, 400, 500]]
    report = _make_report(results)
    assert report.mean_latency_ms() == pytest.approx(300.0)


def test_report_per_category():
    items = [
        _make_item(id=1, gt_tool="file_list", category="file_ops"),
        _make_item(id=2, gt_tool="git_status", category="git_ops"),
    ]
    results = [
        build_eval_result(items[0], _make_call("file_list"),  100, False, None),
        build_eval_result(items[1], _make_call("git_status"), 200, False, None),
    ]
    report = _make_report(results)
    cats = report.per_category()
    assert "file_ops" in cats
    assert "git_ops" in cats
    assert cats["file_ops"]["tool_accuracy"] == 1.0


def test_report_to_dict_structure():
    item = _make_item()
    results = [build_eval_result(item, _make_call(), 100, False, None)]
    report = _make_report(results)
    d = report.to_dict()
    for key in ("model", "summary", "per_category", "per_difficulty", "results"):
        assert key in d
    assert d["summary"]["total"] == 1


# ── Report generation ─────────────────────────────────────────────────────────

def test_report_generates_files(tmp_path):
    item = _make_item()
    results = [build_eval_result(item, _make_call(), 150, False, None)]
    report = _make_report(results)
    report.ablation_label = "test_gen"
    json_p, md_p = generate_report(report, tmp_path)
    assert json_p.exists()
    assert md_p.exists()
    data = json.loads(json_p.read_text())
    assert data["summary"]["total"] == 1
    md = md_p.read_text()
    assert "Tool Accuracy" in md
    assert "Action Accuracy" in md
