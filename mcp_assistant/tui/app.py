from __future__ import annotations
import asyncio
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header

from mcp_assistant import config
from mcp_assistant.llm.client import OllamaClient
from mcp_assistant.llm.prompt_builder import PromptBuilder
from mcp_assistant.llm.response_parser import parse_response, ParseError
from mcp_assistant.llm.confidence import should_clarify, should_clarify_chain, register_known_tools
from mcp_assistant.mcp.schema import MCPCall, MCPChain
from mcp_assistant.mcp.registry import ToolRegistry
from mcp_assistant.mcp.dispatcher import MCPDispatcher
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant.audit.logger import AuditLogger
from mcp_assistant.audit.retention import cleanup_old_logs
from mcp_assistant.context.buffer import ConversationBuffer
from mcp_assistant.tools.file_handler import FileHandler
from mcp_assistant.tools.git_tool import GitTool
from mcp_assistant.tools.system_tool import SystemTool
from mcp_assistant.tools.test_runner import TestRunner

from mcp_assistant.tui.theme import APP_CSS
from mcp_assistant.tui.widgets.stats_sidebar import StatsSidebar
from mcp_assistant.tui.widgets.history_panel import HistoryPanel
from mcp_assistant.tui.widgets.tool_inspector import ToolInspector
from mcp_assistant.tui.widgets.input_bar import InputBar


