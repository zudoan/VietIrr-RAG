"""
Comprehensive unit tests for 3-Level retrieval metrics and provenance verification in VietIRR-RAG.

Verifies:
1. Level 1: Source Discovery
   - Unique-Page Hit@K vs Region-Budget Hit@K
   - MRR (normalized strictly in [0, 1])
   - nDCG@K (deduplicated IDCG guaranteed in [0, 1])
2. Level 2: Evidence Completeness
   - Strict Complete Coverage@K (1.0 if ALL target pages recovered)
   - Missing evidence component count
   - Exact Region Hit@K
3. Level 3: Downstream Readiness Diagnostic
   - Technical entity, parameter, value, unit, condition, and provenance integrity
"""

import math
import re
import pytest


def compute_unique_page_hit_at_k(ranked_candidates, target_pairs, k=5):
    seen_pages = []
    for cand in ranked_candidates:
        pair = (cand["doc_id"], cand["page_num"])
        if pair not in seen_pages:
            seen_pages.append(pair)
        if len(seen_pages) == k:
            break
    
    for pair in seen_pages:
        if pair in target_pairs:
            return 1.0
    return 0.0


def compute_region_budget_hit_at_k(ranked_candidates, target_pairs, k=5):
    for cand in ranked_candidates[:k]:
        pair = (cand["doc_id"], cand["page_num"])
        if pair in target_pairs:
            return 1.0
    return 0.0


def compute_mrr(ranked_candidates, target_pairs):
    for rank, cand in enumerate(ranked_candidates, start=1):
        pair = (cand["doc_id"], cand["page_num"])
        if pair in target_pairs:
            return 1.0 / rank
    return 0.0


def compute_ndcg_at_k(ranked_candidates, target_pairs, k=5):
    dcg = 0.0
    seen_correct = set()
    for rank, cand in enumerate(ranked_candidates[:k], start=1):
        pair = (cand["doc_id"], cand["page_num"])
        if pair in target_pairs and pair not in seen_correct:
            seen_correct.add(pair)
            dcg += 1.0 / math.log2(rank + 1)
            
    idcg = 0.0
    num_relevant = min(len(target_pairs), k)
    for rank in range(1, num_relevant + 1):
        idcg += 1.0 / math.log2(rank + 1)
        
    return dcg / idcg if idcg > 0 else 0.0


def compute_complete_coverage_at_k(ranked_candidates, target_pairs, k=5):
    seen_pages = set()
    for cand in ranked_candidates:
        pair = (cand["doc_id"], cand["page_num"])
        seen_pages.add(pair)
        if len(seen_pages) == k:
            break
            
    if all(pair in seen_pages for pair in target_pairs):
        return 1.0
    return 0.0


def compute_missing_components(ranked_candidates, target_pairs, k=5):
    seen_pages = set()
    for cand in ranked_candidates:
        pair = (cand["doc_id"], cand["page_num"])
        seen_pages.add(pair)
        if len(seen_pages) == k:
            break
    found = {p for p in seen_pages if p in target_pairs}
    return len(target_pairs) - len(found)


def assess_readiness(text, target_pairs, candidate_pairs):
    has_entity = any(e in text.lower() for e in ["hồ", "đập", "tả trạch", "núi cốc"])
    has_param = any(p in text.lower() for p in ["mực nước", "dung tích", "cao trình"])
    has_val = bool(re.search(r"\b\d+([.,]\d+)?\b", text))
    has_unit = any(u in text.lower() for u in ["m", "triệu m3", "m3/s"])
    has_prov = any(pair in target_pairs for pair in candidate_pairs)
    return {
        "entity": has_entity,
        "parameter": has_param,
        "value": has_val,
        "unit": has_unit,
        "provenance": has_prov,
        "overall": has_entity and has_param and has_val and has_prov
    }


# Test Cases
def test_budget_distinction():
    candidates = [
        {"doc_id": "DocA", "page_num": 1, "region_id": f"reg_{i}"} for i in range(1, 6)
    ] + [
        {"doc_id": "DocA", "page_num": 2, "region_id": "reg_target"}
    ]
    target_pairs = {("DocA", 2)}
    assert compute_region_budget_hit_at_k(candidates, target_pairs, k=5) == 0.0
    assert compute_unique_page_hit_at_k(candidates, target_pairs, k=5) == 1.0


def test_mrr_and_ndcg_normalization():
    candidates = [
        {"doc_id": "DocX", "page_num": 1, "region_id": "r1"},
        {"doc_id": "DocA", "page_num": 3, "region_id": "r2"},
        {"doc_id": "DocA", "page_num": 4, "region_id": "r3"},
    ]
    target_pairs = {("DocA", 3), ("DocA", 4)}
    mrr = compute_mrr(candidates, target_pairs)
    ndcg = compute_ndcg_at_k(candidates, target_pairs, k=5)
    assert mrr == 0.5
    assert 0.0 <= ndcg <= 1.0


def test_level2_completeness_and_missing_components():
    target_pairs = {("DocA", 1), ("DocA", 2)}
    candidates_partial = [
        {"doc_id": "DocA", "page_num": 1, "region_id": "r1"},
        {"doc_id": "DocB", "page_num": 5, "region_id": "r2"},
    ]
    assert compute_complete_coverage_at_k(candidates_partial, target_pairs, k=5) == 0.0
    assert compute_missing_components(candidates_partial, target_pairs, k=5) == 1

    candidates_complete = [
        {"doc_id": "DocA", "page_num": 1, "region_id": "r1"},
        {"doc_id": "DocA", "page_num": 2, "region_id": "r2"},
    ]
    assert compute_complete_coverage_at_k(candidates_complete, target_pairs, k=5) == 1.0
    assert compute_missing_components(candidates_complete, target_pairs, k=5) == 0


def test_level3_downstream_readiness_and_provenance():
    text = "Mực nước hồ Tả Trạch hiện tại là 35.5 m theo quy trình vận hành."
    target_pairs = {("DOC_001", 3)}
    cand_pairs = [("DOC_001", 3), ("DOC_002", 1)]
    readiness = assess_readiness(text, target_pairs, cand_pairs)
    assert readiness["entity"] is True
    assert readiness["parameter"] is True
    assert readiness["value"] is True
    assert readiness["unit"] is True
    assert readiness["provenance"] is True
    assert readiness["overall"] is True

    # Negative provenance test
    wrong_cand_pairs = [("DOC_WRONG", 1)]
    wrong_readiness = assess_readiness(text, target_pairs, wrong_cand_pairs)
    assert wrong_readiness["provenance"] is False
    assert wrong_readiness["overall"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
