"""MCP Terminal Assistant — Textual TUI using FastMCP Client."""
from __future__ import annotations
import asyncio
import json
import time
from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header, Static, LoadingIndicator

from mcp_assistant import config
from mcp_assistant.llm.client import OllamaClient
from mcp_assistant.llm.prompt_builder import PromptBuilder
from mcp_assistant.llm.response_parser import parse_response, ParseError
from mcp_assistant.llm.confidence import should_clarify, should_clarify_chain, register_known_tools
from mcp_assistant.server.schema import ToolCall, ToolChain, ToolResult
from mcp_assistant.server.hallucination_guard import HallucinationGuard
from mcp_assistant.server.app import get_server
from mcp_assistant.server.state import audit, policy
from mcp_assistant.audit.logger import AuditLogger
from mcp_assistant.audit.retention import cleanup_old_logs
from mcp_assistant.context.buffer import ConversationBuffer

from mcp_assistant.tui.theme import APP_CSS
from mcp_assistant.tui.widgets.stats_sidebar import StatsSidebar
from mcp_assistant.tui.widgets.history_panel import HistoryPanel
from mcp_assistant.tui.widgets.tool_inspector import ToolInspector
from mcp_assistant.tui.widgets.input_bar import InputBar
from mcp_assistant.tui.widgets.command_palette import CommandPalette
from mcp_assistant.tui.widgets.welcome_screen import WelcomeScreen
from mcp_assistant.tui.widgets.confirm_bar import ConfirmBar


def _tools_requiring_confirmation(parsed: ToolCall | ToolChain) -> list[str]:
    """Return tool names in parsed that require policy confirmation."""
    def _needs(tool_name: str) -> bool:
        ns, _, action = tool_name.partition("_")
        return policy.requires_confirmation(ns, action)

    if isinstance(parsed, ToolCall):
        return [parsed.tool] if _needs(parsed.tool) else []
    return [s.tool for s in parsed.steps if _needs(s.tool)]


def _extract_tool_output(raw) -> str:
    """Extract text string from a FastMCP call_tool result."""
    if hasattr(raw, "content"):
        for item in raw.content:
            if hasattr(item, "text"):
                return item.text
    if hasattr(raw, "data"):
        return json.dumps(raw.data, indent=2) if raw.data else ""
    return str(raw)


def _resolve_chain_templates(params: dict, prior_outputs: list[str]) -> dict:
    """Replace ``{{step_N.output}}`` placeholders with prior step outputs."""
    import re
    result = {}
    for k, v in params.items():
        if isinstance(v, str):
            def replacer(m: re.Match) -> str:
                idx = int(m.group(1)) - 1
                return prior_outputs[idx] if 0 <= idx < len(prior_outputs) else m.group(0)
            v = re.sub(r"\{\{step_(\d+)\.output\}\}", replacer, v)
        result[k] = v
    return result


