from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest

from viirr_retrieval.io_utils import read_jsonl
from viirr_retrieval.r1 import (
    build_retrieval_representations,
    load_r1_dev,
    make_token_windows,
    max_pool_window_scores,
    serialize_table,
)


ROOT = Path(__file__).resolve().parents[1]


class CharacterTokenizer:
    def __call__(self, text, add_special_tokens=True, truncation=False):
        ids = [ord(char) for char in text]
        if add_special_tokens:
            ids = [1] + ids + [2]
        return {"input_ids": ids}

    def decode(self, ids, skip_special_tokens=True, clean_up_tokenization_spaces=False):
        return "".join(chr(value) for value in ids if value > 2)


def synthetic_structure():
    return {
        "documents": {"DOC": {"doc_id": "DOC", "title": "Verified title"}},
        "regions": {"REG": {
            "region_id": "REG", "page_id": "PAGE", "section_id": "SEC",
            "reading_order": 2, "region_type": "PARAGRAPH",
        }},
        "tables": {"TAB": {
            "table_id": "TAB", "caption": "Verified caption", "headers": ["H1", "H2"],
            "row_labels": ["A"], "rows": [["A", "12"]],
            "semantic_tuples": [{"unit": {"raw": "m"}}],
        }},
        "pages": {},
        "sections": {"SEC": {"section_id": "SEC", "section_title": "Verified section", "parent_section": None}},
        "page_sections": {"PAGE": "SEC"},
        "headings_by_page": {"PAGE": [{
            "reading_order": 1, "normalized_text": "Verified heading",
        }]},
    }


def synthetic_units():
    return [
        {"evidence_id": "REG", "doc_id": "DOC", "page_id": "PAGE", "page_number": 1,
         "unit_type": "TEXT_REGION", "index_text": "Original paragraph."},
        {"evidence_id": "TAB", "doc_id": "DOC", "page_id": "PAGE", "page_number": 1,
         "unit_type": "TABLE_REGION", "index_text": "Original table."},
    ]


def test_representation_builder_has_no_question_gold_or_answer_inputs():
    parameters = inspect.signature(build_retrieval_representations).parameters
    assert set(parameters) == {"units", "structure"}


def test_context_comes_from_verified_source_and_preserves_content():
    reps = build_retrieval_representations(synthetic_units(), synthetic_structure())
    row = reps["R1"][0]
    assert "Document: Verified title" in row["retrieval_text"]
    assert "Section: Verified section" in row["retrieval_text"]
    assert "Context: Verified heading" in row["retrieval_text"]
    assert row["retrieval_text"].endswith("Content: Original paragraph.")
    assert not row["gold_or_qa_used"]


def test_missing_metadata_is_omitted_not_fabricated():
    structure = synthetic_structure()
    structure["documents"] = {}
    structure["regions"] = {}
    structure["sections"] = {}
    structure["page_sections"] = {}
    structure["headings_by_page"] = {}
    row = build_retrieval_representations([synthetic_units()[0]], structure)["R1"][0]
    assert "UNKNOWN" not in row["retrieval_text"]
    assert row["retrieval_text"] == "Page: 1\nContent: Original paragraph."


def test_r2_changes_only_table_representation():
    reps = build_retrieval_representations(synthetic_units(), synthetic_structure())
    assert reps["R2"][0]["retrieval_text"] == reps["R1"][0]["retrieval_text"]
    assert reps["R2"][1]["retrieval_text"] != reps["R1"][1]["retrieval_text"]
    assert "Original table content: Original table." in reps["R2"][1]["retrieval_text"]


def test_table_serialization_uses_existing_fields_only():
    text, trace = serialize_table(synthetic_structure()["tables"]["TAB"])
    assert "Verified caption" in text and "H1 | H2" in text and "A | 12" in text
    assert trace["source_table_id"] == "TAB"
    assert trace["fallback_reason"] is None


def test_table_without_structure_falls_back():
    text, trace = serialize_table({"table_id": "TAB"})
    assert text is None
    assert trace["fallback_reason"] == "NO_VERIFIED_TABLE_STRUCTURE"


def test_windowing_maps_every_window_to_original_evidence_id():
    rows = [{"representation": "R0", "evidence_id": "E1", "retrieval_text": "a" * 20}]
    windows, metadata = make_token_windows(rows, CharacterTokenizer(), 8, 2)
    assert len(windows) > 1
    assert {row["evidence_id"] for row in windows} == {"E1"}
    assert {row["unit_index"] for row in windows} == {0}
    assert metadata["mapping_valid"]


def test_window_pooling_does_not_create_extra_evidence_units():
    scores = np.asarray([0.1, 0.8, 0.2, 0.3])
    parents = np.asarray([0, 0, 1, 1])
    pooled = max_pool_window_scores(scores, parents, 2)
    assert pooled.tolist() == pytest.approx([0.8, 0.3])


def test_evidence_ids_and_parent_mapping_are_unchanged():
    units = read_jsonl(ROOT / "data/processed/evidence_units.jsonl")
    assert len(units) == 27045
    assert len({row["evidence_id"] for row in units}) == 27045
    assert all(row["doc_id"] and row["page_id"] for row in units)


def test_candidate_test_cannot_be_selected():
    with pytest.raises(ValueError, match="DEV-only"):
        load_r1_dev(ROOT, "candidate_test")


def test_representation_is_deterministic():
    first = build_retrieval_representations(synthetic_units(), synthetic_structure())
    second = build_retrieval_representations(synthetic_units(), synthetic_structure())
    assert first == second
