from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from viirr_retrieval.c11 import (
    _evidence_time_keys,
    _provenance_score_v2,
    build_evidence_representation,
    extract_question_requirements_v2,
    load_c11_dev,
    set_aware_v2,
)
from viirr_retrieval.io_utils import read_jsonl


ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = {
    "base_relevance": 0.65,
    "unmet_requirement": 0.25,
    "provenance_compatibility": 0.1,
    "redundancy_penalty": 0.1,
}


def _unit(item_id: str, doc: str = "D1", page: str = "P1", text: str = "") -> dict:
    return {"evidence_id": item_id, "doc_id": doc, "page_id": page, "page_number": 1,
            "unit_type": "TEXT_REGION", "index_text": text}


def _result(item_id: str, score: float, rank: int, doc: str = "D1", page: str = "P1") -> dict:
    return {"evidence_id": item_id, "score": score, "rank": rank, "doc_id": doc,
            "page_id": page, "page_number": 1, "unit_type": "TEXT_REGION"}


def _representation(item_id: str, roles: list[str], times: list[dict] | str = "UNKNOWN",
                    doc: str = "D1", page: str = "P1") -> dict:
    return {
        "evidence_id": item_id, "doc_id": doc, "page_id": page, "evidence_roles": roles,
        "evidence_time": times, "document_reporting_time": "UNKNOWN",
        "structured_query_overlap": 0.0, "metadata_known": True,
        "content_tokens": [item_id.casefold()],
    }


def test_candidate_test_cannot_be_loaded():
    with pytest.raises(ValueError, match="DEV-only"):
        load_c11_dev(ROOT, "candidate_test")


def test_date_alone_is_not_temporal_comparison():
    prediction = extract_question_requirements_v2(
        "Theo bản tin ngày 06/10, mực nước hồ A là bao nhiêu?"
    )
    assert prediction["requirements"] == ["VALUE"]


def test_explicit_change_is_temporal_comparison():
    prediction = extract_question_requirements_v2(
        "Mực nước hồ A thay đổi thế nào giữa ngày 05/10 và 06/10?"
    )
    assert "TEMPORAL_COMPARISON" in prediction["requirements"]


def test_forecast_document_mention_is_not_forecast_intent():
    prediction = extract_question_requirements_v2(
        "Theo bản tin dự báo ngày 06/10, mực nước hồ A là bao nhiêu?"
    )
    assert "VALUE" in prediction["requirements"]
    assert "FORECAST" not in prediction["requirements"]


def test_explicit_forecast_predicate_is_detected():
    prediction = extract_question_requirements_v2(
        "Mực nước hồ A được dự báo sẽ tăng như thế nào?"
    )
    assert "FORECAST" in prediction["requirements"]


def test_value_and_recommendation_are_separate_components():
    prediction = extract_question_requirements_v2(
        "Mực nước hồ A là bao nhiêu và có khuyến nghị gì?"
    )
    assert prediction["requirements"] == ["VALUE", "RECOMMENDATION"]
    assert prediction["component_count"] == 2


def test_no_explicit_intent_abstains():
    prediction = extract_question_requirements_v2("Thông tin liên quan đến hồ A?")
    assert prediction["status"] == "UNCERTAIN"
    assert prediction["requirements"] == []


def test_structured_table_mapping_keeps_report_and_evidence_time_distinct():
    candidate = "T1"
    units = {candidate: {**_unit(candidate), "unit_type": "TABLE_REGION"}}
    tables = {candidate: {
        "table_id": candidate, "doc_id": "D1", "page_id": "P1",
        "semantic_tuples": [{
            "tuple_id": "X", "entity": {"raw": "Hồ A", "canonical": "ho a"},
            "metric": {"raw": "Mực nước", "canonical": "WaterLevel"},
            "value": {"raw": "12", "normalized": "12"},
            "unit": {"raw": "m", "normalized": "m"},
            "time": {"raw": "05/10/2025", "normalized_start": "2025-10-05",
                     "normalized_end": "2025-10-05", "period_type": "DAY"},
        }],
    }}
    documents = {"D1": {"doc_id": "D1", "document_reporting_period": {
        "raw": "06/10/2025", "normalized_start": "2025-10-06", "normalized_end": "2025-10-06"
    }}}
    representation = build_evidence_representation(
        "Mực nước hồ A là bao nhiêu?", candidate, units, tables, {}, documents,
    )
    assert representation["entity"] != "UNKNOWN"
    assert representation["metric"] != "UNKNOWN"
    assert "MEASUREMENT" in representation["evidence_roles"]
    assert representation["evidence_time"][0]["start"] == "2025-10-05"
    assert representation["document_reporting_time"]["normalized_start"] == "2025-10-06"
    assert representation["metadata_basis"]["report_date_used_as_evidence_date"] is False


