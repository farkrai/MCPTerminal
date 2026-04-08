from __future__ import annotations
import sys
from mcp_assistant import config
from mcp_assistant.llm.client import OllamaClient
from mcp_assistant.llm.prompt_builder import PromptBuilder
from mcp_assistant.llm.response_parser import parse_response, ParseError
from mcp_assistant.llm.confidence import should_clarify, should_clarify_chain, register_known_tools
from mcp_assistant.mcp.schema import MCPCall, MCPChain, MCPResult
from mcp_assistant.mcp.registry import ToolRegistry
from mcp_assistant.mcp.dispatcher import MCPDispatcher
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant.audit.logger import AuditLogger
from mcp_assistant.context.buffer import ConversationBuffer
from mcp_assistant.audit.retention import cleanup_old_logs
from mcp_assistant.tools.file_handler import FileHandler
from mcp_assistant.tools.git_tool import GitTool
from mcp_assistant.tools.system_tool import SystemTool
from mcp_assistant.tools.test_runner import TestRunner

config.ensure_dirs()


def _build_registry(policy: PolicyConfig, client: OllamaClient) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(FileHandler(policy))
    registry.register(GitTool())
    registry.register(SystemTool())
    registry.register(TestRunner(llm_client=client))
    discovered = registry.discover_plugins(config.PLUGINS_DIR)
    if discovered:
        print(f"[plugins] Loaded: {', '.join(discovered)}")
    return registry


def _handle_special(cmd: str, policy, dispatcher, buffer, audit) -> None:
    parts = cmd[1:].strip().split()
    name = parts[0].lower() if parts else ""

    if name == "help":
        print(
            "Special commands:\n"
            "  !dry-run on|off  — toggle dry-run mode (preview before execute)\n"
            "  !context         — show current conversation context\n"
            "  !context clear   — clear conversation context\n"
            "  !verify          — verify today's audit log chain\n"
            "  !help            — show this message"
        )

    elif name == "dry-run":
        arg = parts[1].lower() if len(parts) > 1 else ""
        if arg == "on":
            policy.dry_run_mode = True
            print("[dry-run] ON — all operations will preview before executing.")
        elif arg == "off":
            policy.dry_run_mode = False
            print("[dry-run] OFF — operations execute directly.")
        else:
            state = "ON" if policy.dry_run_mode else "OFF"
            print(f"[dry-run] Currently {state}. Use '!dry-run on' or '!dry-run off'.")

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
                print(f"[context] {len(turns)} turn(s):")
                for t in turns:
                    role = t["role"].upper()
                    print(f"  [{role}] {t['content'][:120]}")

    elif name == "verify":
        from mcp_assistant.audit.logger import AuditLogger
        from datetime import datetime
        log_file = config.AUDIT_LOG_DIR / f"audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        if not log_file.exists():
            print(f"[verify] No audit log found for today: {log_file}")
        else:
            ok, errors = AuditLogger.verify_chain(log_file)
            if ok:
                print(f"[verify] Audit chain OK — {log_file.name}")
            else:
                print(f"[verify] Chain INVALID — {len(errors)} error(s):")
                for e in errors:
                    print(f"  {e}")
    else:
        print(f"Unknown special command: !{name}  (type !help for list)")


def _print_dispatch_result(result: MCPResult) -> None:
    status = "OK" if result.success else "ERR"
    print(f"\n[{status}] {result.call.tool}.{result.call.action}  ({result.duration_ms:.0f}ms)")
    print(result.output)


def run_cli() -> None:
    client = OllamaClient()

    if not client.is_available():
        print("ERROR: Ollama is not running. Start it with: ollama serve")
        sys.exit(1)

    policy = PolicyConfig.load_or_default(config.MCPRC_FILE)
    registry = _build_registry(policy, client)
    audit = AuditLogger(config.AUDIT_LOG_DIR)
    dispatcher = MCPDispatcher(registry, policy, audit)
    buffer = ConversationBuffer(max_turns=policy.context_window_size)
    buffer.load()

    removed = cleanup_old_logs(config.AUDIT_LOG_DIR, policy.audit_retention_days)
    if removed:
        print(f"[audit] Removed {len(removed)} old log(s): {removed}")

    builder = PromptBuilder(tool_summary=registry.generate_summary())
    register_known_tools(registry.tool_names())
    system = builder.system_prompt()

    print("MCP Terminal Assistant")
    print(f"Model: {client.model}   Tools: {', '.join(sorted(registry.tool_names()))}")
    print("Special commands: !dry-run on|off  !context  !verify  !help")
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

        # ── Special commands (prefixed with !) ────────────────────────────────
        if user_input.startswith("!"):
            _handle_special(user_input, policy, dispatcher, buffer, audit)
            continue

        prompt = builder.user_prompt(user_input, buffer.get_context())

        # LLM call with retry on parse failure
        raw = ""
        parsed = None
        for attempt in range(config.MAX_PARSE_RETRIES + 1):
            try:
                _prompt = prompt if attempt == 0 else prompt + "\n\nREMINDER: Respond ONLY with valid JSON. No other text."
                raw = client.generate(_prompt, system=system)
                parsed = parse_response(raw)
                break
            except ParseError:
                if attempt == config.MAX_PARSE_RETRIES:
                    print(f"[ERROR] Could not parse LLM response after {config.MAX_PARSE_RETRIES} retries.")
                    print(f"  Raw: {raw[:200]}")

        if parsed is None:
            continue

        # Confidence gate
        if isinstance(parsed, MCPCall) and should_clarify(parsed, policy.confidence_threshold):
            print(f"[LOW CONFIDENCE: {parsed.confidence:.2f}] Did you mean: {parsed.tool}.{parsed.action}? (y/n)")
            if input("  > ").strip().lower() not in {"y", "yes"}:
                print("  Skipped. Please rephrase.")
                continue
        elif isinstance(parsed, MCPChain) and should_clarify_chain(parsed, policy.confidence_threshold):
            print(f"[LOW CONFIDENCE chain] Steps: {[f'{s.tool}.{s.action}' for s in parsed.steps]}  Proceed? (y/n)")
            if input("  > ").strip().lower() not in {"y", "yes"}:
                print("  Skipped. Please rephrase.")
                continue

        # Dispatch
        if isinstance(parsed, MCPChain):
            print(f"\n[CHAIN] {parsed.description}  ({len(parsed.steps)} steps)")
            results = dispatcher.dispatch_chain(parsed)
            for i, r in enumerate(results, 1):
                print(f"\n  Step {i}:", end="")
                _print_dispatch_result(r)
            output_for_context = " | ".join(r.output[:100] for r in results)
        else:
            result = dispatcher.dispatch(parsed)
            _print_dispatch_result(result)
            output_for_context = result.output[:200]

        buffer.add_turn("user", user_input)
        buffer.add_turn("assistant", output_for_context)


def main() -> None:
    if "--cli" in sys.argv:
        run_cli()
    else:
        from mcp_assistant.tui.app import run_tui
        run_tui()


if __name__ == "__main__":
    main()
