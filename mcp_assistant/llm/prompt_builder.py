from __future__ import annotations
import json

# Default tool registry summary used before real registry is available.
# Overwritten at runtime by ToolRegistry.generate_summary().
_DEFAULT_TOOL_SUMMARY = """\
Tool: FileHandler
  Read, write, list, search, and delete files within sandboxed paths.
  Actions: read, write, list, search, delete

Tool: GitTool
  Git repository operations.
  Actions: status, diff, log, commit, branch_list, branch_switch, add

Tool: SystemTool
  System resource monitoring and process management.
  Actions: cpu_stats, ram_stats, disk_stats, list_processes, kill_process, env_info

Tool: TestRunner
  Detect and run test suites; explain failures.
  Actions: detect, run, run_file, explain_failures"""

_SYSTEM_PROMPT_TEMPLATE = """\
You are a terminal assistant that controls a set of tools via the Model Context Protocol (MCP).

RESPONSE FORMAT RULES — follow exactly:
1. Respond ONLY with a single valid JSON object. No prose, no explanation, no markdown.
2. The JSON must have exactly these keys:
   - "tool"       : string — one of the tool names listed below
   - "action"     : string — one of the supported actions for that tool
   - "params"     : object — key/value parameters for the action (can be empty {{}})
   - "confidence" : float  — your confidence from 0.0 to 1.0

3. If you cannot map the request to any tool, set "tool" to "unknown", "action" to "unknown",
   "params" to {{}}, and "confidence" below 0.4.

4. Use a CHAIN when the request explicitly asks for multiple sequential operations.
   Chain trigger words: "then", "after that", "first...then", "and also", "followed by".
   Example: "check git status then show the diff" → use chain with two GitTool steps.
   Example: "list files then read the largest one" → use chain with two FileHandler steps.
   For a chain, return this exact structure (no other keys at top level):
   {{
     "chain": true,
     "description": "one-line plan summary",
     "steps": [
       {{"tool": "ToolName", "action": "action_name", "params": {{}}, "confidence": 0.9}},
       {{"tool": "ToolName", "action": "action_name", "params": {{}}, "confidence": 0.9}}
     ]
   }}
   If NO chain trigger words are present, always return a single tool call (not a chain).

AVAILABLE TOOLS:
{tool_summary}

IMPORTANT PARAM CONVENTIONS:
- File paths: use "path" key. Relative paths are resolved from the project root.
- Git working directory: use "cwd" key (defaults to project root if omitted).
- Process operations: use "pid" (integer) or "name" (string) key.
- Test operations: use "cwd" for the directory containing tests.
- Search: use "pattern" for glob or regex patterns.
"""


class PromptBuilder:
    def __init__(self, tool_summary: str = _DEFAULT_TOOL_SUMMARY) -> None:
        self._tool_summary = tool_summary

    def update_tool_summary(self, summary: str) -> None:
        self._tool_summary = summary

    def system_prompt(self) -> str:
        return _SYSTEM_PROMPT_TEMPLATE.format(tool_summary=self._tool_summary)

    def user_prompt(
        self,
        nl_input: str,
        context: list[dict] | None = None,
    ) -> str:
        parts: list[str] = []

        if context:
            parts.append("=== CONVERSATION HISTORY (most recent last) ===")
            for turn in context:
                role = turn.get("role", "user").upper()
                content = turn.get("content", "")
                parts.append(f"[{role}] {content}")
            parts.append("=== END HISTORY ===\n")

        parts.append(f"USER REQUEST: {nl_input}")
        parts.append("\nRespond with JSON only.")
        return "\n".join(parts)

    def clarification_prompt(self, original_input: str, tool: str, action: str) -> str:
        return (
            f"I wasn't confident about your request: '{original_input}'\n"
            f"I interpreted it as: {tool}.{action}\n"
            "Could you rephrase or confirm? (or type 'yes' to proceed)"
        )

    def explain_failures_prompt(self, test_output: str) -> str:
        return (
            "The following test suite output contains failures. "
            "Explain each failure clearly and suggest a specific fix for each one. "
            "Be concise and practical.\n\n"
            f"TEST OUTPUT:\n{test_output}"
        )

    def summarize_git_diff_prompt(self, diff_output: str) -> str:
        return (
            "Summarize the following git diff in plain English. "
            "List the key changes made, grouped by file. Be concise.\n\n"
            f"GIT DIFF:\n{diff_output}"
        )
