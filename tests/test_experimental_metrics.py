"""Unit tests for corrected retrieval metrics and canonical target evaluation.

Tests the actual implementation imported from scripts.experiment_validity_helpers:
- Canonical (doc_id, page_number) identity matching.
- Zero cross-document false positive page matches.
- Strict mathematical guarantee 0.0 <= nDCG <= 1.0 without clamping.
- Semicolon-separated multi-document parsing.
- Consistency: Page Hit@k == 0 <=> MRR == 0.
- Zero targets and multiple relevant document-page pairs (any-page hit vs complete coverage).
"""

from __future__ import annotations

import math
from typing import Any
import pytest

from scripts.experiment_validity_helpers import (
    evaluate_retrieval_metrics,
    parse_canonical_targets,
)


def test_cross_document_page_mismatch_rejected():
    """Page number matches but doc_id differs: must score 0 for page hit and MRR."""
    target_docs = {"DOC_CORRECT"}
    target_pairs = {("DOC_CORRECT", 24)}

    # Retrieved item has page 24 but wrong document
    retrieved = [
        {"doc_id": "DOC_WRONG", "page_number": 24},
        {"doc_id": "DOC_WRONG2", "page_number": 10},
    ]

    metrics = evaluate_retrieval_metrics(retrieved, target_docs, target_pairs, k=5)
    assert metrics["doc_hit"] == 0.0
    assert metrics["page_hit"] == 0.0
    assert metrics["mrr"] == 0.0
    assert metrics["ndcg"] == 0.0
    assert metrics["complete_coverage"] == 0.0


def test_ndcg_multiple_regions_same_page_bounded_to_one():
    """Multiple regions from the same target page must not cause nDCG > 1.0."""
    target_docs = {"DOC_A"}
    target_pairs = {("DOC_A", 24)}

    # Top 3 are all from the same target page
    retrieved = [
        {"doc_id": "DOC_A", "page_number": 24},
        {"doc_id": "DOC_A", "page_number": 24},
        {"doc_id": "DOC_A", "page_number": 24},
        {"doc_id": "DOC_B", "page_number": 1},
        {"doc_id": "DOC_C", "page_number": 2},
    ]

    metrics = evaluate_retrieval_metrics(retrieved, target_docs, target_pairs, k=5)
    assert metrics["page_hit"] == 1.0
    assert metrics["mrr"] == 1.0
    assert metrics["ndcg"] == 1.0  # Exactly 1.0, NOT > 1.0
    assert metrics["complete_coverage"] == 1.0


def test_multi_document_semicolon_parsing():
    """Verify parsing and evaluation of multi-document targets like V44-QA-004."""
    doc_str = "IRR_CTL_2025_57989573; IRR_CTL_2025_c3d033a0"
    page_str = "Page 2; Page 2"

    docs, pairs = parse_canonical_targets(doc_str, page_str)
    assert docs == {"IRR_CTL_2025_57989573", "IRR_CTL_2025_c3d033a0"}
    assert pairs == {("IRR_CTL_2025_57989573", 2), ("IRR_CTL_2025_c3d033a0", 2)}

    # Case A: Retrieve first doc's page at rank 1, second doc's page at rank 3
    retrieved = [
        {"doc_id": "IRR_CTL_2025_57989573", "page_number": 2},
        {"doc_id": "OTHER_DOC", "page_number": 10},
        {"doc_id": "IRR_CTL_2025_c3d033a0", "page_number": 2},
    ]

    metrics = evaluate_retrieval_metrics(retrieved, docs, pairs, k=5)
    assert metrics["doc_hit"] == 1.0
    assert metrics["page_hit"] == 1.0
    assert metrics["mrr"] == 1.0
    assert metrics["complete_coverage"] == 1.0  # Both pages retrieved
    assert 0.0 < metrics["ndcg"] <= 1.0

    # Theoretical check: DCG = 1/log2(2) + 1/log2(4) = 1.0 + 0.5 = 1.5
    # IDCG (2 items) = 1/log2(2) + 1/log2(3) = 1.0 + 0.6309 = 1.6309
    expected_ndcg = 1.5 / (1.0 + 1.0 / math.log2(3))
    assert abs(metrics["ndcg"] - expected_ndcg) < 1e-4


def test_mrr_and_page_hit_exact_consistency():
    """Page Hit@5 == 0 must strictly imply MRR == 0."""
    target_docs = {"DOC_X"}
    target_pairs = {("DOC_X", 5)}

    retrieved_miss = [
        {"doc_id": "DOC_X", "page_number": 4},
        {"doc_id": "DOC_Y", "page_number": 5},
    ]
    m_miss = evaluate_retrieval_metrics(retrieved_miss, target_docs, target_pairs, k=5)
    assert m_miss["page_hit"] == 0.0
    assert m_miss["mrr"] == 0.0

    retrieved_hit = [
        {"doc_id": "OTHER", "page_number": 1},
        {"doc_id": "DOC_X", "page_number": 5},
    ]
    m_hit = evaluate_retrieval_metrics(retrieved_hit, target_docs, target_pairs, k=5)
    assert m_hit["page_hit"] == 1.0
    assert m_hit["mrr"] == 0.5


def test_zero_and_empty_relevant_targets():
    """Zero relevant targets must produce well-defined 0.0 metrics without ZeroDivisionError."""
    empty_docs: set[str] = set()
    empty_pairs: set[tuple[str, int]] = set()

    retrieved = [
        {"doc_id": "DOC_A", "page_number": 1},
        {"doc_id": "DOC_B", "page_number": 2},
    ]

    metrics = evaluate_retrieval_metrics(retrieved, empty_docs, empty_pairs, k=5)
    assert metrics["doc_hit"] == 0.0
    assert metrics["page_hit"] == 0.0
    assert metrics["complete_coverage"] == 0.0
    assert metrics["mrr"] == 0.0
    assert metrics["ndcg"] == 0.0


def test_any_page_hit_vs_complete_multi_page_coverage():
    """Distinguish any-page hit (Hit@k=1.0) from complete multi-page coverage (e.g. 50%)."""
    docs = {"DOC_MULTI"}
    # 2 target pages: Page 1 and Page 4
    pairs = {("DOC_MULTI", 1), ("DOC_MULTI", 4)}

    # Retrieved only Page 1 (Page 4 is missing)
    retrieved = [
        {"doc_id": "DOC_MULTI", "page_number": 1},
        {"doc_id": "DOC_UNRELATED", "page_number": 10},
    ]

    metrics = evaluate_retrieval_metrics(retrieved, docs, pairs, k=5)
    assert metrics["doc_hit"] == 1.0
    assert metrics["page_hit"] == 1.0  # At least one page hit
    assert metrics["complete_coverage"] == 0.5  # Only 1 of 2 pages retrieved (50%)
    assert metrics["mrr"] == 1.0
    assert 0.0 < metrics["ndcg"] < 1.0  # Partial relevance