class MCPAssistantApp(App):
    CSS = APP_CSS
    TITLE = "MCP Terminal Assistant"
    SUB_TITLE = "Offline AI · Model Context Protocol"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+d", "toggle_dry_run", "Dry-run"),
        Binding("ctrl+l", "clear_context", "Clear ctx"),
        Binding("ctrl+p", "toggle_palette", "Palette"),
        Binding("ctrl+e", "export_session", "Export"),
        Binding("f1", "show_help", "Help"),
        Binding("up", "history_prev", "Prev cmd", show=False),
        Binding("down", "history_next", "Next cmd", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        config.ensure_dirs()

        self._llm = OllamaClient()
        self._buffer = ConversationBuffer(policy.context_window_size)
        self._buffer.load()
        self._builder = PromptBuilder()
        self._system_prompt = self._builder.system_prompt()

        self._available_tools: list = []
        self._tool_descriptions: dict[str, str] = {}
        self._fastmcp_client = None
        self._guard: HallucinationGuard | None = None

        cleanup_old_logs(config.AUDIT_LOG_DIR, policy.audit_retention_days)

        self._pending_call: ToolCall | ToolChain | None = None
        self._pending_user_text: str = ""
        self._awaiting_confirm = False
        self._palette_visible = False
        self._welcome_visible = True
        self._session_start = datetime.now()

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        yield WelcomeScreen(id="welcome-overlay")
        yield CommandPalette(id="command-palette-container", classes="hidden")
        yield Static("", id="toast-container", classes="hidden")
        yield StatsSidebar()
        with Vertical(id="center-col"):
            yield Static(
                f"  ● {self._llm.model}  │  loading…  │  session {audit._session_id}",
                id="session-bar",
            )
            yield HistoryPanel()
            with Vertical(id="thinking-bar", classes="hidden"):
                yield LoadingIndicator()
                yield Static("Thinking…", id="thinking-label")
            yield ConfirmBar(classes="hidden")
            yield InputBar(dry_run=policy.dry_run_mode)
        yield ToolInspector()
        yield Footer()

    async def on_mount(self) -> None:
        from fastmcp import Client

        self.query_one(ToolInspector).show_idle()
        history = self.query_one(HistoryPanel)

        # Connect FastMCP client for the session lifetime
        mcp = get_server()
        self._fastmcp_client = Client(mcp)
        await self._fastmcp_client.__aenter__()

        self._available_tools = await self._fastmcp_client.list_tools()
        tool_names = {t.name for t in self._available_tools}
        self._tool_descriptions: dict[str, str] = {
            t.name: (t.description or "").splitlines()[0]
            for t in self._available_tools
        }

        register_known_tools(tool_names)
        self._builder.update_from_fastmcp_tools(self._available_tools)
        self._system_prompt = self._builder.system_prompt()
        self._guard = HallucinationGuard(known_tools=tool_names, auto_correct=True)

        domain_tools = [
            t for t in self._available_tools
            if not t.name.startswith(("prompt_", "resource_"))
        ]
        n_tools = len(domain_tools)

        self.query_one("#session-bar", Static).update(
            f"  ● {self._llm.model}  │  {n_tools} tools  │  session {audit._session_id}"
        )

        history.add_system(f"Model: {self._llm.model}  ·  Tools: {n_tools} FastMCP tools loaded")
        history.add_system("Type a natural-language command below to get started.")

        if not self._llm.is_available():
            history.add_error("Ollama is not running — start with: ollama serve")

        self.set_timer(4.0, self._fade_welcome)

    async def on_unmount(self) -> None:
        if self._fastmcp_client is not None:
            await self._fastmcp_client.__aexit__(None, None, None)

    # ── Toast notifications ───────────────────────────────────────────────────

    def _show_toast(self, text: str, variant: str = "success", duration: float = 3.0) -> None:
        toast = self.query_one("#toast-container", Static)
        toast.remove_class("hidden", "toast-error", "toast-warn")
        if variant == "error":
            toast.add_class("toast-error")
        elif variant == "warn":
            toast.add_class("toast-warn")
        toast.update(f"  {text}")
        self.set_timer(duration, lambda: toast.add_class("hidden"))

    def _fade_welcome(self) -> None:
        if self._welcome_visible:
            self.query_one("#welcome-overlay").add_class("fading")
            self.set_timer(0.6, self._hide_welcome)

    def _hide_welcome(self) -> None:
        self._welcome_visible = False
        self.query_one("#welcome-overlay").add_class("hidden")

    # ── Input handling ────────────────────────────────────────────────────────

    def on_input_bar_command_submitted(self, event: InputBar.CommandSubmitted) -> None:
        text = event.text.strip()
        if not text:
            return

        if self._welcome_visible:
            self._hide_welcome()

        if text.startswith("!"):
            self._handle_special(text)
            return

        if self._awaiting_confirm:
            self._handle_clarification_response(text)
            return

        self.query_one(InputBar).set_busy(True)
        self._show_thinking(True)
        self.query_one(HistoryPanel).add_user(text)
        self.run_worker(self._process_command(text), exclusive=True)

    def on_command_palette_command_selected(self, event: CommandPalette.CommandSelected) -> None:
        self._toggle_palette_off()
        cmd = event.command
        if cmd.startswith("!"):
            self._handle_special(cmd)
        else:
            self.query_one(InputBar).set_busy(True)
            self._show_thinking(True)
            self.query_one(HistoryPanel).add_user(cmd)
            self.run_worker(self._process_command(cmd), exclusive=True)

    async def _process_command(self, text: str) -> None:
        history = self.query_one(HistoryPanel)
        input_bar = self.query_one(InputBar)

        prompt = self._builder.user_prompt(text, self._buffer.get_context())

        # Hint the model to use chain format when the request clearly asks for multiple steps
        _CHAIN_KEYWORDS = ("then", "after that", "first", "followed by", "and also",
                           "next", "and then", "afterwards", "step by step")
        if any(kw in text.lower() for kw in _CHAIN_KEYWORDS):
            prompt += (
                "\n\nIMPORTANT: This request has multiple steps. "
                "You MUST respond with the chain format: "
                "{\"chain\": true, \"description\": \"...\", \"steps\": [...]}"
            )

        parsed = None
        for attempt in range(config.MAX_PARSE_RETRIES + 1):
            try:
                p = prompt if attempt == 0 else prompt + "\n\nREMINDER: Respond ONLY with valid JSON."
                raw = await asyncio.to_thread(
                    lambda p=p: self._llm.generate(p, system=self._system_prompt, format="json")
                )
                parsed = parse_response(raw)
                break
            except ParseError:
                if attempt == config.MAX_PARSE_RETRIES:
                    history.add_error("Could not parse LLM response. Please rephrase.")
                    input_bar.set_busy(False)
                    self._show_thinking(False)
                    return

        if parsed is None:
            input_bar.set_busy(False)
            self._show_thinking(False)
            return

        # Hallucination guard
        if isinstance(parsed, ToolCall) and self._guard:
            parsed, h_report = self._guard.validate(parsed)
            if h_report and not h_report.auto_corrected:
                history.add_error(
                    f"Unknown tool '{h_report.original_tool}'. "
                    f"Suggestion: {h_report.suggested_tool or 'none'}. Skipping."
                )
                input_bar.set_busy(False)
                self._show_thinking(False)
                return
        elif isinstance(parsed, ToolChain) and self._guard:
            parsed, _ = self._guard.validate_chain(parsed)

        # Confidence gate
        needs_clarify = (
            isinstance(parsed, ToolCall) and should_clarify(parsed, policy.confidence_threshold)
        ) or (
            isinstance(parsed, ToolChain) and should_clarify_chain(parsed, policy.confidence_threshold)
        )

        if needs_clarify:
            self._pending_call = parsed
            self._pending_user_text = text
            self._awaiting_confirm = True
            inspector = self.query_one(ToolInspector)
            if isinstance(parsed, ToolCall):
                inspector.show_clarification(parsed.tool, parsed.confidence)
                history.add_system(
                    f"Low confidence ({parsed.confidence:.0%}): "
                    f"{parsed.tool} — type 'yes' to confirm."
                )
            else:
                steps_desc = " → ".join(s.tool for s in parsed.steps)
                history.add_system(f"Low confidence chain: {steps_desc}. Type 'yes' to confirm.")
            input_bar.set_busy(False)
            self._show_thinking(False)
            return

        # Policy confirmation gate — skipped in dry-run mode (nothing destructive runs)
        tools_needing_confirm = _tools_requiring_confirmation(parsed)
        if tools_needing_confirm and not policy.dry_run_mode:
            names = ", ".join(tools_needing_confirm)
            self._pending_call = parsed
            self._pending_user_text = text
            self._show_thinking(False)
            self.query_one(ConfirmBar).show(f"Confirm: {names}?")
            return

        await self._dispatch_parsed(parsed, text)
        input_bar.set_busy(False)
        self._show_thinking(False)

    def _handle_clarification_response(self, text: str) -> None:
        self._awaiting_confirm = False
        pending = self._pending_call
        user_text = self._pending_user_text
        self._pending_call = None
        self._pending_user_text = ""

        if text.lower() in {"y", "yes"} and pending is not None:
            self.query_one(InputBar).set_busy(True)
            self._show_thinking(True)
            self.run_worker(self._dispatch_and_cleanup(pending, user_text), exclusive=True)
        else:
            self.query_one(HistoryPanel).add_system("Skipped. Please rephrase if needed.")
            self.query_one(ToolInspector).show_idle()

    async def on_confirm_bar_confirmed(self, event: ConfirmBar.Confirmed) -> None:
        parsed = self._pending_call
        text = self._pending_user_text
        self._pending_call = None
        self._pending_user_text = ""
        if event.accepted and parsed is not None:
            self._show_thinking(True)
            await self._dispatch_parsed(parsed, text)
            self._show_thinking(False)
        else:
            self.query_one(HistoryPanel).add_system("Cancelled.")
        self.query_one(InputBar).set_busy(False)

    async def _dispatch_and_cleanup(self, parsed: ToolCall | ToolChain, user_text: str) -> None:
        await self._dispatch_parsed(parsed, user_text)
        self.query_one(InputBar).set_busy(False)
        self._show_thinking(False)

    async def _dispatch_parsed(self, parsed: ToolCall | ToolChain, user_text: str) -> None:
        history = self.query_one(HistoryPanel)
        inspector = self.query_one(ToolInspector)

        if isinstance(parsed, ToolChain):
            history.add_chain_header(parsed.description, len(parsed.steps))
            results = await self._dispatch_chain(parsed)
            for i, result in enumerate(results, 1):
                history.add_chain_step(i, result.tool, result.success)
            # Summarize all chain steps together then display
            if any(r.success for r in results):
                summary = await self._summarize_chain(user_text, results)
            else:
                summary = None
            all_ok = all(r.success for r in results)
            history.add_result(summary or "\n".join(r.output[:200] for r in results), all_ok)
            inspector.show_chain(results)
            ctx_output = summary or " | ".join(r.output[:80] for r in results)
        else:
            history.add_tool_call(parsed.tool, parsed.confidence)
            result = await self._call_tool(parsed.tool, parsed.params, parsed.confidence)
            if result.success:
                tool_desc = self._tool_descriptions.get(result.tool, "")
                result.summary = await self._summarize(user_text, result.tool, result.output, tool_desc)
            history.add_result(result.summary or result.output, result.success)
            inspector.show_call(result)
            ctx_output = result.summary or result.output[:200]

        self._buffer.add_turn("user", user_text)
        self._buffer.add_turn("assistant", ctx_output[:300])

    async def _call_tool(
        self, tool: str, params: dict, confidence: float = 1.0
    ) -> ToolResult:
        """Invoke a single FastMCP tool and return a ToolResult."""
        start = time.perf_counter()
        try:
            raw = await self._fastmcp_client.call_tool(tool, params)
            output = _extract_tool_output(raw)
            success = True
            error = None
        except Exception as exc:
            output = str(exc)
            success = False
            error = str(exc)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        return ToolResult(
            tool=tool, params=params, output=output,
            success=success, error=error, duration_ms=duration_ms, confidence=confidence,
        )

    async def _dispatch_chain(self, chain: ToolChain) -> list[ToolResult]:
        """Execute all steps in a ToolChain sequentially."""
        results: list[ToolResult] = []
        prior_outputs: list[str] = []
        for step in chain.steps:
            params = _resolve_chain_templates(step.params, prior_outputs)
            result = await self._call_tool(step.tool, params, step.confidence)
            results.append(result)
            prior_outputs.append(result.output)
            if not result.success and not chain.continue_on_error:
                break
        return results

    async def _summarize(
        self, user_text: str, tool_name: str, raw_output: str, tool_desc: str = ""
    ) -> str | None:
        """Ask the LLM to answer the user's question using the raw tool output."""
        if not self._llm.is_available():
            return None
        prompt = self._builder.summarize_result_prompt(user_text, tool_name, raw_output, tool_desc)
        try:
            return await asyncio.to_thread(
                lambda: self._llm.generate(prompt, temperature=0.5)
            )
        except Exception:
            return None

    async def _summarize_chain(
        self, user_text: str, results: list[ToolResult]
    ) -> str | None:
        """Ask the LLM to summarize the combined output of all chain steps."""
        if not self._llm.is_available():
            return None
        steps = [(r.tool, r.output) for r in results]
        prompt = self._builder.summarize_chain_prompt(user_text, steps)
        try:
            return await asyncio.to_thread(
                lambda: self._llm.generate(prompt, temperature=0.3)
            )
        except Exception:
            return None

    # ── Thinking indicator ────────────────────────────────────────────────────

    def _show_thinking(self, show: bool) -> None:
        bar = self.query_one("#thinking-bar")
        if show:
            bar.remove_class("hidden")
        else:
            bar.add_class("hidden")

    # ── Special ! commands ────────────────────────────────────────────────────

    def _handle_special(self, cmd: str) -> None:
        history = self.query_one(HistoryPanel)
        parts = cmd[1:].strip().split()
        name = parts[0].lower() if parts else ""

        if name == "help":
            history.add_system(
                "╔══ Commands ══════════════════════════╗\n"
                "║  !sandbox <path>   Set sandbox dir    ║\n"
                "║  !dry-run on|off   Toggle dry-run    ║\n"
                "║  !context          Show context       ║\n"
                "║  !context clear    Clear context      ║\n"
                "║  !verify           Verify audit chain ║\n"
                "║  !history          Command history    ║\n"
                "║  !toolkit <kit>    Activate ToolKit   ║\n"
                "║  !export md|json   Export session     ║\n"
                "║  !stats            Session statistics ║\n"
                "║  !tools            List tools         ║\n"
                "║  !clear            Clear display      ║\n"
                "╠══ Shortcuts ═════════════════════════╣\n"
                "║  Ctrl+P   Command palette            ║\n"
                "║  Ctrl+D   Toggle dry-run             ║\n"
                "║  Ctrl+E   Quick export               ║\n"
                "║  Ctrl+L   Clear context              ║\n"
                "║  Ctrl+Q   Quit                       ║\n"
                "║  F1       This help                  ║\n"
                "║  ↑/↓      Command recall             ║\n"
                "╚══════════════════════════════════════╝"
            )

        elif name == "dry-run":
            arg = parts[1].lower() if len(parts) > 1 else "toggle"
            if arg == "on":
                policy.dry_run_mode = True
            elif arg == "off":
                policy.dry_run_mode = False
            else:
                policy.dry_run_mode = not policy.dry_run_mode
            state = "ON" if policy.dry_run_mode else "OFF"
            self.query_one(InputBar).set_dry_run(policy.dry_run_mode)
            self._show_toast(f"Dry-run: {state}", "warn" if policy.dry_run_mode else "success")

        elif name == "context":
            arg = parts[1].lower() if len(parts) > 1 else ""
            if arg == "clear":
                self._buffer.clear()
                self._show_toast("Context cleared", "success")
            else:
                turns = self._buffer.get_context()
                history.add_system(f"Context buffer: {len(turns)} turn(s)")
                for t in turns[-4:]:
                    history.add_system(f"  [{t['role'].upper()}] {t['content'][:80]}")

        elif name == "verify":
            log_file = config.AUDIT_LOG_DIR / f"audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
            if not log_file.exists():
                history.add_system("No audit log for today.")
            else:
                ok, errors = AuditLogger.verify_chain(log_file)
                if ok:
                    self._show_toast(f"Audit chain verified — {log_file.name}")
                else:
                    history.add_error(f"Audit chain INVALID ({len(errors)} error(s))")
                    for e in errors[:3]:
                        history.add_error(f"  {e}")

        elif name == "history":
            cmds = self.query_one(InputBar).get_history()
            if not cmds:
                history.add_system("No command history yet.")
            else:
                history.add_system(f"Command History ({len(cmds)} entries)")
                for i, c in enumerate(cmds[:20], 1):
                    history.add_system(f"  {i:>3}. {c}")

        elif name == "toolkit":
            kit_name = parts[1].lower() if len(parts) > 1 else ""
            if not kit_name:
                history.add_system("Usage: !toolkit <file|git|system|test|network|read-only|all>")
            else:
                from mcp_assistant.server.toolkit import ToolRouter
                router = ToolRouter(get_server())
                if kit_name == "all":
                    router.activate_all()
                    history.add_system("All tools restored.")
                elif router.activate(kit_name):
                    history.add_system(f"ToolKit '{kit_name}' activated.")
                else:
                    history.add_system(
                        f"Unknown kit '{kit_name}'. "
                        "Available: file git system test network read-only all"
                    )

        elif name == "export":
            fmt = parts[1].lower() if len(parts) > 1 else "md"
            self._export_session(fmt)

        elif name == "stats":
            inspector_stats = self.query_one(ToolInspector).get_stats()
            elapsed = (datetime.now() - self._session_start).total_seconds()
            h, rem = divmod(int(elapsed), 3600)
            m, s = divmod(rem, 60)
            history.add_system(
                f"╔══ Session Stats ═══════════════════╗\n"
                f"║  Duration    {h}h {m:02d}m {s:02d}s             ║\n"
                f"║  Tool calls  {inspector_stats['call_count']:<22}║\n"
                f"║  Total time  {inspector_stats['total_ms']:.0f}ms                 ║\n"
                f"║  Avg latency {inspector_stats['avg_ms']:.0f}ms                 ║\n"
                f"║  Context     {len(self._buffer)} turns              ║\n"
                f"║  Model       {self._llm.model[:19]:<19}║\n"
                f"╚═══════════════════════════════════╝"
            )

        elif name == "tools":
            domain_tools = [
                t for t in self._available_tools
                if not t.name.startswith(("prompt_", "resource_"))
            ]
            history.add_system(f"Available FastMCP Tools ({len(domain_tools)} total)")
            for tool in sorted(domain_tools, key=lambda t: t.name):
                desc = (tool.description or "").splitlines()[0][:55]
                history.add_system(f"  {tool.name:<32} {desc}")

        elif name == "sandbox":
            raw_path = " ".join(parts[1:]).strip().strip('"').strip("'")
            if not raw_path:
                history.add_system(
                    f"Current sandbox: {policy.sandbox_root}\n"
                    "Usage: !sandbox /path/to/your/project"
                )
            else:
                from pathlib import Path as _Path
                new_root = _Path(raw_path).expanduser().resolve()
                if not new_root.is_dir():
                    history.add_error(f"Directory not found: {new_root}")
                else:
                    config.write_default_mcprc(new_root)
                    policy.reload(config.MCPRC_FILE)
                    self._system_prompt = self._builder.system_prompt()
                    self._show_toast(f"Sandbox → {new_root}", "success", 4.0)
                    history.add_system(f"Sandbox set to: {new_root}")

        elif name == "clear":
            history.clear_log()
            self._show_toast("History cleared")

        else:
            history.add_system(f"Unknown command: !{name}  (type !help)")

    def _export_session(self, fmt: str = "md") -> None:
        history = self.query_one(HistoryPanel)
        entries = history.get_entries()
        export_dir = config.PROJECT_ROOT / "exports"
        export_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        if fmt == "json":
            path = export_dir / f"session_{ts}.json"
            data = {
                "session_id": audit._session_id,
                "model": self._llm.model,
                "exported_at": datetime.now().isoformat(),
                "entries": entries,
            }
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            path = export_dir / f"session_{ts}.md"
            lines = [
                "# MCP Terminal Assistant — Session Export",
                "",
                f"**Session:** {audit._session_id}  ",
                f"**Model:** {self._llm.model}  ",
                f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
                "",
                "---",
                "",
            ]
            for entry in entries:
                role = entry.get("role", "system")
                content = entry.get("content", "")
                ts_str = entry.get("ts", "")
                if role == "user":
                    lines.append(f"### `{ts_str}` You")
                    lines.append("```")
                    lines.append(content)
                    lines.append("```")
                else:
                    lines.append(f"**Assistant** ({ts_str})")
                    lines.append(content)
                lines.append("")
            path.write_text("\n".join(lines), encoding="utf-8")

        rel = path.relative_to(config.PROJECT_ROOT)
        self._show_toast(f"Exported → {rel}")

    # ── Key bindings ──────────────────────────────────────────────────────────

    def action_toggle_dry_run(self) -> None:
        self._handle_special("!dry-run")

    def action_clear_context(self) -> None:
        self._handle_special("!context clear")

    def action_show_help(self) -> None:
        self._handle_special("!help")

    def action_toggle_palette(self) -> None:
        if self._palette_visible:
            self._toggle_palette_off()
        else:
            self._palette_visible = True
            palette_container = self.query_one("#command-palette-container")
            palette_container.remove_class("hidden")
            self.query_one(CommandPalette).focus_input()

    def _toggle_palette_off(self) -> None:
        self._palette_visible = False
        self.query_one("#command-palette-container").add_class("hidden")
        self.query_one(InputBar).query_one("#cmd-input").focus()

    def action_export_session(self) -> None:
        self._export_session("md")

    def action_history_prev(self) -> None:
        self.query_one(InputBar).recall_previous()

    def action_history_next(self) -> None:
        self.query_one(InputBar).recall_next()

    def action_quit(self) -> None:
        self._buffer.save()
        self.exit()


def run_tui() -> None:
    app = MCPAssistantApp()
    app.run()
