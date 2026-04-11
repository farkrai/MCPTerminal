APP_CSS = """
/* ── Root layout: 3 columns side by side ───────────────────────────────── */
Screen {
    layout: horizontal;
    background: $surface;
}

/* ── Stats sidebar (left) ───────────────────────────────────────────────── */
StatsSidebar {
    width: 24;
    height: 100%;
    border: round $primary-darken-2;
    border-title-color: $primary;
    padding: 0 1;
    background: $surface-darken-1;
    overflow-y: auto;
}

StatsSidebar .stats-label {
    color: $text-muted;
    text-style: bold;
}

StatsSidebar .stats-value {
    color: $success;
}

StatsSidebar ProgressBar {
    width: 1fr;
}

/* ── Center column: history + input stacked ─────────────────────────────── */
#center-col {
    width: 1fr;
    height: 100%;
    layout: vertical;
}

/* ── History panel (center, top) ────────────────────────────────────────── */
HistoryPanel {
    height: 1fr;
    border: round $primary-darken-2;
    border-title-color: $primary;
    background: $surface;
    overflow-y: auto;
    padding: 0 1;
}

#streaming-line {
    height: auto;
    color: $text-muted;
    padding: 0 1;
}

/* ── Input bar (center, bottom) ─────────────────────────────────────────── */
InputBar {
    height: 3;
    border: round $accent-darken-1;
    background: $surface;
    layout: horizontal;
}

InputBar Input {
    width: 1fr;
    border: none;
    background: $surface;
}

InputBar .mode-badge {
    width: 7;
    padding: 0 1;
    content-align: center middle;
    color: $accent;
    text-style: bold;
}

/* ── Tool inspector (right) ─────────────────────────────────────────────── */
ToolInspector {
    width: 30;
    height: 100%;
    border: round $primary-darken-2;
    border-title-color: $accent;
    padding: 0 1;
    background: $surface-darken-1;
    overflow-y: auto;
}

ToolInspector .inspector-key   { color: $accent; }
ToolInspector .inspector-val   { color: $text; }
ToolInspector .inspector-ok    { color: $success; text-style: bold; }
ToolInspector .inspector-err   { color: $error; text-style: bold; }

ConfirmModal {
    align: center middle;
}

#confirm-dialog {
    width: 70;
    max-height: 30;
    border: round $warning;
    background: $surface;
    padding: 1 2;
    layout: vertical;
}

#preview {
    height: auto;
    max-height: 16;
    overflow-y: auto;
    border: round $accent-darken-1;
    padding: 1;
    margin-bottom: 1;
}

#confirm-buttons {
    align-horizontal: center;
    height: auto;
}

/* ── History entry styles ────────────────────────────────────────────────── */
.history-user      { color: $accent; text-style: bold; }
.history-tool      { color: $text-muted; }
.history-ok        { color: $success; }
.history-err       { color: $error; }
.history-chain     { color: $warning; }
"""
