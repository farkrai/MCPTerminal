from __future__ import annotations
import asyncio
import concurrent.futures
import threading
import requests
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header

from mcp_assistant import config
from mcp_assistant.llm.client import OllamaClient
from mcp_assistant.llm import cache as llm_cache
from mcp_assistant.llm.ecosystem import report as ecosystem_report
from mcp_assistant.llm.inference import infer_call, prepare_inference_request
from mcp_assistant.llm.model_router import ModelRouter
from mcp_assistant.llm.prompt_builder import PromptBuilder
from mcp_assistant.llm.response_parser import parse_response
from mcp_assistant.llm.confidence import register_known_tools
from mcp_assistant.mcp.schema import MCPCall, MCPChain, ParseError
from mcp_assistant.mcp.registry import ToolRegistry
from mcp_assistant.mcp.dispatcher import MCPDispatcher
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant.audit.logger import AuditLogger
from mcp_assistant.audit.retention import cleanup_old_logs
from mcp_assistant.context.buffer import ConversationBuffer
from mcp_assistant.orchestration import build_assistant_orchestrator
from mcp_assistant.tools.file_handler import FileHandler
from mcp_assistant.tools.git_tool import GitTool
from mcp_assistant.tools.system_tool import SystemTool
from mcp_assistant.tools.test_runner import TestRunner

from mcp_assistant.tui.theme import APP_CSS
from mcp_assistant.tui.widgets.stats_sidebar import StatsSidebar
from mcp_assistant.tui.widgets.history_panel import HistoryPanel
from mcp_assistant.tui.widgets.tool_inspector import ToolInspector
from mcp_assistant.tui.widgets.input_bar import InputBar
from mcp_assistant.tui.widgets.confirm_modal import ConfirmModal


