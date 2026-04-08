import json
from mcp_assistant.context.buffer import ConversationBuffer


def test_add_and_get():
    buf = ConversationBuffer(max_turns=5)
    buf.add_turn("user", "hello")
    buf.add_turn("assistant", "world")
    ctx = buf.get_context()
    assert len(ctx) == 2
    assert ctx[0]["role"] == "user"
    assert ctx[1]["content"] == "world"


def test_max_turns_respected():
    buf = ConversationBuffer(max_turns=2)
    for i in range(10):
        buf.add_turn("user", f"msg {i}")
        buf.add_turn("assistant", f"resp {i}")
    # max_turns=2 → keeps last 4 entries (2 pairs)
    ctx = buf.get_context()
    assert len(ctx) == 4


def test_clear():
    buf = ConversationBuffer()
    buf.add_turn("user", "hi")
    buf.clear()
    assert len(buf.get_context()) == 0


def test_persist_and_reload(tmp_path, monkeypatch):
    import mcp_assistant.config as cfg
    monkeypatch.setattr(cfg, "CONTEXT_PERSIST_DIR", tmp_path)

    buf = ConversationBuffer(max_turns=5)
    buf.add_turn("user", "test input")
    buf.add_turn("assistant", "test output")
    buf.save()

    buf2 = ConversationBuffer(max_turns=5)
    buf2.load()
    ctx = buf2.get_context()
    assert len(ctx) == 2
    assert ctx[0]["content"] == "test input"


def test_call_field_stripped_from_context():
    buf = ConversationBuffer()
    buf.add_turn("assistant", "result", call={"tool": "GitTool"})
    ctx = buf.get_context()
    assert "call" not in ctx[0]


def test_get_context_n():
    buf = ConversationBuffer(max_turns=10)
    for i in range(6):
        buf.add_turn("user", f"u{i}")
        buf.add_turn("assistant", f"a{i}")
    ctx = buf.get_context(n=2)
    assert len(ctx) == 4  # last 2 pairs = 4 turns
