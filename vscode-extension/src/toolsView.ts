/**
 * Tree view listing all MCP tools and their actions.
 */
import * as vscode from 'vscode';
import { MCPBridge, MCPToolInfo } from './bridge';

class ToolItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState,
        public readonly toolInfo?: MCPToolInfo,
        public readonly actionName?: string,
    ) {
        super(label, collapsibleState);
        if (toolInfo && !actionName) {
            this.description = toolInfo.description;
            this.iconPath = new vscode.ThemeIcon('symbol-class');
            this.tooltip = `${toolInfo.name}\n${toolInfo.description}\nActions: ${toolInfo.actions.join(', ')}`;
        } else if (actionName) {
            this.iconPath = new vscode.ThemeIcon('symbol-method');
            this.tooltip = `${actionName}`;
            this.command = {
                command: 'mcpAssistant.sendCommand',
                title: 'Run Action',
            };
        }
    }
}

export class MCPToolsProvider implements vscode.TreeDataProvider<ToolItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<ToolItem | undefined>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private tools: MCPToolInfo[] = [];
    private bridge: MCPBridge;

    constructor(bridge: MCPBridge) {
        this.bridge = bridge;
        this.loadTools();
    }

    private async loadTools() {
        this.tools = await this.bridge.getToolList();
        this._onDidChangeTreeData.fire(undefined);
    }

    refresh() {
        this.loadTools();
    }

    getTreeItem(element: ToolItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: ToolItem): ToolItem[] {
        if (!element) {
            return this.tools.map(t =>
                new ToolItem(t.name, vscode.TreeItemCollapsibleState.Collapsed, t)
            );
        }
        if (element.toolInfo) {
            return element.toolInfo.actions.map(a =>
                new ToolItem(a, vscode.TreeItemCollapsibleState.None, undefined, a)
            );
        }
        return [];
    }
}
