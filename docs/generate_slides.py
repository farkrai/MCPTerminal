"""
Generate PowerPoint slides for MCP Terminal Assistant project.
Run: venv/bin/python docs/generate_slides.py
"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
import copy

# ── Colour palette ─────────────────────────────────────────────────────────────
BG_DARK   = RGBColor(0x0D, 0x1B, 0x2A)   # deep navy
BG_CARD   = RGBColor(0x16, 0x2A, 0x40)   # slightly lighter navy
ACCENT    = RGBColor(0x00, 0xB4, 0xD8)   # cyan
ACCENT2   = RGBColor(0x90, 0xE0, 0xEF)   # light cyan
WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
GRAY      = RGBColor(0xAA, 0xBB, 0xCC)
GREEN     = RGBColor(0x2E, 0xCC, 0x71)
ORANGE    = RGBColor(0xF3, 0x96, 0x14)

SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)


def new_prs() -> Presentation:
    prs = Presentation()
    prs.slide_width  = SLIDE_W
    prs.slide_height = SLIDE_H
    return prs


def blank_layout(prs):
    return prs.slide_layouts[6]   # completely blank


def fill_bg(slide, color=BG_DARK):
    """Fill slide background."""
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_rect(slide, left, top, width, height, color, alpha=None):
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        left, top, width, height
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    return shape


def add_text(slide, text, left, top, width, height,
             font_size=18, bold=False, color=WHITE,
             align=PP_ALIGN.LEFT, italic=False, wrap=True):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    return txBox


def slide_title_card(prs):
    """Slide 1 — Title."""
    slide = prs.slides.add_slide(blank_layout(prs))
    fill_bg(slide)

    # Accent bar left
    add_rect(slide, Inches(0), Inches(0), Inches(0.18), SLIDE_H, ACCENT)

    # Top stripe
    add_rect(slide, Inches(0.18), Inches(0), SLIDE_W, Inches(0.06), ACCENT)

    # Decorative circle top-right
    cir = slide.shapes.add_shape(9, Inches(10.5), Inches(-1.2), Inches(4), Inches(4))
    cir.fill.solid(); cir.fill.fore_color.rgb = BG_CARD
    cir.line.fill.background()

    cir2 = slide.shapes.add_shape(9, Inches(11.3), Inches(-0.5), Inches(2.5), Inches(2.5))
    cir2.fill.solid(); cir2.fill.fore_color.rgb = RGBColor(0x00, 0x70, 0x90)
    cir2.line.fill.background()

    # Badge
    add_rect(slide, Inches(0.6), Inches(1.4), Inches(2.6), Inches(0.38), ACCENT)
    add_text(slide, "MAJOR PROJECT — 12 CREDITS",
             Inches(0.62), Inches(1.42), Inches(2.56), Inches(0.34),
             font_size=9, bold=True, color=BG_DARK, align=PP_ALIGN.CENTER)

    add_text(slide, "MCP Integrated\nTerminal Assistant",
             Inches(0.6), Inches(1.95), Inches(9), Inches(2.2),
             font_size=52, bold=True, color=WHITE, align=PP_ALIGN.LEFT)

    add_text(slide, "An Offline AI-Powered Terminal that Understands Plain English",
             Inches(0.6), Inches(4.25), Inches(9), Inches(0.55),
             font_size=20, color=ACCENT2, align=PP_ALIGN.LEFT)

    add_text(slide, "Ollama  ·  Model Context Protocol  ·  Python  ·  Textual TUI",
             Inches(0.6), Inches(4.85), Inches(9), Inches(0.42),
             font_size=14, color=GRAY, align=PP_ALIGN.LEFT)

    add_text(slide, "K R Shrivathsan  |  2026",
             Inches(0.6), Inches(6.6), Inches(5), Inches(0.4),
             font_size=13, color=GRAY)

    return slide


def section_divider(prs, number, title, subtitle=""):
    """Section break slide."""
    slide = prs.slides.add_slide(blank_layout(prs))
    fill_bg(slide)

    # Full-width horizontal band
    add_rect(slide, Inches(0), Inches(3.0), SLIDE_W, Inches(1.5), BG_CARD)
    add_rect(slide, Inches(0), Inches(3.0), Inches(0.5), Inches(1.5), ACCENT)

    # Section number
    add_text(slide, f"{number:02d}",
             Inches(1.2), Inches(2.0), Inches(3), Inches(1.2),
             font_size=80, bold=True, color=RGBColor(0x1E, 0x3A, 0x55))

    add_text(slide, title,
             Inches(0.9), Inches(3.08), Inches(11), Inches(0.82),
             font_size=34, bold=True, color=WHITE, align=PP_ALIGN.LEFT)

    if subtitle:
        add_text(slide, subtitle,
                 Inches(0.9), Inches(4.6), Inches(11), Inches(0.5),
                 font_size=16, color=ACCENT2)
    return slide


def bullet_slide(prs, title, bullets, accent_bar=True):
    """Generic bullet-point slide."""
    slide = prs.slides.add_slide(blank_layout(prs))
    fill_bg(slide)

    if accent_bar:
        add_rect(slide, Inches(0), Inches(0), Inches(0.12), SLIDE_H, ACCENT)

    # Title underline
    add_text(slide, title,
             Inches(0.4), Inches(0.28), Inches(12.5), Inches(0.62),
             font_size=26, bold=True, color=WHITE)
    add_rect(slide, Inches(0.4), Inches(0.96), Inches(12.5), Inches(0.04), ACCENT)

    top = Inches(1.15)
    for icon, text in bullets:
        # Bullet dot
        add_rect(slide, Inches(0.5), top + Inches(0.07), Inches(0.1), Inches(0.1), ACCENT)
        add_text(slide, f"{icon}  {text}",
                 Inches(0.72), top, Inches(12.0), Inches(0.48),
                 font_size=17, color=WHITE)
        top += Inches(0.54)

    return slide


def two_col_slide(prs, title, left_items, right_items,
                  left_head="", right_head=""):
    slide = prs.slides.add_slide(blank_layout(prs))
    fill_bg(slide)
    add_rect(slide, Inches(0), Inches(0), Inches(0.12), SLIDE_H, ACCENT)

    add_text(slide, title,
             Inches(0.4), Inches(0.28), Inches(12.5), Inches(0.62),
             font_size=26, bold=True, color=WHITE)
    add_rect(slide, Inches(0.4), Inches(0.96), Inches(12.5), Inches(0.04), ACCENT)

    # Divider
    add_rect(slide, Inches(6.76), Inches(1.1), Inches(0.03), Inches(6.2), BG_CARD)

    for col, (head, items, left_x) in enumerate([
        (left_head, left_items, Inches(0.5)),
        (right_head, right_items, Inches(6.9)),
    ]):
        top = Inches(1.15)
        if head:
            add_text(slide, head, left_x, top, Inches(5.9), Inches(0.4),
                     font_size=14, bold=True, color=ACCENT2)
            top += Inches(0.5)
        for icon, text in items:
            add_rect(slide, left_x, top + Inches(0.08), Inches(0.1), Inches(0.1), ACCENT)
            add_text(slide, f"{icon}  {text}",
                     left_x + Inches(0.2), top, Inches(5.9), Inches(0.46),
                     font_size=15, color=WHITE)
            top += Inches(0.52)

    return slide


def architecture_slide(prs):
    """4-layer architecture diagram."""
    slide = prs.slides.add_slide(blank_layout(prs))
    fill_bg(slide)
    add_rect(slide, Inches(0), Inches(0), Inches(0.12), SLIDE_H, ACCENT)

    add_text(slide, "System Architecture — 4-Layer Design",
             Inches(0.4), Inches(0.28), Inches(12.5), Inches(0.62),
             font_size=26, bold=True, color=WHITE)
    add_rect(slide, Inches(0.4), Inches(0.96), Inches(12.5), Inches(0.04), ACCENT)

    layers = [
        (ACCENT,                   "Layer 1 — TUI / Interface",   "Textual 3-column layout  ·  Live stats sidebar  ·  History panel  ·  Tool inspector"),
        (RGBColor(0x00,0x7A,0xA0), "Layer 2 — LLM  (Ollama)",     "phi3:latest  ·  Prompt builder  ·  Response parser (4 formats)  ·  Confidence gating"),
        (RGBColor(0x00,0x55,0x80), "Layer 3 — MCP Dispatcher",    "Schema validation  ·  Policy engine (.mcprc)  ·  Dry-run  ·  Chain execution  ·  Audit log"),
        (RGBColor(0x00,0x38,0x60), "Layer 4 — Tool Implementations", "FileHandler  ·  GitTool  ·  SystemTool  ·  TestRunner  ·  Plugin SDK"),
    ]

    top = Inches(1.15)
    for color, title, desc in layers:
        add_rect(slide, Inches(0.5), top, Inches(12.2), Inches(0.95), color)
        add_text(slide, title,
                 Inches(0.7), top + Inches(0.05), Inches(4.5), Inches(0.4),
                 font_size=15, bold=True, color=WHITE)
        add_text(slide, desc,
                 Inches(0.7), top + Inches(0.45), Inches(11.5), Inches(0.42),
                 font_size=12, color=ACCENT2)
        top += Inches(1.08)

    # Arrow annotations
    add_text(slide, "↑ User input   ↓ Results",
             Inches(10.5), Inches(1.15), Inches(2.5), Inches(4.5),
             font_size=11, color=GRAY, align=PP_ALIGN.CENTER)

    return slide


def data_flow_slide(prs):
    """Single-command data flow."""
    slide = prs.slides.add_slide(blank_layout(prs))
    fill_bg(slide)
    add_rect(slide, Inches(0), Inches(0), Inches(0.12), SLIDE_H, ACCENT)

    add_text(slide, "Data Flow — Single Command Execution",
             Inches(0.4), Inches(0.28), Inches(12.5), Inches(0.62),
             font_size=26, bold=True, color=WHITE)
    add_rect(slide, Inches(0.4), Inches(0.96), Inches(12.5), Inches(0.04), ACCENT)

    steps = [
        (ACCENT,                   "① User Input",       "Natural-language command entered in InputBar"),
        (RGBColor(0x00,0x9A,0xC8), "② Prompt Builder",   "Injects tool registry + conversation history → structured prompt"),
        (RGBColor(0x00,0x7A,0xA0), "③ Ollama LLM",       "phi3 generates JSON: {tool, action, params, confidence}"),
        (RGBColor(0x00,0x5E,0x85), "④ Response Parser",  "Extracts MCPCall from 4 output formats; retries on ParseError"),
        (RGBColor(0x00,0x48,0x70), "⑤ Policy Engine",    "Checks sandbox, tool whitelist, requires confirmation?"),
        (RGBColor(0x00,0x33,0x55), "⑥ Tool Execute",     "FileHandler / GitTool / SystemTool / TestRunner → result"),
        (RGBColor(0x00,0x20,0x38), "⑦ Audit + Display",  "SHA-256 chain entry written; result shown in History + Inspector"),
    ]

    top = Inches(1.1)
    h = Inches(0.72)
    for color, step, desc in steps:
        add_rect(slide, Inches(0.5), top, Inches(12.2), h, color)
        add_text(slide, step,
                 Inches(0.7), top + Inches(0.06), Inches(2.8), Inches(0.35),
                 font_size=14, bold=True, color=WHITE)
        add_text(slide, desc,
                 Inches(3.6), top + Inches(0.06), Inches(9.0), Inches(0.55),
                 font_size=13, color=ACCENT2)
        top += h + Inches(0.04)

    return slide


def algo_slide_llm(prs):
    """Algorithm: LLM parsing."""
    slide = prs.slides.add_slide(blank_layout(prs))
    fill_bg(slide)
    add_rect(slide, Inches(0), Inches(0), Inches(0.12), SLIDE_H, ORANGE)

    add_text(slide, "Algorithm — LLM Response Parsing (Multi-Format)",
             Inches(0.4), Inches(0.28), Inches(12.5), Inches(0.62),
             font_size=26, bold=True, color=WHITE)
    add_rect(slide, Inches(0.4), Inches(0.96), Inches(12.5), Inches(0.04), ORANGE)

    pseudocode = [
        ("function", "parse_response(raw_text):"),
        ("",         "   attempt = 0"),
        ("",         "   while attempt ≤ MAX_PARSE_RETRIES (2):"),
        ("",         "      1. Try direct json.loads(raw_text)"),
        ("",         "      2. Try regex extract ```json ... ``` block"),
        ("",         "      3. Try regex extract first { ... } in prose"),
        ("",         "      4. Try chain format: steps[{tool, action}, ...]"),
        ("",         "      → if any succeeds: validate keys, clamp conf ∈ [0,1]"),
        ("",         "      → if all fail: raise ParseError, retry with JSON reminder"),
        ("",         "   return MCPCall | MCPChain"),
    ]

    top = Inches(1.1)
    add_rect(slide, Inches(0.5), top, Inches(12.2), Inches(5.5), BG_CARD)
    top += Inches(0.15)
    for style, line in pseudocode:
        color = ORANGE if style == "function" else ACCENT2
        add_text(slide, line,
                 Inches(0.75), top, Inches(11.7), Inches(0.42),
                 font_size=14, bold=(style == "function"), color=color)
        top += Inches(0.48)

    add_text(slide, "Confidence threshold < 0.5  →  ask user to clarify before dispatching",
             Inches(0.5), Inches(6.85), Inches(12.2), Inches(0.4),
             font_size=13, italic=True, color=GRAY)
    return slide


def algo_slide_policy(prs):
    """Algorithm: Policy / dispatch flow."""
    slide = prs.slides.add_slide(blank_layout(prs))
    fill_bg(slide)
    add_rect(slide, Inches(0), Inches(0), Inches(0.12), SLIDE_H, GREEN)

    add_text(slide, "Algorithm — Policy Enforcement & Dispatch",
             Inches(0.4), Inches(0.28), Inches(12.5), Inches(0.62),
             font_size=26, bold=True, color=WHITE)
    add_rect(slide, Inches(0.4), Inches(0.96), Inches(12.5), Inches(0.04), GREEN)

    steps = [
        ("Check tool exists in registry",            "→ ToolNotFoundError if missing"),
        ("Check tool in allowed_tools (policy)",     "→ PolicyViolationError if blocked"),
        ("Validate required params present",         "→ ValidationError if incomplete"),
        ("Dry-run mode OR requires_confirmation?",   "→ Show preview, await user y/n"),
        ("Execute tool.execute(call)",               "→ MCPResult(success, output, data, duration_ms)"),
        ("Write audit log entry",                    "→ JSONL with SHA-256 hash chain"),
        ("Return MCPResult to dispatcher / TUI",     "→ Display in history + inspector panels"),
    ]

    top = Inches(1.1)
    for i, (action, outcome) in enumerate(steps):
        bg = BG_CARD if i % 2 == 0 else RGBColor(0x1A, 0x30, 0x48)
        add_rect(slide, Inches(0.5), top, Inches(12.2), Inches(0.68), bg)
        add_text(slide, f"Step {i+1}:  {action}",
                 Inches(0.7), top + Inches(0.04), Inches(7.5), Inches(0.36),
                 font_size=14, bold=True, color=WHITE)
        add_text(slide, outcome,
                 Inches(8.3), top + Inches(0.04), Inches(4.2), Inches(0.58),
                 font_size=12, color=GREEN, align=PP_ALIGN.RIGHT)
        top += Inches(0.72)

    return slide


def algo_slide_audit(prs):
    """Algorithm: Audit hash chain."""
    slide = prs.slides.add_slide(blank_layout(prs))
    fill_bg(slide)
    add_rect(slide, Inches(0), Inches(0), Inches(0.12), SLIDE_H, ACCENT)

    add_text(slide, "Algorithm — Tamper-Evident Audit Log (SHA-256 Chain)",
             Inches(0.4), Inches(0.28), Inches(12.5), Inches(0.62),
             font_size=26, bold=True, color=WHITE)
    add_rect(slide, Inches(0.4), Inches(0.96), Inches(12.5), Inches(0.04), ACCENT)

    pseudocode = [
        "on_tool_execute(call, result):",
        "   entry = {seq, session_id, ts, user, hostname,",
        "            call, result, prev_hash}",
        "   entry_hash = SHA256(json.dumps(entry))",
        "   append entry + entry_hash → audit_YYYY-MM-DD.jsonl",
        "   prev_hash = entry_hash      # chain for next entry",
        "",
        "verify_chain(log_file):",
        "   prev = '0' * 64            # genesis hash",
        "   for entry in read_jsonl(log_file):",
        "      stored_hash = entry.pop('entry_hash')",
        "      computed    = SHA256(json.dumps(entry))",
        "      assert computed == stored_hash,  'TAMPERED'",
        "      assert entry['prev_hash'] == prev",
        "      prev = stored_hash",
        "   return VERIFIED",
    ]

    top = Inches(1.1)
    add_rect(slide, Inches(0.5), top, Inches(12.2), Inches(5.7), BG_CARD)
    top += Inches(0.12)
    for line in pseudocode:
        color = ACCENT if line.endswith(":") else ACCENT2
        add_text(slide, line,
                 Inches(0.75), top, Inches(11.7), Inches(0.34),
                 font_size=13, bold=line.endswith(":"), color=color)
        top += Inches(0.36)

    add_text(slide, "Triggered via !verify command or CLI: venv/bin/python -m mcp_assistant.audit.logger <logfile>",
             Inches(0.5), Inches(7.0), Inches(12.2), Inches(0.35),
             font_size=11, italic=True, color=GRAY)
    return slide


def eval_slide(prs):
    """Evaluation methodology."""
    slide = prs.slides.add_slide(blank_layout(prs))
    fill_bg(slide)
    add_rect(slide, Inches(0), Inches(0), Inches(0.12), SLIDE_H, ACCENT)

    add_text(slide, "Evaluation Methodology — Ablation Study",
             Inches(0.4), Inches(0.28), Inches(12.5), Inches(0.62),
             font_size=26, bold=True, color=WHITE)
    add_rect(slide, Inches(0.4), Inches(0.96), Inches(12.5), Inches(0.04), ACCENT)

    # Dataset box
    add_rect(slide, Inches(0.5), Inches(1.1), Inches(5.8), Inches(2.1), BG_CARD)
    add_text(slide, "Dataset  —  60 Items",
             Inches(0.7), Inches(1.15), Inches(5.4), Inches(0.38),
             font_size=14, bold=True, color=ACCENT2)
    dataset_lines = [
        "• 15 File operations  (easy / medium / hard)",
        "• 15 Git operations",
        "• 15 System monitoring",
        "• 10 Test runner",
        "• 5  Multi-step chains",
    ]
    top = Inches(1.6)
    for line in dataset_lines:
        add_text(slide, line, Inches(0.75), top, Inches(5.3), Inches(0.35),
                 font_size=13, color=WHITE)
        top += Inches(0.36)

    # Metrics box
    add_rect(slide, Inches(6.7), Inches(1.1), Inches(6.1), Inches(2.1), BG_CARD)
    add_text(slide, "Metrics  &  Targets",
             Inches(6.9), Inches(1.15), Inches(5.7), Inches(0.38),
             font_size=14, bold=True, color=ACCENT2)
    metric_lines = [
        "• Tool Accuracy     > 85%",
        "• Action Accuracy   > 75%",
        "• Parse Failures    < 10%",
        "• Hallucination     < 5%",
        "• Mean Latency      < 3 000 ms",
    ]
    top = Inches(1.6)
    for line in metric_lines:
        add_text(slide, line, Inches(6.9), top, Inches(5.7), Inches(0.35),
                 font_size=13, color=WHITE)
        top += Inches(0.36)

    # Ablation conditions
    add_text(slide, "4 Ablation Conditions",
             Inches(0.5), Inches(3.4), Inches(12.2), Inches(0.4),
             font_size=14, bold=True, color=ACCENT2)
    conditions = [
        ("no_context  |  no_conf_gate",  "Baseline: no history, no threshold"),
        ("ctx=5       |  no_conf_gate",  "5-turn rolling context"),
        ("ctx=10      |  no_conf_gate",  "10-turn context"),
        ("ctx=10      |  conf ≥ 0.5",    "10-turn + confidence gating"),
    ]
    top = Inches(3.9)
    for i, (label, desc) in enumerate(conditions):
        bg = BG_CARD if i % 2 == 0 else RGBColor(0x1A, 0x30, 0x48)
        add_rect(slide, Inches(0.5), top, Inches(12.2), Inches(0.56), bg)
        add_text(slide, label, Inches(0.7), top + Inches(0.08), Inches(4), Inches(0.36),
                 font_size=13, bold=True, color=ORANGE)
        add_text(slide, desc, Inches(4.9), top + Inches(0.08), Inches(7.6), Inches(0.36),
                 font_size=13, color=WHITE)
        top += Inches(0.6)

    return slide


def tools_slide(prs):
    """Tools overview."""
    slide = prs.slides.add_slide(blank_layout(prs))
    fill_bg(slide)
    add_rect(slide, Inches(0), Inches(0), Inches(0.12), SLIDE_H, ACCENT)

    add_text(slide, "Tool Implementations — MCP Layer",
             Inches(0.4), Inches(0.28), Inches(12.5), Inches(0.62),
             font_size=26, bold=True, color=WHITE)
    add_rect(slide, Inches(0.4), Inches(0.96), Inches(12.5), Inches(0.04), ACCENT)

    tools = [
        (ACCENT,                   "FileHandler",  "read · write · list · search · delete",
         "Sandboxed to project root  ·  10 MB guard  ·  Destructive ops need confirmation"),
        (RGBColor(0x00,0x7A,0xA0), "GitTool",      "status · diff · log · add · commit · branch_list · branch_switch",
         "subprocess(git ...)  ·  dry_run shows staged diff before commit"),
        (RGBColor(0x2E,0xCC,0x71), "SystemTool",   "cpu_stats · ram_stats · disk_stats · list_processes · kill_process · env_info",
         "psutil-based live metrics  ·  kill_process always requires confirmation"),
        (ORANGE,                   "TestRunner",   "detect · run · run_file · explain_failures",
         "Auto-detects pytest / Jest  ·  LLM-powered failure explanation"),
        (RGBColor(0x99,0x66,0xFF), "TimeTool",     "current_time · utc_time · unix_timestamp",
         "Plugin SDK demo  ·  Loaded dynamically from plugins/ without core changes"),
    ]

    top = Inches(1.1)
    for color, name, actions, note in tools:
        add_rect(slide, Inches(0.5), top, Inches(12.2), Inches(0.94), BG_CARD)
        add_rect(slide, Inches(0.5), top, Inches(0.18), Inches(0.94), color)
        add_text(slide, name,
                 Inches(0.85), top + Inches(0.05), Inches(2.0), Inches(0.38),
                 font_size=15, bold=True, color=color)
        add_text(slide, actions,
                 Inches(2.95), top + Inches(0.05), Inches(9.5), Inches(0.38),
                 font_size=12, color=ACCENT2)
        add_text(slide, note,
                 Inches(0.85), top + Inches(0.48), Inches(11.6), Inches(0.38),
                 font_size=11, color=GRAY)
        top += Inches(1.02)

    return slide


def plugin_sdk_slide(prs):
    """Plugin SDK."""
    slide = prs.slides.add_slide(blank_layout(prs))
    fill_bg(slide)
    add_rect(slide, Inches(0), Inches(0), Inches(0.12), SLIDE_H, ACCENT)

    add_text(slide, "Plugin SDK — Extensibility Without Core Changes",
             Inches(0.4), Inches(0.28), Inches(12.5), Inches(0.62),
             font_size=26, bold=True, color=WHITE)
    add_rect(slide, Inches(0.4), Inches(0.96), Inches(12.5), Inches(0.04), ACCENT)

    code = [
        "# plugins/my_tool.py",
        "from mcp_assistant.mcp.base import MCPTool",
        "from mcp_assistant.mcp.schema import MCPCall, MCPResult",
        "",
        "class MyTool(MCPTool):",
        "    TOOL_NAME           = 'MyTool'",
        "    TOOL_DESCRIPTION    = 'Does something useful'",
        "    SUPPORTED_ACTIONS   = ['do_thing']",
        "    DESTRUCTIVE_ACTIONS = []",
        "",
        "    def execute(self, call: MCPCall) -> MCPResult:",
        "        if call.action == 'do_thing':",
        "            return self._ok(call, 'Done!', {})",
        "        return self._err(call, f'Unknown action: {call.action}')",
    ]

    top = Inches(1.12)
    add_rect(slide, Inches(0.5), top, Inches(7.8), Inches(5.5), BG_CARD)
    top += Inches(0.15)
    for line in code:
        color = ORANGE if line.startswith("#") else (ACCENT2 if "class " in line or "def " in line else WHITE)
        add_text(slide, line, Inches(0.72), top, Inches(7.4), Inches(0.34),
                 font_size=12.5, bold=("class " in line or "def " in line), color=color)
        top += Inches(0.36)

    # Benefits panel
    add_rect(slide, Inches(8.6), Inches(1.12), Inches(4.6), Inches(5.5), BG_CARD)
    add_text(slide, "How It Works",
             Inches(8.8), Inches(1.22), Inches(4.2), Inches(0.38),
             font_size=14, bold=True, color=ACCENT2)
    benefit_lines = [
        "Drop file in plugins/",
        "ToolRegistry.discover_plugins()",
        "importlib loads & inspects",
        "MCPTool subclasses registered",
        "LLM prompt updated automatically",
        "Policy rules apply equally",
        "",
        "No core file edits needed",
        "Zero downtime — restart only",
    ]
    top2 = Inches(1.72)
    for line in benefit_lines:
        color = GREEN if line.startswith("No") or line.startswith("Zero") else (GRAY if not line else WHITE)
        add_text(slide, f"{'→' if line else ''} {line}",
                 Inches(8.8), top2, Inches(4.2), Inches(0.38),
                 font_size=13, color=color)
        top2 += Inches(0.42)

    return slide


def tui_slide(prs):
    """TUI layout."""
    slide = prs.slides.add_slide(blank_layout(prs))
    fill_bg(slide)
    add_rect(slide, Inches(0), Inches(0), Inches(0.12), SLIDE_H, ACCENT)

    add_text(slide, "Textual TUI — 3-Column Async Interface",
             Inches(0.4), Inches(0.28), Inches(12.5), Inches(0.62),
             font_size=26, bold=True, color=WHITE)
    add_rect(slide, Inches(0.4), Inches(0.96), Inches(12.5), Inches(0.04), ACCENT)

    # ASCII layout
    ascii_art = [
        "┌─────────────────┬─────────────────────────────────┬──────────────────────┐",
        "│  System Stats   │         Conversation             │   Tool Inspector     │",
        "│  CPU: ████░░  │  You: show git status             │  SUCCESS  [8ms]      │",
        "│  49.3%          │  → GitTool.status (conf 1.00)   │  CALL                │",
        "│  RAM: ███░░░  │  ✓ On branch main …               │    tool: GitTool     │",
        "│  DISK: ████   │                                   │    action: status    │",
        "│  89.2 / 100 GB  │                                   │    conf:  1.00       │",
        "│  UPTIME: 2h 14m ├─────────────────────────────────│  OUTPUT              │",
        "│  PROCS: 312     │  [MCP] > Type your command…      │    On branch main…   │",
        "└─────────────────┴─────────────────────────────────┴──────────────────────┘",
    ]

    add_rect(slide, Inches(0.5), Inches(1.1), Inches(12.2), Inches(3.6), BG_CARD)
    top = Inches(1.18)
    for line in ascii_art:
        add_text(slide, line, Inches(0.65), top, Inches(11.9), Inches(0.33),
                 font_size=11, color=ACCENT2)
        top += Inches(0.34)

    # Panel descriptions
    panels = [
        (Inches(0.5),  "Left Panel",   "Live CPU/RAM/Disk stats.\nRefreshes every 2 s."),
        (Inches(4.5),  "Center Panel", "Conversation history +\ninput bar ([MCP]/[DRY])."),
        (Inches(8.5),  "Right Panel",  "Full tool call detail:\nparams, output, timing."),
    ]
    for x, name, desc in panels:
        add_rect(slide, x, Inches(5.0), Inches(3.6), Inches(2.1), BG_CARD)
        add_text(slide, name, x + Inches(0.15), Inches(5.08), Inches(3.3), Inches(0.4),
                 font_size=14, bold=True, color=ACCENT2)
        add_text(slide, desc, x + Inches(0.15), Inches(5.55), Inches(3.3), Inches(1.3),
                 font_size=13, color=WHITE)

    return slide


def safety_slide(prs):
    two_col_slide(
        prs,
        "Safety & Security Design",
        left_head="Always Blocked",
        left_items=[
            ("🔒", "Paths outside project root"),
            ("🔒", ".env, .pem, .key, id_rsa files"),
            ("🔒", "Files > 10 MB"),
            ("🔒", "SSH directories"),
            ("🔒", "Disabled tools (policy)"),
        ],
        right_head="Requires Confirmation",
        right_items=[
            ("⚠", "Write to any file"),
            ("⚠", "Delete any file"),
            ("⚠", "Git commit"),
            ("⚠", "Kill process"),
            ("⚠", "Any action in dry-run mode"),
        ],
    )


def conclusion_slide(prs):
    slide = prs.slides.add_slide(blank_layout(prs))
    fill_bg(slide)

    add_rect(slide, Inches(0), Inches(0), Inches(0.18), SLIDE_H, ACCENT)
    add_rect(slide, Inches(0.18), Inches(0), SLIDE_W, Inches(0.06), ACCENT)

    add_text(slide, "Key Achievements",
             Inches(0.6), Inches(0.5), Inches(11), Inches(0.55),
             font_size=26, bold=True, color=WHITE)
    add_rect(slide, Inches(0.6), Inches(1.1), Inches(12.1), Inches(0.04), ACCENT)

    achievements = [
        ("✓", "65 unit tests — all passing across 10 test modules"),
        ("✓", "60-item evaluation dataset with ablation study (4 conditions)"),
        ("✓", "Tamper-evident audit log with SHA-256 hash chaining"),
        ("✓", "Plugin SDK — add new tools without touching core"),
        ("✓", "Policy engine — TOML-configurable, sandboxed, auditable"),
        ("✓", "Fully offline — Ollama local LLM, no data leaves machine"),
        ("✓", "Async Textual TUI with live system stats sidebar"),
    ]

    top = Inches(1.25)
    for icon, text in achievements:
        add_rect(slide, Inches(0.6), top + Inches(0.06), Inches(0.12), Inches(0.12), GREEN)
        add_text(slide, text, Inches(0.9), top, Inches(11.5), Inches(0.48),
                 font_size=16, color=WHITE)
        top += Inches(0.54)

    add_rect(slide, Inches(0.6), Inches(5.35), Inches(12.1), Inches(0.9), BG_CARD)
    add_text(slide, "\"Offline, structured, safe — plain English → real terminal actions\"",
             Inches(0.85), Inches(5.45), Inches(11.7), Inches(0.72),
             font_size=18, bold=True, italic=True, color=ACCENT2, align=PP_ALIGN.CENTER)

    add_text(slide, "K R Shrivathsan  |  12-Credit Major Project  |  2026",
             Inches(0.6), Inches(6.6), Inches(12.1), Inches(0.4),
             font_size=13, color=GRAY, align=PP_ALIGN.CENTER)
    return slide


# ── Build presentation ─────────────────────────────────────────────────────────

def build():
    prs = new_prs()

    slide_title_card(prs)

    section_divider(prs, 1, "Project Overview",
                    "What it does, why it matters")
    bullet_slide(prs, "Project Overview", [
        ("→", "Offline AI terminal assistant — zero cloud dependency"),
        ("→", "Natural language → structured tool invocation via MCP"),
        ("→", "Local LLM: Ollama + phi3:latest (3.8B Q4_0, ~2.3 GB)"),
        ("→", "4 built-in tools: FileHandler, GitTool, SystemTool, TestRunner"),
        ("→", "Plugin SDK: add new tools without changing core code"),
        ("→", "Policy engine (.mcprc) for safety & sandboxing"),
        ("→", "SHA-256 tamper-evident audit log"),
        ("→", "Async Textual TUI + CLI fallback"),
        ("→", "60-item evaluation dataset with 4-condition ablation study"),
        ("→", "65 unit tests — pytest, 10 test modules"),
    ])

    section_divider(prs, 2, "Design Methodology",
                    "Architecture, data flow, and design decisions")
    architecture_slide(prs)
    data_flow_slide(prs)

    section_divider(prs, 3, "Algorithms & Implementation",
                    "LLM parsing, policy dispatch, audit chain")
    algo_slide_llm(prs)
    algo_slide_policy(prs)
    algo_slide_audit(prs)

    section_divider(prs, 4, "Tool Implementations & Plugin SDK",
                    "MCP tool layer and extensibility")
    tools_slide(prs)
    plugin_sdk_slide(prs)

    section_divider(prs, 5, "TUI, Safety & Evaluation",
                    "User interface, security, and benchmarking")
    tui_slide(prs)
    safety_slide(prs)
    eval_slide(prs)

    section_divider(prs, 6, "Conclusion & Achievements", "")
    conclusion_slide(prs)

    out = "docs/MCP_Terminal_Assistant_Slides.pptx"
    prs.save(out)
    print(f"Saved: {out}  ({prs.slides.__len__()} slides)")


if __name__ == "__main__":
    build()
