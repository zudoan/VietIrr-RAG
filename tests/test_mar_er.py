from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from viirr_retrieval.io_utils import read_jsonl
from viirr_retrieval.mar_er import (
    adaptive_relevance,
    conservative_candidates,
    constrained_rank_stable_order,
    load_mar_dev,
    rank_stability_summary,
    rank_utility,
)


ROOT = Path(__file__).resolve().parents[1]


def test_rank_utility_is_normalized_and_missing_is_zero():
    ranks = np.asarray([1, 2, 0, 100])
    utility = rank_utility(ranks, 60)
    assert utility.tolist() == pytest.approx([1.0, 61 / 62, 0.0, 61 / 160])


def test_adaptive_score_matches_frozen_formula_and_is_one_sided():
    raw, adaptive, parts = adaptive_relevance(
        np.asarray([5, 80, 1]),
        np.asarray([3, 120, 2]),
        np.asarray([2, 10, 100]),
        np.asarray([4, 0, 1]),
        np.asarray([True, True, True]),
        60,
    )
    expected_dense = 61 / 63 + max(61 / 65, 61 / 64) * (61 / 62 - 61 / 63)
    assert parts["adaptive_dense"][0] == pytest.approx(expected_dense)
    assert np.all(adaptive >= raw)
    assert parts["adaptive_contribution"][2] == 0.0


def test_invalid_alternate_fallback_never_double_counts_raw():
    raw, adaptive, parts = adaptive_relevance(
        np.asarray([1]), np.asarray([2]), np.asarray([1]), np.asarray([1]),
        np.asarray([False]), 60,
    )
    assert parts["u_alternate"][0] == 0.0
    assert parts["adaptive_contribution"][0] == 0.0
    assert adaptive[0] == pytest.approx(raw[0])


def test_conservative_candidate_recovery_retains_80_and_unique_100():
    ids = np.asarray([f"E{i:03d}" for i in range(140)], dtype=object)
    scores = np.linspace(0.0, 1.0, len(ids))
    baseline = np.arange(100, dtype=np.int32)
    sources = {
        "BASELINE": baseline,
        "GLOBAL": np.arange(40, 140, dtype=np.int32),
        "DUPLICATE_SOURCE": np.arange(40, 140, dtype=np.int32),
    }
    selected, provenance = conservative_candidates(baseline, sources, scores, ids, 100, 80)
    assert selected[:80].tolist() == list(range(80))
    assert len(selected) == len(set(selected.tolist())) == 100
    assert any(index >= 100 for index in selected)
    assert provenance[100] == ["DUPLICATE_SOURCE", "GLOBAL"]


def test_cross_document_candidate_is_not_filtered():
    ids = np.asarray([f"E{i:03d}" for i in range(101)], dtype=object)
    scores = np.zeros(101)
    scores[100] = 10.0
    baseline = np.arange(100, dtype=np.int32)
    selected, _ = conservative_candidates(
        baseline, {"BASELINE": baseline, "CROSS_DOCUMENT": np.asarray([100])},
        scores, ids, 100, 80,
    )
    assert 100 in selected


def test_rank_stability_preserves_top15_and_bounds_displacement():
    ids = np.asarray([f"E{i:03d}" for i in range(110)], dtype=object)
    baseline = np.arange(100, dtype=np.int32)
    candidates = np.asarray(list(range(95)) + list(range(100, 105)), dtype=np.int32)
    scores = np.linspace(1.0, 0.0, len(ids))
    scores[100:105] = 2.0
    order, selected = constrained_rank_stable_order(candidates, baseline, scores, ids, 20, 5)
    audit = rank_stability_summary(order, baseline, 20, 5)
    assert selected["anchors"] == list(range(15))
    assert set(selected["challengers"]) == set(range(100, 105))
    assert audit["baseline_top15_retained"] == 15
    assert audit["baseline_top20_overlap"] == 15
    assert audit["protected_relative_order_preserved"]
    assert audit["maximum_protected_downward_displacement"] == 5
    assert audit["invariants_pass"]


def test_gold_at_baseline_rank_16_is_not_falsely_guaranteed():
    ids = np.asarray([f"E{i:03d}" for i in range(110)], dtype=object)
    baseline = np.arange(100, dtype=np.int32)
    candidates = np.asarray(list(range(95)) + list(range(100, 105)), dtype=np.int32)
    scores = np.linspace(1.0, 0.0, len(ids))
    scores[100:105] = 2.0
    order, _ = constrained_rank_stable_order(candidates, baseline, scores, ids, 20, 5)
    assert 15 not in set(order[:20])


def test_rank_stable_output_is_deterministic_under_ties():
    ids = np.asarray([f"E{i:03d}" for i in range(105)], dtype=object)
    baseline = np.arange(100, dtype=np.int32)
    candidates = np.asarray(list(range(95)) + list(range(100, 105)), dtype=np.int32)
    scores = np.ones(len(ids))
    first, _ = constrained_rank_stable_order(candidates, baseline, scores, ids, 20, 5)
    second, _ = constrained_rank_stable_order(candidates, baseline, scores, ids, 20, 5)
    assert first.tolist() == second.tolist()


def test_inference_functions_accept_no_gold_answer_or_outcome_labels():
    for function in (adaptive_relevance, conservative_candidates, constrained_rank_stable_order):
        parameters = set(inspect.signature(function).parameters)
        assert not parameters & {"gold", "gold_ids", "answer", "labels", "success"}


def test_phase_a_mapping_and_expected_counts_are_unchanged():
    units = read_jsonl(ROOT / "data/processed/evidence_units.jsonl")
    assert len(units) == len({row["evidence_id"] for row in units}) == 27045
    assert sum(row["unit_type"] == "TEXT_REGION" for row in units) == 26954
    assert sum(row["unit_type"] == "TABLE_REGION" for row in units) == 91
    assert all(row["doc_id"] and row["page_id"] for row in units)


def test_dev_counts_and_candidate_test_loader_guard():
    dev = load_mar_dev(ROOT, "dev")
    signatures = {"|".join(sorted(qa["retrieval_evidence_ids"])) for qa in dev}
    multi_signatures = {
        "|".join(sorted(qa["retrieval_evidence_ids"]))
        for qa in dev if qa["retrieval_multi_evidence"]
    }
    assert len(dev) == 93
    assert sum(qa["retrieval_multi_evidence"] for qa in dev) == 25
    assert len(signatures) == 45
    assert len(multi_signatures) == 8
    with pytest.raises(ValueError, match="DEV-only"):
        load_mar_dev(ROOT, "candidate_test")


def test_frozen_config_has_no_grid_search_and_exact_budgets():
    config = json.loads((ROOT / "configs/mar_er.json").read_text(encoding="utf-8"))
    retrieval = config["retrieval"]
    assert retrieval["candidate_budget"] == 100
    assert retrieval["candidate_anchor"] == 80
    assert retrieval["rescue_quota"] == 20
    assert retrieval["final_k"] == 20
    assert retrieval["protected_top_k"] == 15
    assert retrieval["intrusion_budget"] == 5
    assert config["one_shot"]
    assert not config["post_result_parameter_changes_allowed"]
    assert config["candidate_test_policy"] == "SEALED_NOT_PARSED; BYTE_HASH_ONLY"
