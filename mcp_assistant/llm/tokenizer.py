from __future__ import annotations


def count_tokens(text: str) -> int:
    """Estimate token count using tiktoken when available, else char/4."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4) if text else 0
