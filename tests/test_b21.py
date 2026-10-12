from __future__ import annotations

import numpy as np

from viirr_retrieval.b21 import _failure_stage, _rrf_order, paired_bootstrap


def test_paired_bootstrap_is_deterministic_and_paired():
    first = paired_bootstrap([1, 1, 0, 1], [0, 1, 0, 0], 1000, 42)
    second = paired_bootstrap([1, 1, 0, 1], [0, 1, 0, 0], 1000, 42)
    assert first == second
    assert first["delta"] == 0.5
    assert first["improvements"] == 2


def test_rrf_page_order_is_deterministic():
    ids = np.asarray(["B", "A", "C"], dtype=object)
    order, scores = _rrf_order(np.zeros(3), np.zeros(3), ids, 60)
    assert ids[order].tolist() == ["A", "B", "C"]
    assert np.all(scores[:-1] >= scores[1:])


def test_failure_stage_uses_pipeline_priority():
    units = {
        "E1": {"page_id": "P1", "unit_type": "TEXT_REGION"},
        "E2": {"page_id": "P2", "unit_type": "TABLE_REGION"},
    }
    stage, details = _failure_stage({"E1", "E2"}, [], ["P1", "P3", "P2"], 1, {"E1"}, units)
    assert stage == "PAGE_PRUNING"
    assert {row["failure_stage"] for row in details} == {"REGION_RANKING", "PAGE_PRUNING"}
