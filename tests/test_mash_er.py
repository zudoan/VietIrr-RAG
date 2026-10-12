from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest

from viirr_retrieval.io_utils import read_jsonl
from viirr_retrieval.mash_er import (
    add_soft_page_prior,
    build_multiview_representations,
    dense_view_weights,
    fuse_view_scores,
    load_mash_dev,
    select_candidates,
)


ROOT = Path(__file__).resolve().parents[1]


def synthetic_units():
    return [
        {"evidence_id": "REG", "doc_id": "DOC1", "page_id": "PAGE1", "page_number": 1,
         "unit_type": "TEXT_REGION", "index_text": "Original paragraph."},
        {"evidence_id": "TAB", "doc_id": "DOC2", "page_id": "PAGE2", "page_number": 2,
         "unit_type": "TABLE_REGION", "index_text": "Original table."},
    ]


def synthetic_structure(table_quality="GOOD"):
    return {
        "documents": {
            "DOC1": {"doc_id": "DOC1", "title": "Verified title"},
            "DOC2": {"doc_id": "DOC2", "title": "Table document"},
        },
        "regions": {"REG": {
            "region_id": "REG", "page_id": "PAGE1", "section_id": "SEC",
            "reading_order": 2, "region_type": "PARAGRAPH",
        }},
        "tables": {"TAB": {
            "table_id": "TAB", "caption": "Verified caption", "headers": ["H1", "H2"],
            "row_labels": ["A"], "rows": [["A", "12"]],
            "semantic_tuples": [{"unit": {"raw": "m"}}],
            "semantic_quality": table_quality, "structural_quality": table_quality,
        }},
        "pages": {"PAGE1": {}, "PAGE2": {}},
        "sections": {"SEC": {
            "section_id": "SEC", "section_title": "Verified section", "parent_section": None,
        }},
        "page_sections": {"PAGE1": "SEC"},
        "headings_by_page": {"PAGE1": [{
            "reading_order": 1, "normalized_text": "Verified heading",
        }]},
    }


def test_representation_builder_cannot_accept_query_gold_or_answer():
    assert set(inspect.signature(build_multiview_representations).parameters) == {"units", "structure"}


def test_text_has_raw_and_verified_context_views():
    row = build_multiview_representations(synthetic_units(), synthetic_structure())[0]
    assert row["raw_view"] == "TEXT_RAW"
    assert row["raw_text"] == "Original paragraph."
    assert row["alternate_view"] == "TEXT_CONTEXT"
    assert "Document: Verified title" in row["alternate_text"]
    assert row["alternate_text"].endswith("Content: Original paragraph.")
    assert not row["gold_answer_or_qa_used"]


def test_verified_table_uses_struct_view_without_text_context():
    row = build_multiview_representations(synthetic_units(), synthetic_structure())[1]
    assert row["raw_view"] == "TABLE_RAW"
    assert row["alternate_view"] == "TABLE_STRUCT"
    assert "Verified caption" in row["alternate_text"]
    assert "H1 | H2" in row["alternate_text"]
    assert "A | 12" in row["alternate_text"]
    assert "Document:" not in row["alternate_text"]


def test_unverified_table_falls_back_to_raw():
    row = build_multiview_representations(
        synthetic_units(), synthetic_structure(table_quality="PARTIAL")
    )[1]
    assert row["alternate_view"] is None
    assert row["alternate_text"] is None
    assert row["fallback_to_raw"]
    assert row["fallback_reason"] == "TABLE_QUALITY_NOT_VERIFIED"


def test_fallback_raw_is_not_double_counted():
    raw_weight, alternate_weight = dense_view_weights(np.asarray([True, False]))
    assert raw_weight.tolist() == pytest.approx([0.5, 1.0])
    assert alternate_weight.tolist() == pytest.approx([0.5, 0.0])


def test_global_rank_rrf_and_view_normalization():
    bm25 = np.asarray([1, 2])
    raw = np.asarray([2, 1])
    alternate = np.asarray([1, 2])
    score, components = fuse_view_scores(
        bm25, raw, alternate, np.asarray([True, False]), rrf_k=60
    )
    assert score[0] == pytest.approx(1 / 61 + 0.5 / 62 + 0.5 / 61)
    assert score[1] == pytest.approx(1 / 62 + 1 / 61)
    assert components["alternate_dense"][1] == 0


def test_soft_page_prior_does_not_remove_unranked_evidence():
    base = np.asarray([0.1, 0.2])
    combined, prior = add_soft_page_prior(base, np.asarray([1, 0]), 60, 0.25)
    assert combined[0] > base[0]
    assert combined[1] == base[1]
    assert prior[1] == 0


def test_candidate_budget_unique_and_tie_break_deterministic():
    ids = np.asarray(["E3", "E1", "E2"], dtype=object)
    selected = select_candidates(np.asarray([1.0, 1.0, 1.0]), ids, 2)
    assert ids[selected].tolist() == ["E1", "E2"]
    assert len(set(ids[selected])) == 2


def test_hard_page_filter_is_explicit_but_soft_is_global():
    ids = np.asarray(["E1", "E2", "E3"], dtype=object)
    scores = np.asarray([0.1, 0.9, 0.8])
    hard = select_candidates(scores, ids, 2, np.asarray([0, 2]))
    soft = select_candidates(scores, ids, 2)
    assert ids[hard].tolist() == ["E3", "E1"]
    assert ids[soft].tolist() == ["E2", "E3"]


def test_cross_document_candidates_are_allowed():
    units = synthetic_units()
    ids = np.asarray([row["evidence_id"] for row in units], dtype=object)
    selected = select_candidates(np.asarray([0.2, 0.3]), ids, 2)
    assert {units[index]["doc_id"] for index in selected} == {"DOC1", "DOC2"}


def test_phase_a_evidence_ids_and_parent_mapping_are_unchanged():
    units = read_jsonl(ROOT / "data/processed/evidence_units.jsonl")
    assert len(units) == len({row["evidence_id"] for row in units}) == 27045
    assert sum(row["unit_type"] == "TEXT_REGION" for row in units) == 26954
    assert sum(row["unit_type"] == "TABLE_REGION" for row in units) == 91
    assert all(row["doc_id"] and row["page_id"] for row in units)


def test_candidate_test_split_cannot_be_loaded():
    with pytest.raises(ValueError, match="DEV-only"):
        load_mash_dev(ROOT, "candidate_test")


def test_representation_output_is_deterministic():
    first = build_multiview_representations(synthetic_units(), synthetic_structure())
    second = build_multiview_representations(synthetic_units(), synthetic_structure())
    assert first == second