def test_missing_text_entity_metric_remain_unknown():
    units = {"R": _unit("R", text="Thông báo vận hành")}
    regions = {"R": {"region_id": "R", "region_type": "PARAGRAPH"}}
    representation = build_evidence_representation(
        "Thông tin gì?", "R", units, {}, regions, {"D1": {"doc_id": "D1"}},
    )
    assert representation["entity"] == "UNKNOWN"
    assert representation["metric"] == "UNKNOWN"
    assert representation["evidence_time"] == "UNKNOWN"


def test_uncertain_prediction_falls_back_exactly_to_e0():
    candidates = ["A", "B"]
    base = [_result("A", 2.0, 1), _result("B", 1.0, 2)]
    reps = {item_id: _representation(item_id, ["UNKNOWN"]) for item_id in candidates}
    selected, trace = set_aware_v2("Thông tin về hồ A?", candidates, base, reps, WEIGHTS, 2)
    assert [row["evidence_id"] for row in selected] == candidates
    assert trace["fallback_to_e0"] is True


def test_reporting_dates_do_not_satisfy_temporal_requirement():
    representation = _representation("A", ["MEASUREMENT"])
    representation["document_reporting_time"] = {"normalized_start": "2025-10-05"}
    assert _evidence_time_keys(representation) == set()


def test_cross_document_comparison_is_allowed():
    candidate = _representation("B", ["MEASUREMENT"], [
        {"start": "2025-10-06", "end": "2025-10-06", "raw": "06/10/2025"}
    ], doc="D2", page="P2")
    selected = [_representation("A", ["MEASUREMENT"], [
        {"start": "2025-10-05", "end": "2025-10-05", "raw": "05/10/2025"}
    ], doc="D1", page="P1")]
    score, decisions = _provenance_score_v2(
        "Theo chuỗi tài liệu, mực nước thay đổi thế nào?", candidate, selected,
        {"2025-10-05"}, ["TEMPORAL_COMPARISON"],
    )
    assert score > 0
    assert "CROSS_DOCUMENT_ALLOWED_BY_QUESTION" in decisions


def test_one_region_with_multiple_values_remains_one_selected_id():
    candidates = ["T", "X"]
    base = [_result("T", 2.0, 1), _result("X", 1.0, 2)]
    reps = {
        "T": _representation("T", ["MEASUREMENT"], [
            {"start": "2025-10-05"}, {"start": "2025-10-06"},
        ]),
        "X": _representation("X", ["UNKNOWN"]),
    }
    selected, _ = set_aware_v2(
        "Mực nước thay đổi thế nào và là bao nhiêu?", candidates, base, reps, WEIGHTS, 2,
    )
    ids = [row["evidence_id"] for row in selected]
    assert len(ids) == len(set(ids))
    assert ids.count("T") == 1


def test_selector_is_deterministic_and_has_no_leakage_parameters():
    forbidden = {"gold", "answer", "relation_type", "supporting_evidence_ids"}
    assert not forbidden.intersection(inspect.signature(set_aware_v2).parameters)
    candidates = ["A", "B"]
    base = [_result("A", 2.0, 1), _result("B", 1.0, 2)]
    reps = {"A": _representation("A", ["MEASUREMENT"]),
            "B": _representation("B", ["MEASUREMENT"])}
    args = ("Mực nước là bao nhiêu?", candidates, base, reps, WEIGHTS, 2)
    assert set_aware_v2(*args) == set_aware_v2(*args)


def test_verified_sources_share_g0_candidates():
    e0 = {row["qa_id"]: row for row in read_jsonl(ROOT / "outputs/C1/rankings/e0_g0_global_rrf_dev.jsonl")}
    e2 = {row["qa_id"]: row for row in read_jsonl(ROOT / "outputs/C1/rankings/e2_g0_cross_encoder_dev.jsonl")}
    e3 = {row["qa_id"]: row for row in read_jsonl(ROOT / "outputs/C1/rankings/e3_g0_set_aware_dev.jsonl")}
    assert len(e0) == 93
    assert all(e0[qa_id]["candidate_ids"] == e2[qa_id]["candidate_ids"] == e3[qa_id]["candidate_ids"]
               for qa_id in e0)

