"""Model-aware offline token counting with an explicit fallback label."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenCount:
    value: int
    method: str
    exact_for_model: bool


def count_text(text: str, model: str | None = None) -> TokenCount:
    try:
        import tiktoken
        if model:
            try:
                encoding = tiktoken.encoding_for_model(model)
                return TokenCount(len(encoding.encode(text)), f"tiktoken:{encoding.name}", True)
            except KeyError:
                pass
        encoding = tiktoken.get_encoding("o200k_base")
        return TokenCount(len(encoding.encode(text)), "tiktoken:o200k_base:model_unmapped", False)
    except (ImportError, ValueError):
        return TokenCount((len(text.encode("utf-8")) + 3) // 4, "utf8_bytes_div_4", False)
