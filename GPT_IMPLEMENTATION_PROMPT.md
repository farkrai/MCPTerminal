=============================================================================
PROJECT: MCP Terminal Assistant — Implementation Prompt
FOR: GPT 5.4 (or equivalent capable model)
SCOPE: Implement the next phase of a college major project
DATE: 2026-04-10
=============================================================================

## SECTION 0 — HOW TO USE THIS PROMPT

This prompt is self-contained. It gives you the full project context, the
codebase structure, the current evaluation results, the objectives, and the
specific implementation tasks. You do not need to search the internet. You
do not need to ask clarifying questions before starting. Work top-to-bottom
through the tasks in the order listed. After each task, verify your output
against the objectives in Section 2.

The project owner will review your output. They expect:
1. Working Python code with no placeholder comments
2. Changes that are minimal and targeted — do not refactor code you are not
   asked to change
3. All existing 65 pytest tests must still pass after your changes
4. Decisions explained when alternatives exist
5. The IMPLEMENTATION_LOG.md updated with what you completed

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## SECTION 1 — PROJECT CONTEXT

### What This Project Is

An offline, local-first AI terminal assistant. Users type natural-language
commands. A local LLM (Ollama, default model: phi3:latest) maps them to
structured JSON tool invocations. A dispatcher validates policy and executes
the appropriate tool. The LLM is a reasoning engine only — it never executes
anything directly.

Core flow:
  User NL input
    → PromptBuilder constructs system + user prompt
    → OllamaClient.generate() → raw LLM string
    → response_parser.parse_response() → MCPCall or MCPChain dataclass
    → confidence.should_clarify() → ask for clarification if low confidence
    → MCPDispatcher.dispatch() → policy check → tool.execute() → MCPResult
    → AuditLogger.log() → SHA-256 chained JSONL
    → TUI displays result

### Repository Structure

```
mcp_assistant/
  config.py          — constants, all env-var overrides
                       KEY VARS: OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT,
                                 CONFIDENCE_THRESHOLD, CONTEXT_WINDOW_SIZE
  main.py            — entry point (TUI or --cli flag)

  llm/
    client.py        — OllamaClient: generate(), generate_stream(), is_available()
                       HTTP POST to http://localhost:11434/api/generate
    prompt_builder.py — PromptBuilder: system_prompt(), user_prompt(nl, context)
                       system prompt contains: format rules + tool summary + examples
    response_parser.py — parse_response(raw_str) → MCPCall or MCPChain
                         handles 4 phi3 output formats; raises ParseError on failure
    confidence.py    — should_clarify(call, threshold), is_hallucinated_tool(call)

  mcp/
    schema.py        — MCPCall, MCPResult, MCPChain, MCPChainStep, ParseError
    base.py          — MCPTool abstract base (Plugin SDK)
                       Subclasses must set: TOOL_NAME, TOOL_DESCRIPTION,
                       SUPPORTED_ACTIONS, DESTRUCTIVE_ACTIONS, ALWAYS_CONFIRM_ACTIONS
                       Required: execute(call: MCPCall) → MCPResult (never raise)
    registry.py      — ToolRegistry.register(), .get(), .discover_plugins(), .generate_summary()
    dispatcher.py    — MCPDispatcher.dispatch(call), .dispatch_chain(chain)
                       7-step pipeline: tool exists → policy → validate → confirm → execute → audit → return
    policy.py        — PolicyConfig loaded from .mcprc (TOML)
                       sandbox_root, blocked_paths, allowed_tools, confirm_required,
                       dry_run_mode (mutable), confidence_threshold

  tools/
    file_handler.py  — FileHandler: read, write, list, search, delete
    git_tool.py      — GitTool: status, diff, log, add, commit, branch_list, branch_switch
    system_tool.py   — SystemTool: cpu_stats, ram_stats, disk_stats, list_processes,
                       kill_process, env_info
    test_runner.py   — TestRunner: detect, run, run_file, explain_failures

  audit/
    logger.py        — AuditLogger: .log(call, result), .verify_chain(path)
                       SHA-256 prev_hash→entry_hash chain in JSONL
    retention.py     — cleanup_old_logs(log_dir, retention_days)

  context/
    buffer.py        — ConversationBuffer: add_turn(), get_context(n), save(), load()
                       sliding window; persists to ~/.mcp_assistant/context.json

  tui/
    app.py           — MCPAssistantApp (Textual App)
                       CRITICAL: use self._tool_registry (NOT self._registry — Textual collision)
                       Blocking calls wrapped in asyncio.to_thread()
                       Worker pattern: self.run_worker(coro, exclusive=True)
    theme.py         — Textual CSS (3-column layout)
    widgets/
      stats_sidebar.py  — live CPU/RAM/disk every 2s
      history_panel.py  — conversation RichLog
      tool_inspector.py — last call detail view
      input_bar.py      — text input, mode badge [MCP]/[DRY]

  eval/
    dataset.py       — load_dataset(path) → list[EvalItem]
    metrics.py       — EvalResult, EvalReport, aggregation
    harness.py       — EvalHarness.run_all(), run_ablation_study()
    report.py        — JSON + Markdown report generation

plugins/
  example_plugin/tool.py  — TimeTool (demonstrate Plugin SDK)

eval_data/
  eval_dataset.json  — 60 NL→tool ground-truth items (5 categories, 3 difficulties)

.mcprc             — TOML security policy (sandbox_root CURRENTLY HARDCODED — fix needed)
pyproject.toml     — package metadata, entry points
requirements.txt   — dependencies
IMPLEMENTATION_LOG.md — living context document (always update after completing work)
```

### Key Data Types (mcp/schema.py)

```python
@dataclass
class MCPCall:
    tool: str                  # e.g. "GitTool"
    action: str                # e.g. "status"
    params: dict               # e.g. {"cwd": "."}
    raw_response: str = ""     # raw LLM string that produced this call
    confidence: float = 1.0   # LLM's self-reported confidence [0.0–1.0]

@dataclass
class MCPResult:
    call: MCPCall
    success: bool
    output: str = ""           # human-readable text for UI
    data: dict = field(default_factory=dict)   # structured data
    error: str | None = None
    duration_ms: float = 0.0

@dataclass
class MCPChainStep:
    tool: str
    action: str
    params: dict
    confidence: float = 1.0

@dataclass
class MCPChain:
    steps: list[MCPChainStep]
    description: str = ""
    continue_on_error: bool = False
```

### Current Evaluation Results (2026-04-07, phi3:latest)

| Metric             | Value    | Target      |
|--------------------|----------|-------------|
| Tool Accuracy      | 93.3%    | ≥ 90%  ✅   |
| Action Accuracy    | 65.0%    | ≥ 80%  ❌ (−15pp) |
| Parse Failure Rate | 0.0%     | < 5%   ✅   |
| Hallucination Rate | 0.0%     | < 1%   ✅   |
| Mean Latency       | 4209 ms  | < 3000 ms ❌ |
| P95 Latency        | 7888 ms  | < 6000 ms ❌ |

**Failure patterns (known root causes):**
- FileHandler: "find/search" → list (not search). 8 failures. Root cause: action
  descriptions for list and search are too similar in system prompt.
- TestRunner: "run tests" → detect (not run). 5 failures. Same root cause.
- GitTool: "show staged changes" → status (not diff). 3 failures.
- SystemTool: "memory usage" → cpu_stats. "list processes" → cpu_stats. 3 failures.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## SECTION 2 — OBJECTIVES (VERIFY AFTER EVERY TASK)

After implementing each task, check your changes against all of these. A change
that improves one objective must not regress another.

- O1 ACCURACY:      Tool Acc ≥ 90%, Action Acc ≥ 80%, Hallucination Rate < 1%.
- O2 SAFETY:        No destructive action without confirmation. Sandbox enforced at dispatch.
- O3 PORTABILITY:   Works on macOS/Linux/WSL with no hardcoded paths. Docker-runnable.
- O4 LATENCY:       Ollama calls never hang. Streaming tokens in TUI. Cache for repeats.
- O5 EXTENSIBILITY: Plugin SDK unchanged. FastMCP server optional add-on.
- O6 OBSERVABILITY: Every call audited. Token count visible. Hallucinations logged.
- O7 ACADEMIC RIGOR: Eval harness measures faithfulness + all metrics. 100+ items.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## SECTION 3 — IMPLEMENTATION TASKS

Work through these in order. Each task has a problem statement, a precise
technical specification, the files to change, and the success criterion.
Do not skip tasks. Do not combine tasks into one commit.

---

### TASK 1 — Fix Action Accuracy via Prompt Engineering
**Priority: CRITICAL. This is the #1 gap (65% vs 80% target).**

**Problem:**
phi3 cannot distinguish between:
- FileHandler.list ("show what's in a directory") vs
  FileHandler.search ("find files matching a pattern")
- TestRunner.detect ("what framework is in use?") vs
  TestRunner.run ("execute the tests")
- GitTool.status ("staged/unstaged summary") vs
  GitTool.diff ("line-level diff of changes")
- SystemTool.cpu_stats vs SystemTool.ram_stats vs SystemTool.env_info

Root cause: action descriptions in `_DEFAULT_TOOL_SUMMARY` and the system prompt
are too terse. phi3 3.8B lacks the reasoning capacity to disambiguate without
strong linguistic signals.

**Specification:**

1. In `mcp_assistant/llm/prompt_builder.py`, add a disambiguation table BEFORE
   the AVAILABLE TOOLS section in `_SYSTEM_PROMPT_TEMPLATE`:

