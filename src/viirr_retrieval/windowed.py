from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class PageWindow:
    window_id: str
    page_id: str
    doc_id: str
    page_number: int
    window_index: int
    token_start: int
    token_end: int
    content_token_count: int
    text: str


def sliding_spans(token_count: int, content_tokens: int = 384, overlap: int = 128) -> list[tuple[int, int]]:
    if token_count < 0:
        raise ValueError("token_count must be non-negative")
    if content_tokens <= 0 or overlap < 0 or overlap >= content_tokens:
        raise ValueError("Require content_tokens > overlap >= 0")
    if token_count == 0:
        return [(0, 0)]
    stride = content_tokens - overlap
    spans: list[tuple[int, int]] = []
    start = 0
    while start < token_count:
        end = min(start + content_tokens, token_count)
        spans.append((start, end))
        if end == token_count:
            break
        start += stride
    return spans


def build_page_windows(
    pages: list[dict[str, Any]], tokenizer: Any,
    content_tokens: int = 384, overlap: int = 128,
) -> tuple[list[PageWindow], dict[str, list[int]], dict[str, int]]:
    windows: list[PageWindow] = []
    page_to_indexes: dict[str, list[int]] = {}
    content_lengths: dict[str, int] = {}
    for page in pages:
        page_id = str(page["page_id"])
        raw = str(page.get("index_text") or page.get("raw_text") or "")
        token_ids = tokenizer.encode(raw, add_special_tokens=False)
        content_lengths[page_id] = len(token_ids)
        indexes: list[int] = []
        for window_index, (start, end) in enumerate(sliding_spans(len(token_ids), content_tokens, overlap)):
            content = tokenizer.decode(token_ids[start:end], skip_special_tokens=True)
            window = PageWindow(
                window_id=f"WIN_{page_id}_{window_index:04d}",
                page_id=page_id,
                doc_id=str(page["doc_id"]),
                page_number=int(page["page_number"]),
                window_index=window_index,
                token_start=start,
                token_end=end,
                content_token_count=end - start,
                text=content,
            )
            indexes.append(len(windows))
            windows.append(window)
        page_to_indexes[page_id] = indexes
    return windows, page_to_indexes, content_lengths


def page_max_scores(
    window_scores: np.ndarray, page_ids: list[str], page_to_indexes: dict[str, list[int]],
) -> np.ndarray:
    output = np.full(len(page_ids), -np.inf, dtype=np.float64)
    for page_index, page_id in enumerate(page_ids):
        indexes = page_to_indexes.get(page_id, [])
        if indexes:
            output[page_index] = float(np.max(window_scores[np.asarray(indexes, dtype=np.int32)]))
    return output


def rank_ids(ids: list[str], scores: np.ndarray) -> list[str]:
    if len(ids) != len(scores):
        raise ValueError("ids and scores must have equal length")
    order = np.lexsort((np.asarray(ids, dtype=object), -np.asarray(scores, dtype=np.float64)))
    return [ids[int(index)] for index in order]


def deterministic_id_hash(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()

