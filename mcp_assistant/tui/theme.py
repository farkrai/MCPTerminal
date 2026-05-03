"""
MCP Terminal Assistant — Modern Animated TUI Theme
React/TypeScript-inspired dark UI with smooth transitions and glow effects.
"""

APP_CSS = """
/* ══════════════════════════════════════════════════════════════════════════
   ROOT
   ══════════════════════════════════════════════════════════════════════════ */
Screen {
    layout: horizontal;
    background: #0a0e17;
    layers: base overlay;
}

/* ── Header / Footer ─────────────────────────────────────────────────────── */
Header {
    background: #0d1526;
    color: #00d4ff;
    text-style: bold;
    dock: top;
    height: 1;
}

Footer {
    background: #0d1526 0%;
    color: #445566;
    dock: bottom;
}

FooterKey {
    background: #0d1526;
    color: #00d4ff;
}

FooterKey .footer-key--key {
    background: #162a44;
    color: #00d4ff;
    text-style: bold;
}

FooterKey .footer-key--description {
    color: #445566;
}

/* ══════════════════════════════════════════════════════════════════════════
   WELCOME OVERLAY — Fade-out panel
   ══════════════════════════════════════════════════════════════════════════ */
#welcome-overlay {
    dock: top;
    height: auto;
    max-height: 16;
    background: #0d1526;
    border-bottom: hkey #00d4ff;
    padding: 1 2 0 2;
    transition: opacity 600ms in_out_cubic;
    opacity: 1.0;
}

#welcome-overlay.fading {
    opacity: 0.0;
}

#welcome-overlay.hidden {
    display: none;
}

#welcome-title {
    text-align: center;
    color: #00d4ff;
    text-style: bold;
    width: 1fr;
}

#welcome-subtitle {
    text-align: center;
    color: #5a6a8a;
    width: 1fr;
    margin-bottom: 1;
}

#welcome-info {
    text-align: center;
    color: #3a5070;
    width: 1fr;
}

/* ══════════════════════════════════════════════════════════════════════════
   LEFT SIDEBAR — System monitor with sparklines
   ══════════════════════════════════════════════════════════════════════════ */
StatsSidebar {
    width: 30;
    height: 100%;
    border: round #162a44;
    border-title-color: #00d4ff;
    border-title-style: bold;
    padding: 0 1;
    background: #0d1526;
    overflow-y: auto;
    transition: background 400ms in_out_cubic;
}

StatsSidebar:focus-within {
    border: round #00d4ff 50%;
}

StatsSidebar .section-header {
    color: #00d4ff;
    text-style: bold;
    margin-top: 1;
    padding: 0;
    height: 1;
}

StatsSidebar .metric-label {
    color: #3a5070;
    text-style: bold;
    height: 1;
}

StatsSidebar .metric-value {
    color: #c8d6e5;
    height: 1;
}

StatsSidebar .metric-good {
    color: #00e676;
}

StatsSidebar .metric-warn {
    color: #ffab00;
}

StatsSidebar .metric-crit {
    color: #ff1744;
}

StatsSidebar Sparkline {
    height: 2;
    margin: 0 0 0 0;
}

StatsSidebar ProgressBar {
    height: 1;
    padding: 0;
}

StatsSidebar ProgressBar Bar {
    width: 1fr;
}

StatsSidebar ProgressBar Bar > .bar--bar {
    color: #162a44;
}

StatsSidebar ProgressBar Bar > .bar--complete {
    color: #00d4ff;
}

/* ══════════════════════════════════════════════════════════════════════════
   CENTER COLUMN
   ══════════════════════════════════════════════════════════════════════════ */
#center-col {
    width: 1fr;
    height: 100%;
    layout: vertical;
}

/* ── Session bar ─────────────────────────────────────────────────────────── */
#session-bar {
    height: 1;
    background: #0d1526;
    color: #3a5070;
    padding: 0 1;
    layout: horizontal;
}

/* ── History panel ───────────────────────────────────────────────────────── */
HistoryPanel {
    height: 1fr;
    border: round #162a44;
    border-title-color: #00d4ff;
    border-title-style: bold;
    background: #0a0e17;
    overflow-y: auto;
    padding: 0 1;
    transition: border 300ms in_out_cubic;
}

HistoryPanel:focus-within {
    border: round #00d4ff 50%;
}

/* ── Loading indicator ───────────────────────────────────────────────────── */
#thinking-bar {
    height: auto;
    max-height: 3;
    background: #0d1526;
    padding: 0 1;
    transition: opacity 300ms in_out_cubic;
    opacity: 1.0;
}

#thinking-bar.hidden {
    display: none;
    opacity: 0;
}

#thinking-bar LoadingIndicator {
    height: 1;
    color: #ff6090;
    background: #0d1526;
}

#thinking-label {
    color: #ff6090;
    text-style: italic;
    height: 1;
    text-align: center;
}

/* ── Input bar ───────────────────────────────────────────────────────────── */
InputBar {
    height: 3;
    border: round #162a44;
    background: #0d1526;
    layout: horizontal;
    transition: border 300ms in_out_cubic;
}

InputBar:focus-within {
    border: round #00d4ff;
}

InputBar Input {
    width: 1fr;
    border: none;
    background: #0d1526;
    color: #e0e6f0;
}

InputBar Input:focus {
    border: none;
}

InputBar .mode-badge {
    width: auto;
    min-width: 7;
    padding: 0 1;
    content-align: center middle;
    text-style: bold;
    transition: color 300ms in_out_cubic, background 300ms in_out_cubic;
}

InputBar .badge-mcp {
    color: #00d4ff;
    background: #0a2030;
}

InputBar .badge-dry {
    color: #ffab00;
    background: #1a1800;
}

InputBar .badge-busy {
    color: #ff6090;
    background: #1a0015;
}

/* ══════════════════════════════════════════════════════════════════════════
   RIGHT SIDEBAR — Tool inspector with animated headers
   ══════════════════════════════════════════════════════════════════════════ */
ToolInspector {
    width: 36;
    height: 100%;
    border: round #162a44;
    border-title-color: #ff6090;
    border-title-style: bold;
    padding: 0 1;
    background: #0d1526;
    overflow-y: auto;
    transition: border 300ms in_out_cubic, background 300ms in_out_cubic;
}

ToolInspector:focus-within {
    border: round #ff6090 50%;
}

/* ══════════════════════════════════════════════════════════════════════════
   COMMAND PALETTE — animated slide-down
   ══════════════════════════════════════════════════════════════════════════ */
#command-palette-container {
    dock: top;
    height: auto;
    max-height: 18;
    background: #0a0e17 90%;
    border: round #00d4ff;
    padding: 1 2;
    layer: overlay;
    transition: opacity 200ms in_out_cubic;
    opacity: 1.0;
}

#command-palette-container.hidden {
    display: none;
    opacity: 0;
}

#command-palette-container Input {
    background: #162a44;
    color: #e0e6f0;
    border: tall #00d4ff;
    margin-bottom: 1;
}

#command-palette-container Input:focus {
    border: tall #ff6090;
}

#palette-results {
    height: auto;
    max-height: 12;
    background: #0d1526;
    overflow-y: auto;
}

.palette-item {
    padding: 0 1;
    color: #c8d6e5;
    height: auto;
    transition: background 150ms linear, color 150ms linear;
}

.palette-item:hover {
    background: #162a44;
    color: #00d4ff;
}

/* ══════════════════════════════════════════════════════════════════════════
   NOTIFICATION TOAST — animated slide-up
   ══════════════════════════════════════════════════════════════════════════ */
#toast-container {
    dock: bottom;
    height: 1;
    background: #00e676;
    color: #0a0e17;
    text-style: bold;
    padding: 0 2;
    text-align: center;
    layer: overlay;
    transition: opacity 500ms in_out_cubic;
    opacity: 1.0;
}

#toast-container.hidden {
    display: none;
    opacity: 0;
}

#toast-container.toast-error {
    background: #ff1744;
    color: #ffffff;
}

#toast-container.toast-warn {
    background: #ffab00;
    color: #0a0e17;
}
"""
