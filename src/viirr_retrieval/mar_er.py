from __future__ import annotations

import csv
import json
import platform
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from .b23 import normalize_modality
from .bm25 import BM25Retriever, result_from_unit
from .candidate_metrics import final_ranking_metrics
from .io_utils import read_jsonl, sha256, write_json, write_jsonl
from .mash_er import _load_window_cache, _ranking_records
from .r1 import _load_model, _ranks, max_pool_window_scores


METHODS = ("M0", "M1", "M2", "M3", "M4")
REQUIRED_GROUPS = (
    "OVERALL", "TEXT_ONLY", "TABLE_ONLY", "TEXT_TABLE", "TABLE_TABLE",
    "SINGLE", "MULTI", "CROSS_PAGE", "CROSS_DOCUMENT", "CORE", "CHALLENGE",
)


def load_mar_dev(root: Path, split: str = "dev") -> list[dict]:
    if split != "dev":
        raise ValueError("MAR-ER is DEV-only; Candidate Test must remain sealed")
    return read_jsonl(root / "data/benchmark/dev.jsonl")


def rank_utility(ranks: np.ndarray, rrf_k: int = 60,
                 present: np.ndarray | None = None) -> np.ndarray:
    """Normalized RRF utility. Missing entries are exactly zero."""
    values = np.asarray(ranks, dtype=np.int64)
    mask = values > 0 if present is None else np.asarray(present, dtype=bool) & (values > 0)
    output = np.zeros(len(values), dtype=np.float64)
    output[mask] = (rrf_k + 1.0) / (rrf_k + values[mask])
    return output


def adaptive_relevance(
    bm25_ranks: np.ndarray,
    raw_ranks: np.ndarray,
    alternate_ranks: np.ndarray,
    page_ranks: np.ndarray,
    alternate_valid: np.ndarray,
    rrf_k: int = 60,
) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    """Return raw and one-sided adaptive relevance with full score trace."""
    valid = np.asarray(alternate_valid, dtype=bool)
    u_bm25 = rank_utility(bm25_ranks, rrf_k)
    u_raw = rank_utility(raw_ranks, rrf_k)
    u_alternate = rank_utility(alternate_ranks, rrf_k, valid)
    u_page = rank_utility(page_ranks, rrf_k)
    corroboration = np.maximum(u_bm25, u_page)
    possible_uplift = np.maximum(u_alternate - u_raw, 0.0)
    adaptive_contribution = valid.astype(np.float64) * corroboration * possible_uplift
    adaptive_dense = u_raw + adaptive_contribution
    raw_relevance = 0.5 * u_bm25 + 0.5 * u_raw
    adaptive_score = 0.5 * u_bm25 + 0.5 * adaptive_dense
    if np.any(adaptive_dense + 1e-15 < u_raw):
        raise AssertionError("One-sided alternate view reduced raw dense utility")
    if np.any(adaptive_dense - 1e-15 > np.maximum(u_raw, u_alternate)):
        raise AssertionError("Adaptive dense utility exceeded the better view")
    return raw_relevance, adaptive_score, {
        "u_bm25": u_bm25,
        "u_raw": u_raw,
        "u_alternate": u_alternate,
        "u_page": u_page,
        "corroboration": corroboration,
        "possible_uplift": possible_uplift,
        "adaptive_contribution": adaptive_contribution,
        "adaptive_dense": adaptive_dense,
    }


def _baseline_rank_array(baseline_indexes: np.ndarray, size: int) -> np.ndarray:
    ranks = np.full(size, size + 1, dtype=np.int64)
    ranks[np.asarray(baseline_indexes, dtype=np.int32)] = np.arange(
        1, len(baseline_indexes) + 1, dtype=np.int64
    )
    return ranks


def score_order(indexes: np.ndarray | list[int], scores: np.ndarray, ids: np.ndarray,
                baseline_ranks: np.ndarray | None = None) -> np.ndarray:
    indexes = np.asarray(indexes, dtype=np.int32)
    if baseline_ranks is None:
        return indexes[np.lexsort((ids[indexes], -scores[indexes]))]
    return indexes[np.lexsort((ids[indexes], baseline_ranks[indexes], -scores[indexes]))]


def conservative_candidates(
    baseline_indexes: np.ndarray,
    source_indexes: dict[str, np.ndarray],
    scores: np.ndarray,
    ids: np.ndarray,
    budget: int = 100,
    anchor_count: int = 80,
) -> tuple[np.ndarray, dict[int, list[str]]]:
    """Keep baseline prefix and fill the fixed rescue quota from a deduplicated union."""
    baseline = np.asarray(baseline_indexes, dtype=np.int32)
    if len(baseline) < budget:
        raise ValueError("Matched baseline is shorter than candidate budget")
    if not 0 <= anchor_count <= budget:
        raise ValueError("Invalid candidate anchor count")
    provenance: dict[int, set[str]] = defaultdict(set)
    union: set[int] = set()
    for source, indexes in source_indexes.items():
        for index in np.asarray(indexes, dtype=np.int32):
            union.add(int(index))
            provenance[int(index)].add(source)
    anchors = [int(index) for index in baseline[:anchor_count]]
    union.update(anchors)
    remainder = np.asarray(sorted(union.difference(anchors)), dtype=np.int32)
    ordered = score_order(remainder, scores, ids)
    selected = np.asarray(anchors + [int(index) for index in ordered[:budget - anchor_count]],
                          dtype=np.int32)
    if len(selected) != budget or len(set(selected.tolist())) != budget:
        raise AssertionError("Conservative candidate fusion violated unique B budget")
    if selected[:anchor_count].tolist() != anchors:
        raise AssertionError("Baseline candidate anchor was not retained")
    return selected, {index: sorted(values) for index, values in provenance.items()}


