from __future__ import annotations

import importlib.metadata
import json
import platform
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .bm25 import BM25Retriever
from .dense import E5Retriever
from .fusion import PageRegionRetriever, RRFHybridRetriever, bounded_round_robin_union
from .io_utils import read_jsonl, sha256, write_json, write_jsonl, load_config
from .metrics import aggregate, evaluate_pages, evaluate_ranking, validate_metric_invariants


METHODS = ("bm25", "e5", "hybrid", "page_region")


def load_dev_queries(root: Path, split: str = "dev") -> list[dict]:
    if split != "dev":
        raise ValueError("B2 execution is sealed to DEV; Candidate Test must not be read")
    return read_jsonl(root / "data" / "benchmark" / "dev.jsonl")


def _page_units(pages: list[dict]) -> list[dict]:
    return [{**row, "evidence_id": row["page_id"], "unit_type": "PAGE"} for row in pages]


def _ranking_record(qa_id: str, results) -> dict:
    return {"qa_id": qa_id, "results": [row.to_dict() for row in results]}


def _ids(results) -> list[str]:
    return [row.evidence_id for row in results]


def _subgroups(row: dict) -> list[str]:
    groups = ["CORE" if not row.get("relation_type") else "CHALLENGE"]
    count = int(row.get("retrieval_evidence_count", len(row.get("retrieval_evidence_ids", []))))
    groups.append("RETRIEVAL_SINGLE" if count == 1 else "RETRIEVAL_MULTI")
    if count >= 3:
        groups.append("RETRIEVAL_3_PLUS")
    location = row.get("location_type")
    if location == "SAME_PAGE": groups.append("SAME_PAGE")
    elif location == "CROSS_PAGE_SAME_DOCUMENT": groups.append("CROSS_PAGE_SAME_DOCUMENT")
    elif location == "CROSS_DOCUMENT": groups.append("CROSS_DOCUMENT")
    modality = str(row.get("modality") or row.get("qa_type") or "").upper()
    if "TEXT_TEXT" in modality or modality == "TEXT_ONLY": groups.append("TEXT_ONLY")
    elif modality in {"TABLE_ONLY", "TABLE"}: groups.append("TABLE_ONLY")
    elif "TEXT_TABLE" in modality: groups.append("TEXT_TABLE")
    elif "TABLE_TABLE" in modality: groups.append("TABLE_TABLE")
    return groups


def _aggregate_page(per_query: list[dict], ps: list[int]) -> dict:
    return {str(p): {name: sum(row[str(p)][name] for row in per_query) / len(per_query)
                     for name in ("any_gold_page_recall", "complete_gold_page_recall")} for p in ps}


def _compact_metric(row: dict) -> dict:
    return {"sample_count": row["sample_count"], "any_r@10": row["10"]["any_recall"],
            "all_r@10": row["10"]["all_recall"], "all_r@20": row["20"]["all_recall"],
            "gold_coverage@20": row["20"]["gold_coverage"]}


