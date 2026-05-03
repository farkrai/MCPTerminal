"""Hallucination guard for FastMCP tool calls.

Detects when the LLM returns a tool name that doesn't exist in the registry
and either auto-corrects it (if a close match is found) or flags it for user
review. Tracks hallucination metrics across the session.
"""
from __future__ import annotations
import difflib
import threading
from dataclasses import dataclass, field

from mcp_assistant.server.schema import ToolCall, ToolChain


@dataclass
class HallucinationReport:
    original_tool: str
    suggested_tool: str | None
    similarity: float
    auto_corrected: bool


@dataclass
class GuardStats:
    total_calls: int = 0
    hallucinated: int = 0
    auto_corrected: int = 0
    rejected: int = 0

    @property
    def hallucination_rate(self) -> float:
        return self.hallucinated / self.total_calls if self.total_calls else 0.0


class HallucinationGuard:
    """Validates and fuzzy-corrects FastMCP tool names from LLM output.

    Strategy
    --------
    1. Exact match → OK.
    2. Case-insensitive match → auto-correct + log.
    3. Edit-distance close match (≥ 0.75 similarity) → auto-correct + log.
    4. Old-format names (e.g. 'FileHandler.read' → 'file_read') → auto-convert.
    5. No match → flag for user; can optionally raise or return report.
    """

    # Mapping from old MCP format to new FastMCP tool names
    _LEGACY_MAP: dict[str, str] = {
        # FileHandler
        "FileHandler.read":    "file_read",
        "FileHandler.write":   "file_write",
        "FileHandler.list":    "file_list",
        "FileHandler.search":  "file_search",
        "FileHandler.delete":  "file_delete",
        # GitTool
        "GitTool.status":        "git_status",
        "GitTool.diff":          "git_diff",
        "GitTool.log":           "git_log",
        "GitTool.add":           "git_add",
        "GitTool.commit":        "git_commit",
        "GitTool.branch_list":   "git_branch_list",
        "GitTool.branch_switch": "git_branch_switch",
        # SystemTool
        "SystemTool.cpu_stats":      "system_cpu_stats",
        "SystemTool.ram_stats":      "system_ram_stats",
        "SystemTool.disk_stats":     "system_disk_stats",
        "SystemTool.list_processes": "system_list_processes",
        "SystemTool.kill_process":   "system_kill_process",
        "SystemTool.env_info":       "system_env_info",
        # TestRunner
        "TestRunner.detect":           "test_detect",
        "TestRunner.run":              "test_run",
        "TestRunner.run_file":         "test_run_file",
        "TestRunner.explain_failures": "test_explain_failures",
        # NetworkTool
        "NetworkTool.ping":       "network_ping",
        "NetworkTool.dns_lookup": "network_dns_lookup",
        "NetworkTool.http_probe": "network_http_probe",
        "NetworkTool.port_check": "network_port_check",
    }

    def __init__(self, known_tools: set[str], auto_correct: bool = True) -> None:
        self._known = set(known_tools)
        self._known_lower = {t.lower(): t for t in known_tools}
        self._auto_correct = auto_correct
        self._stats = GuardStats()
        self._lock = threading.Lock()
        self._history: list[HallucinationReport] = []

    def update_known_tools(self, tools: set[str]) -> None:
        self._known = set(tools)
        self._known_lower = {t.lower(): t for t in tools}

    def validate(self, call: ToolCall) -> tuple[ToolCall, HallucinationReport | None]:
        """Validate *call* and optionally auto-correct the tool name.

        Returns (corrected_call, report_or_None).
        report is None if the tool was valid; non-None if it was hallucinated.
        """
        with self._lock:
            self._stats.total_calls += 1

        tool = call.tool

        # 1. Exact match — clean
        if tool in self._known:
            return call, None

        # 2. Legacy dot-notation format (FileHandler.read → file_read)
        if tool in self._LEGACY_MAP:
            corrected = self._LEGACY_MAP[tool]
            return self._correct(call, corrected, 1.0, True)

        # 3. Case-insensitive match
        if tool.lower() in self._known_lower:
            corrected = self._known_lower[tool.lower()]
            return self._correct(call, corrected, 0.95, True)

        # 4. Fuzzy match via SequenceMatcher
        matches = difflib.get_close_matches(tool, self._known, n=1, cutoff=0.65)
        if matches:
            sim = difflib.SequenceMatcher(None, tool, matches[0]).ratio()
            return self._correct(call, matches[0], sim, self._auto_correct)

        # 5. No match — genuine hallucination
        report = HallucinationReport(
            original_tool=tool,
            suggested_tool=None,
            similarity=0.0,
            auto_corrected=False,
        )
        with self._lock:
            self._stats.hallucinated += 1
            self._stats.rejected += 1
            self._history.append(report)
        return call, report

    def validate_chain(
        self, chain: ToolChain
    ) -> tuple[ToolChain, list[HallucinationReport]]:
        """Validate every step in a chain.  Returns corrected chain + any reports."""
        from mcp_assistant.server.schema import ToolCall, ToolChainStep
        reports: list[HallucinationReport] = []
        corrected_steps = []
        for step in chain.steps:
            dummy = ToolCall(tool=step.tool, params=step.params, confidence=step.confidence)
            corrected_dummy, report = self.validate(dummy)
            if report:
                reports.append(report)
            corrected_steps.append(
                ToolChainStep(tool=corrected_dummy.tool, params=corrected_dummy.params, confidence=corrected_dummy.confidence)
            )
        from mcp_assistant.server.schema import ToolChain as TC
        return TC(steps=corrected_steps, description=chain.description,
                  continue_on_error=chain.continue_on_error), reports

    def stats(self) -> GuardStats:
        with self._lock:
            return GuardStats(
                total_calls=self._stats.total_calls,
                hallucinated=self._stats.hallucinated,
                auto_corrected=self._stats.auto_corrected,
                rejected=self._stats.rejected,
            )

    def history(self) -> list[HallucinationReport]:
        with self._lock:
            return list(self._history)

    # ── Private ────────────────────────────────────────────────────────────────

    def _correct(
        self, call: ToolCall, corrected: str, sim: float, auto: bool
    ) -> tuple[ToolCall, HallucinationReport]:
        report = HallucinationReport(
            original_tool=call.tool,
            suggested_tool=corrected,
            similarity=sim,
            auto_corrected=auto,
        )
        with self._lock:
            self._stats.hallucinated += 1
            if auto:
                self._stats.auto_corrected += 1
            else:
                self._stats.rejected += 1
            self._history.append(report)

        if auto:
            return ToolCall(tool=corrected, params=call.params,
                            confidence=call.confidence * sim,
                            raw_response=call.raw_response), report
        return call, report
