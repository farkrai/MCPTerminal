"""FastMCP prompt templates used by the LLM layer."""
from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.prompts import Message


def register_prompts(mcp: FastMCP) -> None:
    """Register all prompt templates on *mcp*."""

    @mcp.prompt(
        name="system-instructions",
        description="Full system prompt for the MCP Terminal Assistant LLM",
    )
    def system_instructions() -> str:
        return (
            "You are an offline AI terminal assistant powered by the Model Context Protocol (MCP). "
            "You translate natural language requests into structured tool calls that the system "
            "executes on the user's local machine — no cloud, no external services.\n\n"
            "RESPONSE FORMAT:\n"
            "Always respond with ONLY a JSON object. Never add prose or markdown fences.\n"
            "Single tool call:\n"
            '  {"tool": "<tool_name>", "params": {<key: value>}, "confidence": <0.0-1.0>}\n'
            "Multi-step chain (use only when the request requires sequential operations):\n"
            '  {"chain": true, "description": "<plan>", "steps": [\n'
            '    {"tool": "<tool_name>", "params": {}, "confidence": 0.9},\n'
            '    ...\n'
            '  ]}\n\n'
            "Chain triggers: 'then', 'after that', 'first...then', 'followed by', 'and also'.\n"
            "If unable to map: {\"tool\": \"unknown\", \"params\": {}, \"confidence\": 0.2}"
        )

    @mcp.prompt(
        name="clarify-intent",
        description="Ask the user to confirm a low-confidence tool interpretation",
    )
    def clarify_intent(
        original_input: str,
        tool_name: str,
        confidence: float,
    ) -> list[Message]:
        return [
            Message(
                f"I'm not fully confident about your request: '{original_input}'\n"
                f"I interpreted it as: **{tool_name}** (confidence: {confidence:.0%})\n\n"
                "Could you rephrase, or reply 'yes' to proceed anyway?"
            )
        ]

    @mcp.prompt(
        name="explain-test-failures",
        description="Prompt the LLM to explain test failure output and suggest fixes",
    )
    def explain_test_failures(test_output: str) -> str:
        return (
            "The following test suite output contains failures. "
            "Explain each failure clearly and suggest a specific fix. "
            "Be concise and practical.\n\n"
            f"TEST OUTPUT:\n{test_output}"
        )

    @mcp.prompt(
        name="summarize-git-diff",
        description="Prompt the LLM to summarise a git diff in plain English",
    )
    def summarize_git_diff(diff_output: str) -> str:
        return (
            "Summarize the following git diff in plain English. "
            "List the key changes grouped by file. Be concise.\n\n"
            f"GIT DIFF:\n{diff_output}"
        )
