# MCP Terminal Assistant — Knowledge Transfer Document

> This document is written for the next developer taking over this project.
> It assumes Python familiarity but no prior knowledge of this codebase.
> Read this before touching any code.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Repository Layout](#2-repository-layout)
3. [Architecture — How the Pieces Connect](#3-architecture--how-the-pieces-connect)
4. [Component Reference](#4-component-reference)
5. [Data Flow — A Single Command End to End](#5-data-flow--a-single-command-end-to-end)
6. [The Plugin SDK — Adding New Tools](#6-the-plugin-sdk--adding-new-tools)
7. [Policy System — `.mcprc`](#7-policy-system--mcprc)
8. [Audit Log — Format and Verification](#8-audit-log--format-and-verification)
9. [Evaluation Harness](#9-evaluation-harness)
10. [Running Tests](#10-running-tests)
11. [Environment Setup from Scratch](#11-environment-setup-from-scratch)
12. [Known Limitations and Design Decisions](#12-known-limitations-and-design-decisions)
13. [Where to Go Next — Suggested Improvements](#13-where-to-go-next--suggested-improvements)
14. [Dependency Map](#14-dependency-map)

---

## 1. Project Overview

**What it is:** A Python application that wraps a local LLM (Ollama/phi3) with
a structured tool invocation protocol (MCP — Model Context Protocol). Users
type natural-language commands; the LLM maps them to tool calls; the tool
connectors execute real operations.

**What makes it different from raw shell AI:**
- The LLM never executes shell commands directly — it only emits structured
  JSON describing *which tool* and *which action* to call.
- A policy engine (`PolicyConfig`) enforces path sandboxing, tool whitelists,
  and confirmation gates before anything destructive runs.
- Every tool invocation is written to a SHA-256 chained audit log.

**Stack:**
- Python 3.13
- Ollama (`phi3:latest`) running locally on `localhost:11434`
- Textual 8.x for the TUI
- psutil for system stats
- No cloud services, no internet required at runtime

**Academic context:** 12-credit major project. The evaluation harness
(`eval/`) is the primary research deliverable — it measures intent accuracy,
latency, and hallucination rate across 60 hand-crafted test cases.

---

## 2. Repository Layout

```
MajorProject/
│
├── mcp_assistant/              ← Main Python package
│   ├── config.py               ← All constants and path resolution
│   ├── main.py                 ← Entry point; routes to TUI or CLI
│   │
│   ├── llm/                    ← LLM communication layer
│   │   ├── client.py           ← HTTP client for Ollama API
│   │   ├── prompt_builder.py   ← Builds system + user prompts
│   │   ├── response_parser.py  ← Parses LLM output → MCPCall/MCPChain
│   │   └── confidence.py       ← Decides whether to ask for clarification
│   │
│   ├── mcp/                    ← Protocol and dispatch layer
│   │   ├── schema.py           ← MCPCall, MCPResult, MCPChain dataclasses
│   │   ├── base.py             ← MCPTool abstract base (Plugin SDK)
│   │   ├── registry.py         ← Tool registration + plugin auto-discovery
│   │   ├── dispatcher.py       ← Routing, policy checks, dry-run, audit
│   │   └── policy.py           ← PolicyConfig loaded from .mcprc
│   │
│   ├── tools/                  ← Concrete tool implementations
│   │   ├── file_handler.py     ← FileHandler — read/write/list/search/delete
│   │   ├── git_tool.py         ← GitTool — git operations via subprocess
│   │   ├── system_tool.py      ← SystemTool — psutil metrics + process mgmt
│   │   └── test_runner.py      ← TestRunner — pytest/jest runner
│   │
│   ├── audit/
│   │   ├── logger.py           ← SHA-256 chained JSONL audit log
│   │   └── retention.py        ← Deletes old log files by age
│   │
│   ├── context/
│   │   └── buffer.py           ← Conversation memory (sliding window)
│   │
│   ├── tui/                    ← Textual terminal UI
│   │   ├── app.py              ← Root App — wires everything together
│   │   ├── theme.py            ← Textual CSS layout
│   │   └── widgets/
│   │       ├── stats_sidebar.py   ← Left panel: live CPU/RAM/disk
│   │       ├── history_panel.py   ← Center: conversation scroll log
│   │       ├── tool_inspector.py  ← Right: last MCPCall details
│   │       └── input_bar.py       ← Bottom: NL input field
│   │
│   └── eval/                   ← Evaluation / research layer
│       ├── dataset.py          ← Loads eval_dataset.json
│       ├── metrics.py          ← EvalResult, EvalReport dataclasses + calculations
│       ├── harness.py          ← Runs evaluations, ablation study, CLI
│       └── report.py           ← Renders JSON + Markdown reports
│
├── plugins/                    ← Drop-in tool plugins (auto-discovered)
│   └── example_plugin/
│       └── tool.py             ← TimeTool — demonstrates the Plugin SDK
│
├── eval_data/
│   └── eval_dataset.json       ← 60 NL commands with ground-truth tool calls
│
├── eval_results/               ← Generated at runtime by the eval harness
├── audit_logs/                 ← Generated at runtime; gitignored
│
├── tests/                      ← pytest suite (65 tests)
│   ├── conftest.py             ← Shared fixtures
│   ├── test_schema.py
│   ├── test_response_parser.py
│   ├── test_policy.py
│   ├── test_audit.py
│   ├── test_dispatcher.py
│   ├── test_context_buffer.py
│   ├── test_plugin_sdk.py
│   ├── test_tools.py
│   └── test_eval.py
│
├── .mcprc                      ← Project policy file (TOML)
├── pyproject.toml              ← Package metadata + pytest config
└── requirements.txt            ← All dependencies
```

---

## 3. Architecture — How the Pieces Connect

The system has four clearly separated layers. Dependencies only flow downward:

```
┌─────────────────────────────────────────────────────────┐
│  INPUT LAYER                                            │
│  TUI (tui/app.py)  or  CLI loop (main.py)              │
└─────────────────────────┬───────────────────────────────┘
                          │ natural-language string
┌─────────────────────────▼───────────────────────────────┐
│  REASONING LAYER                                        │
│  OllamaClient → PromptBuilder → response_parser        │
│  → MCPCall or MCPChain dataclass                        │
└─────────────────────────┬───────────────────────────────┘
                          │ MCPCall / MCPChain
┌─────────────────────────▼───────────────────────────────┐
│  ACTION LAYER                                           │
│  MCPDispatcher (policy checks + audit logging)         │
│  → ToolRegistry.get(tool_name)                         │
│  → MCPTool.execute(call) → MCPResult                   │
└─────────────────────────┬───────────────────────────────┘
                          │ MCPResult
┌─────────────────────────▼───────────────────────────────┐
│  OUTPUT LAYER                                           │
│  HistoryPanel / ToolInspector (TUI) or print (CLI)     │
│  ConversationBuffer.add_turn(...)                       │
└─────────────────────────────────────────────────────────┘
```

**Key invariant:** The LLM never executes anything. It only produces a JSON
object naming a tool and action. The dispatcher is the sole executor, and it
always checks policy before calling `execute()`.

---

## 4. Component Reference

### `mcp/schema.py` — Shared Data Types

Everything in the system is expressed through these four types:

```python
MCPCall(tool, action, params, raw_response, confidence)
MCPResult(call, success, output, data, error, duration_ms)
MCPChainStep(tool, action, params, confidence)
MCPChain(steps, description, continue_on_error)
```

If you add fields here, update `to_dict()` methods and the eval harness.

---

### `llm/client.py` — OllamaClient

POSTs to `http://localhost:11434/api/generate`. Key methods:
- `generate(prompt, system, temperature)` → `str` — blocking, returns full response
- `generate_stream(...)` → `Iterator[str]` — yields tokens (used for future streaming)
- `is_available()` → `bool` — quick health check

Temperature is set to `0.1` for structured tool-call generation (low entropy
= more deterministic JSON) and `0.7` for natural-language prompts like
test-failure explanations.

---

### `llm/prompt_builder.py` — PromptBuilder

Constructs two prompts for every query:

1. **System prompt** — Injected once per session. Contains: JSON format rules,
   chain trigger instructions, and the full tool registry summary (every tool
   name, description, and action). This is what teaches the LLM what tools
   exist.

2. **User prompt** — Built per query. Prepends conversation history (last N
   turns from `ConversationBuffer`), then appends the current query.

**Critical:** If you add a new tool, call `registry.generate_summary()` and
pass the result to `PromptBuilder(tool_summary=...)`. Without this, the LLM
doesn't know the tool exists.

---

### `llm/response_parser.py` — parse_response()

phi3 does not always return clean JSON. This module handles four output
formats that phi3 produces in practice:

| Format | Example |
|---|---|
| Clean JSON | `{"tool": "GitTool", ...}` |
| Markdown-fenced | ` ```json\n{...}\n``` ` |
| Prose-wrapped | `Sure! Here is the answer:\n{...}` |
| Chain | `{"chain": true, "steps": [...]}` |

The fallback path uses `re.search(r'\{.*\}', text, re.DOTALL)` to extract
JSON from anywhere in the response.

If parsing fails after `MAX_PARSE_RETRIES` (default 2), the harness appends
`"REMINDER: Respond ONLY with valid JSON."` to the next attempt.

**Returns:** `MCPCall` or `MCPChain`. Raises `ParseError` on unrecoverable failure.

---

### `mcp/dispatcher.py` — MCPDispatcher

The central security enforcement point. For every `dispatch(call)` call:

1. Tool must exist in registry → else return failure result
2. Tool must be allowed by policy → else return failure result
3. `tool.validate_params(call)` → else return failure result
4. If `dry_run_mode` OR action in `confirm_required` OR action in
   `DESTRUCTIVE_ACTIONS` → call `tool.dry_run()`, call `confirm_fn(preview)`
   → if user says no, return cancelled result
5. `tool.execute(call)` → `MCPResult`
6. `audit_logger.log(call, result)`
7. Return result

`dispatch_chain(chain)` loops over steps, passing each through `dispatch()`,
and resolves `{{step_N.output}}` templates in later steps' params.

The `confirm_fn` parameter is dependency-injected. The TUI passes a function
that auto-confirms (the UI handles confirmation differently); the CLI passes
`_default_confirm` which calls `input()`.

---

### `mcp/policy.py` — PolicyConfig

Loaded from `.mcprc` using Python 3.13's stdlib `tomllib`. Falls back to
`PolicyConfig.default()` if no `.mcprc` exists.

Key enforcement methods:
- `is_path_allowed(path)` — resolves to absolute, checks sandbox_root, checks
  blocked_paths globs
- `is_tool_allowed(tool_name)` — checks disabled_tools, then allowed_tools
- `requires_confirmation(tool, action)` — checks confirm_required set

**Important:** `PolicyConfig` is a mutable dataclass. The TUI modifies
`policy.dry_run_mode` in-place when the user toggles `Ctrl+D`. This is
intentional — no restart needed for policy changes at runtime.

---

### `mcp/base.py` — MCPTool (Plugin SDK)

Every tool must inherit from `MCPTool` and set four class-level attributes:

```python
TOOL_NAME: str             # Must match what the LLM emits
TOOL_DESCRIPTION: str      # Injected into LLM system prompt
SUPPORTED_ACTIONS: dict    # action_name → description (injected into prompt)
DESTRUCTIVE_ACTIONS: set   # Actions that trigger dry-run/confirm
```

The only required method is `execute(call: MCPCall) -> MCPResult`. It must
**never raise** — catch all exceptions inside and return `self._err(call, str(e))`.

Helper methods on `MCPTool`:
- `self._ok(call, output, data, duration_ms)` → success MCPResult
- `self._err(call, error, duration_ms)` → failure MCPResult

---

### `mcp/registry.py` — ToolRegistry

Two ways tools get registered:

1. **Explicit:** `registry.register(FileHandler(policy))` in `main.py` / `tui/app.py`
2. **Plugin discovery:** `registry.discover_plugins(config.PLUGINS_DIR)` — walks
   `plugins/*/`, imports every `.py` file, finds non-abstract `MCPTool` subclasses

If a plugin fails to import, it is silently skipped. Check stderr for import errors.

After registration, call `registry.generate_summary()` and pass it to
`PromptBuilder` before the first LLM call. The summary is what populates the
system prompt's tool list.

---

### `audit/logger.py` — AuditLogger

Writes to `audit_logs/audit_YYYY-MM-DD.jsonl`. Each line is a JSON object with:
- `seq`, `session_id`, `ts`, `user`, `hostname`
- `call` — full MCPCall dict
- `result` — success, output (truncated to 500 chars), error, duration_ms
- `prev_hash` — SHA-256 of the previous entry
- `entry_hash` — SHA-256 of this entry (excluding `entry_hash` itself)

The hash chain means: to verify integrity, recompute every hash and check
`entry_hash == SHA256(entry_without_entry_hash)` and
`prev_hash == previous_entry_hash`. Any discrepancy means tampering.

Verification: `AuditLogger.verify_chain(path)` returns `(bool, list[str])`.

---

### `context/buffer.py` — ConversationBuffer

A list of `{"role", "content", "call"}` dicts, capped at `max_turns * 2`
entries (each exchange = 1 user + 1 assistant turn = 2 entries).

- `save()` / `load()` persist to `~/.mcp_assistant/context.json`
- `get_context(n)` strips the internal `call` field before returning — only
  `role` and `content` go to the LLM prompt

Context is loaded at startup and saved on clean exit (`Ctrl+Q` or `exit`).

---

### `tui/app.py` — MCPAssistantApp

The Textual `App` subclass. Key design points:

- **Attribute naming:** Use `self._tool_registry`, NOT `self._registry`. Textual
  uses `_registry` internally; the collision caused a crash during Phase 4.

- **Blocking calls:** All Ollama HTTP calls and dispatcher calls are wrapped in
  `asyncio.to_thread(lambda: ...)` so they don't block the UI event loop.

- **Worker pattern:** Commands are processed via `self.run_worker(coro)`.
  `exclusive=True` prevents a second command from starting while one is running.

- **Clarification flow:** When the LLM returns low-confidence output, the app
  sets `self._awaiting_confirm = True` and stores `self._pending_call`. The
  next input is interpreted as a y/n response rather than a new command.

---

## 5. Data Flow — A Single Command End to End

**Input:** User types `"show git status"` and presses Enter.

```
InputBar.on_input_submitted
  → post_message(CommandSubmitted("show git status"))

MCPAssistantApp.on_input_bar_command_submitted
  → query_one(HistoryPanel).add_user("show git status")
  → run_worker(_process_command("show git status"))

_process_command (async, in thread pool for blocking parts)
  → PromptBuilder.user_prompt("show git status", context=[...])
  → asyncio.to_thread(OllamaClient.generate(prompt, system=system_prompt))
       → POST http://localhost:11434/api/generate
       → returns: '{"tool": "GitTool", "action": "status", "params": {}, "confidence": 1.0}'
  → parse_response(raw) → MCPCall(tool="GitTool", action="status", ...)
  → confidence.should_clarify(call) → False (conf=1.0 > threshold=0.5)
  → _dispatch_parsed(call)

_dispatch_parsed
  → asyncio.to_thread(dispatcher.dispatch(call))

MCPDispatcher.dispatch(call)
  → registry.get("GitTool") → GitTool instance
  → policy.is_tool_allowed("GitTool") → True
  → GitTool.validate_params(call) → [] (no errors)
  → policy.requires_confirmation("GitTool", "status") → False
  → GitTool.execute(call) → subprocess.run(["git", "status"]) → stdout
  → MCPResult(success=True, output="On branch main\n...")
  → audit_logger.log(call, result) → appends to JSONL file

back in _dispatch_parsed
  → HistoryPanel.add_result(result.output, True)
  → ToolInspector.show_call(call, result)
  → ConversationBuffer.add_turn("assistant", result.output[:200])
  → InputBar.set_busy(False)
```

---

## 6. The Plugin SDK — Adding New Tools

Create a new directory under `plugins/` and add a `tool.py`:

```python
# plugins/my_plugin/tool.py
from mcp_assistant.mcp.base import MCPTool
from mcp_assistant.mcp.schema import MCPCall, MCPResult
import time

class MyTool(MCPTool):
    TOOL_NAME = "MyTool"
    TOOL_DESCRIPTION = "What this tool does, in one sentence."
    SUPPORTED_ACTIONS = {
        "my_action": "Description of what this action does. Params: param_name",
    }
    DESTRUCTIVE_ACTIONS = set()       # add action names that need confirmation

    def execute(self, call: MCPCall) -> MCPResult:
        start = time.perf_counter()
        action = call.action
        try:
            if action == "my_action":
                result_str = "done"
                return self._ok(call, result_str, duration_ms=_ms(start))
            else:
                return self._err(call, f"Unknown action: {action}", _ms(start))
        except Exception as e:
            return self._err(call, str(e), _ms(start))

def _ms(start):
    return round((time.perf_counter() - start) * 1000, 2)
```

No other files need to change. On next startup, `ToolRegistry.discover_plugins()`
finds `MyTool`, registers it, and the LLM system prompt automatically includes it.

**Rules:**
- Class name can be anything. `TOOL_NAME` is what the LLM uses.
- `execute()` must never raise. Always `try/except` and return `_err`.
- `validate_params()` is optional but recommended for required params.
- `dry_run()` is optional — override to give a meaningful preview for
  destructive actions.

---

## 7. Policy System — `.mcprc`

The `.mcprc` file in the project root is loaded at startup using
`tomllib` (Python 3.13 stdlib). Every field has a safe default.

```toml
[security]
sandbox_root = "/home/krshrivathsan/MajorProject"
blocked_paths = ["**/.env", "**/*.pem", "**/*.key", "**/id_rsa", "**/.ssh/**"]
max_file_size_mb = 10

[tools]
allowed_tools = ["FileHandler", "GitTool", "SystemTool", "TestRunner"]
# Whitelist. Empty list = all tools allowed.
disabled_tools = []

[confirmations]
confirm_required = ["FileHandler.write", "FileHandler.delete", "GitTool.commit", "SystemTool.kill_process"]
confirm_all_destructive = true
# If true, any action in DESTRUCTIVE_ACTIONS also triggers confirm

[behavior]
dry_run_mode = false
confidence_threshold = 0.5   # Below this → ask user to confirm intent
context_window_size = 10     # How many conversation turns to remember

[audit]
log_dir = "audit_logs"
retention_days = 30          # 0 = keep forever
```

`PolicyConfig.load_or_default(path)` handles missing files gracefully.
`PolicyConfig.default()` hardcodes safe defaults identical to the above.

**To disable a tool entirely** (e.g., prevent SystemTool from being used):
```toml
[tools]
disabled_tools = ["SystemTool"]
```

**To block an additional path pattern:**
```toml
[security]
blocked_paths = ["**/.env", "**/*.pem", "**/my_secrets/**"]
```

---

## 8. Audit Log — Format and Verification

**Location:** `audit_logs/audit_YYYY-MM-DD.jsonl`

**Single entry (formatted for readability — actual file is one line):**
```json
{
  "seq": 1,
  "session_id": "a3f9b2c1",
  "ts": "2026-04-07T14:23:11.847291+00:00",
  "user": "krshrivathsan",
  "hostname": "fedora-workstation",
  "call": {
    "tool": "GitTool",
    "action": "status",
    "params": {},
    "raw_response": "{...}",
    "confidence": 1.0
  },
  "result": {
    "success": true,
    "output": "On branch main\n...",
    "error": null,
    "duration_ms": 8.3
  },
  "prev_hash": "e3b0c44298fc1c149afb4c8996fb92427ae41e4649b934ca495991b7852b855",
  "entry_hash": "b94d27b9934d3e08a52e52d7da7dabfac484efe04294e576f3d48e6e3a72db6e"
}
```

**Verification algorithm** (in `AuditLogger.verify_chain`):
1. Read all entries from the JSONL file
2. For each entry: recompute `SHA256(json.dumps(entry_without_entry_hash, sort_keys=True))`
3. Assert computed hash == stored `entry_hash`
4. Assert stored `prev_hash` == previous entry's `entry_hash`
5. First entry has `prev_hash = "0" * 64` (genesis)

Any mismatch indicates tampering at or after that position.

---

## 9. Evaluation Harness

**Purpose:** Measures the LLM's intent-detection accuracy on a fixed dataset
of 60 natural-language commands.

**Dataset** (`eval_data/eval_dataset.json`):
Each entry has `id`, `nl_input`, `ground_truth` (`{tool, action, params}`),
`category`, and `difficulty`. Chain entries also have `is_chain` and `chain_steps`.

```
60 items:  file_ops(15)  git_ops(15)  system_ops(15)  test_ops(10)  chaining(5)
Difficulty: easy(30)  medium(20)  hard(10)
```

**Metrics collected:**

| Metric | Definition |
|---|---|
| Tool Accuracy | % where `predicted.tool == ground_truth.tool` |
| Action Accuracy | % where both tool AND action match |
| Parse Failure Rate | % where LLM output could not be parsed as JSON |
| Hallucination Rate | % where predicted tool is not a registered tool name |
| Mean / P95 Latency | LLM call duration (ms) |

**Ablation study** (4 conditions, run with `--ablation`):

| Condition | Context | Conf. Gate |
|---|---|---|
| `no_context_no_conf_gate` | 0 turns | off |
| `ctx5_no_conf_gate` | 5 turns | off |
| `ctx10_no_conf_gate` | 10 turns | off |
| `ctx10_with_conf_gate` | 10 turns | 0.5 threshold |

The ablation shows the marginal effect of context and confidence gating on
accuracy. Expected finding: context helps on follow-up queries; confidence
gating reduces hallucinations at the cost of clarification overhead.

**Adding new eval items:** Edit `eval_data/eval_dataset.json`. Follow the
existing schema. Add `"is_chain": true` and `"chain_steps": [...]` for
multi-step ground truths. Update tests in `tests/test_eval.py` if total count
changes.

---

## 10. Running Tests

```bash
# Fast (excludes TestRunner which invokes pytest recursively)
venv/bin/pytest tests/ --ignore=tests/test_tools.py -q

# Full suite (takes ~2 min — TestRunner test runs a subprocess pytest)
venv/bin/pytest tests/ -q

# Single module
venv/bin/pytest tests/test_dispatcher.py -v

# With coverage
venv/bin/pytest tests/ --cov=mcp_assistant --cov-report=term-missing
```

**Current state:** 65 tests, all passing.

**Fixtures** (in `tests/conftest.py`):
- `policy` — `PolicyConfig` loaded from `.mcprc`
- `registry` — all 4 tools registered
- `audit` — `AuditLogger` writing to `tmp_path`
- `dispatcher` — `MCPDispatcher` with `confirm_fn=lambda _: True` (auto-approves)

Most tests use `dispatcher` as the entry point, which exercises the full
dispatch stack without the LLM.

---

## 11. Environment Setup from Scratch

```bash
# 1. Clone / enter project
cd /home/krshrivathsan/MajorProject

# 2. Create venv (if not already present)
python3.13 -m venv venv

# 3. Install all dependencies
venv/bin/pip install requests pydantic psutil textual rich pytest pytest-cov

# 4. Install the package in editable mode
venv/bin/pip install -e .

# 5. Install Ollama (if not present)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull phi3:latest

# 6. Start Ollama
ollama serve &

# 7. Verify
venv/bin/python -m mcp_assistant.llm.client   # should print "Ollama available"
venv/bin/pytest tests/ -q                     # should show 65 passed

# 8. Launch
venv/bin/python -m mcp_assistant.main
```

**Entry points** (after `pip install -e .`):
```bash
mcp           # launches TUI
mcp --cli     # launches plain CLI
mcp-eval      # evaluation harness
mcp-verify    # audit chain verifier
```

---

## 12. Known Limitations and Design Decisions

### phi3 Latency
phi3 3.8B Q4_0 takes 3–8 seconds per response on CPU. This is expected. If
latency needs to improve:
- Use a GPU-accelerated Ollama setup (`ollama run phi3:latest` with CUDA)
- Switch to a smaller model (`phi3:mini`) — accuracy will drop
- Use `generate_stream()` and show tokens as they arrive in the TUI

### Chain Detection
phi3 does not reliably emit chain JSON for every multi-step request. The
prompt engineering in `prompt_builder.py` uses explicit trigger words ("then",
"first...then") and examples. If chain detection is still unreliable:
- Try a larger model (llama3 8B or larger)
- Add a pre-processing step that detects multi-step keywords and hard-codes
  a chain prompt variant

### TUI Confirmation Flow
Destructive operations in the TUI auto-confirm (via `confirm_fn=lambda _: True`)
because the dispatcher's blocking `input()` call cannot be used in an async
event loop. The TUI instead relies on `dry_run_mode` and the policy
`confirm_required` list to show previews. A proper modal dialog (`Textual`
supports `app.push_screen()`) would be a cleaner solution.

### `self._tool_registry` Naming
Do not rename this back to `self._registry` in `tui/app.py`. Textual uses
`_registry` internally; the collision causes a `TypeError: 'ToolRegistry'
object is not iterable` crash during app shutdown.

### File Writes Require `content` Param
The FileHandler `write` action requires the LLM to emit `{"path": "...",
"content": "..."}`. phi3 often omits `content` for ambiguous requests like
"create a file". The validator catches this and returns an error, preventing
crashes, but the user must rephrase.

### No Streaming in TUI
The TUI uses `asyncio.to_thread(client.generate(...))` for blocking calls.
The `generate_stream()` method exists but is not wired to the TUI yet. Adding
streaming would require yielding tokens through a Textual reactive/message
system.

---

## 13. Where to Go Next — Suggested Improvements

These are the highest-value extensions, roughly ordered by impact:

**1. Streaming LLM output in the TUI**
Wire `generate_stream()` to the history panel so the user sees tokens appear
in real time. This dramatically reduces perceived latency.

**2. Proper TUI confirmation modal**
Replace the auto-confirm `lambda _: True` with a `textual` modal screen
(`app.push_screen(ConfirmModal(preview))`) that blocks the coroutine until
the user responds. This makes destructive-op confirmation visible in the UI.

**3. Larger or smarter model**
Swap phi3 for `llama3.1:8b` or `deepseek-coder:6.7b`. The dataset + harness
are model-agnostic — just change `OLLAMA_MODEL` in `config.py` or set the
env var.

**4. Docker Tool**
Add `plugins/docker_tool/tool.py` with actions: `list_containers`,
`start`, `stop`, `logs`. The Plugin SDK means this requires zero changes to
core code.

**5. Database Inspector Tool**
Add a read-only SQLite/PostgreSQL tool. Actions: `query`, `schema`, `tables`.
Enforce SELECT-only by parsing the SQL before execution.

**6. Shell Integration**
Add a Fish/Zsh/Bash keybind that lifts the current typed command into the
assistant for NL augmentation. This makes the tool usable without switching
windows.

**7. Benchmark Against Cloud Assistants**
The eval harness is designed for this. Run the same 60 queries against
Amazon Q CLI and GitHub Copilot CLI (where available), record their output,
score manually, and add comparison columns to the ablation table.

---

## 14. Dependency Map

```
mcp_assistant.main
  ├── mcp_assistant.config
  ├── mcp_assistant.llm.client          ← requests
  ├── mcp_assistant.llm.prompt_builder
  ├── mcp_assistant.llm.response_parser ← mcp.schema
  ├── mcp_assistant.llm.confidence
  ├── mcp_assistant.mcp.schema
  ├── mcp_assistant.mcp.registry        ← mcp.base
  ├── mcp_assistant.mcp.dispatcher      ← mcp.{registry,policy,schema}, audit.logger
  ├── mcp_assistant.mcp.policy          ← tomllib (stdlib)
  ├── mcp_assistant.audit.logger        ← hashlib, json (stdlib)
  ├── mcp_assistant.audit.retention
  ├── mcp_assistant.context.buffer
  ├── mcp_assistant.tools.file_handler  ← mcp.{base,schema,policy}
  ├── mcp_assistant.tools.git_tool      ← subprocess (stdlib)
  ├── mcp_assistant.tools.system_tool   ← psutil
  ├── mcp_assistant.tools.test_runner   ← subprocess (stdlib)
  └── mcp_assistant.tui.app             ← textual, all of the above

mcp_assistant.eval.harness
  ├── mcp_assistant.eval.dataset
  ├── mcp_assistant.eval.metrics
  ├── mcp_assistant.eval.report
  ├── mcp_assistant.llm.{client,prompt_builder,response_parser}
  └── mcp_assistant.config

External dependencies:
  requests     — Ollama HTTP client
  pydantic     — installed but not yet used for schema validation (future use)
  psutil       — SystemTool metrics
  textual      — TUI framework
  rich         — text rendering (textual dependency)
  tomllib      — .mcprc parsing (Python 3.13 stdlib)
  pytest       — test runner
```

---

*Last updated: 2026-04-07*
*Author: K R Shrivathsan*
*Successor: update the "Last updated" date and your name when you take over.*
