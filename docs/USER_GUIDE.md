# MCP Terminal Assistant — User Guide

> An offline, AI-powered terminal assistant that understands plain English and
> executes real system operations — files, git, system stats, and tests —
> safely and privately, with no internet required.

---

## Table of Contents

1. [What It Does](#1-what-it-does)
2. [Starting the Assistant](#2-starting-the-assistant)
3. [Typing Commands](#3-typing-commands)
4. [The TUI Screen Layout](#4-the-tui-screen-layout)
5. [Available Tools and What to Say](#5-available-tools-and-what-to-say)
6. [Multi-Step Commands (Chains)](#6-multi-step-commands-chains)
7. [Special Commands](#7-special-commands)
8. [Keyboard Shortcuts](#8-keyboard-shortcuts)
9. [Safety — What Is and Isn't Allowed](#9-safety--what-is-and-isnt-allowed)
10. [Dry-Run Mode](#10-dry-run-mode)
11. [Audit Log](#11-audit-log)
12. [Running the Evaluator](#12-running-the-evaluator)
13. [Docker Quickstart](#13-docker-quickstart)
14. [Optional Enhancements](#14-optional-enhancements)
15. [Claude Desktop / FastMCP](#15-claude-desktop--fastmcp)
16. [Troubleshooting](#16-troubleshooting)

---

## 1. What It Does

The MCP Terminal Assistant takes a natural-language sentence and converts it
into a real terminal action. You do not need to know exact command syntax.

| You type | What happens |
|---|---|
| `show git status` | Runs `git status` in your project |
| `how much RAM is free` | Reads live memory stats |
| `find all python files` | Searches recursively for `*.py` |
| `run the tests` | Detects and runs your test suite |
| `first check git status then show the diff` | Runs two commands in sequence |

Everything runs **locally**. Your code and queries never leave your machine.

---

## 2. Starting the Assistant

### Prerequisites

- Python **3.11 or newer** is required.
- Ollama must be installed locally.

Recommended setup from the project root:

```bash
cd <project-root>
/opt/homebrew/bin/python3.11 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip setuptools wheel

# TUI + CLI
python -m pip install -e ".[tui]"

# Optional: FastMCP server wrapper
# python -m pip install -e ".[server]"
```

If you prefer a plain requirements install instead of package extras:

```bash
python -m pip install -r requirements.txt
```

Workspace scope:
- By default, tool access is sandboxed to your user workspace root (`~`).
- To use a different workspace root, set `MCP_WORKSPACE` before launch.

Example:

```bash
export MCP_WORKSPACE=~/Documents
```

### Start Ollama

Make sure Ollama is running first. If `ollama serve` says the port is already
in use, Ollama is already running and you can continue.

```bash
ollama serve
```

Pull the default local model once:

```bash
ollama pull dolphin-mistral:latest
```

### Launch the Assistant

Then launch the assistant:

```bash
# TUI (recommended — full visual interface)
python -m mcp_assistant.main

# Plain CLI (no TUI, text only)
python -m mcp_assistant.main --cli
```

You will see the three-panel TUI appear. The input bar is at the bottom center.
Type your command and press **Enter**.

The assistant now routes every request through the orchestration graph:
`classify -> planner -> router/direct -> aggregate -> finalize`.
If the request can be answered directly, it avoids MCP tools; if it depends on
workspace, git, tests, or system state, it routes into MCP execution and then
aggregates the result into a structured response.

For a clean test session, clear old memory right after launch:

```text
!context clear
```

In the TUI you can also press `Ctrl+L`.

To override model roles later, set any of these before launch:

```bash
export OLLAMA_MODEL=dolphin-mistral:latest
export CLASSIFIER_MODEL=dolphin-mistral:latest
export PLANNER_MODEL=dolphin-mistral:latest
export ROUTER_MODEL=dolphin-mistral:latest
export AGGREGATOR_MODEL=dolphin-mistral:latest
```

You can also clear the structured LLM cache at any time with:

```bash
mcp-cache clear
```

---

## 3. Typing Commands

Write commands the way you would say them out loud. You do not need to use
specific keywords — the AI interprets your intent.

**Works well:**
```
list all files in the current directory
show me the git log
how much CPU am I using
run the test suite
read the pyproject.toml file
find all json files
```

**Multi-step (chain) commands — use words like "then", "first...then", "after that":**
```
first show git status then show the diff
check memory usage then list running processes
detect the test framework then run all tests
```

**If confidence is low**, the assistant will ask you to confirm before acting:
```
Low confidence (0.42): did you mean FileHandler.read? (y/n)
```
Type `yes` to proceed, or rephrase your command.

---

## 4. The TUI Screen Layout

```
┌──────────────────┬──────────────────────────────────┬──────────────────────┐
│   System Stats   │         Conversation             │   Tool Inspector     │
│                  │                                  │                      │
│  CPU: ████░░░  │  You: show git status             │  SUCCESS  [8ms]      │
│  49.3%           │  → GitTool.status (conf 1.00)   │                      │
│                  │  ✓ On branch main                │  CALL                │
│  RAM: ███░░░   │    Changes not staged…            │    tool: GitTool     │
│  5.1 / 15.0 GB   │                                  │    action: status    │
│                  │  You: how much RAM               │    conf: 1.00        │
│  DISK /          │  → SystemTool.ram_stats          │                      │
│  ████████░░      │  ✓ RAM Total: 15.03 GB…          │  OUTPUT              │
│  89.2/100 GB     │                                  │    On branch main    │
│                  │                                  │    …                 │
│  UPTIME: 2h 14m  ├──────────────────────────────────│                      │
│  PROCS: 312      │ [MCP] > Type your command…       │                      │
└──────────────────┴──────────────────────────────────┴──────────────────────┘
```

| Panel | What it shows |
|---|---|
| **Left — System Stats** | Live CPU %, RAM, Disk, Uptime, Process count. Refreshes every 2 seconds. |
| **Center top — Conversation** | Everything you type and every result, in scroll order. |
| **Center bottom — Input** | Where you type. `[MCP]` badge = normal mode, `[DRY]` = dry-run. |
| **Right — Tool Inspector** | Full detail of the last tool call: which tool, which action, parameters, full output, timing. |

---

## 5. Available Tools and What to Say

### FileHandler — Files and Directories

| What to say | What happens |
|---|---|
| `list files in the current directory` | Lists all files and folders here |
| `list files in mcp_assistant/` | Lists files in a specific folder |
| `read requirements.txt` | Shows the full contents of a file |
| `show me the config.py source code` | Reads a source file |
| `find all python files` | Searches recursively for `*.py` |
| `find all json files under eval_data` | Searches within a specific folder |
| `write hello world to notes.txt` | Creates or overwrites a file *(asks for confirmation)* |
| `delete temp.txt` | Deletes a file *(asks for confirmation)* |

> **Sandboxed:** File operations are restricted to the active workspace root.
> By default this is your user workspace (`~`). You can override it with
> `MCP_WORKSPACE` or by setting `sandbox_root` in `.mcprc`.
> Sensitive files like `.env`, keys, and SSH material are still blocked.

---

### GitTool — Git Operations

| What to say | What happens |
|---|---|
| `show git status` | Current branch, staged/unstaged changes |
| `show the git diff` | Unstaged changes |
| `show staged changes` | What is staged and ready to commit |
| `show the last 10 commits` | Recent commit history |
| `show recent commits` | Last 10 commits (default) |
| `list all branches` | All local and remote branches |
| `switch to the main branch` | Runs `git checkout main` *(asks for confirmation)* |
| `commit my changes with message "fix login bug"` | Commits staged changes *(asks for confirmation)* |

---

### SystemTool — System Monitoring

| What to say | What happens |
|---|---|
| `how much RAM is being used` | Total, used, available RAM + swap |
| `what is the CPU usage` | CPU % and core count |
| `show disk space` | Usage for every mounted partition |
| `show running processes` | Top 15 processes by CPU usage |
| `show top 5 processes` | Top N processes |
| `what is my system info` | OS, hostname, Python version, uptime |
| `kill process named chrome` | Terminates a process by name *(always asks for confirmation)* |

---

### TestRunner — Test Suites

| What to say | What happens |
|---|---|
| `detect the test framework` | Checks for pytest, jest configuration |
| `run the tests` | Runs the detected test suite |
| `run the file tests/test_schema.py` | Runs a specific test file |
| `run only the audit tests` | Runs `tests/test_audit.py` |

The TestRunner automatically detects whether your project uses **pytest** or
**Jest**. If tests fail, you can follow up with:

```
explain those test failures
```

The assistant will send the output back to the AI and return a plain-English
explanation with suggested fixes.

---

### TimeTool — Date and Time (Plugin Example)

| What to say | What happens |
|---|---|
| `what time is it` | Current local date and time |
| `show UTC time` | Current UTC time |
| `show the unix timestamp` | Current Unix epoch timestamp |

> TimeTool is the built-in example plugin. It demonstrates how new tools can
> be added without changing any core code.

---

## 6. Multi-Step Commands (Chains)

If you want multiple actions in sequence, use trigger words:
**"then", "first...then", "after that", "followed by"**

```
first show git status then show the diff
check memory then list running processes
detect the test framework then run all tests
show cpu stats then show ram stats then list top processes
```

Each step is shown separately in the conversation panel. If any step fails and
chain-continue is off (the default), the chain stops there.

---

## 7. Special Commands

These are typed into the input bar with a `!` prefix:

| Command | What it does |
|---|---|
| `!help` | Shows all special commands |
| `!dry-run on` | Turn on dry-run mode — previews all operations before running |
| `!dry-run off` | Turn off dry-run mode |
| `!context` | Show the last few conversation turns the AI remembers |
| `!context clear` | Wipe the conversation context (AI forgets prior exchanges) |
| `!cache clear` | Clears the on-disk LLM response cache |
| `!verify` | Verify today's audit log has not been tampered with |

---

## 8. Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Enter` | Submit your command |
| `Ctrl+D` | Toggle dry-run mode on/off |
| `Ctrl+L` | Clear conversation context |
| `Ctrl+Q` | Quit (context is saved automatically) |
| `F1` | Show help in the conversation panel |

---

## 9. Safety — What Is and Isn't Allowed

The assistant enforces a policy loaded from `.mcprc` in the project root.
That policy controls the workspace sandbox used by file, git, and test tools.

**Always blocked (regardless of what you ask):**
- Any path outside the active workspace sandbox
- `.env` files, private keys (`.pem`, `.key`, `id_rsa`), SSH directories
- Files larger than 10 MB

**Requires confirmation before running:**
- Writing to any file
- Deleting any file
- Making a git commit
- Killing a process

When confirmation is required, you will see a preview of what will happen and
must press `y` or `yes` to continue.

To customise these rules, edit `.mcprc` in the project root. See the
Knowledge Transfer document for the full schema.

---

## 10. Dry-Run Mode

Dry-run mode lets you preview every operation before it executes. Nothing
changes on disk or in git while dry-run is on.

Turn it on:
```
!dry-run on      (or press Ctrl+D)
```

The `[MCP]` badge in the input bar changes to `[DRY]`. Every tool call now
shows you a preview and asks for confirmation. Turn it off the same way.

---

## 11. Audit Log

Every tool call is recorded in `audit_logs/audit_YYYY-MM-DD.jsonl`. Entries
are chained with SHA-256 hashes so any tampering is detectable.

To verify the log for today:
```
!verify
```

Or from the terminal:
```bash
venv/bin/python -m mcp_assistant.audit.logger audit_logs/audit_2026-04-07.jsonl
```

Logs older than 30 days are automatically deleted on startup (configurable
via `retention_days` in `.mcprc`).

---

## 12. Running the Evaluator

The evaluator measures how accurately the AI maps natural-language commands to
the correct tool and action, across a dataset of 80 test cases.

**Single run (no context window):**
```bash
venv/bin/python -m mcp_assistant.eval.harness \
  --label my_run \
  --output eval_results/
```

**With context window (AI remembers prior questions):**
```bash
venv/bin/python -m mcp_assistant.eval.harness \
  --context 10 \
  --label ctx10_run \
  --output eval_results/
```

**Full ablation study (4 conditions, academic use):**
```bash
venv/bin/python -m mcp_assistant.eval.harness \
  --ablation \
  --output eval_results/
```

Reports are saved as `.md` (human-readable) and `.json` (raw data) in the
output directory.

---

## 13. Docker Quickstart

```bash
docker compose up -d ollama
docker compose exec ollama ollama pull dolphin-mistral:latest
docker compose run --rm mcp-assistant
```

The assistant container talks to Ollama over the internal `ollama` service
name, so no extra configuration is needed.

---

## 14. Optional Enhancements

The assistant automatically detects and uses these tools if installed:

| Tool | Install | What it enhances |
|---|---|---|
| `ripgrep` | `brew install ripgrep` | File search (much faster than Python glob) |
| `bat` | `brew install bat` | File display with syntax highlighting |
| `git-delta` | `brew install git-delta` | Syntax-highlighted git diffs |
| `eza` | `brew install eza` | Rich directory listings |
| `fd` | `brew install fd` | Faster file finding |
| `zoxide` | `brew install zoxide` | Fuzzy working-directory resolution |

None are required. The assistant still works with the pure-Python fallbacks.

---

## 15. Claude Desktop / FastMCP

If you install the server extra, the project can expose its tools through the
official MCP protocol:

```bash
python -m pip install -e ".[server]"
python -m mcp_assistant.fastmcp_server
```

Example Claude Desktop config:

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

---

## 16. Troubleshooting

| Problem | Fix |
|---|---|
| `ERROR: Ollama is not running` | Run `ollama serve` in a separate terminal |
| `Could not parse LLM response` | Rephrase your command more specifically |
| `Path not allowed by policy` | The file is outside the sandbox or is a blocked type |
| AI gives wrong tool / low confidence | Rephrase; use more specific vocabulary (e.g. "git" instead of "version control") |
| TUI does not appear | Use `--cli` flag for plain text mode |
| Context feels stale / AI forgets nothing | Run `!context clear` to reset the conversation memory |

---

*MCP Terminal Assistant — 12-Credit Major Project, 2026*
