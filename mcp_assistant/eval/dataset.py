from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EvalItem:
    id: int
    nl_input: str
    ground_truth: dict          # {"tool": ..., "action": ..., "params": ...}
    category: str
    difficulty: str
    is_chain: bool = False
    chain_steps: list[dict] = field(default_factory=list)


def load_dataset(path: Path) -> list[EvalItem]:
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    items = []
    for entry in raw:
        items.append(EvalItem(
            id=entry["id"],
            nl_input=entry["nl_input"],
            ground_truth=entry["ground_truth"],
            category=entry["category"],
            difficulty=entry["difficulty"],
            is_chain=entry.get("is_chain", False),
            chain_steps=entry.get("chain_steps", []),
        ))
    return items