```
ACTION DISAMBIGUATION — use this table to pick the correct action:
| User says (or implies)                                  | Tool        | Action          |
| "list", "show contents of", "what's in [folder]"        | FileHandler | list            |
| "find", "search for", "look for", "grep", "locate"      | FileHandler | search          |
| "read", "show me", "display contents of [file]"         | FileHandler | read            |
| "delete", "remove", "erase"                             | FileHandler | delete          |
| "write", "create file", "save to", "append"             | FileHandler | write           |
| "what changed", "changes since", "line-level diff"      | GitTool     | diff            |
| "what's staged", "staged changes", "ready to commit"    | GitTool     | diff            |
| "git status", "current state", "modified files"         | GitTool     | status          |
| "run tests", "execute tests", "test suite"              | TestRunner  | run             |
| "run this test file", "run only", "specific test"       | TestRunner  | run_file        |
| "what framework", "detect framework", "which test tool" | TestRunner  | detect          |
| "CPU usage", "processor"                                | SystemTool  | cpu_stats       |
| "RAM", "memory", "how much memory"                      | SystemTool  | ram_stats       |
| "disk", "storage", "free space"                         | SystemTool  | disk_stats      |
| "processes", "running programs", "top processes"        | SystemTool  | list_processes  |
| "uptime", "how long running", "system info", "hostname" | SystemTool  | env_info        |
| "kill", "terminate process"                             | SystemTool  | kill_process    |
```

2. Rewrite `SUPPORTED_ACTIONS` in each tool to include the disambiguation signal:

In `file_handler.py`:
```python
SUPPORTED_ACTIONS = {
    "list":   "List files and directories in a folder (not recursive file search). Use when the request asks what is IN a specific directory. Params: path (str)",
    "search": "Find files recursively by name pattern. Use when the request asks to FIND, SEARCH, or LOOK FOR files. Params: pattern (str, glob), path (str, optional root)",
    "read":   "Read and display the full text contents of a specific file. Params: path (str)",
    "write":  "Write or overwrite a file with new content. DESTRUCTIVE. Params: path (str), content (str)",
    "delete": "Delete a file permanently. DESTRUCTIVE. Params: path (str)",
}
```

In `test_runner.py`:
```python
SUPPORTED_ACTIONS = {
    "detect":           "Probe the project to IDENTIFY which test framework is configured (pytest or jest). Use only when the user asks WHAT framework is in use, not when they want to run tests.",
    "run":              "EXECUTE the full test suite. Use when the user says 'run tests', 'test', or 'execute tests'. Params: cwd (str, optional)",
    "run_file":         "EXECUTE a specific test file. Use when the user names a specific test file or says 'only'. Params: file (str), cwd (str, optional)",
    "explain_failures": "Send test failure output to the LLM for a plain-English explanation. Use after a failed run. Params: output (str)",
}
```

In `git_tool.py`:
```python
SUPPORTED_ACTIONS = {
    "status":        "Show high-level summary of staged/unstaged changes (like 'git status'). Use when user asks about current state, modified files, or what branch they're on.",
    "diff":          "Show line-level diff of changes. Use when the user asks WHAT CHANGED, what the differences are, or what is STAGED. Params: staged (bool, optional)",
    "log":           "Show recent commit history. Params: n (int, default 10)",
    "add":           "Stage files for commit. Params: path (str)",
    "commit":        "Commit staged changes. DESTRUCTIVE. Params: message (str)",
    "branch_list":   "List all branches.",
    "branch_switch": "Switch to a branch. DESTRUCTIVE. Params: branch (str)",
}
```

In `system_tool.py`:
```python
SUPPORTED_ACTIONS = {
    "cpu_stats":      "CPU usage percentage and core count. Use ONLY for CPU/processor questions.",
    "ram_stats":      "RAM/memory usage: total, used, available. Use for MEMORY or RAM questions.",
    "disk_stats":     "Disk/storage usage per partition. Use for DISK or STORAGE questions.",
    "list_processes": "List top N running processes by CPU. Use for PROCESS or PROGRAM questions. Params: n (int, default 15)",
    "kill_process":   "Terminate a process. ALWAYS CONFIRM. Params: pid (int) or name (str)",
    "env_info":       "System environment: OS, hostname, Python version, UPTIME. Use for UPTIME, SYSTEM INFO, or HOSTNAME questions.",
}
```