class MCPAssistantApp(App):
    CSS = APP_CSS
    TITLE = "MCP Terminal Assistant"
    SUB_TITLE = "Offline AI-Augmented CLI"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+d", "toggle_dry_run", "Dry-run"),
        Binding("ctrl+l", "clear_context", "Clear ctx"),
        Binding("f1", "show_help", "Help"),
    ]

    def __init__(self) -> None:
        super().__init__()
        config.ensure_dirs()

        self._policy = PolicyConfig.load_or_default(config.MCPRC_FILE)
        self._client = OllamaClient()
        self._tool_registry = self._build_registry()
        self._audit = AuditLogger(config.AUDIT_LOG_DIR)
        self._dispatcher = MCPDispatcher(
            self._tool_registry, self._policy, self._audit,
            confirm_fn=self._tui_confirm,
        )
        self._buffer = ConversationBuffer(self._policy.context_window_size)
        self._buffer.load()
        self._builder = PromptBuilder(self._tool_registry.generate_summary())
        register_known_tools(self._tool_registry.tool_names())
        self._system_prompt = self._builder.system_prompt()

        cleanup_old_logs(config.AUDIT_LOG_DIR, self._policy.audit_retention_days)

        # Pending clarification state
        self._pending_call: MCPCall | MCPChain | None = None
        self._awaiting_confirm = False

    # ── Compose ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatsSidebar()
        with Vertical(id="center-col"):
            yield HistoryPanel()
            yield InputBar(dry_run=self._policy.dry_run_mode)
        yield ToolInspector()
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(ToolInspector).show_idle()
        history = self.query_one(HistoryPanel)
        history.add_system(f"Model: {self._client.model}")
        history.add_system(f"Tools: {', '.join(sorted(self._tool_registry.tool_names()))}")
        history.add_system("Ready. Type a natural-language command below.")
        history.add_system("Ctrl+D = toggle dry-run  |  Ctrl+L = clear context  |  F1 = help")

        if not self._client.is_available():
            history.add_error("Ollama is not running. Start it with: ollama serve")

    # ── Input handling ────────────────────────────────────────────────────────

    def on_input_bar_command_submitted(self, event: InputBar.CommandSubmitted) -> None:
        text = event.text.strip()
        if not text:
            return

        # Special ! commands
        if text.startswith("!"):
            self._handle_special(text)
            return

        # Clarification response
        if self._awaiting_confirm:
            self._handle_clarification_response(text)
            return

        self.query_one(InputBar).set_busy(True)
        self.query_one(HistoryPanel).add_user(text)
        self.run_worker(self._process_command(text), exclusive=True)

    async def _process_command(self, text: str) -> None:
        history = self.query_one(HistoryPanel)
        inspector = self.query_one(ToolInspector)
        input_bar = self.query_one(InputBar)

        prompt = self._builder.user_prompt(text, self._buffer.get_context())

        # LLM call with retry
        parsed = None
        for attempt in range(config.MAX_PARSE_RETRIES + 1):
            try:
                p = prompt if attempt == 0 else prompt + "\n\nREMINDER: Respond ONLY with valid JSON."
                raw = await asyncio.to_thread(
                    lambda p=p: self._client.generate(p, system=self._system_prompt)
                )
                parsed = parse_response(raw)
                break
            except ParseError:
                if attempt == config.MAX_PARSE_RETRIES:
                    history.add_error("Could not parse LLM response. Please rephrase.")
                    input_bar.set_busy(False)
                    return

        if parsed is None:
            input_bar.set_busy(False)
            return

        # Confidence gate
        needs_clarify = (
            isinstance(parsed, MCPCall) and should_clarify(parsed, self._policy.confidence_threshold)
        ) or (
            isinstance(parsed, MCPChain) and should_clarify_chain(parsed, self._policy.confidence_threshold)
        )

        if needs_clarify:
            self._pending_call = parsed
            self._awaiting_confirm = True
            if isinstance(parsed, MCPCall):
                inspector.show_clarification(parsed.tool, parsed.action, parsed.confidence)
                history.add_system(
                    f"Low confidence ({parsed.confidence:.2f}): did you mean "
                    f"{parsed.tool}.{parsed.action}? Type 'yes' to confirm or rephrase."
                )
            else:
                steps_desc = " → ".join(f"{s.tool}.{s.action}" for s in parsed.steps)
                history.add_system(f"Low confidence chain: {steps_desc}. Type 'yes' to confirm.")
            input_bar.set_busy(False)
            return

        await self._dispatch_parsed(parsed)
        input_bar.set_busy(False)

    def _handle_clarification_response(self, text: str) -> None:
        self._awaiting_confirm = False
        pending = self._pending_call
        self._pending_call = None

        if text.lower() in {"y", "yes"} and pending is not None:
            self.query_one(InputBar).set_busy(True)
            self.run_worker(self._dispatch_parsed(pending), exclusive=True)
        else:
            self.query_one(HistoryPanel).add_system("Skipped. Please rephrase.")
            self.query_one(ToolInspector).show_idle()

    async def _dispatch_parsed(self, parsed: MCPCall | MCPChain) -> None:
        history = self.query_one(HistoryPanel)
        inspector = self.query_one(ToolInspector)
        input_bar = self.query_one(InputBar)

        if isinstance(parsed, MCPChain):
            history.add_chain_header(parsed.description, len(parsed.steps))
            results = await asyncio.to_thread(
                lambda: self._dispatcher.dispatch_chain(parsed)
            )
            for i, result in enumerate(results, 1):
                history.add_chain_step(i, result.call.tool, result.call.action, result.success)
                history.add_result(result.output, result.success)
            inspector.show_chain(results)
            ctx_output = " | ".join(r.output[:80] for r in results)

        else:
            history.add_tool_call(parsed.tool, parsed.action, parsed.confidence)
            result = await asyncio.to_thread(lambda: self._dispatcher.dispatch(parsed))
            history.add_result(result.output, result.success)
            inspector.show_call(parsed, result)
            ctx_output = result.output[:200]

        self._buffer.add_turn("user", "")   # text already added before worker
        self._buffer.add_turn("assistant", ctx_output)
        input_bar.set_busy(False)

    # ── Special ! commands ────────────────────────────────────────────────────

    def _handle_special(self, cmd: str) -> None:
        history = self.query_one(HistoryPanel)
        parts = cmd[1:].strip().split()
        name = parts[0].lower() if parts else ""

        if name == "help":
            history.add_system(
                "Special commands:\n"
                "  !dry-run on|off  — toggle dry-run mode\n"
                "  !context         — show conversation context\n"
                "  !context clear   — clear context\n"
                "  !verify          — verify today's audit log\n"
                "  Ctrl+D           — toggle dry-run\n"
                "  Ctrl+L           — clear context\n"
                "  Ctrl+Q           — quit"
            )

        elif name == "dry-run":
            arg = parts[1].lower() if len(parts) > 1 else "toggle"
            if arg == "on":
                self._policy.dry_run_mode = True
            elif arg == "off":
                self._policy.dry_run_mode = False
            else:
                self._policy.dry_run_mode = not self._policy.dry_run_mode
            state = "ON" if self._policy.dry_run_mode else "OFF"
            self.query_one(InputBar).set_dry_run(self._policy.dry_run_mode)
            history.add_system(f"Dry-run mode: {state}")

        elif name == "context":
            arg = parts[1].lower() if len(parts) > 1 else ""
            if arg == "clear":
                self._buffer.clear()
                history.add_system("Context cleared.")
            else:
                turns = self._buffer.get_context()
                history.add_system(f"Context: {len(turns)} turn(s)")
                for t in turns[-4:]:
                    history.add_system(f"  [{t['role'].upper()}] {t['content'][:80]}")

        elif name == "verify":
            from datetime import datetime
            log_file = config.AUDIT_LOG_DIR / f"audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
            if not log_file.exists():
                history.add_system("No audit log found for today.")
            else:
                ok, errors = AuditLogger.verify_chain(log_file)
                if ok:
                    history.add_system(f"Audit chain OK — {log_file.name}")
                else:
                    history.add_error(f"Audit chain INVALID ({len(errors)} error(s))")
                    for e in errors[:3]:
                        history.add_error(f"  {e}")
        else:
            history.add_system(f"Unknown command: !{name}  (type !help)")

    # ── Key bindings ──────────────────────────────────────────────────────────

    def action_toggle_dry_run(self) -> None:
        self._handle_special("!dry-run")

    def action_clear_context(self) -> None:
        self._handle_special("!context clear")

    def action_show_help(self) -> None:
        self._handle_special("!help")

    def action_quit(self) -> None:
        self._buffer.save()
        self.exit()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(FileHandler(self._policy))
        registry.register(GitTool())
        registry.register(SystemTool())
        registry.register(TestRunner(llm_client=self._client))
        registry.discover_plugins(config.PLUGINS_DIR)
        return registry

    def _tui_confirm(self, prompt: str) -> bool:
        # In TUI mode, confirmations for destructive ops go through the history panel
        # and a modal would be ideal — for now, dry_run_mode controls this.
        # Confirmation prompts from dispatcher are shown as history messages.
        self.query_one(HistoryPanel).add_system(prompt)
        # Always auto-confirm in TUI (user controls via !dry-run or policy)
        return True


def run_tui() -> None:
    app = MCPAssistantApp()
    app.run()
