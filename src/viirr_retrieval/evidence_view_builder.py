"""Query-grounded, provenance-preserving evidence views for cross-encoding.

The builder never sees QA labels.  It selects authentic page regions using the
query and carries their source identifiers forward to the reranker trace.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Callable

from viirr_retrieval.ontology_query_guide import normalize_vietnamese
from viirr_retrieval.table_aware import is_table_unit


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"\w+", normalize_vietnamese(text)) if len(t) > 1}


def _unit_score(query: str, unit: dict[str, Any]) -> tuple[int, int]:
    """Stable lexical score; table units only receive a tie-breaking bonus."""
    q = _tokens(query)
    text = str(unit.get("raw_text") or unit.get("index_text") or "")
    overlap = len(q & _tokens(text))
    phrase_bonus = sum(2 for x in ("dung tich", "muc nuoc", "luu luong", "cao trinh")
                       if x in normalize_vietnamese(query) and x in normalize_vietnamese(text))
    return overlap + phrase_bonus, int(is_table_unit(unit))


def build_evidence_views(*, page: dict[str, Any], units: list[dict[str, Any]],
                         unit_indices: list[int], query: str, header: str,
                         table_renderer: Callable[[dict[str, Any]], str] | None = None,
                         char_budget: int = 1800) -> list[dict[str, Any]]:
    """Return exactly one W1 evidence view with bounded neighbour context."""
    pid = str(page["page_id"])
    if not unit_indices:
        content = (header + "\n" + str(page.get("raw_text") or page.get("index_text") or ""))[:char_budget]
        selected: list[int] = []
    else:
        ranked = sorted(unit_indices, key=lambda i: (-_unit_score(query, units[i])[0], -_unit_score(query, units[i])[1], i))
        anchor = ranked[0]
        at = unit_indices.index(anchor)
        selected = [unit_indices[i] for i in (at - 1, at, at + 1) if 0 <= i < len(unit_indices)]
        fragments = []
        for idx in selected:
            unit = units[idx]
            raw = table_renderer(unit) if is_table_unit(unit) and table_renderer else str(unit.get("raw_text") or unit.get("index_text") or "")
            prefix = "[TABLE WITH HEADER/ROW] " if is_table_unit(unit) else "[PASSAGE] "
            fragments.append(prefix + raw.strip())
        content = (header + "\n" + "\n".join(fragments))[:char_budget]
    source_ids = [str(units[i].get("evidence_id") or units[i].get("region_id") or i) for i in selected]
    return [{
        "view_id": f"{pid}_EV1", "document_id": str(page.get("doc_id") or ""), "page_id": pid,
        "evidence_ids": source_ids, "source_unit_indices": selected, "view_type": "query_aware_structured",
        "content": content, "text": content, "heading_context": header, "provenance_status": "EXTRACTED",
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "token_count": len(re.findall(r"\S+", content)),
    }]
