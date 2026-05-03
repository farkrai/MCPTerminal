/**
 * Tree view showing system stats (CPU, RAM, Disk).
 */
import * as vscode from 'vscode';
import { MCPBridge } from './bridge';
import * as os from 'os';

class StatItem extends vscode.TreeItem {
    constructor(label: string, value: string, icon: string) {
        super(label, vscode.TreeItemCollapsibleState.None);
        this.description = value;
        this.iconPath = new vscode.ThemeIcon(icon);
    }
}

export class MCPStatsProvider implements vscode.TreeDataProvider<StatItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<StatItem | undefined>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private bridge: MCPBridge;

    constructor(bridge: MCPBridge) {
        this.bridge = bridge;
    }

    refresh() {
        this._onDidChangeTreeData.fire(undefined);
    }

    getTreeItem(element: StatItem): vscode.TreeItem {
        return element;
    }

    getChildren(): StatItem[] {
        const cpus = os.cpus();
        const totalMem = os.totalmem();
        const freeMem = os.freemem();
        const usedMem = totalMem - freeMem;
        const memPct = ((usedMem / totalMem) * 100).toFixed(1);
        const uptimeH = Math.floor(os.uptime() / 3600);
        const uptimeM = Math.floor((os.uptime() % 3600) / 60);

        const loadAvg = os.loadavg();

        return [
            new StatItem('CPU', `${cpus.length} cores`, 'dashboard'),
            new StatItem('Load', `${loadAvg[0].toFixed(2)} ${loadAvg[1].toFixed(2)} ${loadAvg[2].toFixed(2)}`, 'pulse'),
            new StatItem('RAM', `${(usedMem / 1e9).toFixed(1)}/${(totalMem / 1e9).toFixed(1)} GB (${memPct}%)`, 'server'),
            new StatItem('Free RAM', `${(freeMem / 1e9).toFixed(1)} GB`, 'arrow-down'),
            new StatItem('Platform', `${os.platform()} ${os.arch()}`, 'device-desktop'),
            new StatItem('Hostname', os.hostname(), 'globe'),
            new StatItem('Uptime', `${uptimeH}h ${uptimeM}m`, 'clock'),
            new StatItem('Node', process.version, 'symbol-namespace'),
        ];
    }
}