def _ollama_version_warning(client: OllamaClient) -> str | None:
    try:
        version = client.ollama_version()
        if version < (0, 1, 34):
            return (
                f"Ollama {'.'.join(map(str, version))} detected. "
                "Upgrade to >= 0.1.34 for structured output support."
            )
    except Exception:
        return None
    return None


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
        self._model_router = ModelRouter(self._client)
        self._tool_registry = self._build_registry()
        self._audit = AuditLogger(config.AUDIT_LOG_DIR)
        self._dispatcher = MCPDispatcher(
            self._tool_registry, self._policy, self._audit,
            confirm_fn=self._tui_confirm,
            client=self._client,
        )
        self._buffer = ConversationBuffer(self._policy.context_window_size)
        self._buffer.load()
        self._builder = PromptBuilder(self._tool_registry.generate_summary())
        self._orchestrator = build_assistant_orchestrator(
            client=self._client,
            prompt_builder=self._builder,
            dispatcher=self._dispatcher,
            registry=self._tool_registry,
            policy=self._policy,
            model_router=self._model_router,
        )
        register_known_tools(self._tool_registry.tool_names())

        cleanup_old_logs(config.AUDIT_LOG_DIR, self._policy.audit_retention_days)

        # Pending clarification state
        self._pending_call: MCPCall | MCPChain | None = None
        self._pending_state: dict | None = None
        self._pending_user_text: str = ""
        self._awaiting_confirm = False
        self._confirm_loop = None

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
        self._confirm_loop = asyncio.get_running_loop()
        self.query_one(ToolInspector).show_idle()
        history = self.query_one(HistoryPanel)
        history.add_system(f"Model: {self._client.model}")
        history.add_system(f"Tools: {', '.join(sorted(self._tool_registry.tool_names()))}")
        history.add_system(f"Workspace root: {config.WORKSPACE_DIR}")
        history.add_system(f"Sandbox root: {self._policy.sandbox_root}")
        history.add_system("Ready. Type a natural-language command below.")
        history.add_system("Ctrl+D = toggle dry-run  |  Ctrl+L = clear context  |  F1 = help")
        self._update_context_tokens()

        if not self._client.is_available():
            history.add_error("Ollama is not running. Start it with: ollama serve")
            return

        warning = _ollama_version_warning(self._client)
        if warning:
            history.add_system(warning)

        self._model_router.warm_up()
        eco_report = ecosystem_report()
        if eco_report:
            for line in eco_report.splitlines():
                history.add_system(line)
        threading.Thread(
            target=_warm_up_kv,
            args=(self._client, self._builder, self._model_router.router_model()),
            daemon=True,
        ).start()

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
        self.query_one(InputBar).start_spinner()
        self.query_one(HistoryPanel).add_user(text)
        self.run_worker(self._process_command(text), exclusive=True)

    async def _process_command(self, text: str) -> None:
        history = self.query_one(HistoryPanel)
        inspector = self.query_one(ToolInspector)
        input_bar = self.query_one(InputBar)

        try:
            state = await asyncio.to_thread(
                lambda: self._orchestrator.invoke(
                    user_message=text,
                    context=self._buffer.get_context(),
                )
            )
        except requests.RequestException as exc:
            history.add_error(f"Ollama request failed after retries: {exc}")
            input_bar.set_busy(False)
            return
        except ParseError as exc:
            history.add_error(f"Could not parse LLM response: {exc}")
            input_bar.set_busy(False)
            return
        except Exception as exc:
            history.add_error(f"Orchestration failed: {exc}")
            input_bar.set_busy(False)
            return

        if state.get("awaiting_clarification"):
            self._pending_call = state.get("parsed_call")
            self._pending_state = state
            self._pending_user_text = text
            self._awaiting_confirm = True
            parsed = state.get("parsed_call")
            if isinstance(parsed, MCPCall):
                inspector.show_clarification(parsed.tool, parsed.action, parsed.confidence)
            clarification = state.get("clarification_prompt") or state.get("final_response") or "Please confirm."
            history.add_system(clarification)
            input_bar.set_busy(False)
            return

        await self._render_orchestration_state(state, text)
        input_bar.set_busy(False)

    def _handle_clarification_response(self, text: str) -> None:
        self._awaiting_confirm = False
        pending = self._pending_call
        pending_state = self._pending_state
        pending_text = self._pending_user_text
        self._pending_call = None
        self._pending_state = None
        self._pending_user_text = ""

        if text.lower() in {"y", "yes"} and pending is not None:
            self.query_one(InputBar).set_busy(True)
            self.run_worker(
                self._dispatch_confirmed_orchestration(pending, pending_state or {}, pending_text),
                exclusive=True,
            )
        else:
            self.query_one(HistoryPanel).add_system("Skipped. Please rephrase.")
            self.query_one(ToolInspector).show_idle()

    async def _dispatch_confirmed_orchestration(
        self,
        parsed: MCPCall | MCPChain,
        prior_state: dict,
        user_text: str,
    ) -> None:
        state = await asyncio.to_thread(
            lambda: self._orchestrator.invoke(
                user_message=user_text,
                context=self._buffer.get_context(),
                parsed_call=parsed,
                confirmed=True,
                extra_state={
                    "difficulty": prior_state.get("difficulty", ""),
                    "execution_plan": dict(prior_state.get("execution_plan") or {}),
                },
            )
        )
        await self._render_orchestration_state(state, user_text)

    async def _render_orchestration_state(self, state: dict, user_text: str) -> None:
        history = self.query_one(HistoryPanel)
        inspector = self.query_one(ToolInspector)
        input_bar = self.query_one(InputBar)
        parsed = state.get("parsed_call")
        results = list(state.get("dispatch_results") or [])

        if isinstance(parsed, MCPChain) or len(results) > 1:
            description = parsed.description if isinstance(parsed, MCPChain) else "workflow"
            history.add_chain_header(description, len(results))
            for i, result in enumerate(results, 1):
                history.add_chain_step(i, result.call.tool, result.call.action, result.success)
                history.add_result(result.output, result.success)
            inspector.show_chain(results)
            ctx_output = state.get("final_response") or " | ".join(r.output[:80] for r in results)
        elif results and isinstance(parsed, MCPCall):
            history.add_tool_call(parsed.tool, parsed.action, parsed.confidence)
            result = results[0]
            history.add_result(result.output, result.success)
            inspector.show_call(parsed, result)
            ctx_output = state.get("final_response") or result.output[:200]
        else:
            message = state.get("final_response") or state.get("error") or "No response produced."
            history.add_result(message, not bool(state.get("error")))
            inspector.show_idle()
            ctx_output = message[:200]

        self._buffer.add_turn("user", user_text)
        self._buffer.add_turn("assistant", ctx_output)
        self._update_context_tokens()
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
                "  !workspace       — show active workspace and sandbox root\n"
                "  !cache clear     — clear LLM cache\n"
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
                self._update_context_tokens()
                history.add_system("Context cleared.")
            else:
                turns = self._buffer.get_context()
                history.add_system(f"Context: {len(turns)} turn(s), {self._buffer.context_token_count()} tok")
                for t in turns[-4:]:
                    history.add_system(f"  [{t['role'].upper()}] {t['content'][:80]}")

        elif name == "workspace":
            history.add_system(f"Workspace root: {config.WORKSPACE_DIR}")
            history.add_system(f"Sandbox root: {self._policy.sandbox_root}")

        elif name == "cache":
            arg = parts[1].lower() if len(parts) > 1 else ""
            if arg == "clear":
                llm_cache.clear_all()
                history.add_system("LLM cache cleared.")
            else:
                history.add_system("Usage: !cache clear")

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
        if self._confirm_loop is None:
            return False

        future: concurrent.futures.Future[bool] = concurrent.futures.Future()

        async def _push_modal() -> None:
            try:
                result = await self.push_screen_wait(ConfirmModal(prompt))
            except Exception:
                future.set_result(False)
            else:
                future.set_result(bool(result))

        def _schedule() -> None:
            asyncio.create_task(_push_modal())

        self._confirm_loop.call_soon_threadsafe(_schedule)
        try:
            return future.result(timeout=120)
        except Exception:
            return False

    async def _infer_with_streaming(self, text: str) -> MCPCall | MCPChain:
        history = self.query_one(HistoryPanel)
        input_bar = self.query_one(InputBar)
        context = self._buffer.get_context()
        request = prepare_inference_request(text, self._builder, self._model_router, context)
        system = request["system"]
        user = request["user"]

        cached = llm_cache.get(system, user)
        if cached:
            input_bar.stop_spinner()
            parsed = parse_response(cached)
            setattr(parsed, "_model_used", request["model"] or self._client.model)
            return parsed

        tokens: list[str] = []
        history.start_streaming_response()
        first_token = False

        try:
            async for token in self._client.generate_stream_async(
                prompt=user,
                system=system,
                temperature=config.OLLAMA_TEMP_STRUCTURED,
                model=request["model"],
                format_schema=request["format_schema"],
            ):
                if not first_token:
                    first_token = True
                    input_bar.stop_spinner()
                tokens.append(token)
                history.append_streaming_token(token)
            raw = "".join(tokens)
            history.finish_streaming_response()
            input_bar.stop_spinner()
            parsed = parse_response(raw)
            setattr(parsed, "_model_used", request["model"] or self._client.model)
            llm_cache.put(system, user, raw)
            return parsed
        except Exception:
            history.finish_streaming_response()
            input_bar.stop_spinner()
            return await asyncio.to_thread(
                lambda: infer_call(
                    nl_input=text,
                    client=self._client,
                    builder=self._builder,
                    model_router=self._model_router,
                    context=context,
                    use_cache=True,
                )
            )

    def _update_context_tokens(self) -> None:
        self.query_one(StatsSidebar).set_context_tokens(self._buffer.context_token_count())


def run_tui() -> None:
    app = MCPAssistantApp()
    app.run()