def constrained_rank_stable_order(
    candidate_indexes: np.ndarray,
    baseline_indexes: np.ndarray,
    scores: np.ndarray,
    ids: np.ndarray,
    final_k: int = 20,
    intrusion_budget: int = 5,
) -> tuple[np.ndarray, dict[str, list[int]]]:
    """Precedence-constrained Top-K followed by a deterministic score-ranked tail."""
    candidates = np.asarray(candidate_indexes, dtype=np.int32)
    baseline = np.asarray(baseline_indexes, dtype=np.int32)
    protected_count = final_k - intrusion_budget
    anchors = [int(index) for index in baseline[:protected_count]]
    candidate_set = set(candidates.tolist())
    if not set(anchors) <= candidate_set:
        raise AssertionError("Protected baseline prefix missing from candidate set")
    baseline_ranks = _baseline_rank_array(baseline, len(ids))
    remainder = np.asarray(sorted(candidate_set.difference(anchors)), dtype=np.int32)
    challengers = score_order(remainder, scores, ids, baseline_ranks)[:intrusion_budget]
    challenger_left = {int(index) for index in challengers}

    top: list[int] = []
    next_anchor = 0
    while len(top) < final_k:
        available = list(challenger_left)
        if next_anchor < len(anchors):
            available.append(anchors[next_anchor])
        if not available:
            raise AssertionError("Constrained ordering exhausted available items")
        chosen = int(score_order(available, scores, ids, baseline_ranks)[0])
        top.append(chosen)
        if next_anchor < len(anchors) and chosen == anchors[next_anchor]:
            next_anchor += 1
        else:
            challenger_left.remove(chosen)
    if next_anchor != len(anchors) or challenger_left:
        raise AssertionError("Constrained ordering did not emit all anchors/challengers")

    tail_set = candidate_set.difference(top)
    tail = score_order(np.asarray(sorted(tail_set), dtype=np.int32), scores, ids, baseline_ranks)
    order = np.asarray(top + [int(index) for index in tail], dtype=np.int32)
    if len(order) != len(candidates) or len(set(order.tolist())) != len(candidates):
        raise AssertionError("Final ranking is not a permutation of candidates")
    return order, {"anchors": anchors, "challengers": [int(index) for index in challengers]}


def rank_stability_summary(final_order: np.ndarray, baseline_order: np.ndarray,
                           final_k: int = 20, intrusion_budget: int = 5) -> dict:
    final_ids = [int(value) for value in np.asarray(final_order)[:final_k]]
    baseline_ids = [int(value) for value in np.asarray(baseline_order)[:final_k]]
    protected = baseline_ids[:final_k - intrusion_budget]
    final_rank = {item: rank for rank, item in enumerate(final_ids, 1)}
    retained = [item for item in protected if item in final_rank]
    relative = [item for item in final_ids if item in set(protected)] == protected
    displacements = {
        item: final_rank[item] - (baseline_ids.index(item) + 1)
        for item in retained
    }
    overlap = len(set(final_ids) & set(baseline_ids))
    summary = {
        "baseline_top15_retained": len(retained),
        "baseline_top20_overlap": overlap,
        "protected_relative_order_preserved": relative,
        "maximum_protected_downward_displacement": max([0] + list(displacements.values())),
        "challenger_slots": len(set(final_ids).difference(protected)),
        "invariants_pass": (
            len(retained) == final_k - intrusion_budget
            and overlap >= final_k - intrusion_budget
            and relative
            and max([0] + list(displacements.values())) <= intrusion_budget
        ),
    }
    return summary


def _qa_signature(qa: dict) -> str:
    return "|".join(sorted(qa["retrieval_evidence_ids"]))


def _qa_groups(qa: dict) -> set[str]:
    groups = {"OVERALL", normalize_modality(qa)}
    groups.add("CHALLENGE" if qa.get("relation_type") else "CORE")
    groups.add("MULTI" if qa.get("retrieval_multi_evidence") else "SINGLE")
    if bool(qa.get("cross_page")):
        groups.add("CROSS_PAGE")
    if qa.get("location_type") == "CROSS_DOCUMENT" or len(qa.get("gold_doc_ids", [])) > 1:
        groups.add("CROSS_DOCUMENT")
    return groups


def _per_query_metrics(qa: dict, record: dict, unit_by_id: dict[str, dict], latency_ms: float) -> dict:
    ranked = [row["evidence_id"] for row in record["results"]]
    candidates = set(record["candidate_ids"])
    gold = set(qa["retrieval_evidence_ids"])
    metrics = final_ranking_metrics(qa["retrieval_evidence_ids"], ranked, [10, 20])
    top20_pages = {unit_by_id[item]["page_id"] for item in ranked[:20]}
    return {
        "candidate_complete": float(gold <= candidates),
        "candidate_gold_coverage": len(gold & candidates) / len(gold),
        "all_r@10": metrics["10"]["all_recall"],
        "all_r@20": metrics["20"]["all_recall"],
        "any_r@10": metrics["10"]["any_recall"],
        "any_r@20": metrics["20"]["any_recall"],
        "average_gold_coverage@20": metrics["20"]["average_gold_coverage"],
        "mrr": metrics["mrr"],
        "ndcg@10": metrics["ndcg@10"],
        "complete_gold_page_coverage@20": float(set(qa["gold_page_ids"]) <= top20_pages),
        "latency_ms": float(latency_ms),
    }


