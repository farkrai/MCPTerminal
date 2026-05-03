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
exports.MCPToolsProvider = void 0;
/**
 * Tree view listing all MCP tools and their actions.
 */
const vscode = __importStar(require("vscode"));
class ToolItem extends vscode.TreeItem {
    label;
    collapsibleState;
    toolInfo;
    actionName;
    constructor(label, collapsibleState, toolInfo, actionName) {
        super(label, collapsibleState);
        this.label = label;
        this.collapsibleState = collapsibleState;
        this.toolInfo = toolInfo;
        this.actionName = actionName;
        if (toolInfo && !actionName) {
            this.description = toolInfo.description;
            this.iconPath = new vscode.ThemeIcon('symbol-class');
            this.tooltip = `${toolInfo.name}\n${toolInfo.description}\nActions: ${toolInfo.actions.join(', ')}`;
        }
        else if (actionName) {
            this.iconPath = new vscode.ThemeIcon('symbol-method');
            this.tooltip = `${actionName}`;
            this.command = {
                command: 'mcpAssistant.sendCommand',
                title: 'Run Action',
            };
        }
    }
}
class MCPToolsProvider {
    _onDidChangeTreeData = new vscode.EventEmitter();
    onDidChangeTreeData = this._onDidChangeTreeData.event;
    tools = [];
    bridge;
    constructor(bridge) {
        this.bridge = bridge;
        this.loadTools();
    }
    async loadTools() {
        this.tools = await this.bridge.getToolList();
        this._onDidChangeTreeData.fire(undefined);
    }
    refresh() {
        this.loadTools();
    }
    getTreeItem(element) {
        return element;
    }
    getChildren(element) {
        if (!element) {
            return this.tools.map(t => new ToolItem(t.name, vscode.TreeItemCollapsibleState.Collapsed, t));
        }
        if (element.toolInfo) {
            return element.toolInfo.actions.map(a => new ToolItem(a, vscode.TreeItemCollapsibleState.None, undefined, a));
        }
        return [];
    }
}
exports.MCPToolsProvider = MCPToolsProvider;
//# sourceMappingURL=toolsView.js.map