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
    /**
     * Get the Python path — prefers config, falls back to workspace venv.
     */
    getPythonPath() {
        const config = vscode.workspace.getConfiguration('mcpAssistant');
        const configured = config.get('pythonPath', '');
        if (configured) {
            return configured;
        }
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (workspaceFolders) {
            const venvPath = path.join(workspaceFolders[0].uri.fsPath, 'venv', 'bin', 'python');
            return venvPath;
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
    /**
     * Execute a Python one-shot command and return parsed JSON result.
     */
    async runPythonCommand(script) {
        return new Promise((resolve, reject) => {
            const pythonPath = this.getPythonPath();
            const cwd = this.getWorkingDir();
            this.outputChannel.appendLine(`[bridge] ${pythonPath} -c "${script.substring(0, 80)}…"`);
            const proc = (0, child_process_1.spawn)(pythonPath, ['-c', script], {
                cwd,
                env: { ...process.env },
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
     */
    async sendCommand(input) {
        const escapedInput = input.replace(/'/g, "\\'").replace(/\\/g, "\\\\");
        const config = vscode.workspace.getConfiguration('mcpAssistant');
        const script = `
import json, sys, os
os.environ.setdefault('OLLAMA_MODEL', '${config.get('model', 'phi3:latest')}')
os.environ.setdefault('OLLAMA_BASE_URL', '${config.get('ollamaUrl', 'http://localhost:11434')}')
os.environ.setdefault('CONFIDENCE_THRESHOLD', '${config.get('confidenceThreshold', 0.5)}')

from mcp_assistant import config as mcfg
from mcp_assistant.llm.client import OllamaClient
from mcp_assistant.llm.prompt_builder import PromptBuilder
from mcp_assistant.llm.response_parser import parse_response
from mcp_assistant.llm.confidence import register_known_tools
from mcp_assistant.mcp.schema import MCPCall, MCPChain
from mcp_assistant.mcp.registry import ToolRegistry
from mcp_assistant.mcp.dispatcher import MCPDispatcher
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant.audit.logger import AuditLogger
from mcp_assistant.tools.file_handler import FileHandler
from mcp_assistant.tools.git_tool import GitTool
from mcp_assistant.tools.system_tool import SystemTool
from mcp_assistant.tools.test_runner import TestRunner
from mcp_assistant.tools.network_tool import NetworkTool

mcfg.ensure_dirs()
policy = PolicyConfig.load_or_default(mcfg.MCPRC_FILE)
policy.dry_run_mode = ${config.get('dryRunMode', false) ? 'True' : 'False'}
client = OllamaClient()
registry = ToolRegistry()
registry.register(FileHandler(policy))
registry.register(GitTool())
registry.register(SystemTool())
registry.register(TestRunner(llm_client=client))
registry.register(NetworkTool())
registry.discover_plugins(mcfg.PLUGINS_DIR)
register_known_tools(registry.tool_names())

audit = AuditLogger(mcfg.AUDIT_LOG_DIR)
dispatcher = MCPDispatcher(registry, policy, audit, confirm_fn=lambda _: True)
builder = PromptBuilder(registry.generate_summary())
system = builder.system_prompt()
prompt = builder.user_prompt('${escapedInput}')

raw = client.generate(prompt, system=system)
parsed = parse_response(raw)

if isinstance(parsed, MCPCall):
    result = dispatcher.dispatch(parsed)
    print(json.dumps({
        "success": result.success,
        "output": result.output,
        "error": result.error,
        "tool": result.call.tool,
        "action": result.call.action,
        "duration_ms": result.duration_ms,
        "confidence": result.call.confidence,
    }))
elif isinstance(parsed, MCPChain):
    results = dispatcher.dispatch_chain(parsed)
    combined = " | ".join(r.output[:200] for r in results)
    all_ok = all(r.success for r in results)
    print(json.dumps({
        "success": all_ok,
        "output": combined,
        "error": None if all_ok else "One or more chain steps failed",
        "tool": "chain",
        "action": parsed.description,
        "duration_ms": sum(r.duration_ms for r in results),
        "confidence": min(s.confidence for s in parsed.steps),
    }))
`;
        try {
            const raw = await this.runPythonCommand(script);
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
     * Get list of available tools.
     */
    async getToolList() {
        const script = `
import json
from mcp_assistant import config as mcfg
from mcp_assistant.mcp.registry import ToolRegistry
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant.tools.file_handler import FileHandler
from mcp_assistant.tools.git_tool import GitTool
from mcp_assistant.tools.system_tool import SystemTool
from mcp_assistant.tools.test_runner import TestRunner
from mcp_assistant.tools.network_tool import NetworkTool

mcfg.ensure_dirs()
policy = PolicyConfig.load_or_default(mcfg.MCPRC_FILE)
registry = ToolRegistry()
registry.register(FileHandler(policy))
registry.register(GitTool())
registry.register(SystemTool())
registry.register(TestRunner())
registry.register(NetworkTool())
registry.discover_plugins(mcfg.PLUGINS_DIR)

tools = []
for t in registry.all_tools():
    tools.append({
        "name": t.TOOL_NAME,
        "description": t.TOOL_DESCRIPTION,
        "actions": list(t.SUPPORTED_ACTIONS.keys()),
    })
print(json.dumps(tools))
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
     * Verify today's audit log.
     */
    async verifyAudit() {
        const script = `
import json
from datetime import datetime
from pathlib import Path
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
        // Cleanup if needed
    }
}
exports.MCPBridge = MCPBridge;
//# sourceMappingURL=bridge.js.map