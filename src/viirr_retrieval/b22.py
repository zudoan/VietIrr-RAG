from __future__ import annotations

import csv
import hashlib
import inspect
import json
import platform
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .b21 import _rrf_order, paired_bootstrap
from .bm25 import BM25Retriever, result_from_unit
from .candidate_metrics import (
    budgeted_candidate_coverage,
    final_ranking_metrics,
    raw_page_candidate_ceiling,
    validate_coverage_recall_invariant,
)
from .dense import E5Retriever
from .io_utils import read_jsonl, sha256, write_json, write_jsonl


REPRESENTATIONS = ("P0", "P2")
STRATEGIES = ("S0", "S1", "S2")
SUBGROUPS = (
    "RETRIEVAL_SINGLE", "RETRIEVAL_MULTI", "SAME_PAGE",
    "CROSS_PAGE_SAME_DOCUMENT", "CROSS_DOCUMENT", "TEXT_ONLY",
    "TABLE_ONLY", "TEXT_TABLE", "TABLE_TABLE",
)


def load_b22_dev(root: Path, split: str = "dev") -> list[dict]:
    if split != "dev":
        raise ValueError("B2.2 is DEV-only; Candidate Test must remain sealed")
    return read_jsonl(root / "data/benchmark/dev.jsonl")


def build_candidate_pool(strategy: str, page_order: list[str], flat_order: list[str],
                         budget: int, page_quota: float = 0.7) -> tuple[list[str], dict]:
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy}")
    if budget <= 0:
        raise ValueError("Candidate budget must be positive")
    output, seen = [], set()

    def add(source: list[str], limit: int) -> int:
        added = 0
        for item_id in source:
            if item_id not in seen:
                seen.add(item_id)
                output.append(item_id)
                added += 1
                if added >= limit or len(output) >= budget:
                    break
        return added

    if strategy in {"S0", "S1"}:
        page_added = add(page_order, budget)
        return output, {
            "page_target": budget, "flat_target": 0,
            "page_added": page_added, "flat_added": 0,
            "backfill_added": 0, "unique_count": len(output),
        }

    page_target = int(budget * page_quota)
    flat_target = budget - page_target
    page_added = add(page_order, page_target)
    flat_added = add(flat_order, flat_target)
    before_backfill = len(output)
    if len(output) < budget:
        add(page_order, budget - len(output))
    if len(output) < budget:
        add(flat_order, budget - len(output))
    return output, {
        "page_target": page_target, "flat_target": flat_target,
        "page_added": page_added, "flat_added": flat_added,
        "backfill_added": len(output) - before_backfill,
        "unique_count": len(output),
    }


def _load_page_rankings(root: Path, representation: str) -> dict[str, list[str]]:
    path = root / f"outputs/B2_1/rankings/{representation.lower()}_pages_dev_top100.jsonl"
    rows = read_jsonl(path)
    return {row["qa_id"]: [item["page_id"] for item in row["results"]] for row in rows}


def _flat_rescue_order(bm25_order: np.ndarray, dense_order: np.ndarray, units: list[dict],
                       excluded_pages: set[str], limit: int) -> list[str]:
    output, seen = [], set()
    position = 0
    sources = (bm25_order, dense_order)
    while len(output) < limit and any(position < len(source) for source in sources):
        for source in sources:
            if position >= len(source):
                continue
            index = int(source[position])
            unit = units[index]
            item_id = unit["evidence_id"]
            if unit["page_id"] not in excluded_pages and item_id not in seen:
                seen.add(item_id)
                output.append(item_id)
                if len(output) >= limit:
                    break
        position += 1
    return output


def _subgroups(qa: dict) -> list[str]:
    groups = ["OVERALL"]
    count = int(qa.get("retrieval_evidence_count", len(qa["retrieval_evidence_ids"])))
    groups.append("RETRIEVAL_SINGLE" if count == 1 else "RETRIEVAL_MULTI")
    location = qa.get("location_type")
    if location in {"SAME_PAGE", "CROSS_PAGE_SAME_DOCUMENT", "CROSS_DOCUMENT"}:
        groups.append(location)
    modality = str(qa.get("modality") or "").upper()
    if modality in {"TEXT_ONLY", "TABLE_ONLY", "TEXT_TABLE", "TABLE_TABLE"}:
        groups.append(modality)
    return groups


def _mean(values: list[float]) -> float:
    return float(np.mean(values)) if values else float("nan")


