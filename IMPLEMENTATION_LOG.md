# MCP Terminal Assistant — Implementation Log

> This file is the living context for the project. It records what has been
> done, what is being worked on, future plans, known problems, and architectural
> decisions. It is intended as the primary context document for any AI model
> that helps with implementation.
>
> Last updated: 2026-04-11
> Maintained by: K R Shrivathsan / Kartik Jhiremath

---

## Table of Contents

1. [Project Snapshot](#1-project-snapshot)
2. [Objectives](#2-objectives)
3. [Implementation History](#3-implementation-history)
4. [Current Status](#4-current-status)
5. [Known Problems & Gaps](#5-known-problems--gaps)
6. [Planned Work (Ordered by Priority)](#6-planned-work-ordered-by-priority)
7. [Architecture Decisions Log](#7-architecture-decisions-log)
8. [Key Technical Keywords & Their Status](#8-key-technical-keywords--their-status)
9. [Evaluation Results History](#9-evaluation-results-history)
10. [Portability Checklist](#10-portability-checklist)
11. [Deferred / Deprioritised Items](#11-deferred--deprioritised-items)

---

## 1. Project Snapshot

**What it is:** A local-first, AI-powered terminal assistant that translates
natural-language commands into structured tool invocations via the Model Context
Protocol (MCP). Users type sentences; the assistant executes real file, git,
system, and test operations — with full security enforcement and audit logging.

**Core invariant:** The LLM never executes anything. It produces a JSON intent.
The dispatcher validates and routes that intent. The LLM is a reasoning engine,
not a command executor.

**Stack (current):**
- Python 3.13 · Ollama `phi3:latest` (local) · Textual TUI · psutil · pytest
- Custom MCP implementation (MCPTool base, MCPDispatcher, ToolRegistry)
- SHA-256 chained JSONL audit log
- 80-item evaluation dataset with faithfulness reporting and ablation harness

**Stack (planned — 3-tier model architecture):**
- Tier 1 Router: `phi3:mini` (1.5B) — always resident; classifies intent + detects complexity
- Tier 2 Executor: configurable per complexity — 3B for simple, 5B for medium, 8B for heavy tasks
- Tier 3 Aggregator: 5B+ model — only for chain synthesis; structured output via Ollama `format`
- Graceful degradation: each tier falls back to the best available model; works on 8GB RAM with only two models
- See ADR-006 for full design and resource analysis

**Repo layout summary:**
```
mcp_assistant/
  config.py         — all constants, env-var overrides
  main.py           — entry point (TUI or --cli)
  llm/              — OllamaClient, PromptBuilder, response_parser, confidence
  mcp/              — schema, base, registry, dispatcher, policy
  tools/            — FileHandler, GitTool, SystemTool, TestRunner
  audit/            — SHA-256 chained JSONL logger + retention
  context/          — sliding-window ConversationBuffer
  tui/              — Textual app + widgets
  eval/             — dataset, metrics, harness, report
plugins/            — auto-discovered MCPTool plugins (e.g. TimeTool)
eval_data/          — eval_dataset.json (60 NL→tool ground-truth items)
eval_results/       — generated eval reports
.mcprc              — TOML security policy
```

---

## 2. Objectives

These are the North Stars for every implementation decision. After any change,
verify that the change moves us closer to all of these and does not regress any.

### O1 — Accuracy
**LLM-to-tool mapping must be reliable.**
- Tool accuracy ≥ 90%, Action accuracy ≥ 80% on eval dataset.
- Hallucination rate < 1% (LLM emits a tool name that does not exist).
- Parse failure rate < 5% (LLM output cannot be decoded as JSON).
- Faithfulness: the executed tool/action must actually fulfil the user's intent
  (not just match the action string in the dataset).

### O2 — Safety
**No destructive action runs without confirmation. No path escapes the sandbox.**
- Every write, delete, commit, kill_process requires explicit user confirmation.
- File paths are sandbox-checked via PolicyConfig before any I/O.
- Blocked paths (.env, .pem, .key, id_rsa, .ssh, secrets) are enforced at
  dispatch time, not just at tool time.
- Audit log must be tamper-evident (SHA-256 hash chain).

### O3 — Portability
**Run identically on macOS, Linux, and Windows (WSL). No hardcoded paths.**
- All paths resolved from PROJECT_ROOT (already done via config.py).
- **WORKSPACE_DIR concept**: the sandbox should default to `Path.cwd()` — the
  directory the user launched `mcp` from, not the package install location.
  `cd ~/myrepo && mcp` → assistant works on `~/myrepo`. This is the correct
  portable behaviour.
- .mcprc sandbox_root: empty = `WORKSPACE_DIR`; relative = resolved from CWD.
- Ollama endpoint is environment-variable driven (OLLAMA_BASE_URL already done).
- No `python3.13`-specific syntax that breaks on 3.11+ (use `sys.version` guard).
- Docker Compose target: `docker compose up` starts Ollama + assistant.
- Works on any device with Python 3.11+ and Ollama accessible on the network.

### O4 — Latency & Responsiveness
**User should never feel blocked.**
- Streaming token feedback in TUI while Ollama generates (perceived latency → 0).
- Mean end-to-end latency < 3 s on modern CPU hardware (p95 < 6 s).
- Incremental retry with exponential backoff on Ollama failures — never hang.
- Cold-storage LLM response cache (SQLite keyed by prompt hash) to skip re-inference
  on repeated queries.

### O5 — Extensibility
**Adding a new tool must not require touching core code.**
- Plugin SDK (MCPTool base class) is the only interface needed.
- FastMCP integration: tools can be exposed as MCP-compliant HTTP endpoints
  so external clients (Claude Desktop, other MCP hosts) can call them.
- Tool descriptions in the LLM system prompt are auto-generated from plugin metadata.

### O6 — Observability
**Every decision and execution must be traceable.**
- Audit log (hash-chained JSONL) captures every tool call with timing.
- Faithfulness score tracked per-call and aggregated in eval reports.
- Context window token count visible in TUI sidebar.
- Hallucination events logged separately with full LLM response for post-analysis.

### O8 — Resource Efficiency
**The tool must remain usable on modest hardware.**
- Default config requires ≤ 4GB RAM and works on any machine with Ollama.
- No mandatory large models. All performance enhancements are opt-in.
- Startup time < 5s. No blocking operations during initialisation.

### O7 — Academic Rigor
**The eval harness is a primary deliverable.**
- 60-item ground-truth dataset; expand to ≥ 100 items before final submission.
- Ablation study covers: context size × confidence threshold × model size.
- Metrics: Tool Acc, Action Acc, Parse Fail Rate, Hallucination Rate,
  Faithfulness Score, Mean/P95 latency.
- Comparison baseline: same queries run against a naïve "shell pass-through"
  and (if available) Amazon Q CLI / GitHub Copilot CLI.

---

## 3. Implementation History

### Phase 1 — Core Tool Framework ✅ (complete)
- MCPCall/MCPChain/MCPResult dataclass schema
- OllamaClient HTTP wrapper for Ollama /api/generate
- PromptBuilder (system + user prompt construction)
- ResponseParser (handles 4 phi3 output patterns: clean JSON, markdown-fenced,
  prose-wrapped, chain)
- ToolRegistry with plugin auto-discovery
- MCPDispatcher with policy enforcement (sandbox, whitelist, confirm gates)
- PolicyConfig loaded from .mcprc (TOML)

### Phase 2 — Tools ✅ (complete)
- FileHandler: read, write, list, search, delete (sandbox-enforced)
- GitTool: status, diff, log, add, commit, branch_list, branch_switch
- SystemTool: cpu_stats, ram_stats, disk_stats, list_processes, kill_process, env_info
- TestRunner: detect, run, run_file, explain_failures

### Phase 3 — Security & Audit ✅ (complete)
- SHA-256 hash-chained JSONL audit logger
- Audit log retention (cleanup by age)
- PolicyConfig with mutable dry_run_mode (Ctrl+D toggle)
- Confidence gating (clarification request on low-confidence LLM output)
- ConversationBuffer (sliding-window, persisted to ~/.mcp_assistant/context.json)

### Phase 4 — TUI ✅ (complete)
- Textual-based 3-panel TUI (StatsSidebar | HistoryPanel+InputBar | ToolInspector)
- Async worker pattern — Ollama calls don't block UI event loop
- Clarification flow (low-confidence → ask user, store pending call)
- Special commands: !help, !dry-run, !context, !verify
- Keyboard shortcuts: Ctrl+Q, Ctrl+D, Ctrl+L, F1

### Phase 5 — Evaluation Harness ✅ (complete)
- 60-item NL→tool ground-truth dataset across 5 categories
- EvalHarness with ablation study (4 conditions)
- Metrics: Tool Acc, Action Acc, Parse Fail Rate, Hallucination Rate, Latency
- Report generation (JSON + Markdown)
- 90 pytest tests, all passing

### Phase 6 — Prompt / Portability / Reliability Pass ✅ (2026-04-10)
- PromptBuilder upgraded with an explicit action-disambiguation table and
  6 few-shot examples targeting the highest-confusion tool/action pairs
- FileHandler, GitTool, SystemTool, and TestRunner action descriptions rewritten
  with stronger trigger words and counter-signals for small-model routing
- Added shared `llm/inference.py` so CLI and TUI use the same
  prompt -> Ollama -> parse retry pipeline
- Added exponential backoff + jitter to `OllamaClient.generate()`
- `.mcprc` now uses auto-detected sandbox roots; relative sandbox roots resolve
  from the `.mcprc` file location
- User-facing docs cleaned up to use `<project-root>` placeholders instead of
  a single developer's home directory
- SystemTool hardened for restricted macOS / sandboxed environments so RAM,
  process, and env queries degrade gracefully instead of failing
- TestRunner now shells out via `sys.executable`, improving portability when
  `python` is not on PATH

### Phase 7 — Performance / Interop / UX Pass ✅ (2026-04-10)
- Added a SQLite-backed LLM cache in `llm/cache.py`, plus `mcp-cache clear`
  and TUI `!cache clear` support
- ConversationBuffer is now token-aware via `llm/tokenizer.py`; the TUI
  sidebar and CLI context view now show context token counts
- TUI inference now streams Ollama output incrementally with a blocking
  fallback path if streaming or parsing fails
- Destructive actions in the TUI now use a real `ConfirmModal` instead of
  auto-confirming everything
- Added `fastmcp_server.py` and the `mcp-server` entry point for optional
  stdio / SSE FastMCP exposure without changing the Plugin SDK
- Eval harness now records a faithfulness score and the eval dataset was
  expanded from 60 to 80 items (IDs 61–80)
- Added Docker assets: `Dockerfile`, `docker-compose.yml`, `.dockerignore`,
  and Docker quickstart documentation
- Implemented a 3-tier model router with graceful fallbacks plus structured
  output routing when Ollama supports the `format` parameter
- Added optional terminal ecosystem delegation (`rg`, `fd`, `bat`, `delta`,
  `eza`/`exa`, `zoxide`) with Python fallbacks when those tools are absent
- Added Ollama performance optimisations: `keep_alive`, KV warm-up, in-memory
  tool result cache, prompt memoization, and dirty-flag context persistence
- Local verification after this phase: `102 passed, 1 skipped`

### Phase 8 — Workflow Orchestration Core ✅ (2026-04-11)
- Added a dedicated orchestration layer in `mcp_assistant/orchestration/graph.py`
  with a shared `GraphState`, named workflow nodes, route selection, node
  tracing, aggregation, and finalization
- Implemented a LangGraph-compatible builder (`build_orchestrator_graph`) plus
  a built-in fallback runner so the workflow contract works even if `langgraph`
  is not installed yet in the local environment
- Added `build_assistant_orchestrator(...)` so the orchestrator wraps the
  existing inference, dispatcher, tool registry, model router, and policy
  instead of replacing them
- CLI requests now run through the orchestrator end-to-end; low-confidence
  requests pause at the router/finalize stage for confirmation before execution
- TUI requests now enter the orchestrator directly so the graph owns the
  direct-vs-MCP decision in both UI modes
- Added orchestration tests covering graph branch selection, clarification
  gating, specialist routing, and chain execution
- Local verification after this phase: `106 passed, 1 skipped`

### Phase 9 — Full Workspace Scope ✅ (2026-04-11)
- Added `WORKSPACE_DIR` to config, defaulting to `MCP_WORKSPACE` when set and
  otherwise to the user's home directory
- Policy loading now treats an empty `.mcprc` `sandbox_root` as the active
  workspace root rather than the repository directory
- FileHandler, GitTool, and TestRunner now resolve relative paths and default
  working directories against `WORKSPACE_DIR` instead of `PROJECT_ROOT`
- Updated tests and user-facing docs to reflect workspace-root sandboxing
- Local verification after this phase: targeted workspace tests `42 passed`

### Phase 10 — Four-Role Orchestrator Routing ✅ (2026-04-11)
- Refactored the orchestration core so every request now flows through
  `classify -> planner -> router/direct -> aggregate -> finalize`
- The planner now decides whether the request should be answered directly by
  the LLM or routed into MCP tool execution for local workspace/state access
- Added a dedicated direct-response branch so conversational or conceptual
  queries can bypass MCP tools instead of being forced into `unknown` calls
- Aggregation now produces a structured payload (`status`, `mode`, `summary`,
  `details`, `tools_used`, `workflow`, `next_step`) before rendering the final
  text response
- Model routing now exposes separate classifier / planner / router /
  aggregator roles while still allowing all of them to default to a single
  installed local model
- Default model baseline switched to `dolphin-mistral:latest`, with env-based
  overrides preserved for each role
- TUI command handling now enters through the orchestrator directly rather than
  pre-resolving an MCP call before graph execution
- Local verification after this phase: `112 passed, 1 skipped`

---

## 4. Current Status

**As of 2026-04-11:**

| Component | Status | Notes |
|-----------|--------|-------|
| Core framework | ✅ Complete | Stable, tested; graph orchestration layer now wraps inference/dispatch |
| Tools (4) | ✅ Complete | Prompt disambiguation shipped; ecosystem-aware delegation added where available |
| Security / Audit | ✅ Complete | Hash chain verified |
| TUI | ✅ Complete | Graph-driven command flow, confirmation modal, structured final rendering |
| Eval harness | ✅ Complete | 80-item dataset, faithfulness metric, 112 passing tests locally |
| Streaming LLM output | ⚠️ Partial | Streaming helper exists, but the graph-first TUI path currently uses blocking orchestration |
| TUI confirmation modal | ✅ Complete | Destructive actions now prompt via Textual modal |
| FastMCP integration | ✅ Complete | Optional `mcp-server` wrapper for stdio / SSE |
| Shared inference pipeline | ✅ Complete | CLI and TUI share graph orchestration; MCP inference now lives inside router stage |
| Incremental retry / backoff | ✅ Complete | Exponential backoff + jitter in `OllamaClient.generate()` |
| Cold-storage LLM cache | ✅ Complete | SQLite cache keyed by prompt hash with CLI/TUI clear support |
| Token-aware context window | ✅ Complete | Token budget enforced with fallback tokenizer heuristic |
| Portable .mcprc | ✅ Complete | Empty root auto-resolves from `.mcprc` location |
| Docker Compose | ✅ Complete | Dockerfile, compose file, and quickstart docs added |
| Faithfulness tracking | ✅ Complete | Eval harness/report now emit faithfulness scores |
| Semantic tool lookup | ❌ Not done | Linear registry scan only |
| Eval dataset expansion | ⚠️ Partial | Expanded to 80 items; broader 100+ target still pending |
| 4-role model routing | ✅ Complete | Classifier / planner / router / aggregator roles with fallback chain |
| Structured output routing | ✅ Complete | Uses Ollama `format` schema when supported and request is not a chain |
| Terminal ecosystem integration | ✅ Complete | Optional delegation to ripgrep/fd/bat/delta/eza/zoxide |
| Ollama performance optimisations | ✅ Complete | `keep_alive`, KV warm-up, tool cache, prompt memoization, dirty saves |
| Workflow orchestration | ✅ Complete | LangGraph-style orchestrator decides direct LLM vs MCP, then aggregates structured output |
| Workspace scope | ✅ Complete | Default sandbox is now full user workspace root, overrideable via `MCP_WORKSPACE` |

**Evaluation results (2026-04-07, phi3:latest, no context window):**
- Tool Accuracy: 93.3% (target ≥ 90% — MET)
- Action Accuracy: 65.0% (target ≥ 80% — NOT MET, 15pp gap)
- Parse Failure Rate: 0.0% (target < 5% — MET)
- Hallucination Rate: 0.0% (target < 1% — MET)
- Mean Latency: 4209 ms (target < 3000 ms — NOT MET, 1.2x over)
- P95 Latency: 7888 ms (target < 6000 ms — NOT MET)

**2026-04-11 verification snapshot:**
- Full local test suite: `112 passed, 1 skipped in 2.18s`
- Compile sanity check: `python3 -m compileall mcp_assistant tests`
- Docker Compose file parses cleanly: `docker compose config`
- Eval dataset now contains exactly 80 items
- Post-implementation eval rerun: still blocked in this environment because
  Ollama was not running (`OllamaClient().is_available() -> False`)

---

## 5. Known Problems & Gaps

### P1 — Action Accuracy: FileHandler.search vs .list confusion (MITIGATED 2026-04-10)
The original ambiguity was addressed by:
- Rewriting all major tool action descriptions with stronger trigger words
- Adding an action-disambiguation table to the system prompt
- Adding 6 few-shot examples for the highest-confusion pairs

What remains:
- Re-run the eval harness with Ollama available to measure the actual post-fix
  Action Accuracy uplift and confirm no regression in Tool Accuracy

### P2 — TestRunner action accuracy (MITIGATED 2026-04-10)
The `detect` vs `run` ambiguity is covered by the same prompt and tool-summary
improvements as P1. Follow-up still needed: verify the gain via eval.

### P3 — GitTool: diff vs status confusion (MITIGATED 2026-04-10)
The prompt now includes explicit staged-change and line-level-diff examples.
This should reduce confusion for small models, but it still needs an eval rerun
to confirm the improvement quantitatively.

### P4 — TUI confirmation is auto-confirm (RESOLVED 2026-04-10)
The TUI now routes destructive confirmation through `ConfirmModal` via
`push_screen_wait()`. This restores the same confirmation gate semantics used
by the dispatcher instead of bypassing them.

### P5 — Portable sandbox roots (RESOLVED 2026-04-10)
`.mcprc` now uses an empty `sandbox_root`, and `PolicyConfig.load()` resolves:
- empty root -> directory containing `.mcprc`
- relative root -> relative to the `.mcprc` directory
- absolute root -> unchanged

This removes the hardcoded `/home/krshrivathsan/...` dependency from runtime
config and docs.

### P6 — No streaming token feedback (RESOLVED 2026-04-10)
TUI inference now streams tokens from `generate_stream_async()` into the
history panel and falls back to blocking inference if streaming fails.

### P7 — Retry/backoff on Ollama failures (RESOLVED 2026-04-10)
`OllamaClient.generate()` now retries transient connection and timeout errors
with exponential backoff and jitter. CLI and TUI both route through the shared
`infer_call()` helper, so parse-retry behavior is no longer duplicated.

### P8 — Context window is turn-count-based, not token-aware (RESOLVED 2026-04-10)
ConversationBuffer now counts tokens with a `tiktoken`-first strategy and a
defensive char/4 fallback, truncating oldest turns until the context fits
`MAX_CONTEXT_TOKENS`.

### P9 — No cold-storage LLM response cache (RESOLVED 2026-04-10)
Repeated identical structured requests now hit a SQLite cache keyed by the
prompt hash. The cache is persisted on disk and can be cleared from both the
CLI (`mcp-cache clear`) and the TUI (`!cache clear`).

### P10 — Not FastMCP-compliant (RESOLVED 2026-04-10)
The custom dispatcher remains the core runtime, but `fastmcp_server.py` now
wraps the existing tools as an optional FastMCP server exposed via the
`mcp-server` entry point.

### P11 — Missing Ollama-level performance optimisations (RESOLVED 2026-04-10)
The client now sends `keep_alive`, the app warms the KV prefix cache in the
background at startup, and the dispatcher uses a short-TTL in-memory tool
cache for read-only actions.

### P12 — System prompt rebuilt on every query (RESOLVED 2026-04-10)
`PromptBuilder.system_prompt()` is now memoized with `functools.lru_cache`,
and the cache is invalidated if the tool summary changes.

### P13 — ConversationBuffer saves to disk on every turn (RESOLVED 2026-04-10)
Conversation persistence now uses a dirty flag so the JSON file is only written
when there is new state to flush.

### P14 — No integration with existing terminal ecosystem tools (RESOLVED 2026-04-10)
The assistant now detects optional ecosystem tools (`rg`, `fd`, `bat`,
`delta`, `eza`/`exa`, `zoxide`) and delegates to them when helpful, while
keeping Python fallbacks for clean portability.

### P15 — No WORKSPACE_DIR concept; sandbox always points at install location (HIGH)
### P15 — No WORKSPACE_DIR concept; sandbox always points at install location (RESOLVED 2026-04-11)
The assistant now has a real `WORKSPACE_DIR` in config. By default it points at
the user's home directory, can be overridden with `MCP_WORKSPACE`, and is used
as the default sandbox root when `.mcprc` leaves `sandbox_root` empty.

### P16 — Single-model architecture limits both speed and quality (RESOLVED 2026-04-10)
The assistant now supports router / executor / aggregator model tiers with a
graceful fallback chain and structured-output routing when the installed
Ollama version supports it.

---

## 6. Planned Work (Ordered by Priority)

**2026-04-10 update:** Sprints D through L are now largely implemented in code.
The remaining follow-up work is to rerun the live Ollama evals, validate the
tooling on Windows/WSL, and expand the eval dataset from 80 items to the
longer-term 100+ target used for the final submission.

### Sprint A — Accuracy & Prompt Engineering (completed in code on 2026-04-10; eval rerun pending)
**Goal:** Push Action Accuracy from 65% to ≥ 80%.

1. Rewrite SUPPORTED_ACTIONS descriptions in all 4 tools:
   - Add explicit trigger words and counter-examples for ambiguous actions
   - FileHandler: clarify list (directory listing, "show what's in folder X") vs
     search (file discovery, "find files matching pattern")
   - TestRunner: clarify detect (probe framework) vs run (execute suite)
   - GitTool: clarify diff (line-level changes) vs status (staged/unstaged summary)

2. Add a "disambiguation table" to the system prompt:
   ```
   If the user says: "find", "search for", "look for", "grep" → action: search
   If the user says: "list", "show files in", "what's in" → action: list
   If the user says: "run tests", "execute tests", "test" → action: run
   If the user says: "detect framework", "what test tool" → action: detect
   ```

3. Add 3 few-shot examples to the system prompt (tool, action, params triples)
   covering the most commonly confused pairs.

4. Re-run eval after each change; commit only if Action Accuracy improves.

### Sprint B — Reliability: Retry & Backoff (completed 2026-04-10)
**Goal:** Ollama calls never hard-fail on transient errors.

Implement in `llm/client.py`:
```python
def generate(self, prompt, system="", temperature=0.1, max_retries=3) -> str:
    delay = 1.0
    for attempt in range(max_retries):
        try:
            response = self._post(prompt, system, temperature)
            return response
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(delay + random.uniform(0, 0.5))  # jitter
            delay = min(delay * 2, 30.0)               # cap at 30s
```

Separate retry for parse failures (already partially done in main.py with
MAX_PARSE_RETRIES=2): make this configurable, log each retry attempt.

### Sprint C — Portability (partially completed 2026-04-10)
**Goal:** `git clone → python -m mcp_assistant.main` works on any machine.

1. Fix .mcprc sandbox_root: completed using `""` (empty string) so the sandbox
   auto-resolves from the `.mcprc` file location. Relative roots also resolve
   from the `.mcprc` directory.

2. Add platform detection in SystemTool for Windows (WSL) differences in
   process management.

3. Create `Dockerfile` (single-stage, python:3.13-slim base) and
   `docker-compose.yml` (services: ollama + mcp-assistant).

4. Ensure all paths use `pathlib.Path` (already mostly done).

5. Update docs/USER_GUIDE.md with Docker quickstart section.

### Sprint D — Streaming TUI Output (fixes P6)
**Goal:** User sees tokens appearing as phi3 generates them.

1. In `tui/app.py`, replace `asyncio.to_thread(client.generate(...))` with an
   async generator wrapper around `client.generate_stream()`.

2. Post incremental `HistoryPanel.update_last_assistant` messages via Textual's
   message system as tokens arrive.

3. Show a spinner in InputBar while the first token has not arrived yet.

4. Graceful degradation: if streaming fails, fall back to blocking generate().

### Sprint E — TUI Confirmation Modal (fixes P4)
**Goal:** Destructive ops require visible y/n confirmation in TUI.

1. Create `tui/widgets/confirm_modal.py` — a Textual ModalScreen that shows
   the dry-run preview and a [y] / [n] button pair.

2. Wire it into dispatcher: replace `confirm_fn=lambda _: True` with an async
   function that calls `await app.push_screen_wait(ConfirmModal(preview))`.

3. Policy.requires_confirmation() drives when the modal appears (same logic
   as CLI — no duplication).

### Sprint F — Cold-Storage LLM Cache (fixes P9)
**Goal:** Repeated identical queries return instantly from cache.

Implementation in `llm/cache.py`:
- SQLite database at `~/.mcp_assistant/llm_cache.db`
- Table: `(prompt_hash TEXT PRIMARY KEY, response TEXT, ts REAL, ttl_s INTEGER)`
- Key: SHA-256(system_prompt + "\n\n" + user_prompt)
- TTL: 3600 s for structured calls (low-temp), 0 (disabled) for NL calls
- Cache hit: return stored response, log "cache_hit" flag in audit entry
- Cache miss: call Ollama, store result
- CLI command: `mcp-cache clear` to flush stale entries

This is the "cold storage" concept: the cache persists across sessions on disk,
so even after restart, frequently-used queries are fast.

### Sprint G — Token-Aware Context Window (fixes P8)
**Goal:** Context never exceeds model's token limit.

1. Add `token_count(text: str) -> int` utility in `llm/tokenizer.py`:
   - Prefer: `tiktoken.encoding_for_model("gpt2").encode(text)` length (≈ accurate)
   - Fallback: `len(text) // 4` (rough but zero-dependency estimate)

2. In `ConversationBuffer.get_context(n)`:
   - Count tokens of assembled context string
   - If > `MAX_CONTEXT_TOKENS` (config, default 3000), drop oldest turns until fits
   - Log "context_truncated" event when this happens

3. Add `context_tokens` to TUI StatsSidebar display.

### Sprint H — FastMCP Integration (addresses P10, achieves O5)
**Goal:** Tools are exposed as a proper MCP server callable from Claude Desktop
and other MCP hosts.

This is the most architecturally significant change. Two approaches:

**Approach A (Recommended): Dual-mode — FastMCP server + existing assistant**
- Add a `fastmcp_server.py` entry point that wraps existing tools as FastMCP tools
- The existing TUI/CLI remains unchanged
- New entry point: `mcp-server` (stdio transport for Claude Desktop, HTTP for network)
- FastMCP tool decorators call into the existing MCPTool.execute() implementations
- This reuses all existing security/audit logic via the dispatcher

**Approach B: Full refactor to FastMCP**
- Replace custom MCPTool base with FastMCP's `@mcp.tool()` decorator
- Higher rewrite cost, breaks Plugin SDK compatibility
- Not recommended for MVP

FastMCP server snippet (Approach A):
```python
from fastmcp import FastMCP
from mcp_assistant.mcp.dispatcher import MCPDispatcher
from mcp_assistant.mcp.schema import MCPCall

mcp = FastMCP("MCP Terminal Assistant")

@mcp.tool()
def git_status(cwd: str = ".") -> str:
    """Show git status for the current repository."""
    call = MCPCall(tool="GitTool", action="status", params={"cwd": cwd}, confidence=1.0)
    result = dispatcher.dispatch(call)
    return result.output

# ... one wrapper per tool action
```

### Sprint I — Eval Dataset Expansion & Faithfulness Metric
**Goal:** 100+ items; measure faithfulness (not just string-match accuracy).

1. Add 40+ eval items covering:
   - Edge cases: ambiguous intent, conflicting keywords
   - Multi-file operations (e.g., "read config.py and pyproject.toml")
   - System + file combos
   - More chain examples

2. Add faithfulness scoring to EvalResult:
   - Faithfulness = 1.0 if result.success and output is semantically relevant to nl_input
   - Semi-automated: use a second LLM call to judge "does this output answer the request?"
   - Store in eval report as separate metric

### Sprint J — 3-Tier Multi-Model Architecture (fixes P11)
**Goal:** Faster routing on simple queries; better quality on complex ones.
        Resource usage stays accessible — no user is forced to download >2 models.

---

#### Background & Design Rationale

The core observation: this assistant makes two categorically different types of
LLM calls, and a single model is a bad fit for both.

| Call type | What it needs | Current | Ideal |
|-----------|--------------|---------|-------|
| Intent routing (JSON) | Fast, deterministic, structured output | phi3 3.8B ~4s | phi3:mini 1.5B ~1s + schema enforcement |
| NL reasoning (explain, summarise) | Nuanced language, broader knowledge | phi3 3.8B (marginal) | 7B–8B+ model |
| Chain aggregation (structured synthesis) | Strong reasoning + structured JSON | phi3 3.8B (weak) | 5B–8B + format enforcement |

The 3-tier model routing pattern matches model size to task complexity.
The router (the smallest model) decides which executor tier handles each job.

---

#### The 3 Tiers

**Tier 1 — Router (always resident)**
- Model: `phi3:mini` (1.5B, ~1GB RAM, ~1GB storage)
- Job: Classify the user's intent into an MCPCall JSON. Also outputs a
  `complexity` field: `"routing"`, `"low"`, `"medium"`, `"high"`.
- Why a small model works here: JSON intent classification is a structured
  output task. With Ollama's `format` parameter (JSON schema enforcement via
  constrained sampling), even 1.5B models produce valid JSON reliably —
  eliminating parse failures almost entirely.
- Stays loaded in Ollama at all times (Ollama keeps the last used model hot
  for 5 minutes; router is called every query, so it never unloads).
- Latency: ~1s on CPU (vs 4s current). For the 80% of queries that are just
  routing calls, this is a 4× perceived improvement.

**Tier 2 — Executor (loaded on demand)**
- Three configurable slots, each defaulting to the next-available model:
  - `EXECUTOR_MODEL_LOW` — default: `phi3:latest` (3.8B). Used for actions
    whose output is simple: git status, cpu stats, list files.
  - `EXECUTOR_MODEL_MEDIUM` — default: same as LOW if unset. Used for
    moderately complex reasoning: git diff explanation, branch operations.
  - `EXECUTOR_MODEL_HIGH` — default: same as MEDIUM if unset. Used for
    heavy NL tasks: test failure explanation, diff summarisation.
- Only invoked for NL reasoning tasks (explain_failures, summarize_git_diff,
  clarification_prompt). For 80% of queries, this tier is never called.
- Ollama model switching overhead (~2–5s cold start) is acceptable here
  because these tasks already take 4–8s.

**Tier 3 — Aggregator (chain synthesis only)**
- Model: `AGGREGATOR_MODEL` — default: same as `EXECUTOR_MODEL_HIGH` if unset.
  Recommended for best quality: `mistral:7b` or `llama3.1:8b`.
- Job: after a multi-step chain completes, synthesise the step results into a
  structured final summary. Uses Ollama `format` parameter to guarantee schema.
- Only invoked when `MCPChain.steps` length ≥ 2 and all steps have completed.
- If only phi3:mini + phi3 are available, falls back to phi3 — same as today.

---

#### Complexity Detection Output (Tier 1 Router)

The router system prompt is extended to output a `complexity` field:

```json
{
  "tool": "TestRunner",
  "action": "explain_failures",
  "params": {"output": "..."},
  "confidence": 0.92,
  "complexity": "high"
}
```

Complexity classification rules injected into router's system prompt:
```
complexity = "routing" if the full answer is just the tool call (no NL needed after dispatch)
complexity = "low"     if the task returns structured data (cpu stats, git status, file list)
complexity = "medium"  if the task involves interpreting data (git diff, branch analysis)
complexity = "high"    if the task requires explanation or synthesis (explain_failures, summarize_diff)
```

The `complexity` field is stripped before the MCPCall is passed to the dispatcher.
It is only used to select the executor model for any subsequent NL call.

---

#### Fallback Chain (ensures accessibility on minimal hardware)

```
EXECUTOR_MODEL_HIGH → EXECUTOR_MODEL_MEDIUM → EXECUTOR_MODEL_LOW → ROUTER_MODEL
AGGREGATOR_MODEL    → EXECUTOR_MODEL_HIGH   → EXECUTOR_MODEL_LOW → ROUTER_MODEL
```

If a model is not available in Ollama, try `OllamaClient.list_models()` and
select the next available tier. Log which model was actually used.
If only the router model is available, all tasks fall back to it — this degrades
quality but never crashes.

---

#### Resource Impact Analysis

| Configuration | Models needed | Total download | Peak RAM | Suitable for |
|--------------|--------------|----------------|----------|--------------|
| Minimal (default) | phi3:mini + phi3:latest | ~3.3GB | ~3.3GB | 8GB RAM laptops |
| Medium quality | phi3:mini + phi3:latest + llama3.2:3b | ~6GB | ~4.3GB | 8GB RAM laptops |
| Full quality | phi3:mini + llama3.2:3b + llama3.1:8b | ~13GB | ~10GB | 16GB RAM machines |
| Max quality | phi3:mini + llama3.2:3b + mistral:7b + llama3.1:8b | ~20GB | ~15GB | 32GB workstations |

**The minimal configuration (default) uses only 1GB more RAM than today's single-model
setup while delivering faster routing for 80% of queries.** Users are not forced
to download additional models to use the tool.

---

#### Implementation Plan

1. In `config.py`, add multi-tier model constants:
   ```python
   ROUTER_MODEL: str           = os.environ.get("ROUTER_MODEL", "phi3:mini")
   EXECUTOR_MODEL_LOW: str     = os.environ.get("EXECUTOR_MODEL_LOW", OLLAMA_MODEL)
   EXECUTOR_MODEL_MEDIUM: str  = os.environ.get("EXECUTOR_MODEL_MEDIUM", EXECUTOR_MODEL_LOW)
   EXECUTOR_MODEL_HIGH: str    = os.environ.get("EXECUTOR_MODEL_HIGH", EXECUTOR_MODEL_MEDIUM)
   AGGREGATOR_MODEL: str       = os.environ.get("AGGREGATOR_MODEL", EXECUTOR_MODEL_HIGH)
   ```

2. In `llm/client.py`, make the model parameter per-call (not global):
   ```python
   def generate(self, prompt, system="", temperature=0.1, model: str | None = None) -> str:
       model = model or config.OLLAMA_MODEL
       # ... POST with model in request body
   ```

3. Create `llm/model_router.py` — a `ModelRouter` class that:
   - Selects which model to use based on call type and complexity
   - Checks `OllamaClient.list_models()` to verify availability
   - Falls back gracefully if preferred model is not installed
   - Logs which model was selected (for audit + eval analysis)

4. Add Ollama structured output to router calls:
   ```python
   # In OllamaClient, add format parameter support:
   payload = {
       "model": model,
       "prompt": prompt,
       "system": system,
       "stream": False,
       "options": {"temperature": temperature},
       "format": json_schema,  # new — enforces output schema
   }
   ```
   Define `MCPCall_SCHEMA` as a JSON Schema dict in `mcp/schema.py`.
   When routing, pass this schema → guaranteed valid JSON → parse failures → 0%.

5. Update `llm/inference.py` to use `ModelRouter`:
   ```python
   def infer_call(nl_input, client, builder, context=None, ...):
       # Phase 1: routing call (always uses ROUTER_MODEL)
       route_result = _route(nl_input, client, builder, context)  # fast, small model
       # Phase 2: if NL reasoning needed, use executor tier selected by router
       if requires_nl_followup(route_result):
           model = model_router.select_executor(route_result.complexity)
           nl_result = _reason(route_result, client, builder, model)
           return nl_result
       return route_result
   ```

6. Update the aggregator path in `mcp/dispatcher.py`'s `dispatch_chain()`:
   - After all steps complete, if `len(chain.steps) >= 2`:
     call `ModelRouter.select_aggregator()` and synthesise with structured output.

7. Add `model_used` field to `MCPResult` (and `AuditLogger`) so every call
   records which model actually handled it. This is valuable for eval analysis.

8. Add to eval report: per-model accuracy breakdown — does action accuracy
   improve when higher-tier models are used for complex tasks?

---

#### Olmega Structured Output (Critical Detail)

Ollama >= 0.1.34 supports `format` in the API request body. This can be either
`"json"` (freeform JSON) or a full JSON Schema object. When a schema is provided,
Ollama uses constrained sampling (grammar-based decoding) to guarantee the output
matches the schema exactly — even with a 1.5B model.

This means:
- Router (1.5B) with `format=MCPCall_SCHEMA` → parse failure rate ≈ 0% (replaces all parse retry logic)
- Aggregator with `format=ChainSummary_SCHEMA` → structured synthesis guaranteed
- This is NOT available for phi3:mini in all Ollama versions — add version check at startup

Add to startup health check in `main.py`:
```python
version = client.ollama_version()  # new method
if version < (0, 1, 34):
    warnings.warn("Ollama < 0.1.34: structured output not available. Upgrade for better routing accuracy.")
```

### Sprint K — Terminal Ecosystem Integration (fixes P14)
**Goal:** Delegate heavy lifting to best-in-class open-source terminal tools
        instead of reimplementing in Python. Detect at startup, use if available,
        fall back to Python if not. Zero new hard dependencies.

---

**The pattern for every integration:**
```python
import shutil

def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None
```
Check at tool init time, cache the result, branch on it.

---

#### Tool-by-Tool Integrations

**FileHandler.search → ripgrep (`rg`) or fd (`fd`)**
- rg is 10–100× faster than Python glob on large repos (written in Rust, parallel)
- fd is faster than Python's `pathlib.rglob` for name-pattern searches
- Both handle `.gitignore` natively (respects ignore rules automatically)
```python
if _has("rg"):
    # rg --files -g <pattern> <path>  — lists files matching glob pattern
    proc = subprocess.run(["rg", "--files", "-g", pattern, str(path)], ...)
elif _has("fd"):
    # fd <pattern> <path>
    proc = subprocess.run(["fd", pattern, str(path)], ...)
else:
    # Python glob fallback (current implementation)
    results = list(Path(path).rglob(pattern))
```

**FileHandler.read display → bat**
- `bat` is `cat` with syntax highlighting, line numbers, git change markers
- When displaying file contents in TUI or CLI, pipe through bat if available
- Falls back to plain text — no visual change to the user when bat is absent
```python
if _has("bat"):
    proc = subprocess.run(["bat", "--color=always", "--style=numbers", path], ...)
    output = proc.stdout
else:
    output = Path(path).read_text()
```

**GitTool.diff display → delta**
- `delta` renders git diffs with syntax highlighting, side-by-side view, line numbers
- Pipe raw `git diff` output through `delta --color-only` for TUI-compatible output
- Falls back to raw diff string — GitTool logic is unchanged
```python
if _has("delta"):
    diff_raw = subprocess.run(["git", "diff", ...], capture_output=True).stdout
    enhanced = subprocess.run(["delta", "--color-only"], input=diff_raw, ...).stdout
    return enhanced.decode()
else:
    return subprocess.run(["git", "diff", ...], capture_output=True, text=True).stdout
```

**Directory resolution → zoxide (`z` / `zoxide query`)**
- zoxide is a smarter `cd` that learns from your navigation history
- When a tool call has a vague `cwd` param ("my project", "the backend folder"),
  resolve it via `zoxide query --list <fuzzy>` before dispatching
- This is an optional enhancement; if zoxide is absent, cwd params are used as-is
```python
def _resolve_cwd(cwd_hint: str) -> str:
    if _has("zoxide") and not Path(cwd_hint).is_absolute():
        result = subprocess.run(
            ["zoxide", "query", "--", cwd_hint],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
    return cwd_hint
```

**FileHandler.list display → eza (or exa)**
- `eza` is a modern replacement for `ls` with colours, icons, tree view
- Use for richer directory listings in the TUI history panel
```python
if _has("eza"):
    proc = subprocess.run(["eza", "--long", "--colour=always", str(path)], ...)
elif _has("exa"):  # older name
    proc = subprocess.run(["exa", "--long", "--colour=always", str(path)], ...)
else:
    # current Python implementation
```

---

#### Capability Detection at Startup

Add `llm/ecosystem.py`:
```python
"""Detects available terminal ecosystem tools at startup."""
import shutil

AVAILABLE = {
    "rg":     shutil.which("rg") is not None,      # ripgrep
    "fd":     shutil.which("fd") is not None,      # fd-find
    "bat":    shutil.which("bat") is not None,     # bat (cat with wings)
    "delta":  shutil.which("delta") is not None,   # git-delta
    "eza":    shutil.which("eza") is not None,     # eza (modern ls)
    "exa":    shutil.which("exa") is not None,     # exa (older name)
    "zoxide": shutil.which("zoxide") is not None,  # zoxide (smart cd)
    "fzf":    shutil.which("fzf") is not None,     # fzf (fuzzy finder)
}

def report() -> str:
    found    = [k for k, v in AVAILABLE.items() if v]
    missing  = [k for k, v in AVAILABLE.items() if not v]
    return (
        f"Terminal tools found: {', '.join(found) or 'none'}\n"
        f"Optional enhancements available if installed: {', '.join(missing)}"
    )
```
Print `ecosystem.report()` at startup (INFO level). Shows users what they're
missing without requiring anything.

---

#### Portability / No Hard Dependencies
- All integrations are strictly optional. Nothing in requirements.txt changes.
- Every code path has a Python fallback tested in CI (tests run without any of
  these tools installed, same as today).
- Document recommended installs in USER_GUIDE.md under "Optional Enhancements".
- Do not shell-inject user input into subprocess calls directly — always pass
  as list args (already the pattern in GitTool, TestRunner).

---

### Sprint L — Ollama Performance Optimisations (fixes P11)
**Goal:** Eliminate hidden latency sources in the Ollama integration layer.

---

#### L1 — `keep_alive` parameter (prevents cold-start on idle)

Add to `OllamaClient._build_payload()`:
```python
payload["keep_alive"] = -1   # -1 = never unload; "5m" = keep for 5 min
```
Or expose as config:
```python
OLLAMA_KEEP_ALIVE: str = os.environ.get("OLLAMA_KEEP_ALIVE", "-1")
```
With `-1`, the model stays loaded until `ollama serve` is restarted. No cold
starts, ever. This costs RAM (the model stays in RAM permanently) — accept the
tradeoff for the router model (1.5B = ~1GB); make it configurable for larger ones.

Impact: eliminates 2–5s cold-start after any idle period.

---

#### L2 — KV prefix cache warm-up (saves 0.5–1s per query)

At application startup, after Ollama is confirmed available, send one warm-up
generation with the system prompt only:
```python
def warm_up_kv_cache(client: OllamaClient, builder: PromptBuilder) -> None:
    """Pre-populate Ollama's KV cache for the system prompt prefix."""
    system = builder.system_prompt()
    try:
        client.generate(
            prompt=".",           # minimal user prompt (discarded)
            system=system,
            temperature=0.0,
            model=config.ROUTER_MODEL,
        )
    except Exception:
        pass  # non-fatal; real queries will populate the cache on first use
```
Call this once in `main.py` after startup health check, in a background thread
so it doesn't delay the TUI appearing. The KV state for the system prompt prefix
is then cached by Ollama for all subsequent requests.

Impact: saves ~0.5–1s on every query after the first.

---

#### L3 — Tool result cache (prevents redundant subprocess calls)

Add `mcp_assistant/mcp/tool_cache.py`:
```python
"""
Short-TTL in-memory cache for idempotent tool results.
Keyed by (tool_name, action, frozen_params). TTL: 15 seconds default.
Only caches read-only actions (never write, delete, commit, kill_process).
"""
import time, json, hashlib
from mcp_assistant.mcp.schema import MCPCall, MCPResult

# Actions that are safe to cache (read-only, deterministic over short window)
CACHEABLE_ACTIONS = {
    "FileHandler":  {"list", "search", "read"},
    "GitTool":      {"status", "diff", "log", "branch_list"},
    "SystemTool":   {"cpu_stats", "ram_stats", "disk_stats", "list_processes", "env_info"},
    "TestRunner":   {"detect"},
}

_CACHE: dict[str, tuple[MCPResult, float]] = {}
TOOL_CACHE_TTL: int = 15  # seconds

def _key(call: MCPCall) -> str:
    params_str = json.dumps(call.params, sort_keys=True)
    raw = f"{call.tool}:{call.action}:{params_str}"
    return hashlib.sha256(raw.encode()).hexdigest()

def get(call: MCPCall) -> MCPResult | None:
    if call.action not in CACHEABLE_ACTIONS.get(call.tool, set()):
        return None
    entry = _CACHE.get(_key(call))
    if entry is None:
        return None
    result, ts = entry
    if time.time() - ts > TOOL_CACHE_TTL:
        del _CACHE[_key(call)]
        return None
    return result

def put(call: MCPCall, result: MCPResult) -> None:
    if call.action not in CACHEABLE_ACTIONS.get(call.tool, set()):
        return
    _CACHE[_key(call)] = (result, time.time())

def clear() -> None:
    _CACHE.clear()
```

Wire into `MCPDispatcher.dispatch()` — check cache before executing, store on
cache miss:
```python
# After policy/validation checks, before tool.execute():
cached = tool_cache.get(call)
if cached:
    cached.data["from_cache"] = True
    return cached

result = tool.execute(call)
tool_cache.put(call, result)
```
The `from_cache` flag in `result.data` lets the TUI show a subtle "cached"
indicator and lets the eval harness exclude cached results from latency measurements.

---

#### L4 — System prompt memoization (trivial, zero cost)

In `prompt_builder.py`:
```python
import functools

class PromptBuilder:
    ...
    @functools.lru_cache(maxsize=1)
    def system_prompt(self) -> str:
        return _SYSTEM_PROMPT_TEMPLATE.format(tool_summary=self._tool_summary)
```
One line. Eliminates repeated `str.format()` calls on the ~500-char template.
Invalidate by calling `self.system_prompt.cache_clear()` if tool_summary changes.

---

#### L5 — ConversationBuffer dirty-flag saves

In `context/buffer.py`:
```python
def add_turn(self, role, content, call=None):
    self._turns.append(...)
    if len(self._turns) > self._max_turns * 2:
        self._turns = self._turns[-(self._max_turns * 2):]
    self._dirty = True   # ← mark as needing save

def save(self):
    if not self._dirty:
        return          # ← skip if nothing changed
    # ... existing write logic ...
    self._dirty = False
```
On clean exit (`Ctrl+Q`), force a final `save()` regardless of dirty flag.

---

#### L6 — Eval harness async execution (dev-time speed-up)

In `eval/harness.py`, run eval items concurrently with `asyncio.gather`:
```python
import asyncio

async def _run_item_async(item, client, builder, dispatcher, ...):
    # wrap blocking infer_call + dispatch in asyncio.to_thread
    call = await asyncio.to_thread(infer_call, ...)
    result = await asyncio.to_thread(dispatcher.dispatch, call)
    return _build_eval_result(item, call, result)

async def run_all_async(self, concurrency: int = 4):
    semaphore = asyncio.Semaphore(concurrency)
    async def _bounded(item):
        async with semaphore:
            return await _run_item_async(item, ...)
    return await asyncio.gather(*[_bounded(item) for item in self._dataset])
```
`concurrency=4` means 4 items in flight simultaneously. Ollama queues extras.
HTTP round-trips overlap. At 4× concurrency, eval time drops from ~6min to ~2min.
Use `concurrency=1` (default, same as today) when `--sequential` flag is passed.

---

## 7. Architecture Decisions Log

### ADR-001: Custom MCP vs FastMCP (2026-04-10)
**Decision:** Keep custom implementation for now; add FastMCP as an optional
server mode (Sprint H, Approach A).
**Rationale:** Rewriting core dispatch to FastMCP would break the Plugin SDK
and the existing 65 tests. Wrapping is lower risk. FastMCP adds interoperability
without disruption.
**Revisit when:** FastMCP stabilizes its Python SDK API; or if a complete rewrite
is feasible before final submission.

### ADR-002: Ollama as sole LLM backend (ongoing)
**Decision:** Ollama is the primary backend. Config supports env-var override.
**Rationale:** Privacy (no cloud), no API cost, reproducible evaluation.
**Alternatives considered:**
- OpenAI-compatible endpoint (can point at LM Studio, llama.cpp): supported
  via OLLAMA_BASE_URL pointing at any OpenAI-compatible server
- Cloud models: opt-in via environment variable; not default
**Revisit when:** Need higher accuracy and GPU is available.

### ADR-003: JSONL audit log (2026-04-07)
**Decision:** Append-only JSONL with SHA-256 hash chain.
**Rationale:** Simple, streaming-friendly, human-readable, tamper-evident.
**Limitation:** Not queryable without parsing; no indexing.
**Future option:** SQLite secondary index over the JSONL for query support.

### ADR-004: Textual for TUI (2026-04-07)
**Decision:** Textual (async-native Python TUI).
**Rationale:** Python-native, CSS-based layout, active development.
**Known issue:** Internal `_registry` name collision (use `_tool_registry`).
**Alternative:** Rich alone (simpler, less interactive); Urwid (more control).

### ADR-005: phi3:latest as default model (2026-04-07)
**Decision:** phi3 3.8B Q4_0 as default model.
**Rationale:** Runs on CPU, fast-ish, good enough JSON formatting.
**Known gap:** Action accuracy 65% (vs target 80%). Swap to llama3.1:8b for
accuracy at cost of latency.
**Switchable via:** `OLLAMA_MODEL=llama3.1:8b mcp` (zero code change).

### ADR-006: 3-Tier Multi-Model Architecture (2026-04-10)
**Decision:** Implement a 3-tier model routing system: Router (1.5B) →
Executor (3B/5B/8B, selected by router based on complexity) →
Aggregator (5B+, chain synthesis only).

**Rationale:**
Single-model architectures force a binary choice: small (fast but weak) or
large (slow but capable). Task complexity in this assistant is bimodal — most
queries are simple JSON routing (perfect for 1.5B) and a minority require
deep NL reasoning (benefits from 7B+). Tiered routing matches model to task.

**Feasibility strategy:**
- All tiers are configurable via env vars with a graceful fallback chain
- Default config requires only phi3:mini + phi3:latest (~3.3GB total) — 1GB more
  than today, but routing becomes 4× faster for 80% of queries
- Larger executor/aggregator models are opt-in, not required
- Ollama structured output (`format` JSON Schema parameter) lets even the 1.5B
  router produce guaranteed-valid JSON without grammar retries

**Rejected alternatives:**
- A: Single weak model (phi3:mini) for everything — accuracy regresses on
  NL reasoning tasks (test failure explanation quality drops significantly)
- B: Single strong model (llama3.1:8b) for everything — requires 5GB+ RAM,
  4–8s latency per query including trivial ones, overkill for routing
- C: Separate embedding model for semantic tool lookup — adds another download
  and startup cost; router-complexity-based selection is simpler and sufficient
  at the current tool count (≤ 20 tools)

**Resource impact (per configuration):**
- Minimal (phi3:mini + phi3): +1GB RAM vs today, 4× faster on simple queries
- Medium (+ llama3.2:3b): +2GB RAM, better NL reasoning
- Full (+ llama3.1:8b): requires 16GB RAM, best quality on complex tasks

**Revisit when:** Tool count exceeds ~50 (then semantic lookup becomes worth
it), or if Ollama adds automatic multi-model caching that keeps all tiers hot.

---

## 8. Key Technical Keywords & Their Status

These were the keywords specified by the project owner. Each maps to a design
concern and a sprint.

| Keyword | What It Means Here | Current Status | Sprint |
|---------|--------------------|----------------|--------|
| **FastMCP** | fastmcp Python library for MCP-compliant tool servers | Optional `mcp-server` wrapper implemented | Sprint H |
| **Tools** | MCPTool subclasses (File, Git, System, Test, plugins) | 4 core + 1 plugin | Ongoing |
| **Context Window** | ConversationBuffer token budget for LLM history | Token-aware with fallback tokenizer heuristic | Sprint G |
| **Hallucinations** | LLM emitting non-existent tool names | 0% on last measured eval; structured output now used when supported | Sprint J |
| **Efficient Tool Lookups** | How router maps NL intent to tool+action | Prompt disambiguation + schema routing improved; semantic lookup still deferred | Sprint J |
| **MCP Routes** | How MCPCall maps to a tool and executes | Dispatcher → Registry.get(name) → tool.execute(); optional FastMCP stdio/SSE wrappers added | Sprint H |
| **Faithfulness** | Does the executed action actually answer the user's intent? | Measured and reported in eval harness | Sprint I |
| **Incremental Retry Backoff** | Exponential backoff on Ollama timeouts/failures | Implemented in `OllamaClient.generate()` | Sprint B |
| **Cold Storage** | Disk-persisted LLM response cache across sessions | SQLite cache implemented | Sprint F |
| **Multi-Model / Model Tiering** | Different models for router vs executor vs aggregator | Implemented with graceful fallback chain | Sprint J |
| **Structured Output** | Ollama `format` JSON Schema parameter for guaranteed-valid JSON | Used for supported router calls when Ollama >= 0.1.34 | Sprint J |
| **Complexity Routing** | Router detects query complexity and selects executor model tier | Implemented for NL reasoning flows | Sprint J |

---

## 9. Evaluation Results History

| Date | Model | Tool Acc | Action Acc | Parse Fail | Halluc | Mean Latency |
|------|-------|----------|------------|-----------|--------|--------------|
| 2026-04-07 | phi3:latest | 93.3% | 65.0% | 0.0% | 0.0% | 4209 ms |

**Targets:** Tool ≥ 90%, Action ≥ 80%, Parse < 5%, Halluc < 1%, Latency < 3000 ms.

**2026-04-10 note:** prompt-disambiguation, shared inference, streaming TUI,
LLM/tool caching, FastMCP wrapping, token-aware context, faithfulness metrics,
and model routing were implemented and covered by the local pytest suite
(`102 passed, 1 skipped`), but the live Ollama-backed eval harness was not
rerun because Ollama was not available in this environment at implementation time.

**Known failure patterns from 2026-04-07 run:**
- FileHandler: list vs search confusion (IDs 6,7,9,10,12,13,14,15) — 8 items
- TestRunner: detect vs run confusion (IDs 48,49,50,52,55) — 5 items
- GitTool: status vs diff confusion (IDs 24,25,26) — 3 items
- SystemTool: cpu_stats when ram/proc/env intended (IDs 32,40,43) — 3 items
- One anomaly: ID 47 took 35029 ms (20× normal) — investigate Ollama queue

---

## 10. Portability Checklist

These are the specific changes needed to make the project work on any device:

- [x] `.mcprc` sandbox_root: hardcoded path removed; empty sandbox roots now
      auto-resolve from the `.mcprc` file location
- [x] `docs/USER_GUIDE.md`: hardcoded project path replaced with `<project-root>`
- [x] `docs/KNOWLEDGE_TRANSFER.md`: hardcoded project path replaced with `<project-root>`
- [x] Test on macOS (darwin) — PATH differences for git, pytest
      `TestRunner` now uses `sys.executable`, and SystemTool has restricted-env fallbacks
- [ ] Test on Windows (WSL) — psutil process names differ; path separators
- [x] Docker Compose: `docker-compose.yml` with ollama + mcp-assistant services
- [x] Dockerfile: python:3.13-slim, installs requirements, sets OLLAMA_BASE_URL
- [ ] Python version: add `if sys.version_info < (3, 11)` guard with clear error
      (`pyproject.toml` now declares `requires-python >=3.11`; runtime guard still pending)
- [x] requirements.txt: add `tomli; python_version < "3.11"` fallback
- [ ] config.py: OLLAMA_BASE_URL env var already exists — ensure documented

---

## 11. Deferred / Deprioritised Items

These are low-priority or out-of-scope for current sprints but worth noting:

- **Benchmark vs cloud assistants**: compare same 60 queries against Amazon Q CLI
  / GitHub Copilot CLI. Requires manual evaluation; deferred to final paper phase.
- **Shell integration**: Zsh/Bash/Fish keybind to lift current command into assistant.
  Good UX feature, but not core to academic deliverable.
- **Docker tool plugin**: `plugins/docker_tool/` — add container management.
  Blocked on portability (Docker not available in all eval environments).
- **Database inspector plugin**: read-only SQLite tool. Good demo, low priority.
- **Pydantic schema validation**: pydantic is installed but unused. MCPCall/MCPResult
  could use pydantic models for stronger validation. Low priority.
- **Multiple concurrent tool registries**: for multi-project use. Out of scope.
- **Web UI**: Replace Textual TUI with a browser-based UI. Out of scope for terminal
  assistant; would change the fundamental premise of the project.

---

*This log is the source of truth for project state. Update it whenever a sprint
completes, a new problem is found, or an architectural decision is made.*
