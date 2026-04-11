from __future__ import annotations
import functools
import json

# Default tool registry summary used before real registry is available.
# Overwritten at runtime by ToolRegistry.generate_summary().
_DEFAULT_TOOL_SUMMARY = """\
Tool: FileHandler
  Read, write, list, search, and delete files within sandboxed paths.
  Actions:
    - list: List files and directories in a folder (not recursive file search). Use when the request asks what is IN a specific directory. Params: path (str)
    - search: Find files recursively by name pattern. Use when the request asks to FIND, SEARCH, or LOOK FOR files. Params: pattern (str, glob), path (str, optional root)
    - read: Read and display the full text contents of a specific file. Params: path (str)
    - write: Write or overwrite a file with new content. DESTRUCTIVE. Params: path (str), content (str)
    - delete: Delete a file permanently. DESTRUCTIVE. Params: path (str)

Tool: GitTool
  Git repository operations.
  Actions:
    - status: Show high-level summary of staged/unstaged changes (like 'git status'). Use when user asks about current state, modified files, or what branch they're on.
    - diff: Show line-level diff of changes. Use when the user asks WHAT CHANGED, what the differences are, or what is STAGED. Params: staged (bool, optional)
    - log: Show recent commit history. Params: n (int, default 10)
    - add: Stage files for commit. Params: path (str)
    - commit: Commit staged changes. DESTRUCTIVE. Params: message (str)
    - branch_list: List all branches.
    - branch_switch: Switch to a branch. DESTRUCTIVE. Params: branch (str)

Tool: SystemTool
  System resource monitoring and process management.
  Actions:
    - cpu_stats: CPU usage percentage and core count. Use ONLY for CPU/processor questions.
    - ram_stats: RAM/memory usage: total, used, available. Use for MEMORY or RAM questions.
    - disk_stats: Disk/storage usage per partition. Use for DISK or STORAGE questions.
    - list_processes: List top N running processes by CPU. Use for PROCESS or PROGRAM questions. Params: n (int, default 15)
    - kill_process: Terminate a process. ALWAYS CONFIRM. Params: pid (int) or name (str)
    - env_info: System environment: OS, hostname, Python version, UPTIME. Use for UPTIME, SYSTEM INFO, or HOSTNAME questions.

Tool: TestRunner
  Detect and run test suites; explain failures.
  Actions:
    - detect: Probe the project to IDENTIFY which test framework is configured (pytest or jest). Use only when the user asks WHAT framework is in use, not when they want to run tests.
    - run: EXECUTE the full test suite. Use when the user says 'run tests', 'test', or 'execute tests'. Params: cwd (str, optional)
    - run_file: EXECUTE a specific test file. Use when the user names a specific test file or says 'only'. Params: path (str) or file (str), cwd (str, optional)
    - explain_failures: Send test failure output to the LLM for a plain-English explanation. Use after a failed run. Params: output (str)"""

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

ACTION DISAMBIGUATION - use this table to pick the correct action:
| User says (or implies)                                  | Tool        | Action         |
| "list", "show contents of", "what's in [folder]"        | FileHandler | list           |
| "find", "search for", "look for", "grep", "locate"      | FileHandler | search         |
| "read", "show me", "display contents of [file]"         | FileHandler | read           |
| "delete", "remove", "erase"                             | FileHandler | delete         |
| "write", "create file", "save to", "append"             | FileHandler | write          |
| "what changed", "changes since", "line-level diff"      | GitTool     | diff           |
| "what's staged", "staged changes", "ready to commit"    | GitTool     | diff           |
| "git status", "current state", "modified files"         | GitTool     | status         |
| "run tests", "execute tests", "test suite"              | TestRunner  | run            |
| "run this test file", "run only", "specific test"       | TestRunner  | run_file       |
| "what framework", "detect framework", "which test tool" | TestRunner  | detect         |
| "CPU usage", "processor"                                | SystemTool  | cpu_stats      |
| "RAM", "memory", "how much memory"                      | SystemTool  | ram_stats      |
| "disk", "storage", "free space"                         | SystemTool  | disk_stats     |
| "processes", "running programs", "top processes"        | SystemTool  | list_processes |
| "uptime", "how long running", "system info", "hostname" | SystemTool  | env_info       |
| "kill", "terminate process"                             | SystemTool  | kill_process   |

AVAILABLE TOOLS:
{tool_summary}

IMPORTANT PARAM CONVENTIONS:
- File paths: use "path" key. Relative paths are resolved from the active workspace root.
- Git working directory: use "cwd" key (defaults to the active workspace root if omitted).
- Process operations: use "pid" (integer) or "name" (string) key.
- Test operations: use "cwd" for the directory containing tests.
- Search: use "pattern" for glob or regex patterns.

