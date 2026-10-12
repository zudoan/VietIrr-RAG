from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from viirr_retrieval.bm25 import BM25Retriever
from viirr_retrieval.experiment import load_dev_queries
from viirr_retrieval.fusion import PageRegionRetriever, bounded_round_robin_union, reciprocal_rank_fusion
from viirr_retrieval.io_utils import read_jsonl, sha256
from viirr_retrieval.metrics import evaluate_pages, evaluate_ranking, validate_metric_invariants


ROOT = Path(__file__).resolve().parents[1]


def toy_units():
    return [
        {"evidence_id": "E1", "doc_id": "D1", "page_id": "P1", "page_number": 1,
         "unit_type": "TEXT_REGION", "index_text": "mực nước hồ chứa"},
        {"evidence_id": "E2", "doc_id": "D1", "page_id": "P2", "page_number": 2,
         "unit_type": "TABLE_REGION", "index_text": "dung tích hồ thiết kế"},
        {"evidence_id": "E3", "doc_id": "D2", "page_id": "P3", "page_number": 1,
         "unit_type": "TEXT_REGION", "index_text": "mưa và dòng chảy"},
    ]


def test_bm25_ranking_and_determinism(tmp_path):
    first = BM25Retriever(toy_units(), tmp_path / "bm25.pkl", "toy")
    ranking1 = [row.evidence_id for row in first.retrieve("mực nước", 3)]
    ranking2 = [row.evidence_id for row in first.retrieve("mực nước", 3)]
    assert ranking1 == ranking2
    assert ranking1[0] == "E1"


def test_e5_dimension_and_normalization():
    torch = pytest.importorskip("torch")
    sentence_transformers = pytest.importorskip("sentence_transformers")
    if not torch.cuda.is_available():
        pytest.skip("CUDA runtime unavailable")
    model = sentence_transformers.SentenceTransformer(
        "intfloat/multilingual-e5-large", device="cuda", local_files_only=True)
    model.max_seq_length = 512
    vector = model.encode(["query: mực nước hồ"], normalize_embeddings=True, convert_to_numpy=True)[0]
    assert vector.shape == (1024,)
    assert np.linalg.norm(vector) == pytest.approx(1.0, abs=1e-5)


def test_rrf_exact_formula_and_tie_break():
    result = reciprocal_rank_fusion([["A", "B"], ["B", "C"]], rrf_k=60)
    scores = dict(result)
    assert scores["A"] == pytest.approx(1 / 61)
    assert scores["B"] == pytest.approx(1 / 62 + 1 / 61)
    assert result[0][0] == "B"


def test_page_region_mapping_and_table_parent_page():
    pages = [{"page_id": "P1"}, {"page_id": "P2"}, {"page_id": "P3"}]
    retriever = PageRegionRetriever(toy_units(), pages, None, None, page_top_p=1)
    selected = retriever.candidate_indexes(["P2"])
    assert selected.tolist() == [1]
    assert toy_units()[selected[0]]["unit_type"] == "TABLE_REGION"
    assert toy_units()[selected[0]]["page_id"] == "P2"


def test_retrieval_gold_mapping_and_no_index_leakage():
    units = read_jsonl(ROOT / "data" / "processed" / "evidence_units.jsonl")
    dev = load_dev_queries(ROOT)
    unit_ids = {row["evidence_id"] for row in units}
    assert all(set(row["retrieval_evidence_ids"]) <= unit_ids for row in dev)
    forbidden = {"question", "answer", "gold_evidence", "retrieval_evidence_ids", "answer_evidence_ids"}
    assert all(not (forbidden & set(row)) for row in units)


def test_multi_evidence_metrics_and_invariants():
    metric = evaluate_ranking(["A", "B"], ["A", "C", "B"], [1, 2, 3])
    assert metric["1"]["any_recall"] == 1
    assert metric["1"]["all_recall"] == 0
    assert metric["3"]["all_recall"] == 1
    validate_metric_invariants(metric, [1, 2, 3])


def test_complete_page_recall():
    metric = evaluate_pages(["P1", "P3"], ["P1", "P2", "P3"], [1, 3])
    assert metric["1"]["any_gold_page_recall"] == 1
    assert metric["1"]["complete_gold_page_recall"] == 0
    assert metric["3"]["complete_gold_page_recall"] == 1


def test_cross_document_gold_is_not_collapsed():
    units = {row["evidence_id"]: row for row in read_jsonl(ROOT / "data" / "processed" / "evidence_units.jsonl")}
    dev = load_dev_queries(ROOT)
    cross = next(row for row in dev if row["location_type"] == "CROSS_DOCUMENT")
    assert len({units[eid]["doc_id"] for eid in cross["retrieval_evidence_ids"]}) >= 2


def test_candidate_union_deduplicates_and_obeys_budget():
    result = bounded_round_robin_union([["A", "B", "C"], ["A", "D", "E"]], 4)
    assert result == ["A", "B", "D", "C"]
    assert len(result) == len(set(result)) == 4


def test_candidate_test_cannot_be_loaded_by_b2_default_path():
    with pytest.raises(ValueError, match="sealed to DEV"):
        load_dev_queries(ROOT, split="candidate_test")


def test_b1_counts_and_candidate_hash_is_stable():
    report = json.loads((ROOT / "reports" / "B1_INTEGRITY.json").read_text(encoding="utf-8"))
    assert report["B1_INTEGRITY"] == "PASS"
    assert report["counts"]["indexable_evidence_units"] == 27045
    candidate = ROOT / "data" / "benchmark" / "candidate_test.jsonl"
    assert sha256(candidate) == sha256(ROOT / "data" / "v3_2_final_semantic" / "candidate_test.jsonl")

