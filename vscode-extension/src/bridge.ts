/**
 * MCPBridge — communicates with the Python MCP assistant backend via subprocess.
 * Sends JSON commands, receives JSON results.
 */
import * as vscode from 'vscode';
import { spawn, ChildProcess } from 'child_process';
import * as path from 'path';

export interface MCPCommandResult {
    success: boolean;
    output: string;
    error?: string;
    tool?: string;
    action?: string;
    duration_ms?: number;
    confidence?: number;
}

export interface MCPToolInfo {
    name: string;
    description: string;
    actions: string[];
}

export class MCPBridge {
    private context: vscode.ExtensionContext;
    private outputChannel: vscode.OutputChannel;

    constructor(context: vscode.ExtensionContext, outputChannel: vscode.OutputChannel) {
        this.context = context;
        this.outputChannel = outputChannel;
    }

    /**
     * Get the Python path — prefers config, falls back to workspace venv.
     */
    private getPythonPath(): string {
        const config = vscode.workspace.getConfiguration('mcpAssistant');
        const configured = config.get<string>('pythonPath', '');
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

    private getWorkingDir(): string {
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (workspaceFolders) {
            return workspaceFolders[0].uri.fsPath;
        }
        return process.cwd();
    }

    /**
     * Execute a Python one-shot command and return parsed JSON result.
     */
    private async runPythonCommand(script: string): Promise<string> {
        return new Promise((resolve, reject) => {
            const pythonPath = this.getPythonPath();
            const cwd = this.getWorkingDir();

            this.outputChannel.appendLine(`[bridge] ${pythonPath} -c "${script.substring(0, 80)}…"`);

            const proc = spawn(pythonPath, ['-c', script], {
                cwd,
                env: { ...process.env },
                timeout: 120000,
            });

            let stdout = '';
            let stderr = '';

            proc.stdout.on('data', (data: Buffer) => { stdout += data.toString(); });
            proc.stderr.on('data', (data: Buffer) => { stderr += data.toString(); });

            proc.on('close', (code: number | null) => {
                if (code === 0) {
                    resolve(stdout.trim());
                } else {
                    this.outputChannel.appendLine(`[bridge] stderr: ${stderr}`);
                    reject(new Error(stderr || `Process exited with code ${code}`));
                }
            });

            proc.on('error', (err: Error) => {
                reject(err);
            });
        });
    }

    /**
     * Send a natural-language command to the MCP assistant.
     */
    async sendCommand(input: string): Promise<MCPCommandResult> {
        const escapedInput = input.replace(/'/g, "\\'").replace(/\\/g, "\\\\");
        const config = vscode.workspace.getConfiguration('mcpAssistant');

        const script = `
import json, sys, os
os.environ.setdefault('OLLAMA_MODEL', '${config.get<string>('model', 'phi3:latest')}')
os.environ.setdefault('OLLAMA_BASE_URL', '${config.get<string>('ollamaUrl', 'http://localhost:11434')}')
os.environ.setdefault('CONFIDENCE_THRESHOLD', '${config.get<number>('confidenceThreshold', 0.5)}')

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
policy.dry_run_mode = ${config.get<boolean>('dryRunMode', false) ? 'True' : 'False'}
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
            return JSON.parse(raw) as MCPCommandResult;
        } catch (err: any) {
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
    async getToolList(): Promise<MCPToolInfo[]> {
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
            return JSON.parse(raw) as MCPToolInfo[];
        } catch {
            return [];
        }
    }

    /**
     * Check if Ollama is running.
     */
    async checkHealth(): Promise<boolean> {
        const script = `
from mcp_assistant.llm.client import OllamaClient
c = OllamaClient()
print("true" if c.is_available() else "false")
`;
        try {
            const result = await this.runPythonCommand(script);
            return result.trim() === 'true';
        } catch {
            return false;
        }
    }

    /**
     * Verify today's audit log.
     */
    async verifyAudit(): Promise<MCPCommandResult> {
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
            return JSON.parse(raw) as MCPCommandResult;
        } catch (err: any) {
            return { success: false, output: err.message, error: err.message };
        }
    }

    dispose() {
        // Cleanup if needed
    }
}