EXAMPLES (follow these exactly):
User: "find all python files" -> {{"tool": "FileHandler", "action": "search", "params": {{"pattern": "*.py"}}, "confidence": 0.97}}
User: "list files in mcp_assistant/" -> {{"tool": "FileHandler", "action": "list", "params": {{"path": "mcp_assistant/"}}, "confidence": 0.97}}
User: "run the tests" -> {{"tool": "TestRunner", "action": "run", "params": {{}}, "confidence": 0.97}}
User: "what test framework is this" -> {{"tool": "TestRunner", "action": "detect", "params": {{}}, "confidence": 0.97}}
User: "show staged changes" -> {{"tool": "GitTool", "action": "diff", "params": {{"staged": true}}, "confidence": 0.95}}
User: "how much memory is free" -> {{"tool": "SystemTool", "action": "ram_stats", "params": {{}}, "confidence": 0.97}}
"""


class PromptBuilder:
    def __init__(self, tool_summary: str = _DEFAULT_TOOL_SUMMARY) -> None:
        self._tool_summary = tool_summary

    def update_tool_summary(self, summary: str) -> None:
        self._tool_summary = summary
        type(self).system_prompt.cache_clear()

    @functools.lru_cache(maxsize=1)
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

    def orchestrator_classify_system_prompt(self) -> str:
        return (
            "You are a classifier that decides how to handle user requests. "
            "Choose 'direct' mode for: greetings (hi, hello), general questions, explanations, conversations, or anything answerable from general knowledge. "
            "Choose 'mcp' mode ONLY for: file operations, git commands, system monitoring, running tests, or anything requiring access to local files/state. "
            "Default to 'direct' for conversational requests. Use 'mcp' only when explicitly needed."
        )

    def orchestrator_classify_prompt(
        self,
        nl_input: str,
        context: list[dict] | None = None,
    ) -> str:
        parts: list[str] = [f"USER REQUEST: {nl_input}"]
        if context:
            parts.append("RECENT CONTEXT:")
            for turn in context[-4:]:
                parts.append(f"- {turn.get('role', 'user')}: {turn.get('content', '')[:200]}")
        parts.append("AVAILABLE TOOLS:")
        parts.append(self._tool_summary)
        parts.append(
            "Return JSON with intent, difficulty, mode_hint, confidence, and reasoning."
        )
        return "\n".join(parts)

    def orchestrator_plan_system_prompt(self) -> str:
        return (
            "You are a planner that creates execution strategies. "
            "For conversational requests (greetings, questions, explanations), always choose 'direct' mode. "
            "For file/git/system operations, choose 'mcp' mode. "
            "Prefer 'direct' for anything that doesn't require accessing local files or system state."
        )

    def orchestrator_plan_prompt(self, nl_input: str, classification: dict[str, object]) -> str:
        payload = json.dumps(classification, indent=2, sort_keys=True)
        return (
            f"USER REQUEST: {nl_input}\n\n"
            f"CLASSIFICATION:\n{payload}\n\n"
            "Return JSON with mode, objective, steps, specialist, and reasoning."
        )

    def direct_response_system_prompt(self) -> str:
        return (
            "You are a helpful AI assistant. "
            "Provide natural, conversational, and detailed responses to the user's questions. "
            "Be friendly, informative, and elaborate when appropriate. "
            "Do not claim to have inspected files, git history, tests, or system state unless it was provided in the context."
        )

    def direct_response_prompt(
        self,
        nl_input: str,
        plan: dict[str, object],
        context: list[dict] | None = None,
    ) -> str:
        parts = [f"USER: {nl_input}"]
        # Keep greetings isolated so stale workspace/tool errors do not bleed into
        # simple conversational turns like "hi" or "hello".
        if context and not _is_simple_greeting(nl_input):
            parts.append("\nCONVERSATION HISTORY:")
            for turn in context[-4:]:
                role = turn.get('role', 'user').upper()
                content = turn.get('content', '')[:300]
                parts.append(f"{role}: {content}")
        parts.append("\nProvide a natural, conversational response. Return JSON with 'answer' (your full response) and 'confidence' (0.0-1.0).")
        return "\n".join(parts)

    def aggregator_system_prompt(self) -> str:
        return (
            "You are the aggregator node in a four-stage orchestrator. "
            "Convert intermediate orchestration data into a structured final response. "
            "Keep the summary concise, details concrete, and mention tools only when they were actually used."
        )

    def aggregator_prompt(
        self,
        user_message: str,
        mode: str,
        workflow: list[str],
        planner_notes: str,
        specialist_notes: dict[str, str],
        tool_calls: list[dict],
        source_text: str,
        status: str = "success",
    ) -> str:
        return (
            f"USER REQUEST: {user_message}\n"
            f"MODE: {mode}\n"
            f"STATUS: {status}\n"
            f"WORKFLOW: {json.dumps(workflow)}\n"
            f"PLANNER NOTES: {planner_notes}\n"
            f"SPECIALIST NOTES: {json.dumps(specialist_notes, sort_keys=True)}\n"
            f"TOOL CALLS: {json.dumps(tool_calls, sort_keys=True)}\n"
            f"SOURCE TEXT:\n{source_text}\n\n"
            "Return JSON with status, mode, summary, details, tools_used, workflow, and next_step."
        )


def _is_simple_greeting(text: str) -> bool:
    normalized = " ".join(text.lower().strip().split())
    return normalized in {
        "hi",
        "hello",
        "hey",
        "yo",
        "hiya",
        "good morning",
        "good afternoon",
        "good evening",
    }
