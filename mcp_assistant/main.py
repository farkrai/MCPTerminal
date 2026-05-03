"""Entry point for the MCP Terminal Assistant.

Modes
-----
  mcp          → launches the Textual TUI (default)
  mcp --cli    → launches the readline CLI (lightweight)
  mcp-server   → starts the FastMCP server in stdio mode (for external MCP clients)
"""
from __future__ import annotations
import asyncio
import sys

from mcp_assistant import config
from mcp_assistant.llm.client import OllamaClient
from mcp_assistant.llm.prompt_builder import PromptBuilder
from mcp_assistant.llm.response_parser import ParseError, parse_response
from mcp_assistant.llm.confidence import (
    register_known_tools,
    should_clarify,
    should_clarify_chain,
)
from mcp_assistant.server.schema import ToolCall, ToolChain
from mcp_assistant.server.hallucination_guard import HallucinationGuard
from mcp_assistant.context.buffer import ConversationBuffer
from mcp_assistant.audit.retention import cleanup_old_logs
from mcp_assistant.server.app import get_server
from mcp_assistant.server.state import audit, policy

config.ensure_dirs()


# ── FastMCP async helpers ─────────────────────────────────────────────────────

async def _call_tool(client, tool: str, params: dict) -> str:
    """Call a FastMCP tool and return the first text content."""
    result = await client.call_tool(tool, params)
    if hasattr(result, "content"):
        for item in result.content:
            if hasattr(item, "text"):
                return item.text
    if hasattr(result, "data"):
        import json
        return json.dumps(result.data, indent=2) if result.data else ""
    return str(result)


async def _summarize(llm, builder, user_text: str, tool_name: str, raw_output: str) -> str | None:
    """Ask Ollama to produce a human-readable summary of raw tool output.

    Returns None when the LLM is unavailable or fails so callers can fall back
    to printing the raw output.
    """
    if not llm.is_available():
        return None
    prompt = builder.summarize_result_prompt(user_text, tool_name, raw_output)
    try:
        return await asyncio.to_thread(lambda: llm.generate(prompt, temperature=0.3))
    except Exception:
        return None


async def _summarize_chain(llm, builder, user_text: str, steps: list[tuple[str, str]]) -> str | None:
    if not llm.is_available():
        return None
    prompt = builder.summarize_chain_prompt(user_text, steps)
    try:
        return await asyncio.to_thread(lambda: llm.generate(prompt, temperature=0.3))
    except Exception:
        return None


# ── CLI ───────────────────────────────────────────────────────────────────────

