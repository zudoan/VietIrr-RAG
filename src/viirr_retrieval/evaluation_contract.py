# -*- coding: utf-8 -*-
"""
VietIRR-RAG: Formal Two-Budget Evaluation Contract
Independent evaluation module separating Budget A (Top-K Distinct Pages)
and Budget B (Top-K Evidence Units).
"""

from typing import Any, Sequence
import math


def evaluate_budget_a_pages(
    ranked_unique_pages: Sequence[tuple[str, int]],
    target_pairs: set[tuple[str, int]],
    k: int = 5,
) -> dict[str, float]:
    """
    Evaluates Budget A: Ranking over DISTINCT (document_id, page_number) tuples.
    Input must be deduplicated distinct pages in descending order of relevance.
    """
    # Defensive deduplication while preserving order
    seen = set()
    dedup_pages: list[tuple[str, int]] = []
    for p in ranked_unique_pages:
        if p not in seen:
            seen.add(p)
            dedup_pages.append(p)

    top_k = dedup_pages[:k]

    # 1. Unique Page Hit@K
    hit_k = 1.0 if any(p in target_pairs for p in top_k) else 0.0

    # 2. Macro Page Recall@K
    if target_pairs:
        matched = sum(1.0 for p in top_k if p in target_pairs)
        recall_k = matched / len(target_pairs)
    else:
        recall_k = 0.0

    # 3. Complete Page Coverage@K (all target pages retrieved within top K)
    if target_pairs:
        coverage_k = 1.0 if all(p in top_k for p in target_pairs) else 0.0
    else:
        coverage_k = 0.0

    # 4. Page MRR (reciprocal rank of first target page in entire ranking)
    mrr = 0.0
    for rank, p in enumerate(dedup_pages, 1):
        if p in target_pairs:
            mrr = 1.0 / rank
            break

    # 5. Page nDCG@K
    dcg = 0.0
    for rank, p in enumerate(top_k, 1):
        if p in target_pairs:
            dcg += 1.0 / math.log2(rank + 1)
    idcg = sum(1.0 / math.log2(r + 1) for r in range(1, min(k, len(target_pairs)) + 1))
    ndcg_k = (dcg / idcg) if idcg > 0 else 0.0

    return {
        f"page_hit@{k}": hit_k,
        f"page_recall@{k}": recall_k,
        f"complete_coverage@{k}": coverage_k,
        "page_mrr": mrr,
        f"page_ndcg@{k}": ndcg_k,
    }


def evaluate_budget_b_evidence_units(
    delivered_units: Sequence[dict[str, Any]],
    target_pairs: set[tuple[str, int]],
    target_regions: set[str] | None = None,
    k: int = 5,
) -> dict[str, float]:
    """
    Evaluates Budget B: Top-K actual evidence units delivered to downstream generation.
    Inputs are up to K evidence unit dicts containing 'doc_id', 'page_number', 'region_id'/'evidence_id'.
    """
    units_k = delivered_units[:k]

    # 1. Region-Budget Page Hit@K: Does the delivered evidence budget contain any correct page?
    rb_page_hit = 1.0 if any((u["doc_id"], u["page_number"]) in target_pairs for u in units_k) else 0.0

    # 2. Region Hit@K: Does the delivered evidence budget contain the exact target region?
    region_hit = 0.0
    if target_regions:
        for u in units_k:
            ev_id = str(u.get("region_id") or u.get("evidence_id") or "")
            base_id = ev_id.split("_R")[0]
            if ev_id in target_regions or base_id in target_regions:
                region_hit = 1.0
                break

    # 3. Complete Evidence Set Recovery where target_regions exist
    complete_ev = 0.0
    if target_regions:
        found_regs = set()
        for u in units_k:
            ev_id = str(u.get("region_id") or u.get("evidence_id") or "")
            base_id = ev_id.split("_R")[0]
            if ev_id in target_regions:
                found_regs.add(ev_id)
            elif base_id in target_regions:
                found_regs.add(base_id)
        complete_ev = 1.0 if len(found_regs) == len(target_regions) else 0.0

    return {
        f"region_budget_page_hit@{k}": rb_page_hit,
        f"region_hit@{k}": region_hit,
        f"complete_evidence_recovery@{k}": complete_ev,
    }
