from __future__ import annotations
import json
from pathlib import Path
from mcp_assistant import config
from mcp_assistant.llm.tokenizer import count_tokens


class ConversationBuffer:
    def __init__(self, max_turns: int = config.CONTEXT_WINDOW_SIZE) -> None:
        self._max_turns = max_turns
        self._turns: list[dict] = []
        self._persist_path = config.CONTEXT_PERSIST_DIR / "context.json"
        self._dirty = False

    def add_turn(self, role: str, content: str, call: dict | None = None) -> None:
        self._turns.append({"role": role, "content": content, "call": call})
        # Keep only last max_turns pairs (user + assistant = 2 per exchange)
        if len(self._turns) > self._max_turns * 2:
            self._turns = self._turns[-(self._max_turns * 2):]
        self._dirty = True

    def get_context(self, n: int | None = None) -> list[dict]:
        turns = self._turns
        if n is not None:
            turns = turns[-(n * 2):]
        turns_clean = [{"role": t["role"], "content": t["content"]} for t in turns]
        while turns_clean:
            assembled = "\n".join(
                f"[{t['role'].upper()}] {t['content']}" for t in turns_clean
            )
            if count_tokens(assembled) <= config.MAX_CONTEXT_TOKENS:
                break
            turns_clean = turns_clean[2:] if len(turns_clean) > 1 else []
        return turns_clean

    def clear(self) -> None:
        self._turns = []
        self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        config.CONTEXT_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        self._persist_path.write_text(
            json.dumps(self._turns, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._dirty = False

    def load(self) -> None:
        if self._persist_path.exists():
            try:
                self._turns = json.loads(self._persist_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._turns = []
        self._dirty = False

    def context_token_count(self, n: int | None = None) -> int:
        turns = self.get_context(n)
        assembled = "\n".join(f"[{t['role'].upper()}] {t['content']}" for t in turns)
        return count_tokens(assembled)

    def __len__(self) -> int:
        return len(self._turns)
