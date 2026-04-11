from __future__ import annotations
import threading
import sys
from mcp_assistant import config
from mcp_assistant.llm.client import OllamaClient
from mcp_assistant.llm import cache as llm_cache
from mcp_assistant.llm.ecosystem import report as ecosystem_report
from mcp_assistant.llm.model_router import ModelRouter
from mcp_assistant.llm.prompt_builder import PromptBuilder
from mcp_assistant.llm.confidence import register_known_tools
from mcp_assistant.mcp.schema import MCPCall, MCPChain, MCPResult
from mcp_assistant.mcp.registry import ToolRegistry
from mcp_assistant.mcp.dispatcher import MCPDispatcher
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant.audit.logger import AuditLogger
from mcp_assistant.context.buffer import ConversationBuffer
from mcp_assistant.audit.retention import cleanup_old_logs
from mcp_assistant.orchestration import build_assistant_orchestrator
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


def _handle_special(cmd: str, policy, buffer) -> None:
    parts = cmd[1:].strip().split()
    name = parts[0].lower() if parts else ""

    if name == "help":
        print(
            "Special commands:\n"
            "  !dry-run on|off  — toggle dry-run mode (preview before execute)\n"
            "  !context         — show current conversation context\n"
            "  !context clear   — clear conversation context\n"
            "  !workspace       — show active workspace and sandbox root\n"
            "  !cache clear     — clear the LLM response cache\n"
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
                print(f"[context] {len(turns)} turn(s), {buffer.context_token_count()} token(s):")
                for t in turns:
                    role = t["role"].upper()
                    print(f"  [{role}] {t['content'][:120]}")

    elif name == "workspace":
        print(f"[workspace] Active workspace root: {config.WORKSPACE_DIR}")
        print(f"[workspace] Active sandbox root:  {policy.sandbox_root}")

    elif name == "cache":
        arg = parts[1].lower() if len(parts) > 1 else ""
        if arg == "clear":
            llm_cache.clear_all()
            print("[cache] LLM cache cleared.")
        else:
            print("[cache] Usage: !cache clear")

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
    if result.model_used:
        print(f"Model: {result.model_used}")
    print(result.output)


def _check_ollama_version(client: OllamaClient) -> None:
    try:
        version = client.ollama_version()
        if version < (0, 1, 34):
            print(
                f"[WARN] Ollama {'.'.join(map(str, version))} detected. "
                "Upgrade to >= 0.1.34 for structured output support."
            )
    except Exception:
        pass


def _warm_up_kv(client: OllamaClient, builder: PromptBuilder, model: str) -> None:
    try:
        client.generate(
            prompt=".",
            system=builder.system_prompt(),
            temperature=0.0,
            model=model,
        )
    except Exception:
        pass


def run_cli() -> None:
    client = OllamaClient()

    if not client.is_available():
        print("ERROR: Ollama is not running. Start it with: ollama serve")
        sys.exit(1)
    _check_ollama_version(client)

    policy = PolicyConfig.load_or_default(config.MCPRC_FILE)
    registry = _build_registry(policy, client)
    audit = AuditLogger(config.AUDIT_LOG_DIR)
    model_router = ModelRouter(client)
    model_router.warm_up()
    dispatcher = MCPDispatcher(registry, policy, audit, client=client)
    buffer = ConversationBuffer(max_turns=policy.context_window_size)
    buffer.load()

    removed = cleanup_old_logs(config.AUDIT_LOG_DIR, policy.audit_retention_days)
    if removed:
        print(f"[audit] Removed {len(removed)} old log(s): {removed}")

    builder = PromptBuilder(tool_summary=registry.generate_summary())
    orchestrator = build_assistant_orchestrator(
        client=client,
        prompt_builder=builder,
        dispatcher=dispatcher,
        registry=registry,
        policy=policy,
        model_router=model_router,
    )
    register_known_tools(registry.tool_names())
    eco_report = ecosystem_report()
    if eco_report:
        print(eco_report)
    threading.Thread(
        target=_warm_up_kv,
        args=(client, builder, model_router.router_model()),
        daemon=True,
    ).start()

    print("MCP Terminal Assistant")
    print(f"Model: {client.model}   Tools: {', '.join(sorted(registry.tool_names()))}")
    print(f"Workspace root: {config.WORKSPACE_DIR}")
    print(f"Sandbox root:   {policy.sandbox_root}")
    print("Special commands: !dry-run on|off  !context  !workspace  !cache clear  !verify  !help")
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
            _handle_special(user_input, policy, buffer)
            continue

        state = orchestrator.invoke(
            user_message=user_input,
            context=buffer.get_context(),
        )
        parsed = state.get("parsed_call")

        if state.get("awaiting_clarification") and parsed is not None:
            print(f"[LOW CONFIDENCE] {state.get('final_response', 'Please confirm the action.')}")
            if input("  > ").strip().lower() not in {"y", "yes"}:
                print("  Skipped. Please rephrase.")
                continue
            state = orchestrator.invoke(
                user_message=user_input,
                context=buffer.get_context(),
                parsed_call=parsed,
                confirmed=True,
                extra_state={
                    "difficulty": state.get("difficulty", ""),
                    "execution_plan": dict(state.get("execution_plan") or {}),
                },
            )
            parsed = state.get("parsed_call")

        # Get the natural language response
        response = ""
        
        # For direct responses (conversational), use the direct_response
        if state.get("direct_response"):
            response = str(state.get("direct_response", ""))
        # For MCP tool results, show the actual tool output
        elif state.get("dispatch_results"):
            results = state.get("dispatch_results", [])
            if results:
                # Show the actual output from the tool
                response = results[-1].output if len(results) == 1 else "\n\n".join(
                    f"Step {i+1}: {r.output}" for i, r in enumerate(results)
                )
        # Fallback to aggregate_text or final_response
        elif state.get("aggregate_text"):
            response = str(state.get("aggregate_text", ""))
        else:
            response = str(state.get("final_response") or state.get("error") or "No response generated.")
        
        # Print only the conversational response
        print(response)
        
        # Store for context
        output_for_context = response[:200]

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