async def _run_cli_async() -> None:
    from fastmcp import Client

    llm = OllamaClient()
    if not llm.is_available():
        print("ERROR: Ollama is not running. Start with: ollama serve")
        sys.exit(1)

    mcp = get_server()
    buffer = ConversationBuffer(max_turns=policy.context_window_size)
    buffer.load()
    builder = PromptBuilder()

    async with Client(mcp) as client:
        # Seed tool registry from live FastMCP schemas
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        register_known_tools(tool_names)
        builder.update_from_fastmcp_tools(tools)

        # Hallucination guard — validates every LLM-generated tool name
        guard = HallucinationGuard(known_tools=tool_names, auto_correct=True)

        system = builder.system_prompt()

        removed = cleanup_old_logs(config.AUDIT_LOG_DIR, policy.audit_retention_days)
        if removed:
            print(f"[audit] Removed {len(removed)} old log(s).")

        print("MCP Terminal Assistant  (FastMCP)")
        print(f"Model: {llm.model}   Tools: {len(tool_names)}")
        print("Commands: !dry-run on|off  !context  !verify  !tools  !help")
        print("Type 'exit' to quit.\n")

        while True:
            try:
                user_input = input("> ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nBye.")
                buffer.save()
                break

            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", "q"}:
                buffer.save()
                break

            if user_input.startswith("!"):
                _handle_special(user_input, client, buffer, guard)
                continue

            # Short-circuit meta-queries — no need to hit the LLM
            if _is_meta_query(user_input):
                _handle_special("!tools", client, buffer, guard)
                continue

            prompt = builder.user_prompt(user_input, buffer.get_context())

            # LLM call with parse retry
            raw, parsed = "", None
            for attempt in range(config.MAX_PARSE_RETRIES + 1):
                try:
                    _p = prompt if attempt == 0 else (
                        prompt + "\n\nREMINDER: Respond ONLY with valid JSON."
                    )
                    raw = llm.generate(_p, system=system)
                    parsed = parse_response(raw)
                    break
                except ParseError:
                    if attempt == config.MAX_PARSE_RETRIES:
                        print(f"[ERROR] Could not parse LLM response after {config.MAX_PARSE_RETRIES} retries.")
                        print(f"  Raw: {raw[:200]}")

            if parsed is None:
                continue

            # Hallucination guard — validate (and optionally auto-correct) tool names
            if isinstance(parsed, ToolCall):
                parsed, h_report = guard.validate(parsed)
                if h_report:
                    if h_report.auto_corrected:
                        print(
                            f"[GUARD] '{h_report.original_tool}' → '{h_report.suggested_tool}' "
                            f"(auto-corrected, sim={h_report.similarity:.2f})"
                        )
                    else:
                        print(
                            f"[GUARD] Unknown tool '{h_report.original_tool}'. "
                            f"Suggestion: {h_report.suggested_tool or 'none'}. Skipping."
                        )
                        continue
            elif isinstance(parsed, ToolChain):
                parsed, h_reports = guard.validate_chain(parsed)
                for h_report in h_reports:
                    if h_report.auto_corrected:
                        print(
                            f"[GUARD] '{h_report.original_tool}' → '{h_report.suggested_tool}' "
                            f"(auto-corrected in chain)"
                        )
                    elif not h_report.suggested_tool:
                        print(
                            f"[GUARD] Unknown tool '{h_report.original_tool}' in chain. "
                            f"Step will fail."
                        )

            # Confidence gate
            if isinstance(parsed, ToolCall) and should_clarify(parsed, policy.confidence_threshold):
                print(
                    f"[LOW CONFIDENCE {parsed.confidence:.2f}] "
                    f"Did you mean: {parsed.tool}? (y/n)"
                )
                if input("  > ").strip().lower() not in {"y", "yes"}:
                    print("  Skipped.")
                    continue
            elif isinstance(parsed, ToolChain) and should_clarify_chain(parsed, policy.confidence_threshold):
                print(
                    f"[LOW CONFIDENCE chain] Steps: "
                    f"{[s.tool for s in parsed.steps]}  Proceed? (y/n)"
                )
                if input("  > ").strip().lower() not in {"y", "yes"}:
                    print("  Skipped.")
                    continue

            # Dispatch via FastMCP client
            output_for_ctx = ""
            if isinstance(parsed, ToolChain):
                print(f"\n[CHAIN] {parsed.description}  ({len(parsed.steps)} steps)")
                prior_outputs: list[str] = []
                step_results: list[tuple[str, str]] = []
                for i, step in enumerate(parsed.steps, 1):
                    params = _resolve_chain_templates(step.params, prior_outputs)
                    print(f"  Step {i}: {step.tool} ", end="", flush=True)
                    try:
                        out = await _call_tool(client, step.tool, params)
                        print("OK")
                        prior_outputs.append(out)
                        step_results.append((step.tool, out))
                    except Exception as exc:
                        print(f"ERR: {exc}")
                        prior_outputs.append("")
                        step_results.append((step.tool, f"error: {exc}"))
                        if not parsed.continue_on_error:
                            break
                # Summarize chain output
                summary = await _summarize_chain(llm, builder, user_input, step_results)
                if summary:
                    print(f"\n{summary}")
                else:
                    for tool_n, raw in step_results:
                        print(f"\n  [{tool_n}] {raw[:300]}")
                output_for_ctx = summary or " | ".join(o[:100] for o in prior_outputs)
            else:
                try:
                    out = await _call_tool(client, parsed.tool, parsed.params)
                    summary = await _summarize(llm, builder, user_input, parsed.tool, out)
                    print(f"\n{summary or out}")
                    output_for_ctx = summary or out[:200]
                except Exception as exc:
                    print(f"\n[ERR] {parsed.tool}: {exc}")
                    output_for_ctx = f"error: {exc}"

            buffer.add_turn("user", user_input)
            buffer.add_turn("assistant", output_for_ctx[:300])


_META_PATTERNS = (
    "list tools", "list all tools", "show tools", "show all tools",
    "what tools", "which tools", "what can you do", "what can you access",
    "available tools", "what tools do you have", "tools available",
    "help me with tools", "capabilities", "what are your capabilities",
)


def _is_meta_query(text: str) -> bool:
    """Return True if the input is clearly asking about available tools."""
    lower = text.lower().strip()
    return any(lower == pat or lower.startswith(pat) for pat in _META_PATTERNS)


def _resolve_chain_templates(params: dict, prior: list[str]) -> dict:
    """Replace ``{{step_N.output}}`` placeholders with prior step outputs."""
    import re
    result = {}
    for k, v in params.items():
        if isinstance(v, str):
            def replacer(m: re.Match) -> str:
                idx = int(m.group(1)) - 1
                return prior[idx] if 0 <= idx < len(prior) else m.group(0)
            v = re.sub(r"\{\{step_(\d+)\.output\}\}", replacer, v)
        result[k] = v
    return result


