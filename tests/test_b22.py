from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from viirr_retrieval.b22 import build_candidate_pool, load_b22_dev
from viirr_retrieval.candidate_metrics import (
    budgeted_candidate_coverage,
    final_ranking_metrics,
    raw_page_candidate_ceiling,
    validate_coverage_recall_invariant,
)
from viirr_retrieval.io_utils import read_jsonl


ROOT = Path(__file__).resolve().parents[1]


def test_candidate_pool_obeys_unique_budget_and_quota():
    page = ["P1", "P2", "P3", "P4", "P5"]
    flat = ["P3", "X1", "X2", "X3", "X4"]
    pool, meta = build_candidate_pool("S2", page, flat, 5, 0.7)
    assert len(pool) == len(set(pool)) == 5
    assert meta["page_target"] == 3
    assert pool[:3] == ["P1", "P2", "P3"]
    assert pool[3:] == ["X1", "X2"]


def test_cross_document_flat_rescue_is_not_filtered_by_doc():
    pool, _ = build_candidate_pool("S2", ["D1_E1", "D1_E2"], ["D2_E1", "D3_E1"], 4, 0.5)
    assert {"D2_E1", "D3_E1"} <= set(pool)


def test_candidate_coverage_is_independent_from_final_recall():
    gold = ["A", "B"]
    candidates = ["A", "B", "C"]
    final = ["A", "C", "B"]
    coverage = budgeted_candidate_coverage(gold, candidates, 3)
    metrics = final_ranking_metrics(gold, final, [1, 2, 3])
    assert coverage == 1.0
    assert metrics["2"]["all_recall"] == 0.0
    assert metrics["3"]["all_recall"] == 1.0
    validate_coverage_recall_invariant(coverage, metrics, [1, 2, 3], 3)


def test_final_recall_cannot_exceed_candidate_coverage():
    with pytest.raises(AssertionError):
        validate_coverage_recall_invariant(0.0, {"1": {"all_recall": 1.0}}, [1], 1)


def test_raw_page_ceiling_uses_parent_mapping():
    mapping = {"E1": "PAGE1", "E2": "PAGE2"}
    assert raw_page_candidate_ceiling(["E1", "E2"], ["PAGE1", "PAGE2"], mapping) == 1.0
    assert raw_page_candidate_ceiling(["E1", "E2"], ["PAGE1"], mapping) == 0.0


def test_candidate_test_cannot_be_loaded():
    with pytest.raises(ValueError, match="DEV-only"):
        load_b22_dev(ROOT, "candidate_test")
    source = inspect.getsource(load_b22_dev)
    assert "candidate_test.jsonl" not in source


def test_p0_p2_page_mapping_and_table_parent():
    pages = {row["page_id"] for row in read_jsonl(ROOT / "data/processed/pages.jsonl")}
    units = read_jsonl(ROOT / "data/processed/evidence_units.jsonl")
    for rep in ("p0", "p2"):
        rankings = read_jsonl(ROOT / f"outputs/B2_1/rankings/{rep}_pages_dev_top100.jsonl")
        assert len(rankings) == 93
        assert all({item["page_id"] for item in row["results"]} <= pages for row in rankings)
    tables = [row for row in units if row["unit_type"] == "TABLE_REGION"]
    assert tables and all(row["page_id"] in pages for row in tables)
