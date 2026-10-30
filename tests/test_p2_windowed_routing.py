from __future__ import annotations

import numpy as np
import pytest

from viirr_retrieval.windowed import deterministic_id_hash, page_max_scores, rank_ids, sliding_spans


def test_sliding_windows_cover_tail_without_gap():
    spans = sliding_spans(1000, content_tokens=384, overlap=128)
    assert spans == [(0, 384), (256, 640), (512, 896), (768, 1000)]
    covered = {position for start, end in spans for position in range(start, end)}
    assert covered == set(range(1000))


@pytest.mark.parametrize("count", [0, 1, 384])
def test_short_page_gets_one_window(count):
    assert sliding_spans(count, 384, 128) == [(0, count)]


def test_window_parameters_reject_invalid_overlap():
    with pytest.raises(ValueError):
        sliding_spans(10, 384, 384)


def test_page_max_is_query_conditioned_max_not_mean():
    scores = np.asarray([0.1, 0.9, 0.4], dtype=np.float32)
    values = page_max_scores(scores, ["P1", "P2"], {"P1": [0, 1], "P2": [2]})
    assert values.tolist() == pytest.approx([0.9, 0.4])


def test_ranking_tie_break_is_deterministic_id_order():
    assert rank_ids(["B", "A", "C"], np.asarray([1.0, 1.0, 0.0])) == ["A", "B", "C"]


def test_candidate_hash_is_order_sensitive_and_stable():
    assert deterministic_id_hash(["A", "B"]) == deterministic_id_hash(["A", "B"])
    assert deterministic_id_hash(["A", "B"]) != deterministic_id_hash(["B", "A"])