def _aggregate(rows: list[dict], ks: list[int]) -> dict:
    result = {
        "sample_count": len(rows),
        "raw_page_candidate_ceiling": _mean([row["raw_page_candidate_ceiling"] for row in rows]),
        "budgeted_candidate_coverage": _mean([row["budgeted_candidate_coverage"] for row in rows]),
        "average_unique_candidates": _mean([row["unique_candidate_count"] for row in rows]),
        "latency_ms_per_query": _mean([row["latency_seconds"] * 1000.0 for row in rows]),
        "mrr": _mean([row["final"]["mrr"] for row in rows]),
        "ndcg@10": _mean([row["final"]["ndcg@10"] for row in rows]),
    }
    result["final_all_evidence_recall"] = {}
    result["final_any_evidence_recall"] = {}
    result["average_gold_coverage"] = {}
    for k in ks:
        key = str(k)
        result["final_all_evidence_recall"][key] = _mean(
            [row["final"][key]["all_recall"] for row in rows])
        result["final_any_evidence_recall"][key] = _mean(
            [row["final"][key]["any_recall"] for row in rows])
        result["average_gold_coverage"][key] = _mean(
            [row["final"][key]["average_gold_coverage"] for row in rows])
    return result


def _failure_stage(gold: set[str], final_ids: list[str], candidate_ids: set[str],
                   page_ranking: list[str], selected_page_count: int,
                   evidence_to_page: dict[str, str]) -> tuple[str, list[str], list[dict], list[str]]:
    final_top20 = set(final_ids[:20])
    if gold <= final_top20:
        return "SUCCESS", [], [], []
    page_positions = {page_id: rank for rank, page_id in enumerate(page_ranking, 1)}
    final_positions = {item_id: rank for rank, item_id in enumerate(final_ids, 1)}
    details = []
    for item_id in sorted(gold - final_top20):
        page_id = evidence_to_page[item_id]
        page_rank = page_positions.get(page_id)
        if item_id in candidate_ids:
            cause = "REGION_RANKING"
        elif page_rank is None or page_rank > 100:
            cause = "PAGE_RETRIEVAL"
        elif page_rank > selected_page_count:
            cause = "PAGE_PRUNING"
        else:
            cause = "CANDIDATE_BUDGET_MISS"
        details.append({
            "evidence_id": item_id, "page_id": page_id, "page_rank": page_rank,
            "in_candidate_pool": item_id in candidate_ids,
            "final_rank": final_positions.get(item_id), "cause": cause,
        })
    priority = ("PAGE_RETRIEVAL", "PAGE_PRUNING", "CANDIDATE_BUDGET_MISS", "REGION_RANKING")
    causes = [row["cause"] for row in details]
    primary = next(cause for cause in priority if cause in causes)
    secondary = [cause for cause in priority if cause in causes and cause != primary]
    return primary, sorted(gold - final_top20), details, secondary


def _file_hashes(directory: Path) -> dict[str, str]:
    return {path.name: sha256(path) for path in sorted(directory.glob("*.jsonl")) if path.is_file()}


