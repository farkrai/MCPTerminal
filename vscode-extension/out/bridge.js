"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.MCPBridge = void 0;
/**
 * MCPBridge — communicates with the Python MCP assistant backend via subprocess.
 * Sends JSON commands, receives JSON results.
 *
 * The Python backend was refactored to FastMCP in v1.0. All subprocess scripts
 * use the new mcp_assistant.server.* module hierarchy and pass user input via
 * environment variables (not inline string interpolation) to prevent injection.
 */
const vscode = __importStar(require("vscode"));
const child_process_1 = require("child_process");
const path = __importStar(require("path"));
class MCPBridge {
    context;
    outputChannel;
    constructor(context, outputChannel) {
        this.context = context;
        this.outputChannel = outputChannel;
    }
    getPythonPath() {
        const config = vscode.workspace.getConfiguration('mcpAssistant');
        const configured = config.get('pythonPath', '');
        if (configured) {
            return configured;
        }
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (workspaceFolders) {
            return path.join(workspaceFolders[0].uri.fsPath, 'venv', 'bin', 'python');
        }
        return 'python3';
    }
    getWorkingDir() {
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (workspaceFolders) {
            return workspaceFolders[0].uri.fsPath;
        }
        return process.cwd();
    }
    async runPythonCommand(script, extraEnv = {}) {
        return new Promise((resolve, reject) => {
            const pythonPath = this.getPythonPath();
            const cwd = this.getWorkingDir();
            this.outputChannel.appendLine(`[bridge] ${pythonPath} -c "${script.substring(0, 80)}…"`);
            const proc = (0, child_process_1.spawn)(pythonPath, ['-c', script], {
                cwd,
                env: { ...process.env, ...extraEnv },
                timeout: 120000,
            });
            let stdout = '';
            let stderr = '';
            proc.stdout.on('data', (data) => { stdout += data.toString(); });
            proc.stderr.on('data', (data) => { stderr += data.toString(); });
            proc.on('close', (code) => {
                if (code === 0) {
                    resolve(stdout.trim());
                }
                else {
                    this.outputChannel.appendLine(`[bridge] stderr: ${stderr}`);
                    reject(new Error(stderr || `Process exited with code ${code}`));
                }
            });
            proc.on('error', (err) => {
                reject(err);
            });
        });
    }
    /**
     * Send a natural-language command to the MCP assistant.
     * User input is passed via MCP_USER_INPUT env var to avoid injection.
     */
    async sendCommand(input) {
        const config = vscode.workspace.getConfiguration('mcpAssistant');
        const script = `
import asyncio, json, os, time

async def main():
    from fastmcp import Client
    from mcp_assistant import config as mcfg
    from mcp_assistant.llm.client import OllamaClient
    from mcp_assistant.llm.prompt_builder import PromptBuilder
    from mcp_assistant.llm.response_parser import parse_response, ParseError
    from mcp_assistant.llm.confidence import register_known_tools
    from mcp_assistant.server.schema import ToolCall, ToolChain
    from mcp_assistant.server.app import get_server
    from mcp_assistant.server.state import policy

    mcfg.ensure_dirs()
    policy.dry_run_mode = os.environ.get('MCP_DRY_RUN', 'false') == 'true'
    user_input = os.environ['MCP_USER_INPUT']

    mcp = get_server()
    async with Client(mcp) as client:
        tools = await client.list_tools()
        register_known_tools({t.name for t in tools})

        builder = PromptBuilder()
        builder.update_from_fastmcp_tools(tools)
        llm = OllamaClient()
        raw = await asyncio.to_thread(
            lambda: llm.generate(builder.user_prompt(user_input), system=builder.system_prompt())
        )

        try:
            parsed = parse_response(raw)
        except ParseError as e:
            print(json.dumps({"success": False, "output": f"Parse error: {e}", "error": str(e)}))
            return

        def extract(result) -> str:
            if hasattr(result, "content"):
                return "".join(i.text for i in result.content if hasattr(i, "text"))
            if hasattr(result, "data") and result.data:
                return json.dumps(result.data, indent=2)
            return str(result)

        start = time.perf_counter()

        if isinstance(parsed, ToolCall):
            try:
                raw_r = await client.call_tool(parsed.tool, parsed.params)
                output, success, error = extract(raw_r), True, None
            except Exception as exc:
                output, success, error = str(exc), False, str(exc)
            print(json.dumps({
                "success": success, "output": output, "error": error,
                "tool": parsed.tool, "action": parsed.tool,
                "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                "confidence": parsed.confidence,
            }))

        elif isinstance(parsed, ToolChain):
            results, all_ok, total = [], True, 0.0
            for step in parsed.steps:
                t0 = time.perf_counter()
                try:
                    raw_r = await client.call_tool(step.tool, step.params)
                    o, ok = extract(raw_r), True
                except Exception as exc:
                    o, ok = str(exc), False
                    all_ok = False
                total += (time.perf_counter() - t0) * 1000
                results.append({"output": o, "success": ok})
                if not ok and not parsed.continue_on_error:
                    break
            print(json.dumps({
                "success": all_ok,
                "output": " | ".join(r["output"][:200] for r in results),
                "error": None if all_ok else "One or more chain steps failed",
                "tool": "chain", "action": parsed.description,
                "duration_ms": round(total, 2),
                "confidence": parsed.min_confidence(),
            }))

asyncio.run(main())
`;
        try {
            const raw = await this.runPythonCommand(script, {
                MCP_USER_INPUT: input,
                MCP_DRY_RUN: config.get('dryRunMode', false) ? 'true' : 'false',
                OLLAMA_MODEL: config.get('model', 'phi3:latest'),
                OLLAMA_BASE_URL: config.get('ollamaUrl', 'http://localhost:11434'),
                CONFIDENCE_THRESHOLD: String(config.get('confidenceThreshold', 0.5)),
            });
            return JSON.parse(raw);
        }
        catch (err) {
            return {
                success: false,
                output: `Bridge error: ${err.message}`,
                error: err.message,
            };
        }
    }
    /**
     * Get list of available tools, grouped by namespace prefix (file, git, system, …).
     */
    async getToolList() {
        const script = `
import asyncio, json

async def main():
    from fastmcp import Client
    from mcp_assistant import config as mcfg
    from mcp_assistant.server.app import get_server

    mcfg.ensure_dirs()
    mcp = get_server()
    async with Client(mcp) as client:
        tools = await client.list_tools()

    namespaces: dict = {}
    for t in tools:
        if t.name.startswith(("prompt_", "resource_")):
            continue
        ns = t.name.split("_", 1)[0]
        if ns not in namespaces:
            desc = (t.description or "").splitlines()[0][:80] if ns == t.name else f"{ns.capitalize()} tools"
            namespaces[ns] = {"name": ns, "description": desc, "actions": []}
        namespaces[ns]["actions"].append(t.name)

    print(json.dumps(list(namespaces.values())))

asyncio.run(main())
`;
        try {
            const raw = await this.runPythonCommand(script);
            return JSON.parse(raw);
        }
        catch {
            return [];
        }
    }
    /**
     * Check if Ollama is running.
     */
    async checkHealth() {
        const script = `
from mcp_assistant.llm.client import OllamaClient
c = OllamaClient()
print("true" if c.is_available() else "false")
`;
        try {
            const result = await this.runPythonCommand(script);
            return result.trim() === 'true';
        }
        catch {
            return false;
        }
    }
    /**
     * Verify today's audit log chain integrity.
     */
    async verifyAudit() {
        const script = `
import json
from datetime import datetime
from mcp_assistant import config as mcfg
from mcp_assistant.audit.logger import AuditLogger

mcfg.ensure_dirs()
log_file = mcfg.AUDIT_LOG_DIR / f"audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
if not log_file.exists():
    print(json.dumps({"success": True, "output": "No audit log for today yet."}))
else:
    ok, errors = AuditLogger.verify_chain(log_file)
    print(json.dumps({
        "success": ok,
        "output": f"Chain OK ({log_file.name})" if ok else f"{len(errors)} error(s): {'; '.join(errors[:3])}",
    }))
`;
        try {
            const raw = await this.runPythonCommand(script);
            return JSON.parse(raw);
        }
        catch (err) {
            return { success: false, output: err.message, error: err.message };
        }
    }
    dispose() {
        // No persistent subprocess to clean up — each call spawns a one-shot process.
    }
}
exports.MCPBridge = MCPBridge;
//# sourceMappingURL=bridge.js.map