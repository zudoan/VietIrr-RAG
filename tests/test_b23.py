from __future__ import annotations

import inspect
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from viirr_retrieval.b23 import (
    global_rrf_scores,
    load_b23_dev,
    normalize_modality,
    rank_global_rrf,
    reranker_pairs,
    subgroup_labels,
)
from viirr_retrieval.io_utils import read_jsonl


ROOT = Path(__file__).resolve().parents[1]


def test_modality_mapping_is_exhaustive_and_exclusive_on_dev():
    dev = load_b23_dev(ROOT)
    mapped = [normalize_modality(qa) for qa in dev]
    assert len(mapped) == 93
    assert Counter(mapped) == {
        "TEXT_ONLY": 29, "TABLE_ONLY": 39, "TEXT_TABLE": 22, "TABLE_TABLE": 3,
    }
    assert all(len(set(subgroup_labels(qa)) & {"TEXT_ONLY", "TABLE_ONLY", "TEXT_TABLE", "TABLE_TABLE"}) == 1
               for qa in dev)


def test_modality_does_not_guess_from_question():
    with pytest.raises(ValueError):
        normalize_modality({"qa_id": "Q", "question": "bảng table text"})


def test_global_rrf_exact_formula():
    bm25_ranks = np.asarray([1, 4, 0], dtype=np.int32)
    dense_ranks = np.asarray([3, 2, 8], dtype=np.int32)
    scores = global_rrf_scores(np.asarray([0, 1, 2]), bm25_ranks, dense_ranks, 60)
    assert scores[0] == pytest.approx(1 / 61 + 1 / 63)
    assert scores[1] == pytest.approx(1 / 64 + 1 / 62)
    assert scores[2] == pytest.approx(1 / 68)


def test_global_tie_break_is_evidence_id():
    ids = np.asarray(["B", "A"], dtype=object)
    mapping = {"B": 0, "A": 1}
    ranks = np.asarray([1, 1], dtype=np.int32)
    indexes, scores = rank_global_rrf(["B", "A"], mapping, ids, ranks, ranks, 60)
    assert ids[indexes].tolist() == ["A", "B"]
    assert scores[0] == scores[1]


def test_local_and_global_rank_are_distinct():
    global_ranks = np.asarray([1, 100], dtype=np.int32)
    global_scores = global_rrf_scores(np.asarray([0, 1]), global_ranks, global_ranks, 60)
    local_scores = np.asarray([2 / 61, 2 / 62])
    assert not np.allclose(global_scores, local_scores)


def test_reranker_input_has_no_gold_or_answer():
    units = {"E": {"index_text": "source evidence"}}
    questions, passages = reranker_pairs("source question", ["E"], units)
    assert questions == ["source question"]
    assert passages == ["source evidence"]
    assert "gold" not in inspect.signature(reranker_pairs).parameters
    assert "answer" not in inspect.signature(reranker_pairs).parameters


def test_candidate_test_cannot_be_loaded():
    with pytest.raises(ValueError, match="DEV-only"):
        load_b23_dev(ROOT, "candidate_test")


def test_b100_candidate_pool_is_unique_and_locked():
    rows = read_jsonl(ROOT / "outputs/B2_2/rankings/p0_s1_b100_dev.jsonl")
    assert len(rows) == 93
    assert all(len(row["candidate_ids"]) == len(set(row["candidate_ids"])) <= 100 for row in rows)