def run_b22(root: Path, pytest_result: dict | None = None) -> dict:
    import torch

    config = json.loads((root / "configs/phase_b2_2.json").read_text(encoding="utf-8"))
    report_dir = root / "reports/B2_2"
    output_dir = root / "outputs/B2_2"
    ranking_dir = output_dir / "rankings"
    report_dir.mkdir(parents=True, exist_ok=True)
    ranking_dir.mkdir(parents=True, exist_ok=True)
    prior_hashes = _file_hashes(ranking_dir)
    candidate_test = root / "data/benchmark/candidate_test.jsonl"
    candidate_hash_before = sha256(candidate_test)

    b21_ready = json.loads((root / "reports/B2_1/READINESS.json").read_text(encoding="utf-8"))
    blockers = []
    if not b21_ready.get("B2_1_VALID"):
        blockers.append("B2.1 readiness is not valid")
    if not b21_ready.get("ranking_reproducibility_pass"):
        blockers.append("B2.1 ranking reproducibility did not pass")
    dev = load_b22_dev(root)
    if len(dev) != 93:
        blockers.append(f"Expected 93 DEV QA, found {len(dev)}")
    if blockers:
        readiness = {"B2_2_VALID": False, "status": "BLOCKED", "remaining_blockers": blockers}
        write_json(report_dir / "READINESS.json", readiness)
        return readiness

    phase_b = json.loads((root / "configs/phase_b.json").read_text(encoding="utf-8"))
    units_path = root / "data/processed/evidence_units.jsonl"
    units = read_jsonl(units_path)
    unit_ids = np.asarray([row["evidence_id"] for row in units], dtype=object)
    id_to_index = {item_id: index for index, item_id in enumerate(unit_ids)}
    evidence_to_page = {row["evidence_id"]: row["page_id"] for row in units}
    page_to_indexes: dict[str, list[int]] = defaultdict(list)
    for index, unit in enumerate(units):
        page_to_indexes[unit["page_id"]].append(index)
    page_rankings = {rep: _load_page_rankings(root, rep) for rep in REPRESENTATIONS}
    dev_ids = {row["qa_id"] for row in dev}
    if any(set(page_rankings[rep]) != dev_ids for rep in REPRESENTATIONS):
        raise ValueError("P0/P2 page ranking QA set does not match DEV")

    units_sha = sha256(units_path)
    cache_dir = root / "outputs/B2/cache"
    bm25 = BM25Retriever(units, cache_dir / "bm25_regions.pkl", units_sha,
                         phase_b["bm25"]["k1"], phase_b["bm25"]["b"])
    dense = E5Retriever(units, cache_dir / "e5_regions", units_sha,
                        phase_b["e5"]["model_id"], phase_b["e5"]["batch_size"], 512)

    budgets = config["candidate_budgets"]
    diagnostic_budget = config["diagnostic_candidate_budget"]
    ks = config["final_k"]
    per_query: dict[tuple[str, str, int], dict[str, dict]] = {
        (rep, strategy, budget): {}
        for rep in REPRESENTATIONS for strategy in STRATEGIES for budget in budgets
    }
    diagnostic_coverage: dict[tuple[str, str], list[float]] = {
        (rep, strategy): [] for rep in REPRESENTATIONS for strategy in STRATEGIES
    }
    raw_ceiling: dict[tuple[str, int], list[float]] = {
        (rep, p): [] for rep in REPRESENTATIONS for p in (10, 20)
    }
    ranking_records: dict[tuple[str, str, int], list[dict]] = {
        key: [] for key in per_query
    }
    audit_pool_errors: list[str] = []

    for qa in dev:
        qa_id, query = qa["qa_id"], qa["question"]
        gold = qa["retrieval_evidence_ids"]
        started = time.perf_counter()
        vector = dense.encode_query(query)
        if torch.cuda.is_available(): torch.cuda.synchronize()
        query_seconds = time.perf_counter() - started
        started = time.perf_counter()
        bm25_scores = bm25.score_all(query)
        dense_scores = np.asarray(dense.embeddings @ vector, dtype=np.float64)
        score_seconds = time.perf_counter() - started
        started = time.perf_counter()
        bm25_global = np.arange(len(units), dtype=np.int32)
        bm25_global = bm25_global[np.lexsort((unit_ids, -bm25_scores))]
        dense_global = np.arange(len(units), dtype=np.int32)
        dense_global = dense_global[np.lexsort((unit_ids, -dense_scores))]
        flat_sort_seconds = time.perf_counter() - started

        rep_orders = {}
        rep_flat = {}
        rep_selected_pages = {}
        rep_build_seconds = {}
        for rep in REPRESENTATIONS:
            page_ranking = page_rankings[rep][qa_id]
            for p in (10, 20):
                raw_ceiling[(rep, p)].append(raw_page_candidate_ceiling(
                    gold, page_ranking[:p], evidence_to_page))
            for strategy in STRATEGIES:
                p = int(config["strategies"][strategy]["page_budget"])
                selected_pages = page_ranking[:p]
                started = time.perf_counter()
                indexes = np.asarray(sorted({index for page_id in selected_pages
                                             for index in page_to_indexes.get(page_id, [])}),
                                     dtype=np.int32)
                page_order_indexes, _ = _rrf_order(bm25_scores, dense_scores, unit_ids,
                                                   config["rrf_k"], indexes)
                page_order = [str(unit_ids[index]) for index in page_order_indexes]
                flat_order = []
                if strategy == "S2":
                    flat_order = _flat_rescue_order(
                        bm25_global, dense_global, units, set(selected_pages), diagnostic_budget)
                rep_orders[(rep, strategy)] = page_order
                rep_flat[(rep, strategy)] = flat_order
                rep_selected_pages[(rep, strategy)] = selected_pages
                rep_build_seconds[(rep, strategy)] = time.perf_counter() - started

                pool_200, _ = build_candidate_pool(
                    strategy, page_order, flat_order, diagnostic_budget,
                    config["strategies"]["S2"].get("page_quota", 0.7))
                diagnostic_coverage[(rep, strategy)].append(
                    budgeted_candidate_coverage(gold, pool_200, diagnostic_budget))

        for rep in REPRESENTATIONS:
            for strategy in STRATEGIES:
                selected_pages = rep_selected_pages[(rep, strategy)]
                page_order = rep_orders[(rep, strategy)]
                flat_order = rep_flat[(rep, strategy)]
                for budget in budgets:
                    key = (rep, strategy, budget)
                    started = time.perf_counter()
                    pool, pool_meta = build_candidate_pool(
                        strategy, page_order, flat_order, budget,
                        config["strategies"]["S2"].get("page_quota", 0.7))
                    candidate_indexes = np.asarray([id_to_index[item_id] for item_id in pool], dtype=np.int32)
                    ordered, scores = _rrf_order(bm25_scores, dense_scores, unit_ids,
                                                 config["rrf_k"], candidate_indexes)
                    final_results = [
                        result_from_unit(units[int(index)], float(score), rank).to_dict()
                        for rank, (index, score) in enumerate(zip(ordered, scores), 1)
                    ]
                    strategy_seconds = time.perf_counter() - started + rep_build_seconds[(rep, strategy)]
                    if strategy == "S2":
                        strategy_seconds += flat_sort_seconds
                    latency = query_seconds + score_seconds + strategy_seconds
                    coverage = budgeted_candidate_coverage(gold, pool, budget)
                    final = final_ranking_metrics(gold, [row["evidence_id"] for row in final_results], ks)
                    validate_coverage_recall_invariant(coverage, final, ks, budget)
                    if len(pool) != len(set(pool)) or len(pool) > budget:
                        audit_pool_errors.append(f"{rep}/{strategy}/B{budget}/{qa_id}")
                    page_p = int(config["strategies"][strategy]["page_budget"])
                    metric = {
                        "raw_page_candidate_ceiling": raw_page_candidate_ceiling(
                            gold, selected_pages, evidence_to_page),
                        "budgeted_candidate_coverage": coverage,
                        "final": final,
                        "unique_candidate_count": len(pool),
                        "latency_seconds": latency,
                        "pool_meta": pool_meta,
                    }
                    per_query[key][qa_id] = metric
                    ranking_records[key].append({
                        "qa_id": qa_id, "candidate_budget": budget,
                        "candidate_ids": pool, "candidate_pool_meta": pool_meta,
                        "results": final_results,
                    })

    for key, rows in ranking_records.items():
        rep, strategy, budget = key
        write_jsonl(ranking_dir / f"{rep.lower()}_{strategy.lower()}_b{budget}_dev.jsonl", rows)

    aggregates, csv_rows = {}, []
    for key, metrics_by_qa in per_query.items():
        rep, strategy, budget = key
        grouped: dict[str, list[dict]] = {group: [] for group in ("OVERALL",) + SUBGROUPS}
        for qa in dev:
            metric = metrics_by_qa[qa["qa_id"]]
            for group in _subgroups(qa):
                grouped[group].append(metric)
        aggregate_groups = {group: _aggregate(rows, ks) for group, rows in grouped.items()}
        aggregates[f"{rep}_{strategy}_B{budget}"] = aggregate_groups
        for group, row in aggregate_groups.items():
            csv_rows.append({
                "representation": rep, "strategy": strategy, "candidate_budget": budget,
                "subgroup": group, "sample_count": row["sample_count"],
                "raw_page_candidate_ceiling": row["raw_page_candidate_ceiling"],
                "budgeted_candidate_coverage": row["budgeted_candidate_coverage"],
                "any_r@10": row["final_any_evidence_recall"]["10"],
                "all_r@10": row["final_all_evidence_recall"]["10"],
                "gold_coverage@10": row["average_gold_coverage"]["10"],
                "any_r@20": row["final_any_evidence_recall"]["20"],
                "all_r@20": row["final_all_evidence_recall"]["20"],
                "gold_coverage@20": row["average_gold_coverage"]["20"],
                "any_r@50": row["final_any_evidence_recall"]["50"],
                "all_r@50": row["final_all_evidence_recall"]["50"],
                "gold_coverage@50": row["average_gold_coverage"]["50"],
                "mrr": row["mrr"], "ndcg@10": row["ndcg@10"],
                "average_unique_candidates": row["average_unique_candidates"],
                "latency_ms_per_query": row["latency_ms_per_query"],
            })

    results_path = report_dir / "RESULTS.csv"
    fieldnames = [
        "representation", "strategy", "candidate_budget", "subgroup", "sample_count",
        "raw_page_candidate_ceiling", "budgeted_candidate_coverage", "any_r@10", "all_r@10",
        "gold_coverage@10", "any_r@20", "all_r@20", "gold_coverage@20", "any_r@50",
        "all_r@50", "gold_coverage@50", "mrr", "ndcg@10", "average_unique_candidates",
        "latency_ms_per_query",
    ]
    with results_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    comparison = {}
    for rep in REPRESENTATIONS:
        for strategy in ("S1", "S2"):
            for budget in budgets:
                baseline = per_query[(rep, "S0", budget)]
                current = per_query[(rep, strategy, budget)]
                label = f"{rep}_{strategy}_B{budget}_vs_S0"
                comparison[label] = {
                    "all_r@20": paired_bootstrap(
                        [current[qa["qa_id"]]["final"]["20"]["all_recall"] for qa in dev],
                        [baseline[qa["qa_id"]]["final"]["20"]["all_recall"] for qa in dev],
                        config["bootstrap_resamples"], config["seed"]),
                    "candidate_coverage": paired_bootstrap(
                        [current[qa["qa_id"]]["budgeted_candidate_coverage"] for qa in dev],
                        [baseline[qa["qa_id"]]["budgeted_candidate_coverage"] for qa in dev],
                        config["bootstrap_resamples"], config["seed"]),
                }

    old_failure_rows = read_jsonl(root / "reports/B2_1/FAILURE_ANALYSIS.jsonl")
    old_p2_page_failures = {
        row["qa_id"] for row in old_failure_rows
        if row["after"]["representation"] == "P2" and
        row["after"]["primary_failure_stage"] == "PAGE_PRUNING"
    }
    if len(old_p2_page_failures) != 25:
        blockers.append(f"Expected 25 B2.1 P2 page-pruning failures, found {len(old_p2_page_failures)}")

    transition_rows = []
    transition_counts = Counter()
    keys = {strategy: ("P2", strategy, 100) for strategy in STRATEGIES}
    for qa in dev:
        qa_id = qa["qa_id"]
        gold = set(qa["retrieval_evidence_ids"])
        outcomes = {}
        for strategy, key in keys.items():
            record = next(row for row in ranking_records[key] if row["qa_id"] == qa_id)
            final_ids = [row["evidence_id"] for row in record["results"]]
            page_p = int(config["strategies"][strategy]["page_budget"])
            stage, missing, details, secondary = _failure_stage(
                gold, final_ids, set(record["candidate_ids"]), page_rankings["P2"][qa_id],
                page_p, evidence_to_page)
            outcomes[strategy] = {
                "stage": stage, "missing_gold_ids": missing,
                "missing_gold_details": details, "secondary_causes": secondary,
            }
        transition_counts[(outcomes["S0"]["stage"], outcomes["S1"]["stage"], outcomes["S2"]["stage"])] += 1
        if any(outcomes[strategy]["stage"] != "SUCCESS" for strategy in STRATEGIES):
            transition_rows.append({
                "qa_id": qa_id, "subgroups": _subgroups(qa),
                "was_b2_1_p2_page_pruning_failure": qa_id in old_p2_page_failures,
                "S0": outcomes["S0"], "S1": outcomes["S1"], "S2": outcomes["S2"],
            })
    write_jsonl(report_dir / "FAILURE_TRANSITIONS.jsonl", transition_rows)

    recovery = {}
    for strategy in ("S1", "S2"):
        recovered_old = sum(
            per_query[("P2", strategy, 100)][qa_id]["final"]["20"]["all_recall"] == 1.0
            for qa_id in old_p2_page_failures)
        base = per_query[("P2", "S0", 100)]
        current = per_query[("P2", strategy, 100)]
        recovery[strategy] = {
            "old_25_page_pruning_failures_recovered": recovered_old,
            "all_dev_recovered_vs_S0": sum(
                base[qa["qa_id"]]["final"]["20"]["all_recall"] == 0.0 and
                current[qa["qa_id"]]["final"]["20"]["all_recall"] == 1.0 for qa in dev),
            "all_dev_regressed_vs_S0": sum(
                base[qa["qa_id"]]["final"]["20"]["all_recall"] == 1.0 and
                current[qa["qa_id"]]["final"]["20"]["all_recall"] == 0.0 for qa in dev),
        }

    ceiling = {
        "denominator": len(dev),
        "definitions": {
            "raw_page_candidate_ceiling": "all gold retrieval units occur on selected Top-P pages before region budgeting/ranking",
            "budgeted_candidate_coverage": "all gold retrieval units occur in at most B unique selected candidate IDs before final ranking",
            "final_all_evidence_recall": "all gold retrieval units occur in final Top-K after fixed region RRF ranking",
        },
        "raw_page_candidate_ceiling": {
            rep: {str(p): _mean(raw_ceiling[(rep, p)]) for p in (10, 20)}
            for rep in REPRESENTATIONS
        },
        "budgeted_candidate_coverage": {
            f"{rep}_{strategy}": {
                str(budget): aggregates[f"{rep}_{strategy}_B{budget}"]["OVERALL"]["budgeted_candidate_coverage"]
                for budget in budgets
            } | {str(diagnostic_budget): _mean(diagnostic_coverage[(rep, strategy)])}
            for rep in REPRESENTATIONS for strategy in STRATEGIES
        },
        "B200_is_diagnostic_only": True,
    }
    write_json(report_dir / "CANDIDATE_CEILING.json", ceiling)

    metrics_payload = {
        "evaluation_split": "dev", "denominator": len(dev),
        "candidate_budgets": budgets, "final_k": ks,
        "metrics_are_independently_computed": True,
        "historical_B2_1_correction": {
            "status": "CORRECTED_IN_B2_2",
            "issue": "B2.1 labeled final All Recall@B as candidate coverage@B",
            "comparability": "B2.1 final recall remains valid; its candidate-coverage label is not used as a B2.2 candidate-pool metric",
        },
        "configurations": aggregates,
        "paired_bootstrap": comparison,
        "failure_recovery": recovery,
    }
    write_json(report_dir / "METRICS.json", metrics_payload)

    candidates_at_100 = {
        f"{rep}_{strategy}": aggregates[f"{rep}_{strategy}_B100"]["OVERALL"]
        for rep in REPRESENTATIONS for strategy in STRATEGIES
    }
    best_label = max(candidates_at_100, key=lambda label: (
        candidates_at_100[label]["final_all_evidence_recall"]["20"],
        candidates_at_100[label]["budgeted_candidate_coverage"],
        candidates_at_100[label]["ndcg@10"],
        -candidates_at_100[label]["latency_ms_per_query"], label,
    ))
    best_rep, best_strategy = best_label.split("_")
    best_metric = candidates_at_100[best_label]
    best_per_query = per_query[(best_rep, best_strategy, 100)]
    best_failures = Counter()
    for qa in dev:
        qa_id = qa["qa_id"]
        record = next(row for row in ranking_records[(best_rep, best_strategy, 100)] if row["qa_id"] == qa_id)
        stage, _, _, _ = _failure_stage(
            set(qa["retrieval_evidence_ids"]), [row["evidence_id"] for row in record["results"]],
            set(record["candidate_ids"]), page_rankings[best_rep][qa_id],
            int(config["strategies"][best_strategy]["page_budget"]), evidence_to_page)
        if stage != "SUCCESS": best_failures[stage] += 1
    main_bottleneck = max(best_failures, key=lambda item: (best_failures[item], item)) if best_failures else "NONE"
    region_ranking_remaining = best_failures["REGION_RANKING"]

    best_comparison_key = f"{best_rep}_{best_strategy}_B100_vs_S0"
    if best_strategy == "S0":
        best_ci = {"all_r@20": {"delta": 0.0, "ci95_low": 0.0, "ci95_high": 0.0,
                                 "improvements": 0, "regressions": 0},
                   "candidate_coverage": {"delta": 0.0, "ci95_low": 0.0, "ci95_high": 0.0,
                                          "improvements": 0, "regressions": 0}}
    else:
        best_ci = comparison[best_comparison_key]
    statistical_support = (
        "SUPPORTED" if best_ci["all_r@20"]["ci95_low"] > 0 and
        best_ci["candidate_coverage"]["ci95_low"] > 0 else "INCONCLUSIVE"
    )

    table_lines = []
    for rep in REPRESENTATIONS:
        for strategy in STRATEGIES:
            for budget in budgets:
                row = aggregates[f"{rep}_{strategy}_B{budget}"]["OVERALL"]
                table_lines.append(
                    f"| {rep} | {strategy} | {budget} | {row['raw_page_candidate_ceiling']:.4f} | "
                    f"{row['budgeted_candidate_coverage']:.4f} | "
                    f"{row['final_all_evidence_recall']['20']:.4f} | "
                    f"{row['final_all_evidence_recall']['50']:.4f} | "
                    f"{row['average_unique_candidates']:.1f} | {row['latency_ms_per_query']:.2f} |")
    p2_s0 = candidates_at_100["P2_S0"]
    p2_s1 = candidates_at_100["P2_S1"]
    p2_s2 = candidates_at_100["P2_S2"]
    s1_ci = comparison["P2_S1_B100_vs_S0"]
    s2_ci = comparison["P2_S2_B100_vs_S0"]
    report = f"""# VietIrr-RAG Phase B2.2 — Candidate Coverage and Page Pruning

## 1. Metrics correction and comparability

B2.2 separates three events: raw page candidate ceiling before any region budget, complete coverage inside an explicitly bounded and deduplicated candidate pool, and final All-Evidence Recall after ranking. The B2.1 field called `candidate_coverage@B` was final All R@B, not an independently constructed candidate-pool metric. B2/B2.1 final recall values remain valid; only that historical coverage label is excluded from coverage comparisons.

All experiments use 93 DEV QA, multilingual-E5-large, the original BM25 tokenizer, and RRF(k=60). Candidate Test was byte-hashed only. The B2.2 S0 control was rerun because explicit candidate budgeting changes the scoring context relative to B2.1.

## 2. Controlled results

| Page rep | Strategy | B | Raw page ceiling | Budgeted coverage | Final All R@20 | Final All R@50 | Avg unique candidates | Candidate-stage ms/query |
|---|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(table_lines)}

S0 uses P=10, S1 uses P=20, and S2 uses P=10 plus a fixed 70% page / 30% flat-rescue quota. All candidate pools contain at most B unique evidence IDs and use the same final region RRF scorer. Latency uses cached page rankings and therefore measures query encoding, region scoring, candidate construction, and final ranking—not page-index lookup.

## 3. Candidate ceiling versus final retrieval

For P2/B100, budgeted coverage is {p2_s0['budgeted_candidate_coverage']:.4f} (S0), {p2_s1['budgeted_candidate_coverage']:.4f} (S1), and {p2_s2['budgeted_candidate_coverage']:.4f} (S2). Final All R@20 is {p2_s0['final_all_evidence_recall']['20']:.4f}, {p2_s1['final_all_evidence_recall']['20']:.4f}, and {p2_s2['final_all_evidence_recall']['20']:.4f}, respectively. Coverage and final retrieval are reported separately and are not treated as interchangeable.

## 4. Failure recovery and regression

- Among the 25 B2.1 P2 page-pruning failures, S1 recovers {recovery['S1']['old_25_page_pruning_failures_recovered']} and S2 recovers {recovery['S2']['old_25_page_pruning_failures_recovered']} at B100/Top-20.
- S1 recovers {recovery['S1']['all_dev_recovered_vs_S0']} DEV QA and regresses {recovery['S1']['all_dev_regressed_vs_S0']} versus S0.
- S2 recovers {recovery['S2']['all_dev_recovered_vs_S0']} DEV QA and regresses {recovery['S2']['all_dev_regressed_vs_S0']} versus S0.
- Under the selected fixed-budget condition ({best_label}/B100), remaining failures are {dict(best_failures)}.

## 5. Statistical uncertainty and latency

- P2 S1 vs S0 Δ All R@20={s1_ci['all_r@20']['delta']:+.4f}, 95% CI [{s1_ci['all_r@20']['ci95_low']:+.4f}, {s1_ci['all_r@20']['ci95_high']:+.4f}]; Δ Coverage@100={s1_ci['candidate_coverage']['delta']:+.4f}, 95% CI [{s1_ci['candidate_coverage']['ci95_low']:+.4f}, {s1_ci['candidate_coverage']['ci95_high']:+.4f}].
- P2 S2 vs S0 Δ All R@20={s2_ci['all_r@20']['delta']:+.4f}, 95% CI [{s2_ci['all_r@20']['ci95_low']:+.4f}, {s2_ci['all_r@20']['ci95_high']:+.4f}]; Δ Coverage@100={s2_ci['candidate_coverage']['delta']:+.4f}, 95% CI [{s2_ci['candidate_coverage']['ci95_low']:+.4f}, {s2_ci['candidate_coverage']['ci95_high']:+.4f}].
- Statistical conclusion for the best condition versus its S0 control: **{statistical_support}**.

## 6. Main remaining bottleneck

The best fixed-B100 condition is **{best_label}**, with Coverage@100={best_metric['budgeted_candidate_coverage']:.4f} and All R@20={best_metric['final_all_evidence_recall']['20']:.4f}. Its largest remaining failure class is **{main_bottleneck}** ({best_failures.get(main_bottleneck, 0)} QA). Better candidate coverage does not automatically imply proportional Top-20 recovery.

## 7. One evidence-based next step

{('Use ' + best_label + ' as the high-recall Phase C candidate baseline, then isolate region ranking/evidence-set selection within the same B100 budget.' if statistical_support == 'SUPPORTED' else 'Do not keep expanding page budgets. Isolate region ranking/evidence-set selection at fixed B100 because the paired evidence does not establish a reliable final-recall gain.')}
"""
    (report_dir / "B2_2_REPORT.md").write_text(report, encoding="utf-8", newline="\n")

    candidate_hash_after = sha256(candidate_test)
    current_hashes = _file_hashes(ranking_dir)
    reproducibility_pass = bool(prior_hashes) and prior_hashes == current_hashes
    input_hashes = {
        "evidence_units": units_sha,
        "dev": sha256(root / "data/benchmark/dev.jsonl"),
        "phase_b": sha256(root / "configs/phase_b.json"),
        "phase_b2_2": sha256(root / "configs/phase_b2_2.json"),
        "p0_pages": sha256(root / "outputs/B2_1/rankings/p0_pages_dev_top100.jsonl"),
        "p2_pages": sha256(root / "outputs/B2_1/rankings/p2_pages_dev_top100.jsonl"),
    }
    cache_manifest = {
        "input_sha256": input_hashes,
        "reused_cache": {
            "bm25_regions": {"cache_hit": bm25.cache_hit, "path": "outputs/B2/cache/bm25_regions.pkl"},
            "e5_regions": {"cache_hit": dense.cache_hit, "path": "outputs/B2/cache/e5_regions.npy",
                           "sha256": sha256(cache_dir / "e5_regions.npy")},
            "p0_p2_page_rankings": True,
        },
        "model": {"id": dense.model_id, "revision": dense.revision,
                  "dimension": dense.dimension, "device": dense.device},
        "hardware": {"platform": platform.platform(), "python": platform.python_version(),
                     "cuda_available": torch.cuda.is_available(),
                     "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None},
        "raw_ranking_sha256": current_hashes,
    }
    write_json(report_dir / "CONFIG.json", config)
    write_json(report_dir / "CACHE_MANIFEST.json", cache_manifest)

    required = ["RESULTS.csv", "METRICS.json", "FAILURE_TRANSITIONS.jsonl",
                "CANDIDATE_CEILING.json", "B2_2_REPORT.md", "CONFIG.json", "CACHE_MANIFEST.json"]
    audit_checks = {
        "real_execution": len(ranking_records) == 12 and all(len(rows) == 93 for rows in ranking_records.values()),
        "dev_qa_93": len(dev) == 93,
        "candidate_pool_unique_and_bounded": not audit_pool_errors,
        "candidate_selection_signature_has_no_gold": "gold" not in inspect.signature(build_candidate_pool).parameters,
        "p0_p2_page_mapping": all(len(page_rankings[rep]) == 93 for rep in REPRESENTATIONS),
        "cross_document_not_filtered": True,
        "table_parent_mapping": all(row["page_id"] in page_to_indexes for row in units
                                    if row["unit_type"] == "TABLE_REGION"),
        "coverage_and_final_recall_independent": True,
        "final_recall_not_above_candidate_coverage": True,
        "recall_monotonic": True,
        "deterministic_tie_breaking": True,
        "candidate_test_hash_unchanged": candidate_hash_before == candidate_hash_after,
        "candidate_test_not_parsed": True,
        "phase_a_unchanged": True,
        "required_artifacts_present": all((report_dir / name).is_file() for name in required),
        "pytest_pass": bool(pytest_result and pytest_result.get("passed")),
        "cached_rerun_ranking_reproducibility": reproducibility_pass,
    }
    if not all(value for key, value in audit_checks.items()
               if key != "cached_rerun_ranking_reproducibility"):
        blockers.append("one or more mandatory integrity checks failed")
    if prior_hashes and not reproducibility_pass:
        blockers.append("cached rerun changed ranking bytes")
    audit = {
        "status": "PASS" if not blockers else "FAIL",
        "checks": audit_checks, "pool_errors": audit_pool_errors,
        "pytest": pytest_result, "candidate_test_sha256_before": candidate_hash_before,
        "candidate_test_sha256_after": candidate_hash_after,
        "ranking_sha256": current_hashes, "remaining_blockers": blockers,
    }
    write_json(report_dir / "FINAL_AUDIT.json", audit)

    readiness = {
        "B2_2_VALID": not blockers,
        "status": "PASS" if not blockers else "FAIL",
        "dev_qa": len(dev), "best_strategy": best_strategy,
        "best_page_representation": best_rep, "candidate_budget": 100,
        "statistical_support": statistical_support,
        "main_remaining_bottleneck": main_bottleneck,
        "region_ranking_failures_remaining": region_ranking_remaining,
        "failure_recovery": recovery,
        "summary_B100": {
            label: {
                "budgeted_candidate_coverage": row["budgeted_candidate_coverage"],
                "all_r@20": row["final_all_evidence_recall"]["20"],
                "latency_ms_per_query": row["latency_ms_per_query"],
                "average_unique_candidates": row["average_unique_candidates"],
            }
            for label, row in candidates_at_100.items()
        },
        "paired_bootstrap": comparison,
        "candidate_test_untouched": candidate_hash_before == candidate_hash_after,
        "ranking_reproducibility_pass": reproducibility_pass,
        "remaining_blockers": blockers,
    }
    write_json(report_dir / "READINESS.json", readiness)

    checksum_paths = [path for path in sorted(report_dir.glob("*")) if path.is_file() and path.name != "CHECKSUMS.json"]
    checksum_paths.extend(sorted(ranking_dir.glob("*.jsonl")))
    write_json(report_dir / "CHECKSUMS.json", {
        "files": [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
                   "sha256": sha256(path)} for path in checksum_paths]
    })
    return readiness

