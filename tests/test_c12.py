from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from viirr_retrieval.c12 import (
    build_evidence_representation_v3,
    extract_question_requirements_v3,
    load_c12_dev,
)
from viirr_retrieval.io_utils import read_jsonl, sha256


ROOT = Path(__file__).resolve().parents[1]


def fixture_maps(time=None, tuples=True):
    evidence_id = "TAB_DOC_A_P0001_01"
    unit = {
        evidence_id: {
            "evidence_id": evidence_id, "doc_id": "DOC_A", "page_id": "PAGE_A_1",
            "unit_type": "TABLE_REGION", "index_text": "Mực nước hồ A là 12 m",
        }
    }
    semantic_tuples = []
    if tuples:
        semantic_tuples = [{
            "tuple_id": "T1", "entity": {"raw": "Hồ A", "canonical": "ho a"},
            "metric": {"raw": "Mực nước", "canonical": "water_level"},
            "value": {"raw": "12", "normalized": "12"},
            "unit": {"raw": "m", "normalized": "m"},
            "time": time if time is not None else {},
        }]
    tables = {evidence_id: {"table_id": evidence_id, "semantic_tuples": semantic_tuples}}
    documents = {"DOC_A": {"doc_id": "DOC_A", "document_reporting_period": {
        "raw_period": "Ngày 06/10/2025", "normalized_start": "2025-10-06",
        "normalized_end": "2025-10-06", "period_type": "EXPLICIT_DATE",
    }}}
    return evidence_id, unit, tables, {}, documents


def build(time=None, tuples=True):
    evidence_id, units, tables, regions, documents = fixture_maps(time, tuples)
    return build_evidence_representation_v3(
        "Mực nước hồ A là bao nhiêu?", evidence_id, units, tables, regions, documents,
    )


def test_temporal_comparison_is_not_reference_comparison():
    temporal = extract_question_requirements_v3(
        "So sánh mực nước ngày 05/10 với ngày 06/10."
    )
    reference = extract_question_requirements_v3(
        "Mực nước hiện tại bằng bao nhiêu phần trăm so với thiết kế?"
    )
    assert "TEMPORAL_COMPARISON" in temporal["requirements"]
    assert "REFERENCE_COMPARISON" not in temporal["requirements"]
    assert "REFERENCE_COMPARISON" in reference["requirements"]
    assert "TEMPORAL_COMPARISON" not in reference["requirements"]


def test_reporting_time_is_not_evidence_time():
    row = build(time={})
    assert row["document_reporting_time"] != "UNKNOWN"
    assert row["evidence_time"] == "UNKNOWN"
    assert not row["reporting_time_used_as_evidence_time"]


@pytest.mark.parametrize("time", [{}, {"raw": None}, {"period_type": "UNKNOWN"}])
def test_empty_time_objects_are_missing(time):
    row = build(time=time)
    assert row["evidence_time"] == "UNKNOWN"
    assert row["field_validity"]["evidence_time"]["status"] == "MISSING"


def test_real_time_is_preserved_from_source():
    row = build(time={
        "raw": "05/10/2025", "normalized_start": "2025-10-05",
        "normalized_end": "2025-10-05", "period_type": "EXPLICIT_DATE",
    })
    assert row["evidence_time"][0]["raw"] == "05/10/2025"
    assert row["evidence_time"][0]["start"] == "2025-10-05"


def test_region_type_does_not_make_structured_metadata_complete():
    evidence_id = "REG_DOC_A_P0001_B001"
    units = {evidence_id: {
        "evidence_id": evidence_id, "doc_id": "DOC_A", "page_id": "PAGE_A_1",
        "unit_type": "TEXT_REGION", "index_text": "Thông báo chung.",
    }}
    regions = {evidence_id: {"region_id": evidence_id, "region_type": "PARAGRAPH"}}
    row = build_evidence_representation_v3("Thông báo gì?", evidence_id, units, {}, regions, {}, [])
    assert row["region_type"] == "PARAGRAPH"
    assert row["structured_metadata_validity"] == "MISSING"


def test_missing_fields_are_not_invented():
    row = build(tuples=False)
    assert row["entity"] == "UNKNOWN"
    assert row["metric"] == "UNKNOWN"
    assert row["value_unit"] == "UNKNOWN"
    assert row["forecast_time"] == "UNKNOWN"
    assert row["reference_value"] == "UNKNOWN"


def test_cross_document_representations_are_allowed():
    evidence_id, units, tables, regions, documents = fixture_maps()
    second = "TAB_DOC_B_P0001_01"
    units[second] = dict(units[evidence_id], evidence_id=second, doc_id="DOC_B", page_id="PAGE_B_1")
    tables[second] = dict(tables[evidence_id], table_id=second)
    documents["DOC_B"] = {"doc_id": "DOC_B", "document_reporting_period": {}}
    rows = [build_evidence_representation_v3(
        "So sánh hồ A", item, units, tables, regions, documents,
    ) for item in (evidence_id, second)]
    assert {row["doc_id"] for row in rows} == {"DOC_A", "DOC_B"}


def test_multiple_table_cells_remain_one_retrieval_unit():
    evidence_id, units, tables, regions, documents = fixture_maps()
    tables[evidence_id]["semantic_tuples"] *= 3
    row = build_evidence_representation_v3(
        "Mực nước hồ A?", evidence_id, units, tables, regions, documents,
    )
    assert row["evidence_id"] == evidence_id
    assert row["metadata_basis"]["semantic_tuples_available"] == 3


def test_eight_missing_multi_qa_are_derived_from_real_g0():
    dev = read_jsonl(ROOT / "data/benchmark/dev.jsonl")
    g0 = {row["qa_id"]: row for row in read_jsonl(ROOT / "outputs/C1/candidates/g0_b100_dev.jsonl")}
    missing = [
        qa for qa in dev if qa["retrieval_multi_evidence"]
        and not set(qa["retrieval_evidence_ids"]) <= set(g0[qa["qa_id"]]["candidate_ids"])
    ]
    assert len(missing) == 8


def test_candidate_test_cannot_be_loaded_as_experiment_split():
    with pytest.raises(ValueError, match="DEV-only"):
        load_c12_dev(ROOT, "candidate_test")


def test_extractors_do_not_accept_gold_or_answer_inputs():
    parameters = inspect.signature(extract_question_requirements_v3).parameters
    assert set(parameters) == {"question"}
    representation_parameters = inspect.signature(build_evidence_representation_v3).parameters
    assert "gold" not in representation_parameters
    assert "answer" not in representation_parameters


def test_representation_is_deterministic_and_read_only():
    sources = [
        ROOT / "data/parsed/tables.jsonl", ROOT / "data/parsed/regions.jsonl",
        ROOT / "outputs/C1/candidates/g0_b100_dev.jsonl",
    ]
    before = {path: sha256(path) for path in sources}
    assert build() == build()
    assert before == {path: sha256(path) for path in sources}
