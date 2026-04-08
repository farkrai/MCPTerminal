from __future__ import annotations
import subprocess
import time
from pathlib import Path
from mcp_assistant.mcp.base import MCPTool
from mcp_assistant.mcp.schema import MCPCall, MCPResult
from mcp_assistant import config

# Pytest exit codes
_PYTEST_EXIT = {0: "passed", 1: "failures", 2: "error", 3: "interrupted", 4: "no tests", 5: "no tests collected"}


class TestRunner(MCPTool):
    TOOL_NAME = "TestRunner"
    TOOL_DESCRIPTION = "Detect and run test suites (pytest/jest). Explain failures via LLM."
    SUPPORTED_ACTIONS = {
        "detect":          "Detect test framework in a directory. Params: cwd (optional)",
        "run":             "Run the detected test suite. Params: cwd (optional)",
        "run_file":        "Run a specific test file. Params: path",
        "explain_failures":"Send failure output to LLM for explanation. Params: output (test output string)",
    }

    def __init__(self, llm_client=None) -> None:
        self._llm = llm_client  # injected in Phase 4; optional for Phase 2

    def execute(self, call: MCPCall) -> MCPResult:
        start = time.perf_counter()
        action = call.action
        cwd = self._resolve_cwd(call.params.get("cwd"))
        try:
            if action == "detect":
                out, data = self._detect(cwd)
            elif action == "run":
                out, data = self._run(cwd)
            elif action == "run_file":
                path = call.params.get("path", "")
                if not path:
                    return self._err(call, "'path' param required for run_file", _ms(start))
                out, data = self._run_file(Path(path))
            elif action == "explain_failures":
                test_output = call.params.get("output", "")
                if not test_output:
                    return self._err(call, "'output' param required for explain_failures", _ms(start))
                out, data = self._explain(test_output)
            else:
                return self._err(call, f"Unknown action: {action}", _ms(start))
        except Exception as e:
            return self._err(call, str(e), _ms(start))

        return self._ok(call, out, data, _ms(start))

    # ── Private actions ───────────────────────────────────────────────────────

    def _detect(self, cwd: Path) -> tuple[str, dict]:
        frameworks: list[str] = []
        details: dict = {}

        # pytest
        for marker in ["pytest.ini", "setup.cfg", "pyproject.toml", "conftest.py"]:
            if (cwd / marker).exists():
                frameworks.append("pytest")
                details["pytest_marker"] = marker
                break

        # jest
        jest_found = False
        for marker in ["jest.config.js", "jest.config.ts", "jest.config.json"]:
            if (cwd / marker).exists():
                frameworks.append("jest")
                details["jest_config"] = marker
                jest_found = True
                break
        if not jest_found and (cwd / "package.json").exists():
            pkg = (cwd / "package.json").read_text()
            if '"jest"' in pkg:
                frameworks.append("jest")
                details["jest_marker"] = "package.json"

        if frameworks:
            return f"Detected test frameworks: {', '.join(frameworks)}", {"frameworks": frameworks, **details}
        return "No test framework detected in this directory.", {"frameworks": []}

    def _run(self, cwd: Path) -> tuple[str, dict]:
        framework, _ = self._detect(cwd)

        if "pytest" in framework:
            return self._run_pytest(cwd, [])
        if "jest" in framework:
            return self._run_jest(cwd)
        raise RuntimeError("No supported test framework found. Run 'detect' first.")

    def _run_file(self, path: Path) -> tuple[str, dict]:
        if not path.is_absolute():
            path = config.PROJECT_ROOT / path
        return self._run_pytest(path.parent, [str(path)])

    def _run_pytest(self, cwd: Path, extra_args: list[str]) -> tuple[str, dict]:
        cmd = ["python", "-m", "pytest", "--tb=short", "-q"] + extra_args
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        combined = result.stdout + result.stderr
        status = _PYTEST_EXIT.get(result.returncode, f"code {result.returncode}")
        summary = f"pytest {status} (exit {result.returncode})\n\n{combined[:3000]}"
        return summary, {"framework": "pytest", "exit_code": result.returncode, "status": status, "output": combined}

    def _run_jest(self, cwd: Path) -> tuple[str, dict]:
        cmd = ["npx", "jest", "--no-coverage"]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        combined = result.stdout + result.stderr
        status = "passed" if result.returncode == 0 else "failures"
        summary = f"jest {status} (exit {result.returncode})\n\n{combined[:3000]}"
        return summary, {"framework": "jest", "exit_code": result.returncode, "status": status, "output": combined}

    def _explain(self, test_output: str) -> tuple[str, str]:
        if self._llm is None:
            return (
                "LLM not connected — cannot explain failures.\n"
                "Failure output:\n" + test_output[:1000],
                test_output,
            )
        from mcp_assistant.llm.prompt_builder import PromptBuilder
        prompt = PromptBuilder().explain_failures_prompt(test_output)
        explanation = self._llm.generate(prompt, temperature=0.7)
        return explanation, explanation

    def _resolve_cwd(self, cwd: str | None) -> Path:
        if cwd:
            p = Path(cwd)
            return p if p.is_absolute() else config.PROJECT_ROOT / p
        return config.PROJECT_ROOT


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)
