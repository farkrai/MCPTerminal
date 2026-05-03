# MCP Terminal Assistant — Knowledge Transfer

> Reading time: ~60 minutes  
> Last updated: 2026-04-11  
> Audience: developer continuing this project from scratch

---

## Table of Contents

1. [What It Is](#1-what-it-is)
2. [Unique Selling Points](#2-unique-selling-points)
3. [Tech Stack](#3-tech-stack)
4. [Repository Layout](#4-repository-layout)
5. [Architecture Overview](#5-architecture-overview)
6. [FastMCP Server Layer](#6-fastmcp-server-layer)
   - 6.1 [Tool Design Pattern](#61-tool-design-pattern)
   - 6.2 [Namespace Mounting](#62-namespace-mounting)
   - 6.3 [Tags & Tag Taxonomy](#63-tags--tag-taxonomy)
   - 6.4 [Middleware Chain](#64-middleware-chain)
   - 6.5 [Resources](#65-resources)
   - 6.6 [Prompts](#66-prompts)
   - 6.7 [FastMCP Transforms (PromptsAsTools / ResourcesAsTools)](#67-fastmcp-transforms-promptsastools--resourcesastools)
7. [Tool Inventory (37 tools)](#7-tool-inventory-37-tools)
8. [Hallucination Prevention](#8-hallucination-prevention)
   - 8.1 [HallucinationGuard](#81-hallucinationguard)
   - 8.2 [Confidence Gating](#82-confidence-gating)
9. [Efficient Tool Lookup (Meta-tools)](#9-efficient-tool-lookup-meta-tools)
10. [ToolKit / ToolRouter — Context-Aware Visibility](#10-toolkit--toolrouter--context-aware-visibility)
11. [Audit System](#11-audit-system)
12. [Policy System (.mcprc)](#12-policy-system-mcprc)
13. [Context Window Management](#13-context-window-management)
14. [LLM Layer (Ollama / deepseek-r1:8b)](#14-llm-layer-ollama--deepseek-r18b)
15. [CLI Entry Point & REPL](#15-cli-entry-point--repl)
16. [Textual TUI](#16-textual-tui)
17. [Evaluation Harness](#17-evaluation-harness)
18. [Configuration Reference](#18-configuration-reference)
19. [How to Run](#19-how-to-run)
20. [How to Extend](#20-how-to-extend)
21. [Known Gaps & Next Steps](#21-known-gaps--next-steps)

---

## 1. What It Is

**MCP Terminal Assistant** is an offline, privacy-preserving AI terminal assistant.  
It translates natural language instructions (e.g. *"show me files changed in the last commit"*) into structured tool calls that execute locally on the developer's machine — no cloud, no external APIs, no telemetry.

It ships three runnable modes:

| Command | What it does |
|---------|--------------|
| `mcp` | Launches the Textual TUI (default) |
| `mcp --cli` | Launches the readline CLI (lightweight) |
| `mcp-server` | Runs the FastMCP server in stdio mode (Claude Desktop / any MCP client) |

---

## 2. Unique Selling Points

### 2.1 Complete Offline Operation
All inference runs via **Ollama** (`deepseek-r1:8b` by default). No internet connection is required after model download. Suitable for air-gapped environments, sensitive codebases, and privacy-conscious developers.

### 2.2 FastMCP 3.2.3 — Industry-Latest Practices
Rebuilt on **FastMCP 3.2.3**, the reference implementation of the Model Context Protocol. Uses every modern FastMCP feature:
- `@mcp.tool()` decorator with `Annotated[type, "description"]` parameter annotation
- `Context` dependency injection for progress reporting (`ctx.report_progress`)
- `ToolAnnotations` with `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`
- Sub-server `mcp.mount(sub, namespace="x")` producing clean `x_toolname` prefixes
- `Middleware` base class with `on_call_tool` hook
- `Visibility` transforms (`mcp.enable(tags=..., only=True)`)
- `PromptsAsTools` and `ResourcesAsTools` transforms

### 2.3 Hallucination Prevention (Multi-Layer)
Three independent defences stop the LLM from calling tools that don't exist:
1. **HallucinationGuard** — fuzzy edit-distance matching + legacy name conversion
2. **Confidence Gating** — prompts user confirmation below a threshold
3. **Policy Middleware** — blocks disallowed tool namespaces at the server level

### 2.4 Tamper-Evident Audit Log
Every tool call and result is appended to a **SHA-256-chained JSONL** file. Each entry contains the hash of the previous entry, making silent tampering detectable. `mcp-verify` CLI command verifies the chain integrity.

### 2.5 Policy-Driven Access Control
A `.mcprc` TOML file controls:
- Which tools are allowed/disabled
- Which paths are sandboxed or blocked
- Which operations require interactive confirmation
- Global dry-run mode (no writes, no deletes)

### 2.6 ToolKit / Visibility Routing
The **ToolRouter** narrows the LLM's tool view to a domain-specific subset via FastMCP Visibility transforms. Fewer tools in the system prompt → lower hallucination rate. Activate with `!toolkit git` or the `toolkit_activate` tool.

### 2.7 In-Process Client (Zero IPC Overhead)
Uses `fastmcp.Client(mcp_server_instance)` for the CLI/TUI. The client and server share the same process — no subprocess spawning, no stdio piping, sub-millisecond tool dispatch.

### 2.8 Eval Harness
A JSON-driven evaluation harness (`mcp-eval`) measures tool accuracy, parse failure rate, chain execution rate, and p95 latency against a golden dataset.

---

## 3. Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| MCP framework | FastMCP | 3.2.3 |
| LLM inference | Ollama (local) | any |
| LLM model | deepseek-r1:8b | — |
| TUI framework | Textual | ≥0.80 |
| System metrics | psutil | ≥5.9 |
| Python | CPython | ≥3.13 |
| Package manager | pip / setuptools | ≥68 |
| Audit storage | JSONL (plain files) | — |
| Config format | TOML (.mcprc) | — |

---

## 4. Repository Layout

```
MajorProject/
├── mcp_assistant/
│   ├── config.py                   ← Global path/env constants
│   ├── main.py                     ← Entry point: TUI / CLI / server
│   │
│   ├── server/                     ← FastMCP server layer (NEW in rewrite)
│   │   ├── app.py                  ← create_server() / get_server() factory
│   │   ├── middleware.py           ← PolicyMiddleware, TimingMiddleware, AuditMiddleware
│   │   ├── resources.py            ← @mcp.resource() registrations
│   │   ├── prompts.py              ← @mcp.prompt() registrations
│   │   ├── schema.py               ← ToolCall, ToolChain, ToolChainStep dataclasses
│   │   ├── state.py                ← Process-level policy + audit singletons
│   │   ├── hallucination_guard.py  ← Fuzzy tool-name validator
│   │   ├── toolkit.py              ← ToolKit / ToolRouter (Visibility transforms)
│   │   └── tools/
│   │       ├── file.py             ← 5 file tools
│   │       ├── git.py              ← 7 git tools
│   │       ├── system.py           ← 6 system tools
│   │       ├── test.py             ← 4 test tools
│   │       ├── network.py          ← 4 network tools
│   │       └── meta.py             ← 3 meta/routing tools
│   │
│   ├── llm/
│   │   ├── client.py               ← OllamaClient (HTTP to localhost:11434)
│   │   ├── prompt_builder.py       ← System prompt + user prompt construction
│   │   ├── response_parser.py      ← JSON parser + <think> tag stripper
│   │   └── confidence.py           ← Confidence gate + known-tools registry
│   │
│   ├── audit/
│   │   ├── logger.py               ← SHA-256-chained JSONL audit writer
│   │   └── retention.py            ← Old log cleanup
│   │
│   ├── context/
│   │   └── buffer.py               ← ConversationBuffer (sliding window, persistence)
│   │
│   ├── tui/
│   │   ├── app.py                  ← Textual App wiring
│   │   ├── theme.py                ← Dark terminal theme
│   │   └── widgets/                ← HistoryPanel, InputBar, StatsSidebar, etc.
│   │
│   └── eval/
│       ├── harness.py              ← CLI evaluation runner
│       ├── dataset.py              ← Golden dataset loader
│       ├── metrics.py              ← Accuracy / latency metrics
│       └── report.py               ← Report renderer
│
├── tests/
├── docs/
│   └── KNOWLEDGE_TRANSFER.md      ← This file
├── .mcprc                          ← Policy config (TOML, gitignored)
├── pyproject.toml
└── audit_logs/                     ← JSONL audit files (gitignored)
```

> **Note:** `mcp_assistant/mcp/` and `mcp_assistant/tools/` are the **old** pre-rewrite modules.
> They still exist for reference but are not used by `main.py` or the server layer.
> Safe to delete after verifying nothing imports them.

---

## 5. Architecture Overview

```
User Input (CLI / TUI)
        │
        ▼
  PromptBuilder ──builds─→ system_prompt + user_prompt
        │
        ▼
  OllamaClient.generate()   [deepseek-r1:8b, temp=0.1]
        │
        ▼
  response_parser.parse_response()
    • strips <think>…</think> (deepseek CoT artifact)
    • parses JSON → ToolCall | ToolChain
        │
        ▼
  HallucinationGuard.validate()
    • exact match → pass
    • legacy "FileHandler.read" → "file_read" auto-convert
    • case-insensitive match → auto-correct
    • fuzzy edit-distance (cutoff 0.65) → auto-correct
    • no match → reject, skip execution
        │
        ▼
  Confidence Gate (should_clarify)
    • confidence < threshold (default 0.5) → ask user y/n
    • hallucinated tool → ask user y/n
        │
        ▼
  fastmcp.Client(mcp_server) ← in-process, no subprocess
        │ call_tool(name, params)
        ▼
  FastMCP Server
    PolicyMiddleware → TimingMiddleware → AuditMiddleware → tool fn
        │
        ▼
  Tool execution (file / git / system / test / network)
        │
        ▼
  Result → ConversationBuffer.add_turn() → display to user
```

---

## 6. FastMCP Server Layer

### 6.1 Tool Design Pattern

Every tool is an `async def` decorated with `@sub_mcp.tool()`:

```python
@file_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"file", "read-only"},
)
async def read(
    path: Annotated[str, "Absolute or relative path to the file"],
    ctx: Context = None,
) -> str:
    """Read and return the full contents of a file."""
    ...
```

Key points:
- **`Annotated[type, "description"]`** — the string becomes the parameter description in the MCP schema, visible to LLM clients.
- **`ctx: Context = None`** — FastMCP dependency injection; use `await ctx.info(...)` for log messages and `await ctx.report_progress(n, total)` for progress events.
- **`ToolAnnotations`** — hints the MCP client how to present the tool: `readOnlyHint=True` marks safe tools; `destructiveHint=True` marks dangerous ones.
- **`tags`** — used for Visibility filtering (ToolKit) and the `describe_tools` meta-tool routing.

### 6.2 Namespace Mounting

Sub-servers are built independently and mounted on the main server with a namespace prefix:

```python
# In server/app.py
mcp.mount(file_mcp, namespace="file")   # read()   → "file_read"
mcp.mount(git_mcp,  namespace="git")    # status() → "git_status"
mcp.mount(meta_mcp)                      # describe_tools → "describe_tools" (no prefix)
```

The sub-server function name becomes the suffix. Exception: functions named after Python builtins (e.g. `list`, `read`) can't be the function name — use `name="list"` in the decorator and name the function something else:

```python
@file_mcp.tool(name="list", ...)
async def list_directory(path, pattern="*", ctx=None) -> dict: ...
# → produces tool name "file_list"
```

### 6.3 Tags & Tag Taxonomy

Tags serve two purposes: **ToolKit routing** (Visibility transforms) and **meta-tool keyword matching**.

| Tag | Meaning |
|-----|---------|
| `file` | File I/O tools |
| `git` | Git VCS tools |
| `system` | OS/process tools |
| `test` | Test framework tools |
| `network` | Network diagnostic tools |
| `read-only` | Safe, non-destructive (cross-namespace) |
| `destructive` | Writes, deletes, process kills |
| `monitoring` | System stats (cpu, ram, disk, env) |
| `diagnostic` | Network probes (ping, dns, http, port) |
| `meta` | Tool discovery and routing |

Most tools carry **two tags**: their domain tag (`file`) and their safety tag (`read-only` or `destructive`).

### 6.4 Middleware Chain

Middleware runs in order: **PolicyMiddleware → TimingMiddleware → AuditMiddleware → tool**.

```
PolicyMiddleware   → check .mcprc; raise ToolError if namespace disabled
TimingMiddleware   → start perf timer
AuditMiddleware    → start perf timer
  [tool fn executes]
AuditMiddleware    → write JSONL entry (SHA-256 chain)
TimingMiddleware   → record elapsed, update histogram
```

**`PolicyMiddleware`** (`middleware.py:27`)  
Extracts the namespace prefix from the tool name (`"file_read"` → `"file"` → `"FileHandler"`), checks `policy.is_tool_allowed()`, raises `ToolError` if blocked.

**`TimingMiddleware`** (`middleware.py:42`)  
Maintains class-level `_totals`, `_counts`, `_min`, `_max` dictionaries. Access via `TimingMiddleware.global_stats()` → dict of `{tool: {calls, avg_ms, min_ms, max_ms, total_ms}}`. The TUI sidebar can surface slow tools using this.

**`AuditMiddleware`** (`middleware.py:98`)  
Calls `audit.log(tool, params, output, success, error, duration_ms)` regardless of success/failure. Captures the first 500 chars of the text content from the MCP result.

### 6.5 Resources

Resources are read-only data endpoints. They are registered in `server/resources.py`:

| URI | Name | Content |
|-----|------|---------|
| `resource://config` | server-config | Current `.mcprc` policy as JSON |
| `resource://audit/today` | audit-log-today | Today's JSONL audit log |
| `resource://audit/verify` | audit-chain-verify | SHA-256 chain integrity report |
| `resource://session` | session-info | Session ID + call count |

Resources are used internally by the `ResourcesAsTools` transform (see §6.7).

### 6.6 Prompts

Prompt templates are registered in `server/prompts.py`:

| Name | Purpose |
|------|---------|
| `system-instructions` | Full system prompt for the LLM (response format, chain syntax) |
| `clarify-intent` | Multi-turn clarification when confidence is low |
| `explain-test-failures` | Asks the LLM to explain pytest/jest failures |
| `summarize-git-diff` | Asks the LLM to summarise a diff in plain English |

Prompts are used internally but also exposed as callable tools via `PromptsAsTools` (§6.7).

### 6.7 FastMCP Transforms (PromptsAsTools / ResourcesAsTools)

```python
# In server/app.py, after mounting all tools:
mcp.add_transform(PromptsAsTools())
mcp.add_transform(ResourcesAsTools())
```

**`PromptsAsTools`** wraps every `@mcp.prompt()` as a tool. An LLM client can call `prompt_explain-test-failures(test_output="...")` directly without needing to know the MCP prompts API. Tool names are `prompt_<original-name>`.

**`ResourcesAsTools`** wraps every `@mcp.resource()` as a zero-argument (or URI-argument) tool. The LLM can call `resource_server-config()` to read the current policy, or `resource_audit-today()` to fetch today's log. Tool names are `resource_<resource-name>`.

---

## 7. Tool Inventory (37 tools)

### File Tools (5) — namespace `file`
| Tool | Tags | Description |
|------|------|-------------|
| `file_read` | file, read-only | Read file contents |
| `file_write` | file, destructive | Write or overwrite a file (dry-run aware) |
| `file_list` | file, read-only | List directory contents with glob filtering |
| `file_search` | file, read-only | Recursive file search by glob pattern |
| `file_delete` | file, destructive | Delete a file (dry-run aware) |

### Git Tools (7) — namespace `git`
| Tool | Tags | Description |
|------|------|-------------|
| `git_status` | git, read-only | Working tree status |
| `git_diff` | git, read-only | Staged / unstaged diff |
| `git_log` | git, read-only | Commit log with configurable depth |
| `git_add` | git | Stage files |
| `git_commit` | git, destructive | Create a commit |
| `git_branch_list` | git, read-only | List branches |
| `git_branch_switch` | git, destructive | Switch branch |

### System Tools (6) — namespace `system`
| Tool | Tags | Description |
|------|------|-------------|
| `system_cpu_stats` | system, monitoring, read-only | CPU usage per core |
| `system_ram_stats` | system, monitoring, read-only | RAM total/used/free |
| `system_disk_stats` | system, monitoring, read-only | Disk partitions usage |
| `system_list_processes` | system, monitoring, read-only | Top processes by CPU |
| `system_kill_process` | system, destructive | Kill a process by PID |
| `system_env_info` | system, monitoring, read-only | OS version, Python, cwd, user |

### Test Tools (4) — namespace `test`
| Tool | Tags | Description |
|------|------|-------------|
| `test_detect` | test, read-only | Detect pytest / jest in a directory |
| `test_run` | test | Auto-detect and run full test suite |
| `test_run_file` | test | Run a specific test file with pytest |
| `test_explain_failures` | test, read-only | Ask LLM to explain failure output |

### Network Tools (4) — namespace `network`
| Tool | Tags | Description |
|------|------|-------------|
| `network_ping` | network, diagnostic | ICMP ping a host |
| `network_dns_lookup` | network, diagnostic | DNS resolve → IPv4/IPv6 |
| `network_http_probe` | network, diagnostic | HTTP/HTTPS status + latency |
| `network_port_check` | network, diagnostic | TCP port open/closed/filtered |

### Meta Tools (3) — no namespace
| Tool | Tags | Description |
|------|------|-------------|
| `describe_tools` | meta, read-only | Find tools matching a natural language query |
| `toolkit_status` | meta, read-only | Show available kits and current active kit |
| `toolkit_activate` | meta | Activate a domain-specific ToolKit |

### PromptsAsTools (4) — via transform
`prompt_system-instructions`, `prompt_clarify-intent`, `prompt_explain-test-failures`, `prompt_summarize-git-diff`

### ResourcesAsTools (4) — via transform
`resource_server-config`, `resource_audit-log-today`, `resource_audit-chain-verify`, `resource_session-info`

---

## 8. Hallucination Prevention

### 8.1 HallucinationGuard

**File:** `mcp_assistant/server/hallucination_guard.py`

The `HallucinationGuard` sits in the CLI/TUI REPL, *before* the FastMCP client call. It validates and optionally auto-corrects every tool name the LLM generates.

```python
guard = HallucinationGuard(known_tools=tool_names, auto_correct=True)
parsed, report = guard.validate(parsed_tool_call)
```

**5-step validation pipeline:**

| Step | Condition | Action |
|------|-----------|--------|
| 1 | Exact match | Accept, return `None` report |
| 2 | `"FileHandler.read"` style | Auto-convert to `"file_read"` via `_LEGACY_MAP` |
| 3 | Case-insensitive match | Auto-correct (sim = 0.95) |
| 4 | Fuzzy edit-distance ≥ 0.65 | Auto-correct with similarity-scaled confidence |
| 5 | No match | Reject, return report with `suggested_tool=None` |

`_LEGACY_MAP` covers all 20 old-format tool names from the pre-rewrite codebase, so existing prompt caches and evaluation datasets continue to work.

**Metrics:** `guard.stats()` returns a `GuardStats(total_calls, hallucinated, auto_corrected, rejected, hallucination_rate)`. Exposed in `!stats` CLI command and TUI sidebar.

**Chain validation:** `guard.validate_chain(chain)` applies the same logic to every step in a `ToolChain`.

### 8.2 Confidence Gating

**File:** `mcp_assistant/llm/confidence.py`

A simpler first-pass check: if the LLM returns a confidence score below the policy threshold (default 0.5), or if the tool name is not in the known-tools set, the user is asked to confirm before dispatch.

```python
if should_clarify(parsed, policy.confidence_threshold):
    # prompt user y/n
```

This runs *after* HallucinationGuard — the guard corrects the name first, then confidence gating checks the score.

---

## 9. Efficient Tool Lookup (Meta-tools)

**File:** `mcp_assistant/server/tools/meta.py`

With 37 tools in the system prompt, the LLM may pick a suboptimal tool. The `describe_tools` meta-tool lets the LLM self-route:

```json
{"tool": "describe_tools", "params": {"query": "read a file"}, "confidence": 0.99}
```

Response includes matching tool names, first-line descriptions, and parameter signatures — no full schemas. Capped at 8 results.

**Keyword → tag routing** maps common words to tag groups for faster scoring:

```python
KEYWORD_TAGS = [
    (["file", "read", "write", "list", ...], "file"),
    (["git", "commit", "diff", ...],         "git"),
    (["cpu", "ram", "memory", ...],           "system"),
    ...
]
```

A tool scores 2 if its tags match, 1 if its description contains query words, 0 otherwise.

---

## 10. ToolKit / ToolRouter — Context-Aware Visibility

**File:** `mcp_assistant/server/toolkit.py`

A `ToolKit` is a named subset of tools identified by tags. Activating it calls FastMCP's Visibility transform to narrow the LLM's tool list:

```python
kit.activate(mcp)   # → mcp.enable(tags=self.tags, only=True)
kit.deactivate(mcp) # → mcp.disable(tags=self.tags)
```

**Available kits:**

| Kit | Tags | Tools visible |
|-----|------|---------------|
| `file` | `{"file"}` | 5 file tools |
| `git` | `{"git"}` | 7 git tools |
| `system` | `{"system"}` | 6 system tools |
| `test` | `{"test"}` | 4 test tools |
| `network` | `{"network"}` | 4 network tools |
| `read-only` | `{"read-only"}` | All non-destructive tools (cross-namespace) |
| `monitoring` | `{"monitoring"}` | CPU/RAM/disk/env tools |
| `diagnostic` | `{"diagnostic"}` | Network probe tools |

**User-facing:** `!toolkit git` in the CLI; `toolkit_activate(kit="git")` as an LLM-callable tool.  
**Reset:** `!toolkit all` or `toolkit_activate(kit="all")`.

Why this matters: reducing the tool list in the system prompt directly reduces hallucination rate — fewer candidates means lower chance of the LLM picking a wrong tool name or fabricating a parameter from a different tool.

---

## 11. Audit System

**File:** `mcp_assistant/audit/logger.py`

Every tool invocation — success or failure — is appended to a daily JSONL file:

```
audit_logs/audit_2026-04-11.jsonl
```

Each line is a JSON object:

```json
{
  "seq": 1,
  "ts": "2026-04-11T10:23:01.123456",
  "session": "a1b2c3d4",
  "tool": "file_read",
  "params": {"path": "/home/user/foo.py"},
  "output": "def main():\n    ...",
  "success": true,
  "error": null,
  "duration_ms": 3.14,
  "prev_hash": "0000000000000000...",
  "hash": "sha256(<prev_hash + current fields>)"
}
```

**Chain integrity:** `AuditLogger.verify_chain(path)` re-computes each hash from scratch and checks it matches. Returns `(ok: bool, errors: list[str])`. The `mcp-verify` CLI and `!verify` REPL command both use this.

**Retention:** `audit/retention.py` deletes logs older than `policy.audit_retention_days` days (default 30). Called at startup.

---

## 12. Policy System (.mcprc)

**File:** `mcp_assistant/mcp/policy.py`  
**Config file:** `.mcprc` (TOML, at project root)

Example `.mcprc`:

```toml
[policy]
sandbox_root = "/home/user/projects"
blocked_paths = ["/etc", "/usr", "~/.ssh"]
max_file_size_mb = 10

allowed_tools = []          # empty = all allowed
disabled_tools = []         # explicit disable list

confirm_required = ["file_delete", "git_commit", "system_kill_process"]
confirm_all_destructive = false
dry_run_mode = false

confidence_threshold = 0.5
context_window_size = 10
audit_retention_days = 30
```

`PolicyConfig.load_or_default()` reads this file on server startup and stores the singleton in `server/state.py`. `PolicyMiddleware` checks `policy.is_tool_allowed()` before each tool call.

---

## 13. Context Window Management

**File:** `mcp_assistant/context/buffer.py`

`ConversationBuffer` is a sliding window of the most recent N user/assistant turns (default N=10, configured via `policy.context_window_size`).

```python
buffer = ConversationBuffer(max_turns=10)
buffer.load()           # restore from ~/.mcp_assistant/context.json
buffer.add_turn("user", "show git diff")
buffer.add_turn("assistant", "file changed: foo.py")
ctx = buffer.get_context()  # → [{"role": "user", "content": "..."}, ...]
buffer.save()           # persist across sessions
```

The context is included in every LLM prompt via `builder.user_prompt(input, buffer.get_context())`, giving the LLM short-term memory of the conversation.

`!context` shows history; `!context clear` wipes it.

---

## 14. LLM Layer (Ollama / deepseek-r1:8b)

### OllamaClient (`llm/client.py`)

Makes HTTP POST requests to `http://localhost:11434/api/generate`. Two temperature settings:
- `OLLAMA_TEMP_STRUCTURED = 0.1` — for tool call generation (deterministic)
- `OLLAMA_TEMP_NL = 0.7` — for natural language explanations

`is_available()` pings the Ollama health endpoint; called at startup.

### PromptBuilder (`llm/prompt_builder.py`)

```python
builder = PromptBuilder()
builder.update_from_fastmcp_tools(tools)  # builds compact tool summary from live schemas
system = builder.system_prompt()           # includes tool summary + format instructions
user   = builder.user_prompt(input, ctx)  # includes conversation context + user input
```

`update_from_fastmcp_tools()` builds a compact one-line-per-tool summary:
```
file_read(path)  — Read and return the full contents of a file.
git_status()     — Show the current working tree status.
...
```

### ResponseParser (`llm/response_parser.py`)

1. Strips `<think>…</think>` blocks (deepseek-r1 chain-of-thought artifact)
2. Extracts JSON from the remaining text
3. Parses into `ToolCall` (single) or `ToolChain` (multi-step)

**Single call format:**
```json
{"tool": "file_read", "params": {"path": "src/main.py"}, "confidence": 0.95}
```

**Chain format:**
```json
{
  "chain": true,
  "description": "Get git status then show diff",
  "steps": [
    {"tool": "git_status", "params": {}, "confidence": 0.95},
    {"tool": "git_diff",   "params": {}, "confidence": 0.90}
  ]
}
```

Chain triggers: words like "then", "after that", "first...then", "followed by", "and also" in the user input.

---

## 15. CLI Entry Point & REPL

**File:** `mcp_assistant/main.py`

### Startup sequence

```python
mcp = get_server()          # lazily creates FastMCP server (once per process)
async with Client(mcp) as client:
    tools = await client.list_tools()
    register_known_tools({t.name for t in tools})
    builder.update_from_fastmcp_tools(tools)
    guard = HallucinationGuard(known_tools=tool_names)
```

### REPL pipeline (per turn)

```
input → PromptBuilder → OllamaClient → ResponseParser
      → HallucinationGuard.validate()
      → Confidence gate (should_clarify)
      → client.call_tool(name, params)
      → print result → ConversationBuffer.add_turn()
```

### Special commands

| Command | Action |
|---------|--------|
| `!help` | Show all commands |
| `!dry-run on\|off` | Toggle dry-run mode |
| `!context` | Show conversation history |
| `!context clear` | Clear history |
| `!verify` | Verify today's audit chain |
| `!tools` | List all FastMCP tools |
| `!toolkit <kit\|all>` | Activate a ToolKit |
| `!stats` | Session stats + guard stats + slow tools |

### Chain template resolution

Chain steps can reference prior outputs with `{{step_N.output}}`:
```json
{"tool": "git_diff", "params": {"ref": "{{step_1.output}}"}}
```
Resolved by `_resolve_chain_templates()` before dispatch.

---

## 16. Textual TUI

**File:** `mcp_assistant/tui/app.py`

Built on [Textual](https://textual.textualize.io/). Widgets:
- **HistoryPanel** — scrollable conversation log
- **InputBar** — user input, sends on Enter
- **StatsSidebar** — live session stats (context window size, call count, guard stats)
- **ToolInspector** — shows the last tool call and its result
- **CommandPalette** — fuzzy command search (Ctrl+P)
- **WelcomeScreen** — shown on first launch

The TUI uses the same `get_server()` singleton and `Client(mcp)` in-process client as the CLI.

---

## 17. Evaluation Harness

**File:** `mcp_assistant/eval/harness.py`

Run with: `mcp-eval --dataset tests/eval_dataset.json`

The harness:
1. Loads a golden dataset of `{input, expected_tool, expected_params}` records
2. Runs each input through the full LLM → parse → guard pipeline
3. Computes accuracy (exact match), parameter match rate, parse failure rate, chain execution rate, p50/p95 latency
4. Prints a summary report

Used to verify that prompt changes or model swaps don't regress tool-call accuracy.

---

## 18. Configuration Reference

| Setting | Default | Source | Description |
|---------|---------|--------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | env var | Ollama server URL |
| `OLLAMA_MODEL` | `deepseek-r1:8b` | env var | Model to use |
| `OLLAMA_TIMEOUT` | `120` | env var | Request timeout (seconds) |
| `CONFIDENCE_THRESHOLD` | `0.5` | env var / .mcprc | Below this → ask confirmation |
| `CONTEXT_WINDOW_SIZE` | `10` | env var / .mcprc | Max turns in context |
| `MAX_PARSE_RETRIES` | `2` | config.py | Retry count on parse failure |
| `audit_retention_days` | `30` | .mcprc | Days to keep audit logs |
| `dry_run_mode` | `false` | .mcprc | Disable all writes/deletes |
| `sandbox_root` | project root | .mcprc | Restrict file ops to this path |

---

## 19. How to Run

### Prerequisites

```bash
# Install Ollama and pull the model
curl https://ollama.ai/install.sh | sh
ollama pull deepseek-r1:8b

# Install the package (editable)
pip install -e ".[tui,dev]"
```

### Run the TUI (default)
```bash
mcp
```

### Run the CLI
```bash
mcp --cli
```

### Run as standalone MCP server (for Claude Desktop)
```bash
mcp-server
# or: python -m mcp_assistant.server.app
```

Add to `~/.config/claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "terminal-assistant": {
      "command": "mcp-server"
    }
  }
}
```

### Run tests
```bash
pytest
```

### Verify audit chain
```bash
mcp-verify
```

### Run evaluation
```bash
mcp-eval
```

---

## 20. How to Extend

### Add a new tool

1. Pick (or create) the right sub-server in `mcp_assistant/server/tools/`.
2. Define an `async def` with `@sub_mcp.tool(annotations=..., tags={...})`.
3. Use `Annotated[type, "description"]` for each parameter; include `ctx: Context = None`.
4. No other wiring needed — `mcp.mount(sub_mcp, namespace="x")` picks it up automatically.
5. Add the new tool name to `_LEGACY_MAP` in `hallucination_guard.py` if it has an old alias.

```python
@file_mcp.tool(
    name="copy",
    annotations=ToolAnnotations(destructiveHint=False),
    tags={"file"},
)
async def copy_file(
    src: Annotated[str, "Source path"],
    dst: Annotated[str, "Destination path"],
    ctx: Context = None,
) -> str:
    """Copy a file from src to dst."""
    ...
```

### Add a new ToolKit

Add a `ToolKit` entry to `ALL_KITS` in `toolkit.py`:

```python
EDITOR_KIT = ToolKit(
    name="editor",
    tags={"file", "git"},
    description="Tools for editing workflows: file + git",
)
ALL_KITS["editor"] = EDITOR_KIT
```

### Swap the LLM model

```bash
ollama pull llama3.1:8b
export OLLAMA_MODEL=llama3.1:8b
mcp --cli
```

Or set `OLLAMA_MODEL` in your shell profile. If the new model doesn't emit `<think>` tags, `_strip_thinking_tags()` in `response_parser.py` is a no-op.

### Add a new middleware

```python
class RateLimitMiddleware(Middleware):
    _calls: dict[str, list[float]] = collections.defaultdict(list)
    _limit = 10  # max calls per tool per minute

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        tool = context.message.name
        now = time.time()
        self._calls[tool] = [t for t in self._calls[tool] if now - t < 60]
        if len(self._calls[tool]) >= self._limit:
            raise ToolError(f"Rate limit exceeded for '{tool}'")
        self._calls[tool].append(now)
        return await call_next(context)
```

Then add it to `middleware=[..., RateLimitMiddleware()]` in `app.py`.

### Add a new resource

```python
@mcp.resource("resource://perf/timing", mime_type="application/json")
def get_timing_stats() -> str:
    from mcp_assistant.server.middleware import TimingMiddleware
    return json.dumps(TimingMiddleware.global_stats(), indent=2)
```

It will automatically be accessible as a tool via `ResourcesAsTools` after the server restarts.

---

## 21. Known Gaps & Next Steps

| Gap | Effort | Notes |
|-----|--------|-------|
| Old `mcp_assistant/mcp/` and `mcp_assistant/tools/` directories | Low | Pre-rewrite modules, unused. Delete after confirming nothing imports them. |
| TUI not yet wired to `HallucinationGuard.global_stats()` | Medium | `StatsSidebar` could show live hallucination rate |
| TUI not yet wired to `TimingMiddleware.global_stats()` | Medium | `StatsSidebar` could show slowest tools |
| `PolicyMiddleware` uses legacy tool-class names for allow/block | Low | Remap to new namespace names (`"file"` instead of `"FileHandler"`) |
| No streaming output | High | Ollama supports streaming; could pipe tokens to TUI in real time |
| No multi-model support | Medium | Abstract `OllamaClient` behind an `LLMClient` protocol; add OpenAI/Anthropic adapters |
| Context window uses token-unaware turn count | Medium | Switch to token budget management using a tokenizer |
| `describe_tools` scores by tags but not by semantic similarity | High | Embed tool descriptions with a local embedding model for true semantic search |
| Eval dataset is minimal | Low | Expand `tests/eval_dataset.json` with more diverse NL inputs |

---

*This document was generated after the complete FastMCP 3.2.3 rewrite of the MCP Terminal Assistant.*
