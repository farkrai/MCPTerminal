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
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const chatView_1 = require("./chatView");
const toolsView_1 = require("./toolsView");
const statsView_1 = require("./statsView");
const bridge_1 = require("./bridge");
let bridge;
let outputChannel;
let statusBarItem;
function activate(context) {
    outputChannel = vscode.window.createOutputChannel('MCP Assistant');
    outputChannel.appendLine('MCP Terminal Assistant activating…');
    bridge = new bridge_1.MCPBridge(context, outputChannel);
    // Status bar
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.text = '$(terminal) MCP';
    statusBarItem.tooltip = 'MCP Terminal Assistant — Click to open';
    statusBarItem.command = 'mcpAssistant.openPanel';
    statusBarItem.color = '#00d4ff';
    statusBarItem.show();
    // Sidebar providers
    const chatProvider = new chatView_1.MCPChatViewProvider(context.extensionUri, bridge, outputChannel);
    context.subscriptions.push(vscode.window.registerWebviewViewProvider('mcpAssistant.chatView', chatProvider));
    const toolsProvider = new toolsView_1.MCPToolsProvider(bridge);
    context.subscriptions.push(vscode.window.registerTreeDataProvider('mcpAssistant.toolsView', toolsProvider));
    const statsProvider = new statsView_1.MCPStatsProvider(bridge);
    context.subscriptions.push(vscode.window.registerTreeDataProvider('mcpAssistant.statsView', statsProvider));
    // Commands
    context.subscriptions.push(vscode.commands.registerCommand('mcpAssistant.openPanel', () => {
        vscode.commands.executeCommand('mcpAssistant.chatView.focus');
    }), vscode.commands.registerCommand('mcpAssistant.sendCommand', async () => {
        const input = await vscode.window.showInputBox({
            prompt: 'Enter a natural-language command for MCP Assistant',
            placeHolder: 'e.g. show git status, list files, check cpu usage',
        });
        if (input) {
            const result = await bridge.sendCommand(input);
            outputChannel.appendLine(`> ${input}`);
            outputChannel.appendLine(result.output);
            if (result.success) {
                vscode.window.showInformationMessage(`MCP: ${result.output.substring(0, 100)}`);
            }
            else {
                vscode.window.showErrorMessage(`MCP Error: ${result.error || result.output.substring(0, 100)}`);
            }
            chatProvider.postResult(input, result);
        }
    }), vscode.commands.registerCommand('mcpAssistant.toggleDryRun', () => {
        const config = vscode.workspace.getConfiguration('mcpAssistant');
        const current = config.get('dryRunMode', false);
        config.update('dryRunMode', !current, vscode.ConfigurationTarget.Workspace);
        const state = !current ? 'ON' : 'OFF';
        vscode.window.showInformationMessage(`MCP Dry-Run: ${state}`);
        statusBarItem.text = !current ? '$(terminal) MCP [DRY]' : '$(terminal) MCP';
    }), vscode.commands.registerCommand('mcpAssistant.showTools', () => {
        bridge.getToolList().then(tools => {
            const items = tools.map(t => `${t.name}: ${t.actions.join(', ')}`);
            vscode.window.showQuickPick(items, { title: 'MCP Available Tools' });
        });
    }), vscode.commands.registerCommand('mcpAssistant.verifyAudit', async () => {
        const result = await bridge.verifyAudit();
        if (result.success) {
            vscode.window.showInformationMessage('MCP: Audit chain verified ✓');
        }
        else {
            vscode.window.showWarningMessage(`MCP: Audit chain issues — ${result.output}`);
        }
    }), vscode.commands.registerCommand('mcpAssistant.checkHealth', async () => {
        const healthy = await bridge.checkHealth();
        if (healthy) {
            vscode.window.showInformationMessage('MCP: Ollama is running ✓');
            statusBarItem.text = '$(terminal) MCP';
        }
        else {
            vscode.window.showErrorMessage('MCP: Ollama is not running. Start with: ollama serve');
            statusBarItem.text = '$(terminal) MCP ⚠';
        }
    }));
    // Health check on activation
    bridge.checkHealth().then(healthy => {
        if (!healthy) {
            statusBarItem.text = '$(terminal) MCP ⚠';
            outputChannel.appendLine('WARNING: Ollama is not running');
        }
        else {
            outputChannel.appendLine('Ollama connected ✓');
        }
    });
    // Refresh stats every 10s
    const statsInterval = setInterval(() => statsProvider.refresh(), 10000);
    context.subscriptions.push({ dispose: () => clearInterval(statsInterval) });
    outputChannel.appendLine('MCP Terminal Assistant activated.');
}
function deactivate() {
    if (bridge) {
        bridge.dispose();
    }
}
//# sourceMappingURL=extension.js.map