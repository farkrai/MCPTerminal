from __future__ import annotations
import json
from pathlib import Path
from mcp_assistant import config


class ConversationBuffer:
    def __init__(self, max_turns: int = config.CONTEXT_WINDOW_SIZE) -> None:
        self._max_turns = max_turns
        self._turns: list[dict] = []
        self._persist_path = config.CONTEXT_PERSIST_DIR / "context.json"

    def add_turn(self, role: str, content: str, call: dict | None = None) -> None:
        self._turns.append({"role": role, "content": content, "call": call})
        # Keep only last max_turns pairs (user + assistant = 2 per exchange)
        if len(self._turns) > self._max_turns * 2:
            self._turns = self._turns[-(self._max_turns * 2):]

    def get_context(self, n: int | None = None) -> list[dict]:
        turns = self._turns
        if n is not None:
            turns = turns[-(n * 2):]
        # Strip internal 'call' field before passing to prompt builder
        return [{"role": t["role"], "content": t["content"]} for t in turns]

    def clear(self) -> None:
        self._turns = []

    def save(self) -> None:
        config.CONTEXT_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        self._persist_path.write_text(
            json.dumps(self._turns, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load(self) -> None:
        if self._persist_path.exists():
            try:
                self._turns = json.loads(self._persist_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._turns = []

    def __len__(self) -> int:
        return len(self._turns)