def _safe_version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def run_b2(root: Path) -> dict:
    import torch

    config = load_config(root)
    report_dir = root / "reports" / "B2"
    output_dir = root / "outputs" / "B2"
    cache_dir = output_dir / "cache"
    ranking_dir = output_dir / "rankings"
    report_dir.mkdir(parents=True, exist_ok=True)
    ranking_dir.mkdir(parents=True, exist_ok=True)
    units_path = root / config["processed"]["evidence_units"]
    pages_path = root / config["processed"]["pages"]
    units = read_jsonl(units_path)
    pages = read_jsonl(pages_path)
    page_units = _page_units(pages)
    dev_path = root / "data" / "benchmark" / "dev.jsonl"
    candidate_path = root / "data" / "benchmark" / "candidate_test.jsonl"
    candidate_hash_before = sha256(candidate_path)
    dev = load_dev_queries(root)
    ks = config["evidence_k"]
    ps = config["page_p"]
    if len(dev) != 93:
        raise ValueError(f"Expected 93 DEV QA, found {len(dev)}")

    corpus_sha = sha256(units_path)
    pages_sha = sha256(pages_path)
    bm25 = BM25Retriever(units, cache_dir / "bm25_regions.pkl", corpus_sha,
                         config["bm25"]["k1"], config["bm25"]["b"])
    dense = E5Retriever(units, cache_dir / "e5_regions", corpus_sha,
                        config["e5"]["model_id"], config["e5"]["batch_size"], config["e5"]["max_length"])
    hybrid = RRFHybridRetriever(units, bm25, dense, config["hybrid"]["rrf_k"])
    page_bm25 = BM25Retriever(page_units, cache_dir / "bm25_pages.pkl", pages_sha,
                              config["bm25"]["k1"], config["bm25"]["b"])
    page_dense = E5Retriever(page_units, cache_dir / "e5_pages", pages_sha,
                             config["e5"]["model_id"], config["e5"]["batch_size"], config["e5"]["max_length"])
    page_hybrid = RRFHybridRetriever(page_units, page_bm25, page_dense, config["hybrid"]["rrf_k"])
    page_region = PageRegionRetriever(units, pages, page_hybrid, hybrid,
                                      config["page_region"]["page_top_p"])
    retrievers = {"bm25": bm25, "e5": dense, "hybrid": hybrid, "page_region": page_region}

    rankings: dict[str, dict[str, list]] = {method: {} for method in METHODS}
    query_timings = {method: 0.0 for method in METHODS}
    page_rankings: dict[str, list] = {}
    started_all = time.perf_counter()
    for row in dev:
        query, qa_id = row["question"], row["qa_id"]
        for method, retriever in retrievers.items():
            started = time.perf_counter()
            results = retriever.retrieve(query, config["top_k"])
            if method in {"e5", "hybrid", "page_region"} and torch.cuda.is_available():
                torch.cuda.synchronize()
            query_timings[method] += time.perf_counter() - started
            rankings[method][qa_id] = results
        page_rankings[qa_id] = page_region.page_ranking(query, max(ps))
    evaluation_seconds = time.perf_counter() - started_all

    for method in METHODS:
        write_jsonl(ranking_dir / f"{method}_dev_top200.jsonl",
                    (_ranking_record(row["qa_id"], rankings[method][row["qa_id"]]) for row in dev))
    write_jsonl(ranking_dir / "page_hybrid_dev_top100.jsonl",
                ({"qa_id": row["qa_id"], "results": [result.to_dict() for result in page_rankings[row["qa_id"]]]}
                 for row in dev))

    per_query_metrics: dict[str, dict[str, dict]] = {method: {} for method in METHODS}
    overall = {}
    subgroup_metrics = {}
    for method in METHODS:
        values = []
        grouped: dict[str, list] = defaultdict(list)
        for row in dev:
            metric = evaluate_ranking(row["retrieval_evidence_ids"], _ids(rankings[method][row["qa_id"]]), ks)
            per_query_metrics[method][row["qa_id"]] = metric
            values.append(metric)
            for group in _subgroups(row):
                grouped[group].append(metric)
        overall[method] = aggregate(values, ks)
        validate_metric_invariants(overall[method], ks)
        subgroup_metrics[method] = {group: _compact_metric(aggregate(items, ks))
                                    for group, items in sorted(grouped.items())}

    unit_by_id = {row["evidence_id"]: row for row in units}
    page_per_query = []
    page_candidate_coverage: dict[str, list[float]] = {str(p): [] for p in ps}
    for row in dev:
        ranked_pages = _ids(page_rankings[row["qa_id"]])
        gold_pages = sorted({unit_by_id[eid]["page_id"] for eid in row["retrieval_evidence_ids"]})
        page_per_query.append(evaluate_pages(gold_pages, ranked_pages, ps))
        for p in ps:
            candidate_ids = {units[int(index)]["evidence_id"] for index in
                             page_region.candidate_indexes(ranked_pages[:p])}
            page_candidate_coverage[str(p)].append(float(set(row["retrieval_evidence_ids"]) <= candidate_ids))
    page_diagnostics = {
        "representation": "direct_text", "retriever": "BM25+E5 RRF(k=60)",
        "gold_page_metrics": _aggregate_page(page_per_query, ps),
        "complete_candidate_coverage_by_page_budget": {
            str(p): sum(page_candidate_coverage[str(p)]) / len(dev) for p in ps},
        "page_top_p_10_is_frozen_baseline": True,
        "other_p_values_are_candidate_ceiling_diagnostics_only": True,
    }
    write_json(report_dir / "B2_PAGE_DIAGNOSTICS.json", page_diagnostics)

    budgets = [20, 50, 100, 200]
    ceiling: dict[str, dict[str, float]] = {method: {} for method in METHODS}
    ceiling["bm25_e5_union"] = {}
    for budget in budgets:
        for method in METHODS:
            ceiling[method][str(budget)] = sum(
                set(row["retrieval_evidence_ids"]) <= set(_ids(rankings[method][row["qa_id"]])[:budget])
                for row in dev) / len(dev)
        ceiling["bm25_e5_union"][str(budget)] = sum(
            set(row["retrieval_evidence_ids"]) <= set(bounded_round_robin_union(
                [_ids(rankings["bm25"][row["qa_id"]]), _ids(rankings["e5"][row["qa_id"]])], budget))
            for row in dev) / len(dev)
    candidate_ceiling = {"metric": "complete gold retrieval-unit coverage", "budgets": budgets,
                         "methods": ceiling,
                         "union_policy": "deterministic round-robin, deduplicated, exactly bounded by unique-candidate budget",
                         "diagnostic_only": ["bm25_e5_union"]}
    write_json(report_dir / "B2_CANDIDATE_CEILING.json", candidate_ceiling)

    failures = []
    oracle = {"10": [], "20": []}
    for row in dev:
        qa_id, query = row["qa_id"], row["question"]
        gold = set(row["retrieval_evidence_ids"])
        gold_pages = sorted({unit_by_id[eid]["page_id"] for eid in gold})
        ranked_pages = _ids(page_rankings[qa_id])
        page_positions = {page_id: rank for rank, page_id in enumerate(ranked_pages, 1)}
        selected = ranked_pages[:10]
        candidates = {units[int(index)]["evidence_id"] for index in page_region.candidate_indexes(selected)}
        oracle_results = page_region.retrieve_with_pages(query, gold_pages, 200)
        oracle_ids = _ids(oracle_results)
        for k in (10, 20):
            oracle[str(k)].append(float(gold <= set(oracle_ids[:k])))
        outcomes = {}
        for k in (10, 20):
            final_ids = set(_ids(rankings["page_region"][qa_id])[:k])
            if gold <= final_ids:
                outcomes[str(k)] = "SUCCESS"
            elif not set(gold_pages) <= set(selected):
                missing_pages = [page_id for page_id in gold_pages if page_id not in selected]
                if all(page_positions.get(page_id, 10**9) <= 100 for page_id in missing_pages):
                    outcomes[str(k)] = "PAGE_PRUNING_MISS"
                else:
                    outcomes[str(k)] = "PAGE_RETRIEVAL_MISS_WITHIN_100"
            elif not gold <= candidates:
                outcomes[str(k)] = "CANDIDATE_MAPPING_FAILURE"
            else:
                outcomes[str(k)] = "REGION_RANKING_FAILURE"
        if outcomes["10"] != "SUCCESS" or outcomes["20"] != "SUCCESS":
            failures.append({
                "qa_id": qa_id, "subgroups": _subgroups(row), "gold_evidence_count": len(gold),
                "gold_page_count": len(gold_pages), "gold_pages_in_top10": set(gold_pages) <= set(selected),
                "gold_page_ranks_within_top100": {page_id: page_positions.get(page_id) for page_id in gold_pages},
                "gold_regions_in_filtered_candidates": gold <= candidates,
                "candidate_count_p10": len(candidates), "outcome_at_10": outcomes["10"],
                "outcome_at_20": outcomes["20"],
                "oracle_gold_page_all_r@10": float(gold <= set(oracle_ids[:10])),
                "oracle_gold_page_all_r@20": float(gold <= set(oracle_ids[:20])),
            })
    write_jsonl(report_dir / "B2_FAILURE_DETAILS.jsonl", failures)
    k20_counts = Counter(row["outcome_at_20"] for row in failures)
    page_localization = k20_counts["PAGE_PRUNING_MISS"] + k20_counts["PAGE_RETRIEVAL_MISS_WITHIN_100"]
    bottlenecks = {
        "failed_at_k10": sum(row["outcome_at_10"] != "SUCCESS" for row in failures),
        "failed_at_k20": sum(row["outcome_at_20"] != "SUCCESS" for row in failures),
        "page_localization_failures_at_k20": page_localization,
        "page_pruning_misses_at_k20": k20_counts["PAGE_PRUNING_MISS"],
        "page_retrieval_misses_beyond_100_at_k20": k20_counts["PAGE_RETRIEVAL_MISS_WITHIN_100"],
        "candidate_mapping_failures_at_k20": k20_counts["CANDIDATE_MAPPING_FAILURE"],
        "region_ranking_failures_at_k20": k20_counts["REGION_RANKING_FAILURE"],
        "oracle_gold_page_all_r@10": sum(oracle["10"]) / len(dev),
        "oracle_gold_page_all_r@20": sum(oracle["20"]) / len(dev),
        "cross_document_failures_at_k20": sum("CROSS_DOCUMENT" in row["subgroups"] and row["outcome_at_20"] != "SUCCESS" for row in failures),
        "table_involving_failures_at_k20": sum(any(group in row["subgroups"] for group in ("TABLE_ONLY", "TEXT_TABLE", "TABLE_TABLE")) and row["outcome_at_20"] != "SUCCESS" for row in failures),
    }
    categories = {"PAGE_LOCALIZATION": page_localization,
                  "CANDIDATE_MAPPING": bottlenecks["candidate_mapping_failures_at_k20"],
                  "REGION_RANKING": bottlenecks["region_ranking_failures_at_k20"]}
    main_bottleneck = max(categories, key=lambda key: (categories[key], key))
    recommendation = {
        "PAGE_LOCALIZATION": "Prioritize page localization and cross-document page candidate recall before region reranking.",
        "CANDIDATE_MAPPING": "Prioritize lossless page-to-region/table mapping and candidate construction.",
        "REGION_RANKING": "Prioritize multi-evidence and table-aware region ranking within high-recall candidates.",
    }[main_bottleneck]
    failure_analysis = {"counts": bottlenecks, "main_bottleneck": main_bottleneck,
                        "recommended_phase_c_direction": recommendation,
                        "oracle_is_diagnostic_only": True}
    failure_md = f"""# Phase B2 Failure Diagnosis

At K=20, Page→Region has {bottlenecks['failed_at_k20']} incomplete-evidence failures among {len(dev)} DEV QA.

- Page localization/pruning: {page_localization}
- Page pruning miss (gold page within Top-100 but outside Top-10): {bottlenecks['page_pruning_misses_at_k20']}
- Page retrieval miss beyond Top-100: {bottlenecks['page_retrieval_misses_beyond_100_at_k20']}
- Candidate mapping: {bottlenecks['candidate_mapping_failures_at_k20']}
- Region ranking after complete candidate coverage: {bottlenecks['region_ranking_failures_at_k20']}
- Cross-document failures: {bottlenecks['cross_document_failures_at_k20']}
- Table-involving failures: {bottlenecks['table_involving_failures_at_k20']}

Oracle gold-page diagnostics recover All R@10={bottlenecks['oracle_gold_page_all_r@10']:.4f} and All R@20={bottlenecks['oracle_gold_page_all_r@20']:.4f}. The oracle is diagnostic only and is not a deployable baseline.

Main bottleneck: **{main_bottleneck}**.

Recommended Phase C direction: {recommendation}
"""
    (report_dir / "B2_FAILURE_ANALYSIS.md").write_text(failure_md, encoding="utf-8")

    metrics_payload = {
        "evaluation_split": "dev", "dev_qa": len(dev),
        "dev_retrieval_multi": sum(row["retrieval_evidence_count"] >= 2 for row in dev),
        "evidence_k": ks, "denominator": len(dev),
        "gold_field": "retrieval_evidence_ids", "tie_breaking": "score descending, then evidence_id ascending",
        "missing_gold_in_top_k": "zero contribution", "overall": overall,
        "subgroups": subgroup_metrics, "page_metrics": page_diagnostics["gold_page_metrics"],
    }
    write_json(report_dir / "B2_BASELINE_METRICS.json", metrics_payload)

    best_method = max(METHODS, key=lambda method: (overall[method]["20"]["all_recall"], method))
    table_rows = "\n".join(
        f"| {method.replace('_', ' ').title()} | {overall[method]['10']['any_recall']:.4f} | "
        f"{overall[method]['10']['all_recall']:.4f} | {overall[method]['20']['all_recall']:.4f} | "
        f"{overall[method]['mrr']:.4f} | {overall[method]['ndcg@10']:.4f} |" for method in METHODS)
    table_group = subgroup_metrics[best_method].get("TABLE_ONLY", {})
    multi_group = subgroup_metrics[best_method].get("RETRIEVAL_MULTI", {})
    cross_group = subgroup_metrics[best_method].get("CROSS_DOCUMENT", {})
    report_md = f"""# VietIrr-RAG Phase B2 — Retrieval Baselines

## DEV results

| Method | Any R@10 | All R@10 | All R@20 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|
{table_rows}

All 93 DEV QA are evaluated against `retrieval_evidence_ids`. Candidate Test remains sealed. Index text comes only from frozen source regions/tables and never from QA, answers, or gold annotations.

## Research questions

1. **Method differences.** BM25 is lexical Unicode retrieval; E5 is fixed multilingual dense inference; Hybrid combines complete rankings with RRF(k=60); Page→Region first retrieves pages using source page text, hard-prunes to Top-10 pages, then applies the same region Hybrid.
2. **Best All-Evidence Recall.** `{best_method}` has the highest DEV All R@20 ({overall[best_method]['20']['all_recall']:.4f}).
3. **Page→Region advantage.** Its All R@20 is {overall['page_region']['20']['all_recall']:.4f}, versus Flat Hybrid {overall['hybrid']['20']['all_recall']:.4f}; no Finance result is reused.
4. **Table retrieval.** For the best method, TABLE_ONLY has n={table_group.get('sample_count', 0)}, All R@20={table_group.get('all_r@20', 0):.4f}. Small subgroups are descriptive, not conclusive.
5. **Multi/cross-document.** RETRIEVAL_MULTI All R@20={multi_group.get('all_r@20', 0):.4f}; CROSS_DOCUMENT All R@20={cross_group.get('all_r@20', 0):.4f}. Page→Region cross-document failures at K=20: {bottlenecks['cross_document_failures_at_k20']}.
6. **Main bottleneck.** `{main_bottleneck}`, based on {categories} at K=20.
7. **Phase C priority.** {recommendation}

## Candidate ceiling

Complete-coverage values at budgets 20/50/100/200 are recorded in `B2_CANDIDATE_CEILING.json`. The BM25+E5 union is a bounded, deduplicated diagnostic baseline, not a proposed method.

## Reproducibility boundaries

- E5 model: `{dense.model_id}` revision `{dense.revision}`, query/passages prefixes enabled, max length 512, L2 normalization.
- Region truncation: {dense.metadata['truncated_count']}/{len(units)} ({dense.metadata['truncated_rate']:.2%}).
- Page truncation: {page_dense.metadata['truncated_count']}/{len(pages)} ({page_dense.metadata['truncated_rate']:.2%}).
- GPU and CPU timings are stored separately in the experiment manifest.
- `HUMAN_VALIDATED=false`.
"""
    (report_dir / "B2_BASELINE_REPORT.md").write_text(report_md, encoding="utf-8")

    candidate_hash_after = sha256(candidate_path)
    manifest = {
        "experiment": "VIETIRR_RAG_PHASE_B2", "evaluation_split": "dev",
        "candidate_test_bytes_hashed_only": True,
        "candidate_test_annotations_loaded_by_runner": False,
        "candidate_test_used_for_evaluation_or_tuning": False,
        "candidate_test_hash_before": candidate_hash_before, "candidate_test_hash_after": candidate_hash_after,
        "input_sha256": {"evidence_units": corpus_sha, "pages": pages_sha, "dev": sha256(dev_path)},
        "corpus_counts": {"evidence_units": len(units), "pages": len(pages)},
        "model": {"id": dense.model_id, "revision": dense.revision, "embedding_dimension": dense.dimension,
                  "query_prefix": "query: ", "passage_prefix": "passage: ", "max_length": dense.max_length,
                  "normalized": True, "similarity": "inner_product_on_L2_normalized_vectors",
                  "training": "none", "device": dense.device,
                  "region_embedding": dense.metadata, "page_embedding": page_dense.metadata},
        "software": {name: _safe_version(name) for name in
                     ("torch", "transformers", "sentence-transformers", "numpy", "scipy", "pytest")},
        "hardware": {"platform": platform.platform(), "python": platform.python_version(),
                     "cuda_available": torch.cuda.is_available(), "cuda_version": torch.version.cuda,
                     "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None},
        "timing_seconds": {"bm25_region_index_cpu": bm25.build_seconds,
                           "bm25_page_index_cpu": page_bm25.build_seconds,
                           "e5_region_embedding_gpu" if dense.device == "cuda" else "e5_region_embedding_cpu": dense.metadata.get("embedding_seconds", 0.0),
                           "e5_page_embedding_gpu" if page_dense.device == "cuda" else "e5_page_embedding_cpu": page_dense.metadata.get("embedding_seconds", 0.0),
                           "e5_query_encoding_gpu" if dense.device == "cuda" else "e5_query_encoding_cpu": dense.query_seconds,
                           "e5_page_query_encoding_gpu" if page_dense.device == "cuda" else "e5_page_query_encoding_cpu": page_dense.query_seconds,
                           "end_to_end_mixed_cpu_gpu_diagnostic_by_method": query_timings,
                           "evaluation_total_mixed_diagnostic": evaluation_seconds},
        "cache": {"bm25_region_hit": bm25.cache_hit, "bm25_page_hit": page_bm25.cache_hit,
                  "e5_region_hit": dense.cache_hit, "e5_page_hit": page_dense.cache_hit},
        "frozen_config": config, "human_validated": False,
    }
    write_json(report_dir / "B2_EXPERIMENT_MANIFEST.json", manifest)
    write_json(report_dir / "B2_FAILURE_SUMMARY.json", failure_analysis)
    return {"overall": overall, "failure_analysis": failure_analysis,
            "candidate_ceiling": candidate_ceiling, "manifest": manifest}
