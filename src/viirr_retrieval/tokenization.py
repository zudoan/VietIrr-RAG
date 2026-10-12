from __future__ import annotations

import re
import unicodedata


TOKEN_PATTERN = re.compile(r"[^\W_]+(?:[./_-][^\W_]+)*", flags=re.UNICODE)


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFC", str(text or "")).casefold()


def tokenize(text: str) -> list[str]:
    """Deterministic Unicode-aware tokenization; accents and numbers are retained."""
    return TOKEN_PATTERN.findall(normalize_text(text))

