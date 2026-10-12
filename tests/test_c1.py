from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from viirr_retrieval.c1 import (
    _provenance_compatibility,
    _time_signatures,
    build_diverse_candidate_union,
    content_evidence_roles,
    detect_question_requirements,
    load_c1_dev,
    set_aware_select,
)
from viirr_retrieval.io_utils import read_jsonl


ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = {
    "base_relevance": 0.6,
    "unmet_requirement": 0.25,
    "provenance_compatibility": 0.1,
    "question_overlap": 0.05,
    "redundancy_penalty": 0.15,
}


def _result(item_id: str, score: float, rank: int) -> dict:
    return {"evidence_id": item_id, "score": score, "rank": rank,
            "doc_id": f"D{rank}", "page_id": f"P{rank}", "page_number": rank,
            "unit_type": "TEXT_REGION"}


def test_candidate_test_cannot_be_loaded():
    with pytest.raises(ValueError, match="DEV-only"):
        load_c1_dev(ROOT, "candidate_test")


def test_g1_fixed_quota_dedup_and_backfill_are_deterministic():
    sources = {
        "P0": [{"evidence_id": value} for value in ("A", "B", "C", "D")],
        "P2": [{"evidence_id": value} for value in ("A", "E", "F", "G")],
        "E5": [{"evidence_id": value} for value in ("B", "H", "I")],
        "BM25": [{"evidence_id": value} for value in ("C", "J", "K")],
    }
    quotas = {"P0": 4, "P2": 2, "E5": 2, "BM25": 2}
    priority = ["P0", "P2", "E5", "BM25"]
    first = build_diverse_candidate_union(sources, quotas, 10, priority)
    second = build_diverse_candidate_union(sources, quotas, 10, priority)
    assert first == second
    assert len(first[0]) == len(set(first[0])) == 10
    assert first[2]["quota_targets"] == quotas
    assert all(first[1][item_id] for item_id in first[0])


def test_generation_and_selector_signatures_have_no_gold_or_answer():
    forbidden = {"gold", "answer", "relation_type", "modality"}
    assert not forbidden.intersection(inspect.signature(build_diverse_candidate_union).parameters)
    assert not forbidden.intersection(inspect.signature(set_aware_select).parameters)


def test_requirement_detection_is_question_only_and_conservative():
    requirements = detect_question_requirements(
        "Mực nước hồ là bao nhiêu và báo cáo khuyến nghị biện pháp gì?"
    )
    assert "VALUE" in requirements
    assert "ACTION" in requirements
    assert detect_question_requirements("Thông tin về hồ A?") == []


def test_set_aware_falls_back_exactly_to_r0_when_no_requirement():
    units = {
        "A": {"evidence_id": "A", "doc_id": "D1", "page_id": "P1", "index_text": "thông tin hồ"},
        "B": {"evidence_id": "B", "doc_id": "D2", "page_id": "P2", "index_text": "tài liệu nguồn"},
    }
    base = [_result("A", 2.0, 1), _result("B", 1.0, 2)]
    selected, trace = set_aware_select("Thông tin về hồ A?", ["A", "B"], base, units, WEIGHTS, 2)
    assert [row["evidence_id"] for row in selected] == ["A", "B"]
    assert trace["fallback_to_r0"] is True


def test_set_aware_is_deterministic_unique_bounded_and_subset():
    units = {
        "A": {"evidence_id": "A", "doc_id": "D1", "page_id": "P1",
              "index_text": "Mực nước 12 m ngày 01/01/2025"},
        "B": {"evidence_id": "B", "doc_id": "D2", "page_id": "P2",
              "index_text": "Khuyến nghị biện pháp vận hành hồ"},
        "C": {"evidence_id": "C", "doc_id": "D3", "page_id": "P3",
              "index_text": "Nội dung không liên quan"},
    }
    base = [_result("A", 3.0, 1), _result("C", 2.0, 2), _result("B", 1.0, 3)]
    args = ("Mực nước bao nhiêu và khuyến nghị biện pháp gì?", ["A", "B", "C"], base, units, WEIGHTS, 2)
    first = set_aware_select(*args)
    second = set_aware_select(*args)
    assert first == second
    ids = [row["evidence_id"] for row in first[0]]
    assert len(ids) == len(set(ids)) <= 2
    assert set(ids) <= {"A", "B", "C"}
    assert set(first[1]["covered_requirements"]) <= set(first[1]["requirements"])


def test_one_table_region_covering_two_roles_is_one_retrieval_unit():
    units = {
        "T": {"evidence_id": "T", "doc_id": "D1", "page_id": "P1",
              "index_text": "Mực nước 12 m; khuyến nghị biện pháp vận hành.",
              "unit_type": "TABLE_REGION"},
        "X": {"evidence_id": "X", "doc_id": "D1", "page_id": "P1",
              "index_text": "Phụ lục", "unit_type": "TABLE_REGION"},
    }
    base = [_result("T", 2.0, 1), _result("X", 1.0, 2)]
    selected, trace = set_aware_select(
        "Mực nước bao nhiêu và khuyến nghị biện pháp gì?", ["T", "X"], base, units, WEIGHTS, 2,
    )
    assert [row["evidence_id"] for row in selected].count("T") == 1
    assert set(trace["steps"][0]["new_requirements"]) >= {"VALUE", "ACTION"}


def test_temporal_provenance_distinguishes_measurement_dates():
    assert _time_signatures("Báo cáo ngày 01/02/2025, đo ngày 31/01/2025") == {
        "01/02/2025", "31/01/2025"
    }
    candidate = {"doc_id": "D2", "page_id": "P2"}
    selected = [{"doc_id": "D1", "page_id": "P1"}]
    score = _provenance_compatibility(
        "So với ngày trước", candidate, selected, {"02/02/2025"}, {"01/02/2025"},
        ["TEMPORAL_COMPARISON"],
    )
    assert score > 0.0


def test_cross_document_candidates_are_allowed_not_hard_rejected():
    score = _provenance_compatibility(
        "Theo chuỗi tài liệu, các báo cáo lần lượt nêu gì?",
        {"doc_id": "D2", "page_id": "P2"}, [{"doc_id": "D1", "page_id": "P1"}],
        set(), set(), [],
    )
    assert 0.0 <= score <= 1.0


def test_content_roles_are_corpus_derived():
    roles = content_evidence_roles("Dự báo mực nước và đề xuất biện pháp ứng phó")
    assert {"VALUE", "FORECAST", "ACTION"} <= set(roles)


def test_dev_gold_mapping_and_locked_g0_pool():
    dev = load_c1_dev(ROOT)
    unit_ids = {row["evidence_id"] for row in read_jsonl(ROOT / "data/processed/evidence_units.jsonl")}
    assert len(dev) == 93
    assert all(set(qa["retrieval_evidence_ids"]) <= unit_ids for qa in dev)
    g0 = read_jsonl(ROOT / "outputs/B2_2/rankings/p0_s1_b100_dev.jsonl")
    e0 = {row["qa_id"]: row for row in read_jsonl(ROOT / "outputs/B2_3/rankings/m1_global_rrf_b100_dev.jsonl")}
    e2 = {row["qa_id"]: row for row in read_jsonl(ROOT / "outputs/B2_3/rankings/m2_cross_encoder_b100_dev.jsonl")}
    assert all(row["candidate_ids"] == e0[row["qa_id"]]["candidate_ids"] == e2[row["qa_id"]]["candidate_ids"]
               for row in g0)

