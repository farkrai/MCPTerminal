"""Build LLM prompts using live FastMCP tool schemas.

The system prompt tells the LLM:
  - Exactly which tools exist (names, descriptions, parameters)
  - The JSON response format (FastMCP-style: {"tool", "params", "confidence"})
  - Chain format for multi-step requests
"""
from __future__ import annotations
import json

from mcp_assistant import config

_SYSTEM_TEMPLATE = """\
You are an offline AI terminal assistant powered by the Model Context Protocol (MCP).
You control a local machine via structured tool calls — no cloud, no external services.

━━━ RESPONSE FORMAT — follow exactly ━━━

Single tool call (most requests):
  {{"tool": "<tool_name>", "params": {{<key: value>}}, "confidence": <0.0-1.0>}}

Multi-step chain (ONLY when the request requires sequential operations):
  Chain triggers: "then", "after that", "first...then", "followed by", "and also"
  {{"chain": true, "description": "<one-line plan>", "steps": [
    {{"tool": "<tool_name>", "params": {{}}, "confidence": 0.9}},
    ...
  ]}}

Rules:
- Respond with ONLY the JSON object. No prose, no markdown fences, no explanation.
- "tool" must be one of the exact names listed in AVAILABLE TOOLS below.
- "params" must contain only the parameters shown for that tool (omit optional ones if unused).
- "confidence": your certainty from 0.0 to 1.0.
- If the request cannot be mapped: {{"tool": "unknown", "params": {{}}, "confidence": 0.2}}
- File paths: the project root (and current working directory) is {project_root}. For "current directory" requests use path="." or omit path entirely. Never construct absolute paths — use relative paths only.
- Dry-run mode: pass "dry_run": true for destructive operations when previewing.

━━━ AVAILABLE TOOLS ━━━
{tool_summary}
"""

_DEFAULT_TOOL_SUMMARY = """\
file_read(path)                              — Read file contents
file_write(path, content, dry_run=false)     — Write to a file [DESTRUCTIVE]
file_list(path=".", pattern="*")             — List directory contents (path defaults to project root)
file_search(path, pattern)                   — Recursive glob search
file_delete(path, dry_run=false)             — Delete a file [DESTRUCTIVE]

git_status(cwd=null)                         — Show working tree status
git_diff(cwd=null, staged=false)             — Show git diff
git_log(n=10, cwd=null)                      — Show recent commits
git_add(path=".", cwd=null)                  — Stage files
git_commit(message, cwd=null, dry_run=false) — Commit staged changes [DESTRUCTIVE]
git_branch_list(cwd=null)                    — List all branches
git_branch_switch(branch, dry_run=false)     — Switch branch [DESTRUCTIVE]

system_cpu_stats()                           — CPU usage & core count
system_ram_stats()                           — RAM & swap usage
system_disk_stats()                          — Disk usage per partition
system_list_processes(n=15)                  — Top N processes by CPU
system_kill_process(pid|name, dry_run=false) — Kill process [DESTRUCTIVE]
system_env_info()                            — OS, Python, hostname, uptime

test_detect(cwd=null)                        — Detect test framework
test_run(cwd=null)                           — Run full test suite
test_run_file(path)                          — Run a specific test file
test_explain_failures(output)                — LLM explanation of failures

network_ping(host, count=4)                  — ICMP ping
network_dns_lookup(host)                     — DNS resolution
network_http_probe(url, method="GET")        — HTTP status probe
network_port_check(host, port)               — TCP port check

shell_run(command, cwd=null, timeout=30, dry_run=false) — Run a shell command [DESTRUCTIVE]
shell_which(name)                            — Check if a program is installed
shell_env(key=null)                          — Read environment variables

docker_ps(all_containers=false)              — List Docker containers
docker_logs(container, lines=50)             — Container logs
docker_inspect(container)                    — Container metadata (ports, mounts, env)
docker_images()                              — List local Docker images
docker_start(container, dry_run=false)       — Start a stopped container
docker_stop(container, dry_run=false)        — Stop a running container [DESTRUCTIVE]

db_tables(path)                              — List tables in a SQLite database
db_schema(path, table)                       — Column definitions for a table
db_query(path, sql, params=null, limit=100)  — Run a SELECT query (read-only)
db_execute(path, sql, params=null, dry_run=false) — Run INSERT/UPDATE/DELETE [DESTRUCTIVE]

code_symbols(path)                           — Extract classes & functions from a .py file
code_lint(path, fix=false)                   — Lint Python with ruff (or py_compile fallback)
code_complexity(path)                        — Cyclomatic complexity per function

memory_set(key, value, tags=null)            — Store a persistent memory entry
memory_get(key)                              — Retrieve a memory by key
memory_list(tag=null, limit=50)             — List stored memories (optionally by tag)
memory_delete(key)                           — Delete a memory [DESTRUCTIVE]
memory_search(query, limit=20)              — Search memories by text\
"""


