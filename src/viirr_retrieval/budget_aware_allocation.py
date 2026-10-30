"""Experimental evidence allocation policies for R6.1-B (not runtime default)."""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def allocate_page_aware(
    retriever: Any, query: str, reranked_pages: list[dict[str, Any]], max_units: int = 5,
) -> list[dict[str, Any]]:
    """Soft coverage allocation: one high-scoring unit per relevant top page.

    A page is admitted only when its best region has positive lexical/structural
    score.  This avoids the invalid rule that every top-five page must consume a
    slot, while testing the rank-five evidence-loss hypothesis.
    """
    rows: list[dict[str, Any]] = []
    for page_rank, page in enumerate(reranked_pages[:5], 1):
        pid = str(page["page_id"])
        candidates = []
        for unit_idx in retriever.page_to_unit_indices.get(pid, []):
            unit = retriever.units[unit_idx]
            row = {"evidence_id": str(unit["evidence_id"]), "region_id": str(unit["evidence_id"]),
                   "doc_id": str(unit["doc_id"]), "page_id": pid, "page_number": int(unit["page_number"]),
                   "unit_type": str(unit.get("unit_type", "")),
                   "text": str(unit.get("raw_text") or unit.get("index_text") or ""), "page_rank": page_rank,
                   "page_score": float(page.get("rerank_score", 0.0))}
            row["allocated_score"] = retriever.allocator.score_region(row, query, page_rank, row["page_score"])
            candidates.append(row)
        if candidates:
            rows.append(max(candidates, key=lambda x: (x["allocated_score"], x["evidence_id"])))

    selected = [r for r in rows if r["allocated_score"] > 0]
    selected.sort(key=lambda x: (-x["allocated_score"], x["page_rank"], x["evidence_id"]))
    if len(selected) < max_units:
        baseline = retriever.allocate_budget_b_evidence(query, reranked_pages, max_units=max_units, table_aware=False)
        seen = {x["evidence_id"] for x in selected}
        for row in baseline:
            if row["evidence_id"] not in seen:
                selected.append(row); seen.add(row["evidence_id"])
            if len(selected) >= max_units:
                break
    return selected[:max_units]