def _handle_special(cmd: str, client, buffer: ConversationBuffer, guard: "HallucinationGuard | None" = None) -> None:
    parts = cmd[1:].strip().split()
    name = parts[0].lower() if parts else ""

    if name == "help":
        print(
            "Special commands:\n"
            "  !dry-run on|off        — toggle dry-run mode\n"
            "  !context               — show conversation history\n"
            "  !context clear         — clear conversation history\n"
            "  !verify                — verify today's audit chain\n"
            "  !tools                 — list available FastMCP tools\n"
            "  !toolkit <kit|all>     — activate a ToolKit (file/git/system/test/network)\n"
            "  !stats                 — session statistics + hallucination guard stats\n"
            "  !help                  — this message"
        )

    elif name == "dry-run":
        arg = parts[1].lower() if len(parts) > 1 else ""
        if arg == "on":
            policy.dry_run_mode = True
            print("[dry-run] ON")
        elif arg == "off":
            policy.dry_run_mode = False
            print("[dry-run] OFF")
        else:
            print(f"[dry-run] {'ON' if policy.dry_run_mode else 'OFF'}")

    elif name == "context":
        arg = parts[1].lower() if len(parts) > 1 else ""
        if arg == "clear":
            buffer.clear()
            print("[context] Cleared.")
        else:
            turns = buffer.get_context()
            if not turns:
                print("[context] Empty.")
            else:
                for t in turns:
                    print(f"  [{t['role'].upper()}] {t['content'][:120]}")

    elif name == "verify":
        from datetime import datetime
        log_file = config.AUDIT_LOG_DIR / f"audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        if not log_file.exists():
            print("[verify] No audit log for today.")
        else:
            from mcp_assistant.audit.logger import AuditLogger
            ok, errors = AuditLogger.verify_chain(log_file)
            if ok:
                print(f"[verify] Audit chain OK — {log_file.name}")
            else:
                print(f"[verify] INVALID — {len(errors)} error(s):")
                for e in errors:
                    print(f"  {e}")

    elif name == "tools":
        import asyncio
        from fastmcp import Client
        async def _list():
            async with Client(get_server()) as c:
                return await c.list_tools()
        tools = asyncio.run(_list())
        print("━━━ FastMCP Tools ━━━")
        for t in tools:
            desc = (t.description or "").splitlines()[0][:60]
            print(f"  {t.name:<40} {desc}")

    elif name == "toolkit":
        kit_name = parts[1].lower() if len(parts) > 1 else ""
        if not kit_name:
            print("Usage: !toolkit <file|git|system|test|network|read-only|all>")
            return
        import asyncio
        from fastmcp import Client
        from mcp_assistant.server.toolkit import ToolRouter

        async def _activate():
            mcp_inst = get_server()
            async with Client(mcp_inst) as c:
                router = ToolRouter(mcp_inst)
                if kit_name == "all":
                    router.activate_all()
                    tools = await c.list_tools()
                    print(f"[toolkit] All tools restored ({len(tools)} visible).")
                elif router.activate(kit_name):
                    tools = await c.list_tools()
                    print(f"[toolkit] '{kit_name}' kit active — {len(tools)} tool(s) visible.")
                else:
                    print(f"[toolkit] Unknown kit '{kit_name}'. Try: file git system test network read-only all")

        asyncio.run(_activate())

    elif name == "stats":
        g_stats = guard.stats() if guard else None
        h_info = ""
        if g_stats and g_stats.total_calls > 0:
            h_info = (
                f"  Hallucination guard: {g_stats.total_calls} calls, "
                f"{g_stats.hallucinated} hallucinated "
                f"({g_stats.hallucination_rate:.1%}), "
                f"{g_stats.auto_corrected} auto-corrected"
            )
        from mcp_assistant.server.middleware import TimingMiddleware
        slow = sorted(TimingMiddleware.global_stats().items(), key=lambda x: -x[1]["avg_ms"])[:3]
        slow_info = ""
        if slow:
            slow_info = "  Slowest tools: " + ", ".join(
                f"{t}={d['avg_ms']}ms" for t, d in slow
            )
        print(
            f"[stats] Context: {len(buffer)} turns  |  "
            f"Session: {audit._session_id}  |  "
            f"Calls logged: {audit._seq}"
        )
        if h_info:
            print(h_info)
        if slow_info:
            print(slow_info)

    else:
        print(f"Unknown: !{name}  (try !help)")


def run_cli() -> None:
    asyncio.run(_run_cli_async())


def main() -> None:
    if "--cli" in sys.argv:
        run_cli()
    elif "--server" in sys.argv:
        # Standalone MCP server for Claude Desktop / other MCP clients
        get_server().run()
    else:
        from mcp_assistant.tui.app import run_tui
        run_tui()


if __name__ == "__main__":
    main()