def _schema_to_summary(tools: list) -> str:
    """Build a compact tool summary from a list of ``mcp.types.Tool`` objects."""
    lines: list[str] = []
    for tool in tools:
        name = tool.name
        desc = (tool.description or "").splitlines()[0][:80]
        params: list[str] = []
        schema = getattr(tool, "inputSchema", {}) or {}
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        for pname, pdef in props.items():
            if pname in {"ctx", "context"}:
                continue
            ptype = pdef.get("type", "any")
            default = pdef.get("default")
            if default is not None:
                params.append(f"{pname}={json.dumps(default)}")
            elif pname not in required:
                params.append(f"{pname}=null")
            else:
                params.append(pname)
        sig = f"{name}({', '.join(params)})"
        lines.append(f"{sig:<50} — {desc}")
    return "\n".join(lines)


# JSON schema passed to Ollama's `format` parameter to enforce structured output.
# Covers both single-call and chain shapes. Ollama ≥ 0.5 enforces this via GGML
# grammar, eliminating most parse failures on smaller models.
TOOL_CALL_FORMAT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "tool":        {"type": "string"},
        "params":      {"type": "object"},
        "confidence":  {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "chain":       {"type": "boolean"},
        "description": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tool":       {"type": "string"},
                    "params":     {"type": "object"},
                    "confidence": {"type": "number"},
                },
                "required": ["tool", "params"],
            },
        },
        "continue_on_error": {"type": "boolean"},
    },
}


class PromptBuilder:
    def __init__(self, tool_summary: str = _DEFAULT_TOOL_SUMMARY) -> None:
        self._tool_summary = tool_summary

    def update_from_fastmcp_tools(self, tools: list) -> None:
        """Update the tool summary from a live ``list_tools()`` response.

        Filters out transform-generated tools (``prompt_*``, ``resource_*``) to
        keep the system prompt compact — those are not tools the LLM should be
        calling directly in the structured-output loop.
        """
        domain_tools = [
            t for t in tools
            if not t.name.startswith(("prompt_", "resource_"))
        ]
        summary = _schema_to_summary(domain_tools)
        if summary:
            self._tool_summary = summary

    def update_tool_summary(self, summary: str) -> None:
        self._tool_summary = summary

    def system_prompt(self) -> str:
        return _SYSTEM_TEMPLATE.format(
            tool_summary=self._tool_summary,
            project_root=config.PROJECT_ROOT,
        )

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

    def clarification_prompt(self, original_input: str, tool: str, confidence: float) -> str:
        return (
            f"I wasn't fully confident about: '{original_input}'\n"
            f"I interpreted it as: {tool}  (confidence: {confidence:.0%})\n"
            "Reply 'yes' to proceed or rephrase your request."
        )

    def summarize_result_prompt(
        self,
        user_request: str,
        tool_name: str,
        raw_output: str,
    ) -> str:
        """Prompt for turning a single raw tool output into a human-readable answer."""
        truncated = raw_output[:3000] + ("…" if len(raw_output) > 3000 else "")
        _PATH_TOOLS = {"file_read", "file_write", "file_list", "file_search", "file_delete",
                       "git_status", "git_diff", "git_log", "git_add", "git_commit",
                       "git_branch_list", "git_branch_switch"}
        path_ctx = (
            f"Context: the project root is {config.PROJECT_ROOT} — copy this path exactly if you mention it.\n\n"
            if tool_name in _PATH_TOOLS else ""
        )
        return (
            f'The user requested: "{user_request}"\n\n'
            f"{path_ctx}"
            f"The tool `{tool_name}` already ran and returned this output:\n"
            f"{truncated}\n\n"
            "Report what was done in 1-2 sentences of plain past-tense English. "
            "Do NOT give instructions or explain how to do it — the action already happened. "
            "Summarise the result factually. "
            "Do not output JSON, code blocks, or tool names. "
            "If the output is an error, explain what went wrong in plain English."
        )

    def summarize_chain_prompt(
        self,
        user_request: str,
        steps: list[tuple[str, str]],   # [(tool_name, raw_output), ...]
    ) -> str:
        """Prompt for summarizing all steps of a multi-tool chain."""
        parts = [f'The user asked: "{user_request}"\n']
        for i, (tool, output) in enumerate(steps, 1):
            truncated = output[:1000] + ("…" if len(output) > 1000 else "")
            parts.append(f"Step {i} (`{tool}`) returned:\n{truncated}")
        parts.append(
            "\nProvide a concise, human-readable summary of all results in 2–5 sentences. "
            "Directly answer what the user wanted to know. No JSON, no raw data dumps."
        )
        return "\n\n".join(parts)

    def explain_failures_prompt(self, test_output: str) -> str:
        return (
            "The following test suite output contains failures. "
            "Explain each failure clearly and suggest a specific fix. "
            "Be concise and practical.\n\n"
            f"TEST OUTPUT:\n{test_output}"
        )

    def summarize_git_diff_prompt(self, diff_output: str) -> str:
        return (
            "Summarize the following git diff in plain English. "
            "List key changes grouped by file. Be concise.\n\n"
            f"GIT DIFF:\n{diff_output}"
        )