3. Add 6 few-shot examples to the system prompt (right before "Respond with
   JSON only"). Cover the 3 most-confused action pairs:

```
EXAMPLES (follow these exactly):
User: "find all python files" → {"tool": "FileHandler", "action": "search", "params": {"pattern": "*.py"}, "confidence": 0.97}
User: "list files in mcp_assistant/" → {"tool": "FileHandler", "action": "list", "params": {"path": "mcp_assistant/"}, "confidence": 0.97}
User: "run the tests" → {"tool": "TestRunner", "action": "run", "params": {}, "confidence": 0.97}
User: "what test framework is this" → {"tool": "TestRunner", "action": "detect", "params": {}, "confidence": 0.97}
User: "show staged changes" → {"tool": "GitTool", "action": "diff", "params": {"staged": true}, "confidence": 0.95}
User: "how much memory is free" → {"tool": "SystemTool", "action": "ram_stats", "params": {}, "confidence": 0.97}
```

**Files to change:**
- `mcp_assistant/llm/prompt_builder.py`
- `mcp_assistant/tools/file_handler.py` (SUPPORTED_ACTIONS only)
- `mcp_assistant/tools/git_tool.py` (SUPPORTED_ACTIONS only)
- `mcp_assistant/tools/system_tool.py` (SUPPORTED_ACTIONS only)
- `mcp_assistant/tools/test_runner.py` (SUPPORTED_ACTIONS only)

**Success criterion:**
Run the eval harness: `python -m mcp_assistant.eval.harness --label post_prompt_fix`.
Action accuracy must be ≥ 75% (improvement from 65%). Do not ship if it
regresses below 65%. Tool accuracy must remain ≥ 90%.

---

### TASK 2 — Fix Portability: .mcprc sandbox_root
**Priority: HIGH. Breaks on every machine that isn't /home/krshrivathsan/.**

**Problem:**
`.mcprc` contains `sandbox_root = "/home/krshrivathsan/MajorProject"`. This path
does not exist on macOS, Windows, or any other developer's machine. On a new
machine, every FileHandler call fails with "Path not allowed by policy".

**Specification:**

1. In `.mcprc`, change `sandbox_root` to an empty string:
   ```toml
   [security]
   sandbox_root = ""   # empty = auto-detect from project root
   ```

2. In `mcp_assistant/mcp/policy.py`, in the loader method, add logic:
   ```python
   sandbox = security_section.get("sandbox_root", "")
   if not sandbox:
       # Auto-detect: resolve to the directory where .mcprc lives
       sandbox = str(mcprc_path.parent.resolve())
   elif not Path(sandbox).is_absolute():
       # Relative path: resolve relative to .mcprc location
       sandbox = str((mcprc_path.parent / sandbox).resolve())
   policy.sandbox_root = sandbox
   ```
   Thread `mcprc_path` through `PolicyConfig.load_or_default(path)` if not
   already present.

3. In `PolicyConfig.default()`, set `sandbox_root` to
   `str(Path(__file__).parent.parent.parent.resolve())` (project root from
   the policy module's location).

4. Replace all hardcoded `/home/krshrivathsan/MajorProject` references in:
   - `docs/USER_GUIDE.md` → use `<project-root>` placeholder
   - `docs/KNOWLEDGE_TRANSFER.md` → same

**Files to change:**
- `.mcprc`
- `mcp_assistant/mcp/policy.py`
- `docs/USER_GUIDE.md`
- `docs/KNOWLEDGE_TRANSFER.md`

**Success criterion:**
Clone repo to a temp directory, run `python -m mcp_assistant.main --cli`,
type "list files". Must succeed with no policy errors.
`pytest tests/test_policy.py` must pass.

---

### TASK 3 — Incremental Retry with Exponential Backoff
**Priority: HIGH. System hangs on Ollama transient failures.**

**Problem:**
`OllamaClient.generate()` raises `requests.ConnectionError` or
`requests.Timeout` if Ollama is busy. There is no retry logic. The command
fails permanently on what may be a 1-second hiccup. Parse-retry logic is also
duplicated between `main.py` and `tui/app.py`.

**Specification:**

1. In `mcp_assistant/llm/client.py`, add retry with exponential backoff
   and jitter to `generate()`:

```python
import time, random

def generate(self, prompt, system="", temperature=config.OLLAMA_TEMP_STRUCTURED,
             max_retries=config.OLLAMA_MAX_RETRIES) -> str:
    delay = 1.0
    last_exc = None
    for attempt in range(max_retries):
        try:
            return self._do_generate(prompt, system, temperature)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                time.sleep(delay + random.uniform(0.0, 0.5))
                delay = min(delay * 2.0, 30.0)
    raise last_exc

def _do_generate(self, prompt, system, temperature) -> str:
    # existing POST logic moved here verbatim
    ...
```

2. Add to `config.py`:
   ```python
   OLLAMA_MAX_RETRIES: int = int(os.environ.get("OLLAMA_MAX_RETRIES", "3"))
   ```

3. Create `mcp_assistant/llm/inference.py` — centralises the full
   prompt→LLM→parse pipeline (removes duplication from main.py and tui/app.py):

```python
# mcp_assistant/llm/inference.py
from mcp_assistant.llm.client import OllamaClient
from mcp_assistant.llm.prompt_builder import PromptBuilder
from mcp_assistant.llm.response_parser import parse_response
from mcp_assistant.mcp.schema import MCPCall, MCPChain, ParseError
from mcp_assistant import config

def infer_call(
    nl_input: str,
    client: OllamaClient,
    builder: PromptBuilder,
    context: list[dict] | None = None,
    max_parse_retries: int = config.MAX_PARSE_RETRIES,
) -> MCPCall | MCPChain:
    """
    Full inference pipeline: prompt → LLM → parse → MCPCall/MCPChain.
    Retries up to max_parse_retries times on ParseError, strengthening the
    reminder on each attempt. Raises ParseError after exhausting retries.
    """
    system = builder.system_prompt()
    user = builder.user_prompt(nl_input, context)
    reminder = ""
    for attempt in range(max_parse_retries + 1):
        raw = client.generate(system=system, prompt=user + reminder)
        try:
            return parse_response(raw)
        except ParseError:
            if attempt == max_parse_retries:
                raise
            reminder = "\n\nREMINDER: Respond ONLY with a single valid JSON object. No prose."
    raise ParseError("Exhausted retries")
```

4. Update `main.py` and `tui/app.py` to call `infer_call()` instead of
   their inline retry loops.

**Files to change:**
- `mcp_assistant/llm/client.py`
- `mcp_assistant/llm/inference.py` (NEW)
- `mcp_assistant/config.py`
- `mcp_assistant/main.py`
- `mcp_assistant/tui/app.py`

**Success criterion:**
`pytest tests/test_response_parser.py` must pass.
Stop Ollama, run a command — must retry 3× with increasing delays then show a
clean error (no traceback). Restart Ollama — next command must succeed.

---

### TASK 4 — Cold-Storage LLM Response Cache
**Priority: MEDIUM-HIGH. Repeated identical queries waste 4+ seconds each.**

**Problem:**
Every query hits Ollama even when the exact same prompt was used 5 seconds ago.
In the eval harness, this inflates latency. In interactive use, "show git status"
three times takes 3×4s instead of 4s+0s+0s.

**Specification:**

1. Create `mcp_assistant/llm/cache.py`:

```python
"""
SQLite-backed LLM response cache. Keyed by SHA-256(system_prompt + user_prompt).
Persists across sessions in ~/.mcp_assistant/llm_cache.db.
TTL is configurable; NL/high-temp calls are never cached.
"""
import hashlib, os, sqlite3, time
from pathlib import Path
from mcp_assistant import config

CACHE_TTL_S: int = int(os.environ.get("MCP_CACHE_TTL", "3600"))
_DB_PATH = config.CONTEXT_PERSIST_DIR / "llm_cache.db"

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_cache (
            key      TEXT PRIMARY KEY,
            response TEXT NOT NULL,
            ts       REAL NOT NULL,
            ttl_s    INTEGER NOT NULL
        )
    """)
    conn.commit()
    return conn

def _key(system: str, user: str) -> str:
    return hashlib.sha256(f"{system}\n\n{user}".encode()).hexdigest()

def get(system: str, user: str) -> str | None:
    conn = _connect()
    row = conn.execute(
        "SELECT response, ts, ttl_s FROM llm_cache WHERE key = ?",
        (_key(system, user),)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    response, ts, ttl_s = row
    if ttl_s > 0 and (time.time() - ts) > ttl_s:
        return None  # expired
    return response

def put(system: str, user: str, response: str, ttl_s: int = CACHE_TTL_S) -> None:
    if ttl_s == 0:
        return
    conn = _connect()
    conn.execute(
        "INSERT OR REPLACE INTO llm_cache (key, response, ts, ttl_s) VALUES (?,?,?,?)",
        (_key(system, user), response, time.time(), ttl_s)
    )
    conn.commit()
    conn.close()

def clear_expired() -> int:
    conn = _connect()
    cursor = conn.execute(
        "DELETE FROM llm_cache WHERE ttl_s > 0 AND (? - ts) > ttl_s",
        (time.time(),)
    )
    conn.commit()
    count = cursor.rowcount
    conn.close()
    return count

def clear_all() -> None:
    conn = _connect()
    conn.execute("DELETE FROM llm_cache")
    conn.commit()
    conn.close()

def _cli() -> None:
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "clear":
        clear_all()
        print("LLM cache cleared.")
    else:
        print("Usage: mcp-cache clear")
```

2. Wire into `mcp_assistant/llm/inference.py` (from Task 3):

```python
from mcp_assistant.llm import cache as llm_cache

def infer_call(..., use_cache: bool = True) -> MCPCall | MCPChain:
    system = builder.system_prompt()
    user = builder.user_prompt(nl_input, context)

    if use_cache:
        cached = llm_cache.get(system, user)
        if cached:
            return parse_response(cached)

    reminder = ""
    for attempt in range(max_parse_retries + 1):
        raw = client.generate(system=system, prompt=user + reminder)
        try:
            result = parse_response(raw)
            if use_cache:
                llm_cache.put(system, user, raw)
            return result
        except ParseError:
            if attempt == max_parse_retries:
                raise
            reminder = "\n\nREMINDER: Respond ONLY with a single valid JSON object. No prose."
    raise ParseError("Exhausted retries")
```

3. Add `!cache clear` special command to `main.py` and `tui/app.py`.

4. Add entry point to `pyproject.toml`:
   ```toml
   mcp-cache = "mcp_assistant.llm.cache:_cli"
   ```

5. In `eval/harness.py`, pass `use_cache=False` to `infer_call()` — eval must
   always hit Ollama fresh.

**Files to change / create:**
- `mcp_assistant/llm/cache.py` (NEW)
- `mcp_assistant/llm/inference.py`
- `mcp_assistant/main.py`
- `mcp_assistant/tui/app.py`
- `mcp_assistant/eval/harness.py`
- `pyproject.toml`

**Success criterion:**
Same command twice in CLI: second must return in < 100 ms. Cache file exists
at `~/.mcp_assistant/llm_cache.db`. Eval accuracy unchanged (cache bypassed).

---

### TASK 5 — Token-Aware Context Window
**Priority: MEDIUM. Prevents silent context overflow on phi3's 4096-token limit.**

**Problem:**
`ConversationBuffer` caps at `max_turns * 2` entries but does not count tokens.
With 10 long turns, the context string can silently overflow phi3's window,
causing truncation or hallucination. Users cannot see how much context is loaded.

**Specification:**

1. Create `mcp_assistant/llm/tokenizer.py`:
```python
def count_tokens(text: str) -> int:
    """Estimate token count. Uses tiktoken if available, else char/4 heuristic."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        return max(1, len(text) // 4)
```

2. Add to `config.py`:
   ```python
   MAX_CONTEXT_TOKENS: int = int(os.environ.get("MAX_CONTEXT_TOKENS", "3000"))
   ```

3. In `context/buffer.py`, make `get_context(n)` token-aware:
```python
from mcp_assistant.llm.tokenizer import count_tokens
from mcp_assistant import config

def get_context(self, n=None) -> list[dict]:
    turns = self._history[-(((n or len(self._history)) * 2)):]
    turns_clean = [{"role": t["role"], "content": t["content"]} for t in turns]
    # Drop oldest pairs until within token budget
    while turns_clean:
        assembled = "\n".join(f"[{t['role'].upper()}] {t['content']}" for t in turns_clean)
        if count_tokens(assembled) <= config.MAX_CONTEXT_TOKENS:
            break
        turns_clean = turns_clean[2:]  # drop oldest user+assistant pair
    return turns_clean
```

4. In `tui/widgets/stats_sidebar.py`, add a "CTX: N tok" display line that
   refreshes alongside the other stats.

**Files to change / create:**
- `mcp_assistant/llm/tokenizer.py` (NEW)
- `mcp_assistant/config.py`
- `mcp_assistant/context/buffer.py`
- `mcp_assistant/tui/widgets/stats_sidebar.py`

**Success criterion:**
`pytest tests/test_context_buffer.py` passes. Filling buffer with 10 long turns
and calling `get_context()` must return only as many turns as fit within
MAX_CONTEXT_TOKENS. TUI sidebar shows "CTX: N tok".

---

### TASK 6 — Streaming LLM Output in TUI
**Priority: MEDIUM. Largest perceived-latency improvement.**

**Problem:**
TUI shows nothing while Ollama generates (3–8s). `generate_stream()` exists in
OllamaClient but is not wired. Users see a frozen UI and assume it crashed.

**Specification:**

Approach: stream tokens to HistoryPanel for live visual feedback. The full
accumulated string is still used for parsing — no parse logic changes.

1. Add to `OllamaClient` in `llm/client.py`:
```python
async def generate_stream_async(self, prompt, system="", temperature=0.1):
    """Async generator yielding tokens from the Ollama streaming API."""
    import asyncio
    for token in self.generate_stream(prompt=prompt, system=system, temperature=temperature):
        yield token
        await asyncio.sleep(0)  # yield control back to event loop
```

2. Add three methods to `HistoryPanel` in `tui/widgets/history_panel.py`:
   - `start_streaming_response()` — add a dim "Thinking…" placeholder line
   - `append_streaming_token(token: str)` — extend the current streaming line
   - `finish_streaming_response()` — change line style from dim to normal

3. In `tui/app.py`, replace the blocking generate call with a streaming path.
   Continue to accumulate the full string for parsing after streaming completes.
   Fallback silently to blocking `generate()` if streaming raises an exception.

4. In `InputBar`, show a cycling spinner character while first token hasn't
   arrived yet. Clear spinner on `finish_streaming_response`.

**Files to change:**
- `mcp_assistant/llm/client.py`
- `mcp_assistant/tui/app.py`
- `mcp_assistant/tui/widgets/history_panel.py`
- `mcp_assistant/tui/widgets/input_bar.py`

**Success criterion:**
Launch TUI, type any command. Tokens must appear incrementally — no 8s freeze.
Final parsed result must match non-streaming path. `pytest tests/` still passes.

---

### TASK 7 — TUI Confirmation Modal
**Priority: MEDIUM. Current auto-confirm is a safety regression.**

**Problem:**
Dispatcher in TUI receives `confirm_fn=lambda _: True`. Every destructive
operation (write, delete, commit, kill_process) is silently auto-confirmed
with no user knowledge. This violates O2 (Safety).

**Specification:**

1. Create `mcp_assistant/tui/widgets/confirm_modal.py`:
```python
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

class ConfirmModal(ModalScreen[bool]):
    def __init__(self, preview: str) -> None:
        super().__init__()
        self._preview = preview

    def compose(self) -> ComposeResult:
        yield Static(self._preview, id="preview")
        yield Label("Proceed with this operation?")
        yield Button("Yes", variant="warning", id="btn-yes")
        yield Button("No", variant="default", id="btn-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-yes")
```

2. In `tui/app.py`, create a sync-bridge confirm function and wire it to
   the dispatcher. The dispatcher calls confirm_fn synchronously from inside
   `asyncio.to_thread()`. Use `concurrent.futures.Future` to bridge:

```python
import concurrent.futures

def _make_sync_confirm(self) -> Callable[[str], bool]:
    loop = asyncio.get_event_loop()
    def _confirm(preview: str) -> bool:
        future: concurrent.futures.Future[bool] = concurrent.futures.Future()
        async def _push():
            result = await self.push_screen_wait(ConfirmModal(preview))
            future.set_result(result)
        loop.call_soon_threadsafe(asyncio.ensure_future, _push())
        return future.result(timeout=120)
    return _confirm
```

Replace `confirm_fn=lambda _: True` with `confirm_fn=self._make_sync_confirm()`.

3. Add CSS for `ConfirmModal` in `theme.py`.

**Files to change / create:**
- `mcp_assistant/tui/widgets/confirm_modal.py` (NEW)
- `mcp_assistant/tui/app.py`
- `mcp_assistant/tui/theme.py`

**Success criterion:**
Type "write hello to test.txt" in TUI. Modal must appear with preview + buttons.
No → operation cancelled. Yes → file written. `pytest tests/test_dispatcher.py`
must pass (CLI confirm path is unchanged).

---

### TASK 8 — FastMCP Server Wrapper
**Priority: MEDIUM for interoperability. HIGH for academic novelty.**

**Problem:**
The custom MCPTool/MCPDispatcher is not compatible with the official MCP
specification. Tools cannot be called from Claude Desktop, Cursor, or any
MCP-compliant host. A FastMCP wrapper layer fixes this without touching core code.

**Approach: Additive wrapper only. No core rewrite.**
Existing TUI/CLI, Plugin SDK, dispatcher, and all 65 tests are untouched.

**Specification:**

1. Add to `requirements.txt`: `fastmcp>=0.4.0`
   Add to `pyproject.toml`:
   ```toml
   [project.optional-dependencies]
   server = ["fastmcp>=0.4.0"]
   ```

2. Create `mcp_assistant/fastmcp_server.py`:

```python
"""
FastMCP server wrapper. Exposes MCP Terminal Assistant tools via the official
MCP protocol. Supports stdio (Claude Desktop) and HTTP/SSE (network) transports.

Usage:
  python -m mcp_assistant.fastmcp_server          # stdio (Claude Desktop)
  python -m mcp_assistant.fastmcp_server --http   # HTTP on port 8765
"""
from fastmcp import FastMCP
from mcp_assistant.mcp.schema import MCPCall
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant.mcp.registry import ToolRegistry
from mcp_assistant.mcp.dispatcher import MCPDispatcher
from mcp_assistant.audit.logger import AuditLogger
from mcp_assistant.tools.file_handler import FileHandler
from mcp_assistant.tools.git_tool import GitTool
from mcp_assistant.tools.system_tool import SystemTool
from mcp_assistant.tools.test_runner import TestRunner
from mcp_assistant import config

config.ensure_dirs()
policy = PolicyConfig.load_or_default(config.MCPRC_FILE)
registry = ToolRegistry()
registry.register(FileHandler(policy))
registry.register(GitTool())
registry.register(SystemTool())
registry.register(TestRunner())
audit = AuditLogger(config.AUDIT_LOG_DIR)
dispatcher = MCPDispatcher(registry, policy, audit, confirm_fn=lambda _: True)

mcp = FastMCP(
    name="MCP Terminal Assistant",
    instructions="Executes file, git, system, and test operations safely via MCP.",
)

def _dispatch(tool: str, action: str, params: dict) -> str:
    call = MCPCall(tool=tool, action=action, params=params, confidence=1.0)
    result = dispatcher.dispatch(call)
    if not result.success:
        raise ValueError(result.error or result.output)
    return result.output

@mcp.tool()
def git_status(cwd: str = ".") -> str:
    """Show git status for the current repository."""
    return _dispatch("GitTool", "status", {"cwd": cwd})

@mcp.tool()
def git_diff(staged: bool = False, cwd: str = ".") -> str:
    """Show git diff. Set staged=True to see staged changes."""
    return _dispatch("GitTool", "diff", {"staged": staged, "cwd": cwd})

@mcp.tool()
def git_log(n: int = 10, cwd: str = ".") -> str:
    """Show recent git commit history."""
    return _dispatch("GitTool", "log", {"n": n, "cwd": cwd})

@mcp.tool()
def file_read(path: str) -> str:
    """Read and return the contents of a file."""
    return _dispatch("FileHandler", "read", {"path": path})

@mcp.tool()
def file_list(path: str = ".") -> str:
    """List files and directories in a folder."""
    return _dispatch("FileHandler", "list", {"path": path})

@mcp.tool()
def file_search(pattern: str, path: str = ".") -> str:
    """Find files recursively matching a glob pattern."""
    return _dispatch("FileHandler", "search", {"pattern": pattern, "path": path})

@mcp.tool()
def system_cpu() -> str:
    """Show CPU usage statistics."""
    return _dispatch("SystemTool", "cpu_stats", {})

@mcp.tool()
def system_ram() -> str:
    """Show RAM/memory usage statistics."""
    return _dispatch("SystemTool", "ram_stats", {})

@mcp.tool()
def system_disk() -> str:
    """Show disk usage per partition."""
    return _dispatch("SystemTool", "disk_stats", {})

@mcp.tool()
def system_processes(n: int = 15) -> str:
    """List top N running processes by CPU usage."""
    return _dispatch("SystemTool", "list_processes", {"n": n})

@mcp.tool()
def test_detect(cwd: str = ".") -> str:
    """Detect the test framework in the project."""
    return _dispatch("TestRunner", "detect", {"cwd": cwd})

@mcp.tool()
def test_run(cwd: str = ".") -> str:
    """Run the full test suite."""
    return _dispatch("TestRunner", "run", {"cwd": cwd})

if __name__ == "__main__":
    import sys
    if "--http" in sys.argv:
        mcp.run(transport="sse", host="0.0.0.0", port=8765)
    else:
        mcp.run(transport="stdio")
```

3. Add to `pyproject.toml` scripts:
   ```toml
   mcp-server = "mcp_assistant.fastmcp_server:mcp.run"
   ```

4. Add Claude Desktop integration instructions to `docs/USER_GUIDE.md`:
   ```json
   {
     "mcpServers": {
       "terminal-assistant": {
         "command": "python",
         "args": ["-m", "mcp_assistant.fastmcp_server"]
       }
     }
   }
   ```

5. Create `tests/test_fastmcp_server.py` (skip if fastmcp not installed):
```python
import pytest
fastmcp = pytest.importorskip("fastmcp")

def test_server_imports():
    from mcp_assistant import fastmcp_server
    assert fastmcp_server.mcp is not None

def test_tools_registered():
    from mcp_assistant import fastmcp_server
    names = [t.name for t in fastmcp_server.mcp._tools.values()]
    assert "git_status" in names
    assert "file_read" in names
```

**Files to change / create:**
- `mcp_assistant/fastmcp_server.py` (NEW)
- `requirements.txt`
- `pyproject.toml`
- `docs/USER_GUIDE.md`
- `tests/test_fastmcp_server.py` (NEW)

**Success criterion:**
`python -m mcp_assistant.fastmcp_server` starts without errors.
`pytest tests/test_fastmcp_server.py` passes.
`git_status` tool appears in FastMCP tool enumeration.

---

### TASK 9 — Faithfulness Metric & Eval Dataset Expansion
**Priority: MEDIUM. Required for academic completeness (O7).**

**Problem:**
Eval measures string-match accuracy only. A tool call that returns an error
scores 100% accuracy but 0% real-world usefulness. Faithfulness is the missing
dimension. Dataset is also small at 60 items.

**Specification:**

1. Add `faithfulness_score: float | None = None` to `EvalResult` in
   `eval/metrics.py`.

2. Add `faithfulness_score() -> float` to `EvalReport`:
   ```python
   def faithfulness_score(self) -> float:
       scored = [r.faithfulness_score for r in self.results if r.faithfulness_score is not None]
       return sum(scored) / len(scored) if scored else 0.0
   ```

3. In `eval/harness.py`, compute heuristic faithfulness after each dispatch:
   ```python
   if not result.success:
       faithfulness = 0.0
   elif len(result.output.strip()) < 20:
       faithfulness = 0.5
   else:
       faithfulness = 1.0
   eval_result.faithfulness_score = faithfulness
   ```

4. Add "Faithfulness Score" row to the Markdown report in `eval/report.py`.

5. Expand `eval_data/eval_dataset.json` from 60 to 80 items (IDs 61–80).
   Add 10 edge-case file_ops, 5 git_ops, 5 system_ops. Follow existing schema
   exactly. All new items must have valid ground_truth fields.

**Files to change:**
- `mcp_assistant/eval/metrics.py`
- `mcp_assistant/eval/harness.py`
- `mcp_assistant/eval/report.py`
- `eval_data/eval_dataset.json`

**Success criterion:**
`pytest tests/test_eval.py` passes (update expected counts).
Eval report includes Faithfulness Score. Dataset has exactly 80 items.

---

### TASK 10 — Docker Compose for Portability
**Priority: LOW-MEDIUM. Completes O3.**

**Specification:**

1. Create `Dockerfile`:
```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN pip install -e .
ENTRYPOINT ["python", "-m", "mcp_assistant.main", "--cli"]
```

2. Create `docker-compose.yml`:
```yaml
version: "3.9"
services:
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped

  mcp-assistant:
    build: .
    stdin_open: true
    tty: true
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
      - OLLAMA_MODEL=phi3:latest
    depends_on:
      - ollama
    volumes:
      - ./audit_logs:/app/audit_logs
      - mcp_context:/root/.mcp_assistant

volumes:
  ollama_data:
  mcp_context:
```

3. Create `.dockerignore`:
```
venv/
__pycache__/
*.pyc
audit_logs/
eval_results/
.git/
```

4. Add Docker quickstart to `docs/USER_GUIDE.md`:
```
## Docker Quickstart
docker compose up -d ollama
docker compose exec ollama ollama pull phi3:latest
docker compose run --rm mcp-assistant
```

**Files to create:**
- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`

**Success criterion:**
`docker compose build` succeeds. `docker compose run --rm mcp-assistant` starts
CLI mode and can reach Ollama via the `ollama` service.

---

### TASK 11 — 3-Tier Multi-Model Architecture
**Priority: HIGH for both performance and quality. Implement after Tasks 1–4.**

---

#### Background

Every LLM call in the current system uses the same phi3:latest (3.8B) model
regardless of what the call needs to do. This is suboptimal in both directions:

- **Simple routing (80% of queries):** "show git status" → MCPCall JSON. This
  is a structured classification task. phi3 3.8B takes ~4s. A 1.5B model with
  JSON schema enforcement takes ~1s with equal or better JSON accuracy.
- **Complex NL reasoning (15% of queries):** "explain these test failures". This
  needs broad language understanding and multi-step reasoning. phi3 3.8B produces
  marginal output. A 7B–8B model produces significantly better explanations.
- **Chain aggregation (5% of queries):** After a multi-step chain, synthesise
  results into a structured summary. Needs strong reasoning AND structured output.

A 3-tier routing architecture matches model size to task type. Users who only
have phi3:mini + phi3 installed get the default (same as today, but 4× faster
routing). Users with more RAM and larger models get quality improvements.
No tier is mandatory beyond the router.

---

#### The 3 Tiers

```
┌─────────────────────────────────────────────────────────────────────┐
│ TIER 1 — ROUTER (always loaded, every query)                        │
│ Model: phi3:mini (1.5B, ~1GB RAM)  +  Ollama structured output      │
│ Job: classify intent → MCPCall JSON + complexity field               │
│ Latency: ~1s (vs 4s current)  ·  Parse failures: ≈ 0% (schema)     │
└───────────────────────┬─────────────────────────────────────────────┘
                        │ MCPCall (tool, action, params, complexity)
                        │
              ┌─────────┴──────────┐
              │ complexity?        │
     "routing"│          "low"     │ "medium"        "high"
     (no NL   │        ↓           ↓                  ↓
      needed) │  ┌──────────────────────────────────────────────┐
              │  │ TIER 2 — EXECUTOR (loaded on demand)         │
              │  │ "low"    → EXECUTOR_MODEL_LOW    (3B default) │
              │  │ "medium" → EXECUTOR_MODEL_MEDIUM (5B default) │
              │  │ "high"   → EXECUTOR_MODEL_HIGH   (8B default) │
              │  │ Job: NL reasoning — explain, summarise, answer │
              │  └───────────────────┬──────────────────────────┘
              │                      │
              └──────────┬───────────┘
                         │ MCPResult (from dispatcher)
                         │
              ┌──────────▼───────────────────────────────────────┐
              │ TIER 3 — AGGREGATOR (chain synthesis only)        │
              │ Model: AGGREGATOR_MODEL (5B+ recommended)         │
              │ Triggered: when chain.steps ≥ 2, all completed    │
              │ Job: synthesise step results → structured summary  │
              │ Output: guaranteed schema-valid via Ollama format  │
              └──────────────────────────────────────────────────┘
```

---

#### Resource Configurations & Feasibility

| Config | Models needed | Download | Peak RAM | Best for |
|--------|--------------|----------|----------|----------|
| **Minimal (default)** | phi3:mini + phi3:latest | ~3.3GB | ~3.3GB | 8GB laptops — same as today + faster routing |
| Medium | phi3:mini + phi3:latest + llama3.2:3b | ~6GB | ~4.3GB | 8GB laptops |
| Full | phi3:mini + llama3.2:3b + llama3.1:8b | ~13GB | ~10GB | 16GB machines |
| Max | phi3:mini + llama3.2:3b + llama3.1:8b (aggregator) | same | ~10GB | 16GB machines |

**The default config uses only 1GB more RAM than today** (phi3:mini stays resident
at 1GB; phi3 loaded on demand). 80% of queries become 4× faster. The user does
not need to download any new model to benefit.

---

#### Ollama Structured Output — The Key Enabler

Ollama >= 0.1.34 supports a `format` parameter in the API request body. When
set to a JSON Schema dict, Ollama uses grammar-constrained decoding to guarantee
the output matches the schema — even with a 1.5B model. This eliminates parse
failures for the router and guarantees structured aggregator output.

For the router, define `MCPCall_SCHEMA` in `mcp/schema.py`:
```python
MCPCall_SCHEMA = {
    "type": "object",
    "required": ["tool", "action", "params", "confidence", "complexity"],
    "properties": {
        "tool":       {"type": "string"},
        "action":     {"type": "string"},
        "params":     {"type": "object"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "complexity": {"type": "string", "enum": ["routing", "low", "medium", "high"]}
    },
    "additionalProperties": False
}
```

For the chain aggregator, define `ChainSummary_SCHEMA`:
```python
ChainSummary_SCHEMA = {
    "type": "object",
    "required": ["summary", "steps_succeeded", "steps_failed", "overall_status"],
    "properties": {
        "summary":         {"type": "string"},
        "steps_succeeded": {"type": "integer"},
        "steps_failed":    {"type": "integer"},
        "overall_status":  {"type": "string", "enum": ["success", "partial", "failure"]}
    }
}
```

---

#### Graceful Fallback Chain

If a preferred model is not installed in Ollama, fall back:
```
EXECUTOR_MODEL_HIGH → EXECUTOR_MODEL_MEDIUM → EXECUTOR_MODEL_LOW → ROUTER_MODEL
AGGREGATOR_MODEL    → EXECUTOR_MODEL_HIGH   → EXECUTOR_MODEL_LOW → ROUTER_MODEL
```

The `ModelRouter` class handles this by calling `OllamaClient.list_models()`
at startup and resolving each tier to the best available model. Log which model
was actually used in the audit entry (`model_used` field on MCPResult).

---

#### Specification

**Files to create:**
- `mcp_assistant/llm/model_router.py`

**Files to change:**
- `mcp_assistant/config.py`
- `mcp_assistant/llm/client.py`
- `mcp_assistant/llm/inference.py`
- `mcp_assistant/mcp/schema.py`
- `mcp_assistant/mcp/dispatcher.py`
- `mcp_assistant/audit/logger.py`
- `tests/test_model_router.py` (NEW)

---

**Step 1 — Add tier constants to `config.py`:**

```python
# Multi-tier model routing (Sprint J)
ROUTER_MODEL: str           = os.environ.get("ROUTER_MODEL",           "phi3:mini")
EXECUTOR_MODEL_LOW: str     = os.environ.get("EXECUTOR_MODEL_LOW",     OLLAMA_MODEL)
EXECUTOR_MODEL_MEDIUM: str  = os.environ.get("EXECUTOR_MODEL_MEDIUM",  EXECUTOR_MODEL_LOW)
EXECUTOR_MODEL_HIGH: str    = os.environ.get("EXECUTOR_MODEL_HIGH",    EXECUTOR_MODEL_MEDIUM)
AGGREGATOR_MODEL: str       = os.environ.get("AGGREGATOR_MODEL",       EXECUTOR_MODEL_HIGH)
```

---

**Step 2 — Make model per-call in `OllamaClient` (`llm/client.py`):**

```python
def generate(
    self,
    prompt: str,
    system: str = "",
    temperature: float = config.OLLAMA_TEMP_STRUCTURED,
    model: str | None = None,
    format_schema: dict | None = None,  # NEW — Ollama structured output
    max_retries: int = config.OLLAMA_MAX_RETRIES,
) -> str:
    ...
    # In the POST payload:
    payload = {
        "model": model or config.OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if format_schema is not None:
        payload["format"] = format_schema
    ...

def ollama_version(self) -> tuple[int, int, int]:
    """Return Ollama server version as (major, minor, patch)."""
    resp = self._session.get(f"{self._base_url}/api/version", timeout=5)
    v = resp.json().get("version", "0.0.0")
    return tuple(int(x) for x in v.split(".")[:3])
```

---

**Step 3 — Create `mcp_assistant/llm/model_router.py`:**

```python
"""
ModelRouter: resolves which Ollama model to use for each inference tier
based on configured tier models and what is actually available.
"""
from __future__ import annotations
import logging
from mcp_assistant import config
from mcp_assistant.llm.client import OllamaClient

log = logging.getLogger(__name__)

# Complexity levels emitted by the router model
COMPLEXITY_ROUTING = "routing"
COMPLEXITY_LOW     = "low"
COMPLEXITY_MEDIUM  = "medium"
COMPLEXITY_HIGH    = "high"

# NL call types that bypass the dispatcher and go directly to an executor model
NL_CALL_TYPES = {"explain_failures", "summarize_git_diff", "clarification"}


class ModelRouter:
    def __init__(self, client: OllamaClient) -> None:
        self._client = client
        self._available: set[str] = set()
        self._resolved: dict[str, str] = {}

    def warm_up(self) -> None:
        """Call at startup. Resolves each tier to the best available model."""
        try:
            self._available = {m["name"] for m in self._client.list_models()}
        except Exception:
            log.warning("Could not list Ollama models — falling back to defaults.")
            self._available = set()

        self._resolved = {
            "router":   self._resolve(config.ROUTER_MODEL),
            "low":      self._resolve(config.EXECUTOR_MODEL_LOW),
            "medium":   self._resolve(config.EXECUTOR_MODEL_MEDIUM),
            "high":     self._resolve(config.EXECUTOR_MODEL_HIGH),
            "aggregator": self._resolve(config.AGGREGATOR_MODEL),
        }
        log.info("Model tiers resolved: %s", self._resolved)

    def router_model(self) -> str:
        return self._resolved.get("router", config.ROUTER_MODEL)

    def executor_model(self, complexity: str) -> str:
        key = complexity if complexity in ("low", "medium", "high") else "low"
        return self._resolved.get(key, config.OLLAMA_MODEL)

    def aggregator_model(self) -> str:
        return self._resolved.get("aggregator", config.OLLAMA_MODEL)

    def _resolve(self, preferred: str) -> str:
        """Return preferred if available, else walk the fallback chain."""
        fallback_chain = [
            preferred,
            config.EXECUTOR_MODEL_HIGH,
            config.EXECUTOR_MODEL_MEDIUM,
            config.EXECUTOR_MODEL_LOW,
            config.ROUTER_MODEL,
        ]
        for model in fallback_chain:
            # Available check: try exact name, then name without tag
            base = model.split(":")[0]
            if any(m == model or m.startswith(base) for m in self._available):
                if model != preferred:
                    log.warning("Model '%s' not found — using '%s' instead.", preferred, model)
                return model
        # Last resort: return preferred and let Ollama error
        return preferred

    def supports_structured_output(self) -> bool:
        """True if Ollama version >= 0.1.34 (structured output support)."""
        try:
            v = self._client.ollama_version()
            return v >= (0, 1, 34)
        except Exception:
            return False
```

---

**Step 4 — Update `llm/inference.py` to use ModelRouter:**

Extend `infer_call()` with a two-phase approach:

```python
from mcp_assistant.llm.model_router import ModelRouter, NL_CALL_TYPES
from mcp_assistant.mcp.schema import MCPCall_SCHEMA

def infer_call(
    nl_input: str,
    client: OllamaClient,
    builder: PromptBuilder,
    model_router: ModelRouter,
    context: list[dict] | None = None,
    max_parse_retries: int = config.MAX_PARSE_RETRIES,
    use_cache: bool = True,
) -> MCPCall | MCPChain:
    system = builder.system_prompt()
    user   = builder.user_prompt(nl_input, context)

    # Check cache first
    if use_cache:
        cached = llm_cache.get(system, user)
        if cached:
            return parse_response(cached)

    # Phase 1 — Routing call (always uses ROUTER_MODEL, always fast)
    use_format = model_router.supports_structured_output()
    raw = client.generate(
        prompt=user,
        system=system,
        temperature=config.OLLAMA_TEMP_STRUCTURED,
        model=model_router.router_model(),
        format_schema=MCPCall_SCHEMA if use_format else None,
    )

    # Parse — if structured output was used, this should never fail
    result = parse_response(raw)

    # Phase 2 — NL reasoning (only if complexity requires it)
    # The 'complexity' field is stripped from MCPCall before dispatch;
    # it is only read here to select the executor model.
    complexity = getattr(result, "_complexity", "routing")  # set by parse_response
    if complexity != "routing" and isinstance(result, MCPCall) and result.action in NL_CALL_TYPES:
        exec_model = model_router.executor_model(complexity)
        # Re-generate with stronger model for the NL task
        # (This only applies to NL generation calls, not dispatch routing)
        raw = client.generate(
            prompt=user,
            system=system,
            temperature=config.OLLAMA_TEMP_NL,
            model=exec_model,
        )
        result = parse_response(raw)

    if use_cache:
        llm_cache.put(system, user, raw)

    return result
```

---

**Step 5 — Add chain aggregation to `MCPDispatcher.dispatch_chain()` (`mcp/dispatcher.py`):**

```python
def dispatch_chain(
    self,
    chain: MCPChain,
    model_router: ModelRouter | None = None,
) -> list[MCPResult]:
    results = []
    for i, step in enumerate(chain.steps):
        params = _resolve_templates(step.params, results)
        call   = MCPCall(tool=step.tool, action=step.action,
                         params=params, confidence=step.confidence)
        result = self.dispatch(call)
        results.append(result)
        if not result.success and not chain.continue_on_error:
            break

    # Aggregation: if ≥ 2 steps completed and model_router provided
    if model_router and len(results) >= 2:
        self._aggregate_chain(chain, results, model_router)

    return results

def _aggregate_chain(
    self,
    chain: MCPChain,
    results: list[MCPResult],
    model_router: ModelRouter,
) -> None:
    """Generate a structured summary of chain results using the aggregator model."""
    from mcp_assistant.llm.client import OllamaClient
    from mcp_assistant.mcp.schema import ChainSummary_SCHEMA

    steps_text = "\n".join(
        f"Step {i+1} ({r.call.tool}.{r.call.action}): "
        f"{'OK' if r.success else 'FAILED'} — {r.output[:200]}"
        for i, r in enumerate(results)
    )
    prompt = (
        f"Summarise the following multi-step operation results.\n"
        f"Chain description: {chain.description}\n\n{steps_text}"
    )
    try:
        raw = self._client.generate(
            prompt=prompt,
            system="You are a terminal assistant. Summarise chain results concisely.",
            temperature=config.OLLAMA_TEMP_STRUCTURED,
            model=model_router.aggregator_model(),
            format_schema=ChainSummary_SCHEMA
                if model_router.supports_structured_output() else None,
        )
        # Store aggregation in the last result's data field for TUI display
        import json
        results[-1].data["chain_summary"] = json.loads(raw)
    except Exception as exc:
        log.warning("Chain aggregation failed: %s", exc)
```

Note: `self._client` must be passed into MCPDispatcher's `__init__`. Add it as
an optional param: `client: OllamaClient | None = None`. Only used for aggregation.

---

**Step 6 — Add `model_used` to `MCPResult` and `AuditLogger`:**

In `mcp/schema.py`:
```python
@dataclass
class MCPResult:
    ...
    model_used: str = ""   # which Ollama model handled this call
```

In `llm/inference.py`, set `result.model_used = actual_model_used`.
In `audit/logger.py`, include `model_used` in the log entry.
In `eval/metrics.py`, add `model_used` to `EvalResult` and include
per-model accuracy breakdown in the eval report.

---

**Step 7 — Add version check to `main.py` startup:**

```python
def _check_ollama_version(client: OllamaClient) -> None:
    try:
        v = client.ollama_version()
        if v < (0, 1, 34):
            print(f"[WARN] Ollama {'.'.join(map(str, v))} detected. "
                  f"Upgrade to >= 0.1.34 for structured output (better routing accuracy).")
    except Exception:
        pass  # non-fatal
```

---

**Step 8 — Tests (`tests/test_model_router.py`):**

```python
import pytest
from unittest.mock import MagicMock, patch
from mcp_assistant.llm.model_router import ModelRouter
from mcp_assistant import config

def _mock_client(available_models):
    c = MagicMock()
    c.list_models.return_value = [{"name": m} for m in available_models]
    c.ollama_version.return_value = (0, 1, 34)
    return c

def test_resolves_router_model_when_available():
    router = ModelRouter(_mock_client(["phi3:mini", "phi3:latest"]))
    router.warm_up()
    assert router.router_model() == "phi3:mini"

def test_falls_back_when_preferred_unavailable():
    router = ModelRouter(_mock_client(["phi3:latest"]))
    router.warm_up()
    # phi3:mini not available → should fall back to phi3:latest
    assert router.router_model() == "phi3:latest"

def test_executor_high_falls_back_to_medium():
    router = ModelRouter(_mock_client(["phi3:mini", "phi3:latest"]))
    router.warm_up()
    # No 8B model → high should fall back to low (phi3:latest)
    assert router.executor_model("high") == config.EXECUTOR_MODEL_LOW

def test_supports_structured_output_version_check():
    router = ModelRouter(_mock_client([]))
    assert router.supports_structured_output() is True

def test_no_structured_output_old_version():
    c = _mock_client([])
    c.ollama_version.return_value = (0, 1, 30)
    router = ModelRouter(c)
    assert router.supports_structured_output() is False
```

---

**Success criterion:**
- `pytest tests/test_model_router.py` — all pass.
- Run eval harness. On minimal config (phi3:mini + phi3):
  - Mean latency must be ≤ 3500 ms (improvement from 4209ms baseline).
  - Action accuracy must not regress below 65%.
- On full config (+ llama3.1:8b as HIGH):
  - Action accuracy on "high" complexity items must be ≥ 80%.
- `model_used` field appears in `audit_logs/*.jsonl` entries.
- `!verify` still passes (audit chain intact).

---

### TASK 12 — Terminal Ecosystem Integration (detect-and-delegate)
**Priority: MEDIUM. Zero new hard dependencies. Improves output quality and speed.**

**Problem:**
FileHandler.search uses Python `pathlib.rglob`. GitTool.diff outputs raw text.
FileHandler.read returns plain text. These work but are slower and visually
inferior to purpose-built terminal tools that users in a developer environment
likely already have installed. There is no reason to reimplement what `rg`,
`bat`, `delta`, `fd`, and `eza` already do — and do better.

**Core principle:**
```python
import shutil
def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None
```
Detect at tool init. Branch on it. Python fallback always exists. No import
changes. No new requirements.txt entries. CI still runs without any of these.

**Specification:**

1. Create `mcp_assistant/llm/ecosystem.py` — capability detection module:
```python
"""Detects available terminal ecosystem tools at startup."""
import shutil

AVAILABLE: dict[str, bool] = {
    "rg":     shutil.which("rg")     is not None,  # ripgrep (fast file search)
    "fd":     shutil.which("fd")     is not None,  # fd-find (fast file find)
    "bat":    shutil.which("bat")    is not None,  # bat (cat with syntax highlighting)
    "delta":  shutil.which("delta")  is not None,  # git-delta (diff renderer)
    "eza":    shutil.which("eza")    is not None,  # eza (modern ls)
    "exa":    shutil.which("exa")    is not None,  # exa (older name for eza)
    "zoxide": shutil.which("zoxide") is not None,  # zoxide (smart directory resolver)
    "fzf":    shutil.which("fzf")    is not None,  # fzf (fuzzy finder, CLI mode only)
}

def report() -> str:
    found   = [k for k, v in AVAILABLE.items() if v]
    missing = [k for k, v in AVAILABLE.items() if not v]
    lines = []
    if found:
        lines.append(f"Ecosystem tools active: {', '.join(found)}")
    if missing:
        lines.append(f"Optional (install for enhanced output): {', '.join(missing)}")
    return "\n".join(lines)
```
Print `ecosystem.report()` at startup (after Ollama health check). Users see
what's available without the tool requiring anything.

2. In `tools/file_handler.py`, update `search` and `list` actions:
```python
from mcp_assistant.llm.ecosystem import AVAILABLE

# In search action:
if AVAILABLE["rg"]:
    proc = subprocess.run(
        ["rg", "--files", "-g", pattern, str(resolved_path)],
        capture_output=True, text=True
    )
    files = proc.stdout.strip().splitlines()
elif AVAILABLE["fd"]:
    proc = subprocess.run(
        ["fd", pattern, str(resolved_path)],
        capture_output=True, text=True
    )
    files = proc.stdout.strip().splitlines()
else:
    files = [str(p) for p in resolved_path.rglob(pattern)]

# In read action — pipe through bat if available for syntax highlighting:
if AVAILABLE["bat"]:
    proc = subprocess.run(
        ["bat", "--color=always", "--style=numbers,changes", str(resolved_path)],
        capture_output=True, text=True
    )
    output = proc.stdout
else:
    output = resolved_path.read_text(encoding="utf-8")

# In list action — use eza/exa if available:
if AVAILABLE["eza"]:
    proc = subprocess.run(["eza", "--long", "--colour=always", str(resolved_path)], ...)
elif AVAILABLE["exa"]:
    proc = subprocess.run(["exa", "--long", "--colour=always", str(resolved_path)], ...)
else:
    # current os.listdir / iterdir() implementation
```

3. In `tools/git_tool.py`, update `diff` action:
```python
from mcp_assistant.llm.ecosystem import AVAILABLE

# In diff action — pipe through delta if available:
raw_diff = subprocess.run(["git", "diff"] + flags, capture_output=True).stdout
if AVAILABLE["delta"] and raw_diff:
    enhanced = subprocess.run(
        ["delta", "--color-only"],
        input=raw_diff, capture_output=True
    ).stdout
    output = enhanced.decode("utf-8", errors="replace")
else:
    output = raw_diff.decode("utf-8", errors="replace")
```

4. Add `_resolve_cwd()` utility in `tools/` (used by GitTool and TestRunner):
```python
from mcp_assistant.llm.ecosystem import AVAILABLE
import subprocess
from pathlib import Path

def resolve_cwd(cwd_hint: str) -> str:
    """
    Resolve a cwd parameter. If it looks like a fuzzy name (not an absolute
    path, not a relative path that exists), try zoxide to resolve it from
    the user's navigation history.
    """
    if not cwd_hint or cwd_hint == ".":
        return cwd_hint
    if Path(cwd_hint).exists():
        return cwd_hint
    if AVAILABLE["zoxide"]:
        result = subprocess.run(
            ["zoxide", "query", "--", cwd_hint],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
    return cwd_hint  # pass through; tool will error naturally if invalid
```

5. Update `docs/USER_GUIDE.md` — add "Optional Enhancements" section:
```
## Optional Enhancements
The assistant automatically detects and uses these tools if installed:
| Tool    | Install              | What it enhances                    |
|---------|---------------------|-------------------------------------|
| ripgrep | brew install ripgrep | File search (10–100× faster)        |
| bat     | brew install bat     | File display (syntax highlighting)  |
| delta   | brew install git-delta | Git diff (syntax-highlighted diffs)|
| eza     | brew install eza     | Directory listing (colours, icons)  |
| fd      | brew install fd      | File find (faster than glob)        |
| zoxide  | brew install zoxide  | Directory resolution (fuzzy cwd)    |
None are required. The assistant works identically without them.
```

**Files to change / create:**
- `mcp_assistant/llm/ecosystem.py` (NEW)
- `mcp_assistant/tools/file_handler.py`
- `mcp_assistant/tools/git_tool.py`
- `mcp_assistant/tools/` — add `_resolve_cwd()` utility
- `mcp_assistant/main.py` (print ecosystem.report() at startup)
- `docs/USER_GUIDE.md`

**Success criterion:**
`pytest tests/test_tools.py` must pass (all fallback paths tested without
ecosystem tools). On a machine with rg installed, `FileHandler.search` must
use rg (verify via tool output showing rg-style paths). Ecosystem report
prints at startup.

**IMPORTANT — security:**
Never interpolate user-provided strings directly into subprocess command lists.
The pattern `["rg", "--files", "-g", pattern, str(path)]` already passes args
as list items (not a shell string) — this is safe. Do NOT use `shell=True`.

---

### TASK 13 — Ollama Performance Optimisations
**Priority: MEDIUM-HIGH. Eliminates hidden latency without code complexity.**

**Problem:**
Three Ollama API features that directly cut latency are not used:
1. Model unloads after 5-min idle → 2–5s cold-start on return
2. System prompt (~200 tokens) reprocessed from scratch on every query
3. Idempotent tool calls (git status, cpu stats) rerun subprocesses on repeats

**Note on retry backoff vs caching:**
These are orthogonal and cover different failure modes:
- LLM cache (Task 4): checked first. Hit → instant return, no Ollama call.
- Tool result cache (this task): checked in dispatcher. Hit → instant result, no subprocess.
- Retry backoff (Task 3): only reached when Ollama is called but fails at network level.
All three are needed; none overlap.

**Specification:**

**13a — `keep_alive` in API payload:**
In `OllamaClient._build_payload()`, add:
```python
payload["keep_alive"] = config.OLLAMA_KEEP_ALIVE
```
In `config.py`:
```python
OLLAMA_KEEP_ALIVE: str = os.environ.get("OLLAMA_KEEP_ALIVE", "-1")
# -1 = never unload. "5m" = keep for 5 min. "0" = unload immediately after call.
```
This alone eliminates the most common hidden latency spike.

**13b — KV prefix cache warm-up:**
In `main.py` (and `tui/app.py`), after startup health check, before first user
input, launch a background warm-up:
```python
import threading

def _warm_up_kv(client: OllamaClient, builder: PromptBuilder) -> None:
    """Pre-populate Ollama KV cache for the system prompt prefix."""
    try:
        client.generate(
            prompt=".",       # discard-level prompt, output ignored
            system=builder.system_prompt(),
            temperature=0.0,
            model=config.ROUTER_MODEL,
        )
    except Exception:
        pass  # non-fatal

# Fire and forget — don't block startup
threading.Thread(target=_warm_up_kv, args=(client, builder), daemon=True).start()
```
Warm-up completes in ~1–2s in background. By the time the user types their
first command, KV cache is hot. Every query after that saves 0.5–1s.

**13c — Tool result cache (short-TTL in-memory):**
Create `mcp_assistant/mcp/tool_cache.py`:
```python
"""
Short-TTL in-memory cache for idempotent (read-only) tool results.
Keyed by SHA-256(tool:action:json(params)). Default TTL: 15 seconds.
Destructive actions (write, delete, commit, kill_process) are never cached.
"""
import time, json, hashlib
from mcp_assistant.mcp.schema import MCPCall, MCPResult

TOOL_CACHE_TTL: int = 15   # seconds

# Read-only actions safe to cache
_CACHEABLE: dict[str, set[str]] = {
    "FileHandler": {"list", "search", "read"},
    "GitTool":     {"status", "diff", "log", "branch_list"},
    "SystemTool":  {"cpu_stats", "ram_stats", "disk_stats", "list_processes", "env_info"},
    "TestRunner":  {"detect"},
}

_STORE: dict[str, tuple[MCPResult, float]] = {}

def _key(call: MCPCall) -> str:
    raw = f"{call.tool}:{call.action}:{json.dumps(call.params, sort_keys=True)}"
    return hashlib.sha256(raw.encode()).hexdigest()

def get(call: MCPCall) -> MCPResult | None:
    if call.action not in _CACHEABLE.get(call.tool, set()):
        return None
    entry = _STORE.get(_key(call))
    if entry is None:
        return None
    result, ts = entry
    if time.time() - ts > TOOL_CACHE_TTL:
        del _STORE[_key(call)]
        return None
    return result

def put(call: MCPCall, result: MCPResult) -> None:
    if result.success and call.action in _CACHEABLE.get(call.tool, set()):
        _STORE[_key(call)] = (result, time.time())

def clear() -> None:
    _STORE.clear()
```

Wire into `MCPDispatcher.dispatch()` — add after validation, before execute:
```python
from mcp_assistant.mcp import tool_cache

# After step 3 (validate params), before step 4 (confirm):
cached = tool_cache.get(call)
if cached:
    cached.data["from_tool_cache"] = True
    self._audit.log(call, cached)
    return cached

# ... existing confirm + execute logic ...
result = tool.execute(call)
tool_cache.put(call, result)
```

**13d — System prompt memoization:**
In `prompt_builder.py`, add `@functools.lru_cache(maxsize=1)` to `system_prompt()`:
```python
import functools

class PromptBuilder:
    @functools.lru_cache(maxsize=1)
    def system_prompt(self) -> str:
        return _SYSTEM_PROMPT_TEMPLATE.format(tool_summary=self._tool_summary)

    def update_tool_summary(self, summary: str) -> None:
        self._tool_summary = summary
        self.system_prompt.cache_clear()   # invalidate when tools change
```

**13e — ConversationBuffer dirty-flag saves:**
In `context/buffer.py`, add a `_dirty` flag:
```python
def __init__(self, ...):
    ...
    self._dirty = False

def add_turn(self, role, content, call=None):
    ...
    self._dirty = True

def save(self):
    if not self._dirty:
        return
    # ... existing write logic ...
    self._dirty = False
```

**Files to change / create:**
- `mcp_assistant/llm/client.py` (add keep_alive to payload)
- `mcp_assistant/llm/ecosystem.py` (NEW — from Task 12)
- `mcp_assistant/config.py` (OLLAMA_KEEP_ALIVE constant)
- `mcp_assistant/main.py` (background KV warm-up thread)
- `mcp_assistant/tui/app.py` (background KV warm-up)
- `mcp_assistant/mcp/tool_cache.py` (NEW)
- `mcp_assistant/mcp/dispatcher.py` (check tool_cache)
- `mcp_assistant/llm/prompt_builder.py` (lru_cache)
- `mcp_assistant/context/buffer.py` (dirty flag)

**Success criterion:**
- First query latency: ≤ 3s (was 4–8s) — warm-up pre-populated KV cache.
- Repeated identical query (within 15s): ≤ 50ms (tool cache hit).
- After 10-min idle, first query: ≤ 3s (keep_alive prevents model unload).
- `pytest tests/` all pass.
- `!verify` passes (audit log intact — tool cache hits are still logged).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## SECTION 4 — WRAP-UP CHECKLIST (after all tasks)

1. Run: `pytest tests/ -q` — all tests must pass.
2. Run: `python -m mcp_assistant.eval.harness --label post_all_tasks --output eval_results/`
   - Tool Accuracy must be ≥ 93.3% (no regression)
   - Action Accuracy must be ≥ 75% (improvement from 65%)
   - Parse Failure Rate: 0.0%
   - Hallucination Rate: 0.0%
3. Update `IMPLEMENTATION_LOG.md`:
   - Move completed sprints to "Implementation History"
   - Add new eval results row to Section 9
   - Update Section 4 status table
   - Add new ADR entries for any architectural decisions made
4. Bump `pyproject.toml` version from `0.1.0` → `0.2.0`.
5. Update "Last updated" date in both docs.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## SECTION 5 — HARD CONSTRAINTS

- DO NOT rename `self._tool_registry` in `tui/app.py`. Textual uses `_registry`
  internally — the collision crashes app shutdown with TypeError.
- DO NOT add cloud LLM calls. All inference goes through OllamaClient.
- DO NOT modify eval dataset items 1–60. Append only (IDs 61+).
- DO NOT import `textual` from modules outside `tui/`. Tests don't mock it.
- DO NOT use `asyncio.run()` inside async functions. Use `await` or
  `asyncio.ensure_future()` — Textual's event loop is already running.
- DO NOT break the audit log hash chain format in `audit/logger.py`.
- DO NOT require multiple large models to be installed for the tool to work.
  The default config (phi3:mini + phi3:latest) must work as a complete setup.
  All higher tiers are strictly opt-in via environment variables.
- DO NOT call the executor or aggregator model for simple routing-only queries
  (complexity = "routing"). The router output is sufficient for dispatch — do
  not add a second LLM call where it is not needed.
- DO NOT hard-code model names anywhere outside `config.py`. All model names
  must be overridable via env vars (ROUTER_MODEL, EXECUTOR_MODEL_LOW, etc.).
- DO NOT use `shell=True` in any subprocess call. Always pass command as a list
  of strings. User-provided params (path, pattern, cwd) go as list items, never
  interpolated into a shell string. This prevents command injection.
- DO NOT cache tool results for destructive actions (write, delete, commit,
  kill_process). Only read-only actions defined in `_CACHEABLE` are cached.
- DO NOT block the startup sequence waiting for KV warm-up. It must run in a
  background thread so the TUI/CLI appears immediately.
- MAX_PARSE_RETRIES must stay ≥ 2. phi3 often wraps JSON in prose on first try.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## SECTION 6 — ALTERNATIVES CONSIDERED

| Decision | Chosen | Rejected (why) |
|----------|--------|----------------|
| FastMCP approach | Additive wrapper | Full rewrite — breaks 65 tests + Plugin SDK |
| Cache backend | SQLite (cold storage) | Redis (extra service) / in-memory (ephemeral, defeats cold-storage goal) |
| Streaming | Accumulate + display tokens | True streaming parse (phi3 JSON output isn't incrementally valid) |
| Faithfulness measurement | Heuristic (no extra LLM call) | LLM-judge (accurate but doubles latency; Phase 2 improvement) |
| Confirm bridge | concurrent.futures.Future | threading.Event (more boilerplate, no built-in timeout) |
| Multi-model design | 3-tier with configurable fallback | Single weak model — accuracy regresses on NL tasks |
| | | Single strong model — high RAM, slow on trivial queries |
| | | Separate embedding model for semantic tool lookup — extra download, overkill at ≤ 20 tools |
| Structured output enforcement | Ollama `format` JSON Schema param | Client-side grammar library (portable but complex) / regex fallback only (fragile) |
| Complexity detection | Router outputs `complexity` field (1 extra token) | Separate classifier call (doubles router latency) / keyword heuristics (brittle) |
| Aggregator model | Reuse EXECUTOR_MODEL_HIGH | Dedicated 4th model — unnecessary RAM overhead for a rare call (5% of queries) |
| Tool result cache backend | In-memory dict (short TTL) | SQLite — overkill for 15s TTL; Redis — extra service; disk write — too slow for <50ms target |
| Ecosystem integration | Detect-and-delegate (shutil.which) | Hard dependency — breaks portability; pip wrapper around rg — defeats the point |
| KV warm-up | Background thread at startup | Block startup — degrades UX; skip — loses 0.5–1s per query |
| System prompt caching | functools.lru_cache(maxsize=1) | Mutable global string — fragile; manual flag — more code for same effect |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## SECTION 7 — GLOSSARY

- **MCPCall**: structured intent from LLM. Fields: tool, action, params, confidence.
- **MCPChain**: sequence of MCPCalls for multi-step requests ("first X then Y").
- **MCPDispatcher**: sole execution gateway. Enforces policy, confirms, executes, audits.
- **MCPTool**: abstract base for plugins. Subclass + set class attrs + implement execute().
- **ToolRegistry**: maps TOOL_NAME → MCPTool instance. Handles plugin auto-discovery.
- **PolicyConfig**: loaded from .mcprc. Controls sandbox, blocked paths, confirm gates.
- **ConversationBuffer**: sliding-window LLM memory, token-aware, persisted to disk.
- **AuditLogger**: append-only SHA-256 hash-chained JSONL. Tamper-evident.
- **Confidence gating**: LLM self-confidence < threshold → ask user before dispatching.
- **Cold storage**: SQLite LLM cache that persists across process restarts.
- **Faithfulness**: whether executed output actually answers the user's intent.
- **FastMCP**: `pip install fastmcp` — Python library for MCP-compliant tool servers.
- **MCP routes**: how MCPCall maps to a tool + action. Currently registry.get(name).
- **Incremental retry backoff**: exponential delay (1s→2s→4s, cap 30s) + jitter on Ollama failures.
- **3-tier model routing**: Router (1.5B, always resident) → Executor (3B/5B/8B, loaded on demand, selected by router) → Aggregator (5B+, chain synthesis only).
- **ModelRouter**: class that resolves each tier to the best available Ollama model via `list_models()` fallback chain. Lives in `llm/model_router.py`.
- **Structured output / Ollama `format`**: Ollama >= 0.1.34 feature. Pass a JSON Schema dict as `format` in the API request — Ollama uses grammar-constrained decoding to guarantee the output matches the schema. Eliminates parse failures for router calls.
- **Complexity field**: extra field the router emits alongside MCPCall: "routing" (no NL followup needed), "low", "medium", "high". Stripped before dispatch; only used by ModelRouter to select executor tier.
- **Aggregator**: the Tier 3 model role. Called only when a chain has ≥ 2 completed steps. Produces a structured `ChainSummary` JSON via Ollama format param. Defaults to the same model as EXECUTOR_MODEL_HIGH — no extra download needed.
- **Graceful degradation**: if a preferred tier model is not installed in Ollama, ModelRouter walks the fallback chain automatically. The tool never fails because a large model is absent; it just uses whatever is available.
- **Tool result cache**: short-TTL (15s) in-memory dict keyed by SHA-256(tool:action:params). Only read-only actions. Lives in `mcp/tool_cache.py`. Distinct from the LLM cache (Task 4) — caches execution output, not routing decisions.
- **keep_alive**: Ollama API payload parameter. `-1` = never unload the model from RAM. Eliminates cold-start latency after idle periods.
- **KV prefix cache**: Ollama caches the KV computation for repeated prompt prefixes. Pre-warm by sending a system-prompt-only generation at startup. Saves 0.5–1s per subsequent query.
- **Ecosystem tools**: optional external binaries (rg, bat, delta, fd, eza, zoxide) that replace Python implementations of file search, display, and diff rendering when available. Detected via `shutil.which()`. Zero new hard dependencies.
- **detect-and-delegate**: the pattern where a tool checks if a superior external binary is available (`shutil.which`) and delegates to it, falling back to the Python implementation if absent. Improves output quality and speed without breaking portability.
- **zoxide**: a smarter `cd` that learns from navigation history. Used in `resolve_cwd()` to map fuzzy directory names in tool `cwd` params to real paths.
- **ripgrep (rg)**: Rust-based recursive file search, 10–100× faster than Python glob. Used in FileHandler.search when available.
- **bat**: syntax-highlighting `cat` replacement. Used in FileHandler.read output when available.
- **delta**: syntax-highlighted git diff renderer. Used in GitTool.diff output when available.

=============================================================================