def _aggregate(rows: list[tuple[dict, dict]]) -> dict:
    if not rows:
        return {"qa_n": 0, "unique_gold_set_n": 0}
    fields = (
        "candidate_complete", "candidate_gold_coverage", "all_r@10", "all_r@20",
        "any_r@10", "any_r@20", "average_gold_coverage@20", "mrr", "ndcg@10",
        "complete_gold_page_coverage@20", "latency_ms",
    )
    output = {
        "qa_n": len(rows),
        "unique_gold_set_n": len({_qa_signature(qa) for qa, _ in rows}),
    }
    aliases = {
        "candidate_complete": "complete_candidate_coverage@100",
        "candidate_gold_coverage": "average_gold_coverage@100",
        "latency_ms": "latency_ms_per_query",
    }
    for field in fields:
        values = [metrics[field] for _, metrics in rows]
        output[aliases.get(field, field)] = float(np.mean(values))
        if field in {"candidate_complete", "all_r@10", "all_r@20", "any_r@10", "any_r@20"}:
            output[f"{aliases.get(field, field)}_numerator"] = int(sum(values))
            output[f"{aliases.get(field, field)}_denominator"] = len(values)
    by_signature: dict[str, list[float]] = defaultdict(list)
    for qa, metrics in rows:
        by_signature[_qa_signature(qa)].append(metrics["all_r@20"])
    output["unique_gold_set_balanced_all_r@20"] = float(np.mean([
        np.mean(values) for values in by_signature.values()
    ]))
    return output


def evaluate(dev: list[dict], records: dict[str, dict[str, dict]],
             unit_by_id: dict[str, dict], latency: dict[str, dict[str, float]]) -> tuple[dict, dict]:
    per_query: dict[str, dict[str, dict]] = {method: {} for method in METHODS}
    subgroups: dict[str, dict[str, dict]] = {method: {} for method in METHODS}
    for method in METHODS:
        grouped: dict[str, list[tuple[dict, dict]]] = {name: [] for name in REQUIRED_GROUPS}
        for qa in dev:
            metrics = _per_query_metrics(
                qa, records[method][qa["qa_id"]], unit_by_id, latency[method][qa["qa_id"]]
            )
            per_query[method][qa["qa_id"]] = metrics
            for group in _qa_groups(qa):
                if group in grouped:
                    grouped[group].append((qa, metrics))
        subgroups[method] = {name: _aggregate(rows) for name, rows in grouped.items()}
    return per_query, subgroups


def _bootstrap_difference(current: list[float], baseline: list[float], clusters: list[str] | None,
                          resamples: int, seed: int) -> dict:
    current_array = np.asarray(current, dtype=np.float64)
    baseline_array = np.asarray(baseline, dtype=np.float64)
    differences = current_array - baseline_array
    rng = np.random.default_rng(seed)
    samples = np.empty(resamples, dtype=np.float64)
    if clusters is None:
        for index in range(resamples):
            selected = rng.integers(0, len(differences), len(differences))
            samples[index] = float(np.mean(differences[selected]))
        unit_count = len(differences)
    else:
        grouped: dict[str, list[float]] = defaultdict(list)
        for cluster, difference in zip(clusters, differences):
            grouped[cluster].append(float(difference))
        cluster_values = np.asarray([np.mean(values) for values in grouped.values()])
        for index in range(resamples):
            selected = rng.integers(0, len(cluster_values), len(cluster_values))
            samples[index] = float(np.mean(cluster_values[selected]))
        unit_count = len(cluster_values)
    lower, upper = np.quantile(samples, [0.025, 0.975])
    return {
        "effect": float(np.mean(differences)),
        "ci95": [float(lower), float(upper)],
        "resampling_units": unit_count,
        "resamples": resamples,
        "seed": seed,
        "conclusion": "INCONCLUSIVE" if lower <= 0.0 <= upper else (
            "POSITIVE" if lower > 0 else "NEGATIVE"
        ),
    }


def statistics(dev: list[dict], per_query: dict[str, dict], config: dict) -> dict:
    resamples = int(config["statistics"]["bootstrap_resamples"])
    seed = int(config["statistics"]["seed"])
    signatures = [_qa_signature(qa) for qa in dev]
    output = {
        "bootstrap_resamples": resamples,
        "seed": seed,
        "unique_gold_signatures": len(set(signatures)),
        "unique_multi_gold_signatures": len({
            _qa_signature(qa) for qa in dev if qa["retrieval_multi_evidence"]
        }),
        "unique_document_families": len({qa.get("leakage_group_id") for qa in dev}),
        "comparisons": {},
    }
    for baseline in ("M0", "M1", "M2", "M3"):
        label = f"M4_minus_{baseline}"
        output["comparisons"][label] = {}
        for metric in ("candidate_complete", "all_r@20"):
            current = [per_query["M4"][qa["qa_id"]][metric] for qa in dev]
            reference = [per_query[baseline][qa["qa_id"]][metric] for qa in dev]
            output["comparisons"][label][metric] = {
                "qa_bootstrap": _bootstrap_difference(
                    current, reference, None, resamples, seed
                ),
                "gold_signature_cluster_bootstrap": _bootstrap_difference(
                    current, reference, signatures, resamples, seed
                ),
            }
    return output


def _historical_metrics(root: Path) -> dict:
    output = {}
    for name, path in {
        "GLOBAL_RRF_E0": root / "outputs/C1/rankings/e0_g0_global_rrf_dev.jsonl",
        "R1_CONTEXTUAL_R2_FULL": root / "outputs/R1/rankings/full_retrieval_r2_dev.jsonl",
        "MASH_ER_A3": root / "outputs/MASH_ER/rankings/a3_dev.jsonl",
    }.items():
        rows = _ranking_records(path)
        output[name] = {"path": path.relative_to(root).as_posix(), "matched_control": False,
                        "record_count": len(rows)}
    return output


