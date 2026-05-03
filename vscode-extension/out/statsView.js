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
exports.MCPStatsProvider = void 0;
/**
 * Tree view showing system stats (CPU, RAM, Disk).
 */
const vscode = __importStar(require("vscode"));
const os = __importStar(require("os"));
class StatItem extends vscode.TreeItem {
    constructor(label, value, icon) {
        super(label, vscode.TreeItemCollapsibleState.None);
        this.description = value;
        this.iconPath = new vscode.ThemeIcon(icon);
    }
}
class MCPStatsProvider {
    _onDidChangeTreeData = new vscode.EventEmitter();
    onDidChangeTreeData = this._onDidChangeTreeData.event;
    bridge;
    constructor(bridge) {
        this.bridge = bridge;
    }
    refresh() {
        this._onDidChangeTreeData.fire(undefined);
    }
    getTreeItem(element) {
        return element;
    }
    getChildren() {
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
exports.MCPStatsProvider = MCPStatsProvider;
//# sourceMappingURL=statsView.js.map