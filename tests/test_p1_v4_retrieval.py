from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p1", ROOT / "scripts/run_p1_v4_retrieval_analysis.py")
p1 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(p1)


def result(rank: int, page: str, doc: str = "D1") -> dict:
    return {"rank": rank, "page_id": page, "doc_id": doc, "evidence_id": f"E{rank}"}


def test_first_rank_and_target_ranks_use_evidence_budget():
    values = [result(1, "P0"), result(2, "P1"), result(3, "P1"), result(4, "P2")]
    assert p1.first_rank(values, {"P1", "P2"}, "page_id") == 2
    assert p1.target_ranks(values, {"P1", "P2", "P3"}, "page_id") == {"P1": 2, "P2": 4, "P3": None}


def test_complete_hit_is_not_any_hit():
    ranks = {"P1": 2, "P2": 30}
    assert p1.any_hit_at(ranks, 20)
    assert not p1.all_hit_at(ranks, 20)


def test_empty_evidence_set_never_succeeds():
    assert not p1.any_hit_at({}, 20)
    assert not p1.all_hit_at({}, 20)


def test_ndcg_deduplicates_repeated_regions_from_same_page():
    values = [result(1, "P1"), result(2, "P1"), result(3, "P2")]
    score = p1.ndcg_at(values, {"P1", "P2"}, "page_id", 10)
    assert 0 < score <= 1
    assert score < 1


def test_reciprocal_rank_uses_first_evidence_rank():
    assert p1.reciprocal_rank([result(1, "P0"), result(2, "P1")], {"P1"}, "page_id") == 0.5


def test_ranking_failure_when_target_only_enters_by_top100():
    record = {"source_document_ids": ["D1"], "source_page_ids": ["P1"]}
    feature = {"risk_tags": [], "modality": "TEXT_DIGITAL"}
    metrics = {"page_all_20": False, "page_any_20": False, "page_any_100": True}
    primary, secondary, certainty, _ = p1.classify_failure(
        record, feature, "bm25", metrics, {"P1": {"raw_text": "a" * 80}}, None
    )
    assert (primary, secondary, certainty) == ("RANKING_FAILURE", "", "HIGH")


def test_page_pruning_requires_flat_hybrid_counterfactual():
    record = {"source_document_ids": ["D1"], "source_page_ids": ["P1"]}
    feature = {"risk_tags": [], "modality": "TEXT_DIGITAL"}
    metrics = {"page_all_20": False, "page_any_20": False, "page_any_100": False}
    hybrid = {"page_any_20": True, "page_any_100": True}
    primary, _, certainty, _ = p1.classify_failure(
        record, feature, "page_region", metrics, {"P1": {"raw_text": "a" * 80}}, hybrid
    )
    assert primary == "PAGE_PRUNING_FAILURE"
    assert certainty == "HIGH"
