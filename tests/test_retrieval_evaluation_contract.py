# -*- coding: utf-8 -*-
"""
Unit tests for the independent two-budget retrieval evaluation contract.
Verifies all mandatory test cases from the Master Plan repair directive.
"""

import pytest
from viirr_retrieval.evaluation_contract import (
    evaluate_budget_a_pages,
    evaluate_budget_b_evidence_units,
)


def test_budget_a_five_distinct_pages_with_hit():
    """Top-5 contains target page at rank 1."""
    ranked_pages = [("DOC_01", 10), ("DOC_01", 11), ("DOC_02", 5), ("DOC_03", 2), ("DOC_04", 1)]
    targets = {("DOC_01", 10)}
    res = evaluate_budget_a_pages(ranked_pages, targets, k=5)
    assert res["page_hit@5"] == 1.0
    assert res["page_recall@5"] == 1.0
    assert res["complete_coverage@5"] == 1.0
    assert res["page_mrr"] == 1.0
    assert res["page_ndcg@5"] == 1.0


def test_budget_a_duplicate_page_ids_deduplication():
    """Verify that duplicate page entries do not consume distinct slots in Budget A."""
    ranked_pages = [
        ("DOC_01", 1),
        ("DOC_01", 1),  # duplicate
        ("DOC_01", 2),
        ("DOC_01", 3),
        ("DOC_01", 4),
        ("DOC_01", 5),  # 5th distinct page
    ]
    targets = {("DOC_01", 5)}
    # If duplicates were not removed, top 5 would be [p1, p1, p2, p3, p4] and p5 would be missed!
    res = evaluate_budget_a_pages(ranked_pages, targets, k=5)
    assert res["page_hit@5"] == 1.0
    assert res["page_mrr"] == 1.0 / 5


def test_budget_a_multiple_correct_pages():
    """Verify macro recall and complete coverage with multiple correct pages."""
    ranked_pages = [("DOC_01", 1), ("DOC_01", 2), ("DOC_02", 3), ("DOC_02", 4), ("DOC_03", 5)]
    targets = {("DOC_01", 1), ("DOC_01", 2), ("DOC_09", 10)}  # 2 of 3 in top 5
    res = evaluate_budget_a_pages(ranked_pages, targets, k=5)
    assert res["page_hit@5"] == 1.0
    assert pytest.approx(res["page_recall@5"], 0.01) == 2.0 / 3.0
    assert res["complete_coverage@5"] == 0.0  # incomplete coverage


def test_budget_b_five_regions_from_one_page():
    """
    Critical case: Budget B contains 5 regions all belonging to page 1.
    Budget B has page hit = 1.0, but only delivers 1 page.
    This demonstrates why Budget B must NEVER be used to compute Budget A metrics!
    """
    delivered_units = [
        {"doc_id": "DOC_01", "page_number": 1, "region_id": f"DOC_01_P001_R{i}"}
        for i in range(1, 6)
    ]
    targets = {("DOC_01", 1)}
    res_b = evaluate_budget_b_evidence_units(delivered_units, targets, k=5)
    assert res_b["region_budget_page_hit@5"] == 1.0

    # If this was a page ranking, it would only have 1 distinct page!
    distinct_pages = list(dict.fromkeys([(u["doc_id"], u["page_number"]) for u in delivered_units]))
    assert len(distinct_pages) == 1


def test_budget_b_five_regions_across_five_pages():
    """Budget B contains 5 regions spread across 5 distinct pages."""
    delivered_units = [
        {"doc_id": f"DOC_{i:02d}", "page_number": i, "region_id": f"DOC_{i:02d}_P{i:03d}_R01"}
        for i in range(1, 6)
    ]
    targets = {("DOC_03", 3)}
    res_b = evaluate_budget_b_evidence_units(delivered_units, targets, k=5)
    assert res_b["region_budget_page_hit@5"] == 1.0


def test_budget_b_correct_page_present_but_correct_region_absent():
    """Page is correct, but the delivered region is the wrong section/paragraph."""
    delivered_units = [
        {"doc_id": "DOC_01", "page_number": 10, "region_id": "DOC_01_P010_R01"},  # intro paragraph
    ]
    targets = {("DOC_01", 10)}
    target_regions = {"DOC_01_P010_TAB_01"}  # expected table block
    res_b = evaluate_budget_b_evidence_units(delivered_units, targets, target_regions, k=5)
    assert res_b["region_budget_page_hit@5"] == 1.0
    assert res_b["region_hit@5"] == 0.0  # Region is missed!


def test_budget_b_reference_cell_mapped_to_containing_table_block():
    """
    Reference region may be a base table block or table sub-region.
    'DOC_01_P010_TAB_01_R02' should match base 'DOC_01_P010_TAB_01'.
    """
    delivered_units = [
        {"doc_id": "DOC_01", "page_number": 10, "region_id": "DOC_01_P010_TAB_01_R02"}
    ]
    targets = {("DOC_01", 10)}
    target_regions = {"DOC_01_P010_TAB_01"}
    res_b = evaluate_budget_b_evidence_units(delivered_units, targets, target_regions, k=5)
    assert res_b["region_hit@5"] == 1.0


def test_strict_independence_budget_a_and_budget_b():
    """
    Assert that Budget A and Budget B can produce completely different results:
    - Page ranking contains target page at Rank 5.
    - Evidence units budget only takes regions from Top-2 pages, so it misses the target page!
    """
    # Budget A (5 distinct pages)
    ranked_pages = [("DOC_01", 1), ("DOC_02", 2), ("DOC_03", 3), ("DOC_04", 4), ("DOC_TARGET", 5)]
    targets = {("DOC_TARGET", 5)}
    res_a = evaluate_budget_a_pages(ranked_pages, targets, k=5)
    assert res_a["page_hit@5"] == 1.0

    # Budget B (5 evidence units taking 3 from page 1 and 2 from page 2)
    delivered_units = [
        {"doc_id": "DOC_01", "page_number": 1, "region_id": "R1"},
        {"doc_id": "DOC_01", "page_number": 1, "region_id": "R2"},
        {"doc_id": "DOC_01", "page_number": 1, "region_id": "R3"},
        {"doc_id": "DOC_02", "page_number": 2, "region_id": "R4"},
        {"doc_id": "DOC_02", "page_number": 2, "region_id": "R5"},
    ]
    res_b = evaluate_budget_b_evidence_units(delivered_units, targets, k=5)
    # Target page is NOT in Budget B!
    assert res_b["region_budget_page_hit@5"] == 0.0
