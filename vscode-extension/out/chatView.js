"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.MCPChatViewProvider = void 0;
class MCPChatViewProvider {
    view;
    bridge;
    outputChannel;
    extensionUri;
    constructor(extensionUri, bridge, outputChannel) {
        this.extensionUri = extensionUri;
        this.bridge = bridge;
        this.outputChannel = outputChannel;
    }
    resolveWebviewView(webviewView, _context, _token) {
        this.view = webviewView;
        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this.extensionUri],
        };
        webviewView.webview.html = this.getHtml();
        webviewView.webview.onDidReceiveMessage(async (message) => {
            if (message.type === 'command') {
                const input = message.text;
                this.outputChannel.appendLine(`[chat] > ${input}`);
                // Show thinking state
                webviewView.webview.postMessage({ type: 'thinking' });
                const result = await this.bridge.sendCommand(input);
                this.outputChannel.appendLine(`[chat] ${result.success ? '✓' : '✗'} ${result.output.substring(0, 100)}`);
                webviewView.webview.postMessage({
                    type: 'result',
                    input,
                    ...result,
                });
            }
        });
    }
    /**
     * Post a result from external command (e.g. quick input).
     */
    postResult(input, result) {
        if (this.view) {
            this.view.webview.postMessage({
                type: 'result',
                input,
                ...result,
            });
        }
    }
    getHtml() {
        return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
    :root {
        --bg: #0a0e17;
        --bg-card: #0d1526;
        --border: #162a44;
        --cyan: #00d4ff;
        --pink: #ff6090;
        --green: #00e676;
        --red: #ff1744;
        --amber: #ffab00;
        --text: #e0e6f0;
        --muted: #5a6a8a;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
        font-family: var(--vscode-font-family, 'Segoe UI', monospace);
        font-size: 13px;
        background: var(--bg);
        color: var(--text);
        height: 100vh;
        display: flex;
        flex-direction: column;
    }
    #chat-log {
        flex: 1;
        overflow-y: auto;
        padding: 8px;
    }
    .entry { margin-bottom: 12px; }
    .entry .user {
        color: var(--cyan);
        font-weight: bold;
        margin-bottom: 4px;
    }
    .entry .tool {
        color: var(--muted);
        font-size: 11px;
        margin-bottom: 2px;
    }
    .entry .tool .action { color: var(--pink); }
    .entry .output {
        background: var(--bg-card);
        border-left: 3px solid var(--border);
        padding: 6px 8px;
        border-radius: 4px;
        white-space: pre-wrap;
        word-break: break-word;
        font-family: monospace;
        font-size: 12px;
        max-height: 300px;
        overflow-y: auto;
    }
    .entry .output.success { border-left-color: var(--green); }
    .entry .output.failure { border-left-color: var(--red); }
    .thinking {
        color: var(--pink);
        font-style: italic;
        padding: 8px;
        animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.4; }
    }
    .meta {
        font-size: 10px;
        color: var(--muted);
        margin-top: 2px;
    }
    #input-area {
        display: flex;
        border-top: 1px solid var(--border);
        background: var(--bg-card);
    }
    #cmd-input {
        flex: 1;
        background: transparent;
        border: none;
        color: var(--text);
        padding: 10px 12px;
        font-size: 13px;
        outline: none;
    }
    #cmd-input::placeholder { color: var(--muted); }
    #send-btn {
        background: var(--cyan);
        color: var(--bg);
        border: none;
        padding: 10px 14px;
        cursor: pointer;
        font-weight: bold;
        font-size: 13px;
    }
    #send-btn:hover { background: #33ddff; }
    .welcome {
        text-align: center;
        padding: 20px;
        color: var(--muted);
    }
    .welcome h3 { color: var(--cyan); margin-bottom: 8px; }
</style>
</head>
<body>
    <div id="chat-log">
        <div class="welcome">
            <h3>MCP Terminal Assistant</h3>
            <p>Type a natural-language command below.<br>
            Examples: <em>show git status</em>, <em>list files</em>, <em>check cpu</em></p>
        </div>
    </div>
    <div id="input-area">
        <input type="text" id="cmd-input" placeholder="Ask me anything…" autofocus />
        <button id="send-btn">Send</button>
    </div>
<script>
    const vscode = acquireVsCodeApi();
    const log = document.getElementById('chat-log');
    const input = document.getElementById('cmd-input');
    const btn = document.getElementById('send-btn');

    function send() {
        const text = input.value.trim();
        if (!text) return;
        vscode.postMessage({ type: 'command', text });
        input.value = '';
    }

    btn.addEventListener('click', send);
    input.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });

    window.addEventListener('message', event => {
        const msg = event.data;

        // Remove thinking indicator
        const thinking = log.querySelector('.thinking');
        if (thinking) thinking.remove();

        if (msg.type === 'thinking') {
            const el = document.createElement('div');
            el.className = 'thinking';
            el.textContent = '⟳ Thinking…';
            log.appendChild(el);
            log.scrollTop = log.scrollHeight;
            return;
        }

        if (msg.type === 'result') {
            // Clear welcome on first result
            const welcome = log.querySelector('.welcome');
            if (welcome) welcome.remove();

            const entry = document.createElement('div');
            entry.className = 'entry';

            const userEl = document.createElement('div');
            userEl.className = 'user';
            userEl.textContent = 'You › ' + msg.input;
            entry.appendChild(userEl);

            if (msg.tool) {
                const toolEl = document.createElement('div');
                toolEl.className = 'tool';
                toolEl.innerHTML = '→ ' + msg.tool + '<span class="action">.' + (msg.action || '') + '</span>' +
                    (msg.confidence !== undefined ? ' (conf ' + msg.confidence.toFixed(2) + ')' : '');
                entry.appendChild(toolEl);
            }

            const outEl = document.createElement('div');
            outEl.className = 'output ' + (msg.success ? 'success' : 'failure');
            outEl.textContent = (msg.success ? '✓ ' : '✗ ') + msg.output;
            entry.appendChild(outEl);

            if (msg.duration_ms) {
                const metaEl = document.createElement('div');
                metaEl.className = 'meta';
                metaEl.textContent = msg.duration_ms.toFixed(0) + 'ms';
                entry.appendChild(metaEl);
            }

            log.appendChild(entry);
            log.scrollTop = log.scrollHeight;
        }
    });
</script>
</body>
</html>`;
    }
}
exports.MCPChatViewProvider = MCPChatViewProvider;
//# sourceMappingURL=chatView.js.map