"""Experimental query-aware CE window builders (R6.1-B).

The builders are deliberately independent of gold labels and are only selected
when ``window_strategy`` is set explicitly.  The runtime default remains the
historical R6 builder in :mod:`high_perf_retriever`.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from viirr_retrieval.ontology_query_guide import normalize_vietnamese
from viirr_retrieval.table_aware import is_table_unit


def _tokens(value: str) -> set[str]:
    return {t for t in re.findall(r"\w+", normalize_vietnamese(value)) if len(t) > 1}


def _score(query: str, unit: dict[str, Any]) -> int:
    """Stable lexical/technical score; no benchmark metadata is consulted."""
    q = _tokens(query)
    text = str(unit.get("raw_text") or unit.get("index_text") or "")
    overlap = len(q & _tokens(text))
    # Exact multi-token names/parameters are more useful than a bag of words.
    phrase_bonus = sum(2 for phrase in ("muc nuoc", "dung tich", "luu luong", "cao trinh")
                       if phrase in normalize_vietnamese(query) and phrase in normalize_vietnamese(text))
    return overlap + phrase_bonus


def _bounded_text(header: str, body: list[str], char_budget: int) -> str:
    prefix = header + "\n"
    remaining = max(0, char_budget - len(prefix))
    pieces: list[str] = []
    for text in body:
        if remaining <= 0:
            break
        clipped = text[:remaining]
        pieces.append(clipped)
        remaining -= len(clipped) + 1
    return prefix + "\n".join(pieces)


def build_query_aware_windows(
    *,
    page: dict[str, Any],
    units: list[dict[str, Any]],
    unit_indices: list[int],
    query: str,
    strategy: str,
    header: str,
    table_renderer: Callable[[dict[str, Any]], str] | None = None,
) -> list[dict[str, Any]]:
    """Build one W1 passage or two W2 non-overlapping windows per page.

    Every returned window carries source unit indices.  W1 uses one 1,800
    character window; W2 splits the same total character budget across at most
    two windows, so W2's higher CE-call count is explicit rather than hidden.
    """
    if strategy not in {"query_passage", "query_multi"}:
        raise ValueError(f"Unsupported experimental strategy: {strategy}")
    pid = str(page["page_id"])
    if not unit_indices:
        raw = str(page.get("raw_text") or page.get("index_text") or "")
        return [{"window_id": f"{pid}_WQFallback", "text": _bounded_text(header, [raw], 1800), "unit_indices": []}]

    ranked = sorted(unit_indices, key=lambda idx: (-_score(query, units[idx]), idx))

    def make_window(anchor: int, window_no: int, budget: int) -> dict[str, Any]:
        # Neighbouring evidence preserves local sentence/row context.
        position = unit_indices.index(anchor)
        related = [i for i in (position - 1, position, position + 1) if 0 <= i < len(unit_indices)]
        selected = [unit_indices[i] for i in related]
        rendered: list[str] = []
        for idx in selected:
            unit = units[idx]
            raw = (table_renderer(unit) if is_table_unit(unit) and table_renderer else
                   str(unit.get("raw_text") or unit.get("index_text") or ""))
            label = "[TABLE] " if is_table_unit(unit) else ""
            rendered.append(label + raw.strip())
        return {
            "window_id": f"{pid}_WQ{window_no}_U{anchor}",
            "text": _bounded_text(header, rendered, budget),
            "unit_indices": selected,
            "anchor_unit_index": anchor,
            "strategy": strategy,
        }

    first = ranked[0]
    if strategy == "query_passage":
        return [make_window(first, 1, 1800)]

    # A second anchor must not reuse the first anchor's local neighbourhood.
    first_pos = unit_indices.index(first)
    forbidden = set(unit_indices[max(0, first_pos - 1): first_pos + 2])
    second = next((idx for idx in ranked if idx not in forbidden), None)
    result = [make_window(first, 1, 900)]
    if second is not None:
        result.append(make_window(second, 2, 900))
    return result