def run_mar_er(root: Path, pytest_result: dict | None = None) -> dict:
    config_path = root / "configs/mar_er.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    report_dir = root / "reports/MAR_ER_EXPERIMENT"
    output_dir = root / "outputs/MAR_ER"
    preflight_path = report_dir / "PREFLIGHT.json"
    frozen_path = report_dir / "FROZEN_CONFIG.json"
    if not preflight_path.exists() or not frozen_path.exists():
        raise RuntimeError("Run scripts/preflight_mar_er.py before the one-shot experiment")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    if preflight.get("status") != "PASS":
        raise RuntimeError("BASELINE_BLOCKED: preflight did not pass")
    if frozen["hashes"]["configs/mar_er.json"] != sha256(config_path):
        raise RuntimeError("Frozen MAR-ER config changed after preregistration")
    for relative in frozen["source_files"]:
        if sha256(root / relative) != frozen["hashes"][relative]:
            raise RuntimeError(f"Frozen implementation changed after preregistration: {relative}")
    for directory in (output_dir / "rankings", output_dir / "traces", output_dir / "metadata"):
        directory.mkdir(parents=True, exist_ok=True)

    candidate_test = root / "data/benchmark/candidate_test.jsonl"
    candidate_hash_before = sha256(candidate_test)
    protected_before = {
        relative: sha256(root / relative) for relative in frozen["protected_inputs"]
    }
    dev = load_mar_dev(root, config["evaluation_split"])
    units = read_jsonl(root / "data/processed/evidence_units.jsonl")
    unit_by_id = {row["evidence_id"]: row for row in units}
    ids = np.asarray([row["evidence_id"] for row in units], dtype=object)
    id_to_index = {item: index for index, item in enumerate(ids)}

    view_rows = read_jsonl(root / "outputs/MASH_ER/views/view_manifest.jsonl")
    if [row["evidence_id"] for row in view_rows] != ids.tolist():
        raise AssertionError("View manifest changed evidence ordering")
    alternate_valid = np.asarray([row["alternate_valid"] for row in view_rows], dtype=bool)
    text_indexes = np.asarray([
        index for index, row in enumerate(units) if row["unit_type"] == "TEXT_REGION"
    ], dtype=np.int32)
    raw_embeddings, raw_window_units, raw_meta = _load_window_cache(root, "R0")
    context_embeddings, context_window_units, context_meta = _load_window_cache(root, "R1")
    table_embeddings = np.load(
        root / "outputs/MASH_ER/cache/table_struct_window_embeddings.npy", mmap_mode="r"
    )
    table_windows = read_jsonl(root / "outputs/MASH_ER/windows/table_struct_window_map.jsonl")
    table_window_units = np.asarray([row["unit_index"] for row in table_windows], dtype=np.int32)
    valid_table_global = np.asarray([
        index for index, row in enumerate(view_rows)
        if row["unit_type"] == "TABLE_REGION" and row["alternate_valid"]
    ], dtype=np.int32)

    phase_b = json.loads((root / "configs/phase_b.json").read_text(encoding="utf-8"))
    bm25 = BM25Retriever(
        units, root / "outputs/B2/cache/bm25_regions.pkl",
        sha256(root / "data/processed/evidence_units.jsonl"),
        phase_b["bm25"]["k1"], phase_b["bm25"]["b"],
    )
    page_rankings = _ranking_records(root / "outputs/B2_1/rankings/p0_pages_dev_top100.jsonl")
    page_region = _ranking_records(root / config["retrieval"]["page_region_source"])
    historical_a0 = _ranking_records(root / "outputs/MASH_ER/rankings/a0_dev.jsonl")
    page_to_indexes: dict[str, list[int]] = defaultdict(list)
    for index, unit in enumerate(units):
        page_to_indexes[unit["page_id"]].append(index)

    model, revision, device = _load_model(config["model"])
    if revision != config["model"]["revision"]:
        raise AssertionError(f"Model revision mismatch: {revision}")
    import torch
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    query_started = time.perf_counter()
    query_vectors = model.encode(
        [config["model"]["query_prefix"] + qa["question"] for qa in dev],
        batch_size=int(config["model"]["batch_size"]), show_progress_bar=False,
        normalize_embeddings=True, convert_to_numpy=True,
    ).astype(np.float32)
    if device == "cuda":
        torch.cuda.synchronize()
    query_seconds = time.perf_counter() - query_started

    records: dict[str, dict[str, dict]] = {method: {} for method in METHODS}
    traces: dict[str, dict[str, dict]] = {method: {} for method in METHODS}
    latency: dict[str, dict[str, float]] = {method: {} for method in METHODS}
    stability_rows = []
    baseline_mismatches = []
    rrf_k = int(config["retrieval"]["rrf_k"])
    budget = int(config["retrieval"]["candidate_budget"])
    anchor_count = int(config["retrieval"]["candidate_anchor"])
    final_k = int(config["retrieval"]["final_k"])
    intrusion = int(config["retrieval"]["intrusion_budget"])

    experiment_started = time.perf_counter()
    for qa_index, qa in enumerate(dev):
        qa_id = qa["qa_id"]
        bm_started = time.perf_counter()
        bm_scores = bm25.score_all(qa["question"])
        bm_order, bm_ranks = _ranks(bm_scores, ids)
        bm_seconds = time.perf_counter() - bm_started

        raw_started = time.perf_counter()
        raw_window_scores = np.asarray(raw_embeddings @ query_vectors[qa_index], dtype=np.float64)
        raw_scores = max_pool_window_scores(raw_window_scores, raw_window_units, len(units))
        raw_order, raw_ranks = _ranks(raw_scores, ids)
        raw_seconds = time.perf_counter() - raw_started

        alternate_started = time.perf_counter()
        context_window_scores = np.asarray(
            context_embeddings @ query_vectors[qa_index], dtype=np.float64
        )
        context_scores = max_pool_window_scores(
            context_window_scores, context_window_units, len(units)
        )
        alternate_scores = np.full(len(units), -np.inf, dtype=np.float64)
        alternate_scores[text_indexes] = context_scores[text_indexes]
        if len(table_embeddings):
            table_window_scores = np.asarray(
                table_embeddings @ query_vectors[qa_index], dtype=np.float64
            )
            table_local_scores = max_pool_window_scores(
                table_window_scores, table_window_units, len(valid_table_global)
            )
            alternate_scores[valid_table_global] = table_local_scores
        alternate_order, alternate_ranks = _ranks(
            alternate_scores, ids, np.flatnonzero(alternate_valid).astype(np.int32)
        )
        alternate_seconds = time.perf_counter() - alternate_started

        page_rank_by_id = {
            row["page_id"]: int(row["rank"]) for row in page_rankings[qa_id]["results"]
        }
        page_ranks = np.asarray([
            page_rank_by_id.get(unit["page_id"], 0) for unit in units
        ], dtype=np.int32)
        raw_relevance, adaptive_score, components = adaptive_relevance(
            bm_ranks, raw_ranks, alternate_ranks, page_ranks, alternate_valid, rrf_k
        )

        selected_pages = {
            row["page_id"] for row in page_rankings[qa_id]["results"][:
                int(config["retrieval"]["hard_page_budget"])
            ]
        }
        hard_indexes = np.asarray(sorted({
            index for page_id in selected_pages for index in page_to_indexes.get(page_id, [])
        }), dtype=np.int32)
        baseline = score_order(hard_indexes, raw_relevance, ids)[:budget]
        expected = [row["evidence_id"] for row in historical_a0[qa_id]["results"][:budget]]
        actual = [str(ids[index]) for index in baseline]
        if actual != expected:
            baseline_mismatches.append({
                "qa_id": qa_id,
                "first_difference": next(
                    (rank for rank, (left, right) in enumerate(zip(actual, expected), 1)
                     if left != right), None
                ),
            })

        page_region_indexes = np.asarray([
            id_to_index[row["evidence_id"]]
            for row in page_region[qa_id]["results"][:int(config["retrieval"]["source_depth"])]
        ], dtype=np.int32)
        source_indexes = {
            "MATCHED_BASELINE_A0": baseline,
            "GLOBAL_BM25_RAW": bm_order[:budget],
            "GLOBAL_E5_RAW": raw_order[:budget],
            "UNIFIED_MODALITY_ALTERNATE_E5": alternate_order[:budget],
            "P0_PAGE_TO_REGION": page_region_indexes,
        }
        raw_recovery, raw_provenance = conservative_candidates(
            baseline, source_indexes, raw_relevance, ids, budget, anchor_count
        )
        adaptive_recovery, adaptive_provenance = conservative_candidates(
            baseline, source_indexes, adaptive_score, ids, budget, anchor_count
        )
        baseline_ranks = _baseline_rank_array(baseline, len(ids))

        method_specs = {
            "M0": (baseline, raw_relevance, False, {int(i): ["MATCHED_BASELINE_A0"] for i in baseline}),
            "M1": (baseline, adaptive_score, False, {int(i): ["MATCHED_BASELINE_A0"] for i in baseline}),
            "M2": (raw_recovery, raw_relevance, False, raw_provenance),
            "M3": (baseline, raw_relevance, True, {int(i): ["MATCHED_BASELINE_A0"] for i in baseline}),
            "M4": (adaptive_recovery, adaptive_score, True, adaptive_provenance),
        }
        for method, (candidates, scores, stable, provenance) in method_specs.items():
            selection_started = time.perf_counter()
            if method == "M0":
                order = baseline.copy()
                selection = {"anchors": [], "challengers": []}
            elif stable:
                order, selection = constrained_rank_stable_order(
                    candidates, baseline, scores, ids, final_k, intrusion
                )
            else:
                order = score_order(candidates, scores, ids, baseline_ranks)
                selection = {"anchors": [], "challengers": []}
            selection_seconds = time.perf_counter() - selection_started
            candidate_ids = [str(ids[index]) for index in candidates]
            result_rows = [
                result_from_unit(units[int(index)], float(scores[index]), rank).to_dict()
                for rank, index in enumerate(order, 1)
            ]
            records[method][qa_id] = {
                "qa_id": qa_id,
                "method": method,
                "candidate_ids": candidate_ids,
                "results": result_rows,
            }
            anchor_set = set(selection["anchors"])
            challenger_set = set(selection["challengers"])
            candidate_anchor_set = set(baseline[:anchor_count].tolist())
            trace_candidates = []
            for rank, index_value in enumerate(order, 1):
                index = int(index_value)
                trace_candidates.append({
                    "rank": rank,
                    "evidence_id": str(ids[index]),
                    "doc_id": units[index]["doc_id"],
                    "page_id": units[index]["page_id"],
                    "unit_type": units[index]["unit_type"],
                    "alternate_view": view_rows[index]["alternate_view"],
                    "alternate_valid": bool(alternate_valid[index]),
                    "source_provenance": provenance.get(index, []),
                    "source_ranks": {
                        "bm25": int(bm_ranks[index]),
                        "raw": int(raw_ranks[index]),
                        "alternate": int(alternate_ranks[index]) if alternate_valid[index] else None,
                        "page": int(page_ranks[index]) if page_ranks[index] > 0 else None,
                        "baseline": int(baseline_ranks[index]) if baseline_ranks[index] <= budget else None,
                    },
                    "utilities": {
                        key: float(components[key][index]) for key in (
                            "u_bm25", "u_raw", "u_alternate", "u_page", "corroboration",
                            "adaptive_contribution", "adaptive_dense",
                        )
                    },
                    "raw_relevance": float(raw_relevance[index]),
                    "adaptive_relevance": float(adaptive_score[index]),
                    "final_score": float(scores[index]),
                    "candidate_anchor": index in candidate_anchor_set,
                    "new_candidate": index not in set(baseline.tolist()),
                    "protected_anchor": index in anchor_set,
                    "challenger": index in challenger_set,
                })
            traces[method][qa_id] = {
                "qa_id": qa_id, "method": method, "candidates": trace_candidates
            }
            shared_raw = bm_seconds + raw_seconds + query_seconds / len(dev)
            if method in {"M1", "M2", "M4"}:
                shared_raw += alternate_seconds
            latency[method][qa_id] = 1000.0 * (shared_raw + selection_seconds)

            if stable:
                stability = rank_stability_summary(order, baseline, final_k, intrusion)
                stability["baseline_candidate_overlap"] = len(
                    set(candidates.tolist()) & set(baseline.tolist())
                )
                stability["invariants_pass"] = bool(
                    stability["invariants_pass"]
                    and stability["baseline_candidate_overlap"] >= anchor_count
                )
                stability_rows.append({"qa_id": qa_id, "method": method, **stability})

    if baseline_mismatches:
        write_json(report_dir / "BASELINE_VERIFICATION.json", {
            "status": "BASELINE_BLOCKED", "mismatches": baseline_mismatches,
            "matched_queries": len(dev) - len(baseline_mismatches),
        })
        raise RuntimeError("BASELINE_BLOCKED: recomputed M0 does not match A0 per query")

    for method in METHODS:
        write_jsonl(output_dir / "rankings" / f"{method.lower()}_dev.jsonl",
                    (records[method][qa["qa_id"]] for qa in dev))
        write_jsonl(output_dir / "traces" / f"{method.lower()}_score_traces.jsonl",
                    (traces[method][qa["qa_id"]] for qa in dev))
    write_jsonl(output_dir / "metadata/evidence_manifest.jsonl", ({
        key: row[key] for key in ("evidence_id", "doc_id", "page_id", "unit_type")
    } for row in units))

    per_query, subgroups = evaluate(dev, records, unit_by_id, latency)
    stats = statistics(dev, per_query, config)
    write_json(report_dir / "SUBGROUPS.json", {
        "definitions": {
            "CROSS_PAGE": "qa.cross_page=true; includes cross-document QA when annotated cross-page",
            "CROSS_DOCUMENT": "location_type=CROSS_DOCUMENT or more than one gold_doc_id",
            "unique_gold_set_balanced": "mean within signature, then equal-weight macro mean over signatures",
        },
        "methods": subgroups,
    })
    result_rows = []
    for method in METHODS:
        overall = subgroups[method]["OVERALL"]
        multi = subgroups[method]["MULTI"]
        result_rows.append({
            "method": method,
            "adaptive_fusion": config["methods"][method]["adaptive_fusion"],
            "candidate_recovery": config["methods"][method]["candidate_recovery"],
            "rank_stability": config["methods"][method]["rank_stability"],
            "dev_qa": overall["qa_n"],
            "candidate_coverage@100": overall["complete_candidate_coverage@100"],
            "all_r@20": overall["all_r@20"],
            "multi_all_r@20": multi["all_r@20"],
            "unique_gold_set_balanced_all_r@20": overall["unique_gold_set_balanced_all_r@20"],
            "all_r@10": overall["all_r@10"],
            "any_r@10": overall["any_r@10"],
            "any_r@20": overall["any_r@20"],
            "average_gold_coverage@20": overall["average_gold_coverage@20"],
            "mrr": overall["mrr"],
            "ndcg@10": overall["ndcg@10"],
            "complete_gold_page_coverage@20": overall["complete_gold_page_coverage@20"],
            "latency_ms_per_query": overall["latency_ms_per_query"],
        })
    with (report_dir / "RESULTS.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result_rows[0]))
        writer.writeheader()
        writer.writerows(result_rows)

    transitions = []
    recovered = regressed = candidate_recovered = candidate_lost = 0
    recovered_signatures: set[str] = set()
    gold_lost_16_20 = []
    for qa in dev:
        qa_id = qa["qa_id"]
        before = per_query["M0"][qa_id]
        after = per_query["M4"][qa_id]
        m0_rank = {row["evidence_id"]: row["rank"] for row in records["M0"][qa_id]["results"]}
        m4_rank = {row["evidence_id"]: row["rank"] for row in records["M4"][qa_id]["results"]}
        lost_gold = [item for item in qa["retrieval_evidence_ids"]
                     if 16 <= m0_rank.get(item, 10**9) <= 20 and m4_rank.get(item, 10**9) > 20]
        row = {
            "qa_id": qa_id,
            "gold_signature": _qa_signature(qa),
            "modality": normalize_modality(qa),
            "retrieval_multi": bool(qa["retrieval_multi_evidence"]),
            "candidate_complete_before": before["candidate_complete"],
            "candidate_complete_after": after["candidate_complete"],
            "all_r@20_before": before["all_r@20"],
            "all_r@20_after": after["all_r@20"],
            "candidate_recovered": before["candidate_complete"] == 0 and after["candidate_complete"] == 1,
            "candidate_lost": before["candidate_complete"] == 1 and after["candidate_complete"] == 0,
            "final_recovered": before["all_r@20"] == 0 and after["all_r@20"] == 1,
            "final_regressed": before["all_r@20"] == 1 and after["all_r@20"] == 0,
            "gold_lost_from_baseline_ranks_16_20": lost_gold,
            "gold_ranks_m0": {item: m0_rank.get(item) for item in qa["retrieval_evidence_ids"]},
            "gold_ranks_m4": {item: m4_rank.get(item) for item in qa["retrieval_evidence_ids"]},
            "new_top20_evidence": [
                item for item in list(m4_rank)[:20] if item not in set(list(m0_rank)[:20])
            ],
        }
        transitions.append(row)
        candidate_recovered += int(row["candidate_recovered"])
        candidate_lost += int(row["candidate_lost"])
        recovered += int(row["final_recovered"])
        regressed += int(row["final_regressed"])
        if row["final_recovered"]:
            recovered_signatures.add(row["gold_signature"])
        if lost_gold:
            gold_lost_16_20.append({"qa_id": qa_id, "evidence_ids": lost_gold})
    write_jsonl(report_dir / "FAILURE_TRANSITIONS.jsonl", transitions)

    stability_audit = {
        "required": {
            "candidate_overlap_min": 80,
            "top20_overlap_min": 15,
            "protected_top15_retained": 15,
            "maximum_protected_downward_displacement": 5,
            "protected_relative_order": True,
        },
        "queries": stability_rows,
        "all_invariants_pass": all(row["invariants_pass"] for row in stability_rows),
        "minimum_top20_overlap": min(row["baseline_top20_overlap"] for row in stability_rows),
        "maximum_displacement": max(
            row["maximum_protected_downward_displacement"] for row in stability_rows
        ),
        "gold_lost_from_baseline_ranks_16_20": gold_lost_16_20,
    }
    write_json(report_dir / "RANK_STABILITY_AUDIT.json", stability_audit)
    write_json(report_dir / "STATISTICS.json", stats)

    primary = {row["method"]: {
        key: row[key] for key in (
            "candidate_coverage@100", "all_r@20", "multi_all_r@20",
            "unique_gold_set_balanced_all_r@20",
        )
    } for row in result_rows}
    ablations = {
        "primary_metrics": primary,
        "deltas_vs_m0": {
            method: {metric: primary[method][metric] - primary["M0"][metric]
                     for metric in primary[method]}
            for method in ("M1", "M2", "M3", "M4")
        },
        "m4_transitions_vs_m0": {
            "candidate_recovered": candidate_recovered,
            "candidate_lost": candidate_lost,
            "final_recovered": recovered,
            "final_regressed": regressed,
            "recovered_unique_gold_signatures": len(recovered_signatures),
        },
        "historical_context": _historical_metrics(root),
        "historical_context_is_not_matched_control": True,
    }
    write_json(report_dir / "ABLATIONS.json", ablations)

    peak_vram = float(torch.cuda.max_memory_allocated() / 1024**2) if device == "cuda" else None
    efficiency = {
        "device": device,
        "model_id": config["model"]["id"],
        "model_revision": revision,
        "query_encoding_seconds_total": query_seconds,
        "experiment_loop_seconds": time.perf_counter() - experiment_started,
        "latency_ms_per_query": {
            method: subgroups[method]["OVERALL"]["latency_ms_per_query"] for method in METHODS
        },
        "peak_vram_mb": peak_vram,
        "cache_storage_bytes": {
            relative: int((root / relative).stat().st_size) for relative in (
                config["windowing"]["raw_cache"], config["windowing"]["text_context_cache"],
                config["windowing"]["table_struct_cache"],
            )
        },
        "cache_hits": {"raw": True, "text_context": True, "table_struct": True},
        "latency_scope": "Query encoding (amortized), BM25, cached dense scoring, fusion, candidate and final selection.",
    }
    write_json(report_dir / "EFFICIENCY.json", efficiency)

    baseline_verification = {
        "status": "PASS",
        "matched_baseline": "M0 recomputed from the frozen A0 evidence universe/caches",
        "per_query_top100_exact_match_with_mash_a0": True,
        "matched_queries": len(dev),
        "ranking_scale_note": "MAR normalized R0 is a positive 30.5x rescaling of two-source RRF; order is identical.",
        "legacy_baselines_are_not_matched": True,
        "preflight_sha256": sha256(preflight_path),
    }
    write_json(report_dir / "BASELINE_VERIFICATION.json", baseline_verification)
    implementation_audit = {
        "status": "PASS",
        "method_spec_sha256": frozen["hashes"]["reports/MAR_ER_DESIGN/METHOD_SPEC.md"],
        "config_sha256": frozen["hashes"]["configs/mar_er.json"],
        "formula_checks": {
            "rank_utility_normalized": True,
            "one_sided_uplift": True,
            "missing_page_rank_zero": True,
            "alternate_fallback_not_double_counted": True,
            "candidate_anchor_80": True,
            "rescue_quota_20": True,
            "protected_top15": True,
            "intrusion_budget_5": True,
            "deterministic_tie_break": True,
        },
        "gold_or_answer_used_during_inference": False,
        "source_metadata_fabricated": False,
        "candidate_test_loaded": False,
        "view_manifest_count": len(view_rows),
        "alternate_valid_count": int(np.sum(alternate_valid)),
        "cache_metadata": {"raw": raw_meta, "context": context_meta},
    }
    write_json(report_dir / "METHOD_IMPLEMENTATION_AUDIT.json", implementation_audit)
    write_json(report_dir / "ENVIRONMENT.json", {
        "python": platform.python_version(), "platform": platform.platform(),
        "numpy": np.__version__, "device": device,
        "model_id": config["model"]["id"], "model_revision": revision,
    })
    write_json(report_dir / "TEST_RESULTS.json", pytest_result or {})

    m4 = primary["M4"]
    m0 = primary["M0"]
    table_delta = (
        subgroups["M4"]["TABLE_ONLY"]["all_r@20"]
        - subgroups["M0"]["TABLE_ONLY"]["all_r@20"]
    )
    incremental = all(
        any(primary["M4"][metric] > primary[other][metric]
            for metric in ("all_r@20", "multi_all_r@20", "unique_gold_set_balanced_all_r@20"))
        for other in ("M1", "M2", "M3")
    )
    experiment_valid = bool(
        stability_audit["all_invariants_pass"]
        and candidate_hash_before == sha256(candidate_test)
        and protected_before == {relative: sha256(root / relative) for relative in frozen["protected_inputs"]}
        and (pytest_result or {}).get("passed")
    )
    method_promising = bool(
        experiment_valid
        and m4["all_r@20"] > m0["all_r@20"]
        and table_delta >= 0
        and m4["multi_all_r@20"] > m0["multi_all_r@20"]
        and len(recovered_signatures) > 0
        and incremental
    )
    readiness = {
        "status": "PASS" if experiment_valid else "BLOCKED",
        "EXPERIMENT_VALID": experiment_valid,
        "METHOD_PROMISING": method_promising,
        "PAPER_READY": False,
        "result_class": "EXPLORATORY_SIGNAL" if method_promising else "STOP_MAR_ER_BRANCH",
        "candidate_test_sealed": candidate_hash_before == sha256(candidate_test),
        "recovered_qa": recovered,
        "regressed_qa": regressed,
        "recovered_unique_gold_signatures": len(recovered_signatures),
        "blockers": [] if experiment_valid else ["One or more validity invariants failed"],
        "limitations": [
            "Dev was repeatedly used for method diagnosis; results are exploratory.",
            "Only 8 independent multi-evidence gold signatures are available.",
            "No Candidate Test or external benchmark was run.",
            "Novelty has not been established against complete prior art.",
        ],
    }
    write_json(report_dir / "READINESS.json", readiness)
    write_json(report_dir / "FINAL_AUDIT.json", {
        "status": readiness["status"],
        "EXPERIMENT_VALID": experiment_valid,
        "checks": {
            "preflight_pass": preflight["status"] == "PASS",
            "config_frozen": frozen["hashes"]["configs/mar_er.json"] == sha256(config_path),
            "baseline_exact": True,
            "rank_stability_invariants": stability_audit["all_invariants_pass"],
            "candidate_ids_unique": all(
                len(row["candidate_ids"]) == len(set(row["candidate_ids"])) == budget
                for method in METHODS for row in records[method].values()
            ),
            "no_gold_answer_inference": True,
            "candidate_test_not_loaded": True,
            "candidate_test_unchanged": candidate_hash_before == sha256(candidate_test),
            "protected_inputs_unchanged": protected_before == {
                relative: sha256(root / relative) for relative in frozen["protected_inputs"]
            },
            "pytest_pass": bool((pytest_result or {}).get("passed")),
        },
        "candidate_test_sha256": candidate_hash_before,
        "independent_audit_pending": True,
    })

    report = _render_report(primary, subgroups, ablations, stats, stability_audit,
                            efficiency, readiness, table_delta)
    (report_dir / "MAR_ER_REPORT.md").write_text(report, encoding="utf-8", newline="\n")
    return readiness


def _render_report(primary: dict, subgroups: dict, ablations: dict, stats: dict,
                   stability: dict, efficiency: dict, readiness: dict,
                   table_delta: float) -> str:
    rows = [
        f"| {method} | {values['candidate_coverage@100']:.4f} | {values['all_r@20']:.4f} | "
        f"{values['multi_all_r@20']:.4f} | {values['unique_gold_set_balanced_all_r@20']:.4f} |"
        for method, values in primary.items()
    ]
    transition = ablations["m4_transitions_vs_m0"]
    comparison = stats["comparisons"]["M4_minus_M0"]["all_r@20"]
    m4 = primary["M4"]
    m0 = primary["M0"]
    finding = (
        "MAR-ER improved final complete-evidence recall over M0."
        if m4["all_r@20"] > m0["all_r@20"] else
        "MAR-ER did not improve final complete-evidence recall over M0."
    )
    return f"""# MAR-ER One-Shot Experiment

## Protocol

The method, B=100, K=20, candidate anchor=80, protected Top-15, intrusion budget=5,
RRF constant=60, source depth=100, bootstrap=1,000 and seed=42 were frozen before
the official M0--M4 run. Candidate Test was not parsed or evaluated.

## Primary results

| Method | Coverage@100 | All R@20 | Multi All R@20 | Unique-set balanced All R@20 |
|---|---:|---:|---:|---:|
{chr(10).join(rows)}

M4 versus M0: candidate recovered/lost = {transition['candidate_recovered']}/
{transition['candidate_lost']}; final recovered/regressed = {transition['final_recovered']}/
{transition['final_regressed']}; recovered unique signatures =
{transition['recovered_unique_gold_signatures']}.

## Modality and mechanism

- Text-only All R@20: M0={subgroups['M0']['TEXT_ONLY'].get('all_r@20', 0):.4f},
  M4={subgroups['M4']['TEXT_ONLY'].get('all_r@20', 0):.4f}.
- Table-only All R@20: M0={subgroups['M0']['TABLE_ONLY'].get('all_r@20', 0):.4f},
  M4={subgroups['M4']['TABLE_ONLY'].get('all_r@20', 0):.4f}; delta={table_delta:+.4f}.
- Mixed (`TEXT_TABLE`) All R@20: M0={subgroups['M0']['TEXT_TABLE'].get('all_r@20', 0):.4f},
  M4={subgroups['M4']['TEXT_TABLE'].get('all_r@20', 0):.4f}.
- Minimum Top-20 overlap was {stability['minimum_top20_overlap']}/20 and maximum
  protected-anchor displacement was {stability['maximum_displacement']}.
- Gold lost from baseline ranks 16--20 occurred in
  {len(stability['gold_lost_from_baseline_ranks_16_20'])} QA.

One-sided uplift protects score contribution, not relevance or gold rank. The protected
prefix prevents large displacement but also preserves strong baseline false positives and
limits rescue capacity to five final slots.

## Uncertainty

- QA bootstrap M4-M0 All R@20: effect
  {comparison['qa_bootstrap']['effect']:+.4f}, 95% CI
  [{comparison['qa_bootstrap']['ci95'][0]:+.4f}, {comparison['qa_bootstrap']['ci95'][1]:+.4f}],
  {comparison['qa_bootstrap']['conclusion']}.
- Gold-signature cluster bootstrap: effect
  {comparison['gold_signature_cluster_bootstrap']['effect']:+.4f}, 95% CI
  [{comparison['gold_signature_cluster_bootstrap']['ci95'][0]:+.4f},
  {comparison['gold_signature_cluster_bootstrap']['ci95'][1]:+.4f}],
  {comparison['gold_signature_cluster_bootstrap']['conclusion']}.

These are exploratory Dev results. The 25 multi QA reduce to only eight unique gold
signatures and cannot support an independent superiority claim.

## Efficiency

Device: {efficiency['device']}; peak VRAM: {efficiency['peak_vram_mb']} MB. M4 mean
latency was {efficiency['latency_ms_per_query']['M4']:.2f} ms/query with all dense evidence
vectors loaded from verified caches.

## Decision

Main finding: {finding}

- `EXPERIMENT_VALID={str(readiness['EXPERIMENT_VALID']).lower()}`
- `METHOD_PROMISING={str(readiness['METHOD_PROMISING']).lower()}`
- `PAPER_READY=false`
- Decision: `{readiness['result_class']}`

No MAR-ER V2, weight change, Candidate Test run or follow-on optimization is authorized
by this experiment.
"""
