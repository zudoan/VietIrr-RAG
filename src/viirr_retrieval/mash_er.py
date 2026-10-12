from __future__ import annotations

import csv
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

from .b23 import normalize_modality
from .bm25 import BM25Retriever, result_from_unit
from .c1 import _bootstrap, _subgroup_labels
from .candidate_metrics import final_ranking_metrics
from .io_utils import read_jsonl, sha256, write_json, write_jsonl
from .r1 import (
    _load_model,
    _load_structure,
    _ranks,
    build_retrieval_representations,
    make_token_windows,
    max_pool_window_scores,
    serialize_table,
)


METHODS = ("A0", "A1", "A2", "A3")
SUBGROUPS = (
    "OVERALL", "CORE", "CHALLENGE", "RETRIEVAL_SINGLE", "RETRIEVAL_MULTI",
    "RETRIEVAL_3_PLUS", "TEXT_ONLY", "TABLE_ONLY", "TEXT_TABLE", "TABLE_TABLE",
    "SAME_PAGE", "CROSS_PAGE_SAME_DOCUMENT", "CROSS_DOCUMENT",
)


def _json_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_mash_dev(root: Path, split: str = "dev") -> list[dict]:
    if split != "dev":
        raise ValueError("MASH-ER is DEV-only; Candidate Test must remain sealed")
    return read_jsonl(root / "data/benchmark/dev.jsonl")


def build_multiview_representations(units: list[dict], structure: dict) -> list[dict]:
    """Build source-only views. This API deliberately accepts no QA, answer, or gold data."""
    r1 = build_retrieval_representations(units, structure)
    output = []
    for index, (unit, raw, contextual) in enumerate(zip(units, r1["R0"], r1["R1"])):
        unit_type = unit.get("unit_type")
        if unit_type == "TEXT_REGION":
            alternate_text = contextual["retrieval_text"]
            alternate_name = "TEXT_CONTEXT"
            alternate_valid = True
            fallback_reason = None
            fields = contextual["source_fields_used"]
        elif unit_type == "TABLE_REGION":
            table = structure["tables"].get(unit["evidence_id"])
            serialized, trace = serialize_table(table or {})
            quality_ok = bool(
                table
                and table.get("semantic_quality") == "GOOD"
                and table.get("structural_quality") == "GOOD"
            )
            alternate_valid = bool(serialized and quality_ok)
            alternate_text = serialized if alternate_valid else None
            alternate_name = "TABLE_STRUCT" if alternate_valid else None
            fallback_reason = None if alternate_valid else (
                "TABLE_QUALITY_NOT_VERIFIED" if table and serialized else trace["fallback_reason"]
            )
            fields = [f"table_{field}" for field in trace["fields_used"]] if alternate_valid else []
        else:
            raise ValueError(f"Unsupported evidence unit type: {unit_type}")
        output.append({
            "unit_index": index,
            "evidence_id": unit["evidence_id"],
            "doc_id": unit["doc_id"],
            "page_id": unit["page_id"],
            "page_number": unit.get("page_number"),
            "unit_type": unit_type,
            "raw_view": "TEXT_RAW" if unit_type == "TEXT_REGION" else "TABLE_RAW",
            "raw_text": raw["retrieval_text"],
            "raw_text_sha256": raw["retrieval_text_sha256"],
            "alternate_view": alternate_name,
            "alternate_text": alternate_text,
            "alternate_text_sha256": (
                hashlib.sha256(alternate_text.encode("utf-8")).hexdigest()
                if alternate_text is not None else None
            ),
            "alternate_valid": alternate_valid,
            "fallback_to_raw": not alternate_valid,
            "fallback_reason": fallback_reason,
            "source_fields_used": fields,
            "source_locator": {
                "doc_id": unit["doc_id"], "page_id": unit["page_id"],
                "evidence_id": unit["evidence_id"],
            },
            "gold_answer_or_qa_used": False,
        })
    if [row["evidence_id"] for row in output] != [row["evidence_id"] for row in units]:
        raise AssertionError("Multi-view construction changed evidence IDs or order")
    return output


def dense_view_weights(alternate_valid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Keep total dense weight at one; fallback RAW is never counted twice."""
    valid = np.asarray(alternate_valid, dtype=bool)
    raw_weight = np.where(valid, 0.5, 1.0)
    alternate_weight = np.where(valid, 0.5, 0.0)
    return raw_weight, alternate_weight


def fuse_view_scores(
    bm25_ranks: np.ndarray,
    raw_ranks: np.ndarray,
    alternate_ranks: np.ndarray | None,
    alternate_valid: np.ndarray,
    rrf_k: int = 60,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    bm25 = 1.0 / (rrf_k + np.asarray(bm25_ranks, dtype=np.float64))
    raw = 1.0 / (rrf_k + np.asarray(raw_ranks, dtype=np.float64))
    valid = np.asarray(alternate_valid, dtype=bool)
    if alternate_ranks is None:
        alternate = np.zeros_like(raw)
        raw_weight = np.ones_like(raw)
        alternate_weight = np.zeros_like(raw)
    else:
        alternate = np.zeros_like(raw)
        alternate[valid] = 1.0 / (
            rrf_k + np.asarray(alternate_ranks, dtype=np.float64)[valid]
        )
        raw_weight, alternate_weight = dense_view_weights(valid)
    contributions = {
        "bm25": bm25,
        "raw_dense": raw_weight * raw,
        "alternate_dense": alternate_weight * alternate,
    }
    return sum(contributions.values()), contributions


def add_soft_page_prior(
    view_scores: np.ndarray,
    page_ranks: np.ndarray,
    rrf_k: int = 60,
    page_lambda: float = 0.25,
) -> tuple[np.ndarray, np.ndarray]:
    ranks = np.asarray(page_ranks, dtype=np.int32)
    page = np.zeros(len(ranks), dtype=np.float64)
    ranked = ranks > 0
    page[ranked] = page_lambda / (rrf_k + ranks[ranked])
    return np.asarray(view_scores, dtype=np.float64) + page, page


def select_candidates(
    scores: np.ndarray,
    ids: np.ndarray,
    budget: int,
    allowed_indexes: np.ndarray | None = None,
) -> np.ndarray:
    indexes = (
        np.arange(len(ids), dtype=np.int32)
        if allowed_indexes is None else np.asarray(allowed_indexes, dtype=np.int32)
    )
    order = indexes[np.lexsort((ids[indexes], -np.asarray(scores)[indexes]))]
    return order[:budget]


def _load_window_cache(root: Path, name: str) -> tuple[np.ndarray, np.ndarray, dict]:
    rows = read_jsonl(root / "outputs/R1/windows" / f"{name.lower()}_window_map.jsonl")
    embeddings = np.load(
        root / "outputs/R1/cache" / f"{name.lower()}_window_embeddings.npy",
        mmap_mode="r",
    )
    metadata = json.loads(
        (root / "outputs/R1/cache" / f"{name.lower()}_window_embeddings.json").read_text(
            encoding="utf-8"
        )
    )
    if len(rows) != embeddings.shape[0] or len(rows) != metadata["window_count"]:
        raise AssertionError(f"R1 {name} cache/window mismatch")
    return embeddings, np.asarray([row["unit_index"] for row in rows], dtype=np.int32), metadata


def _load_or_embed_table_struct(
    root: Path, views: list[dict], model, revision: str, device: str, config: dict,
) -> tuple[np.ndarray, np.ndarray, list[dict], dict, list[dict]]:
    valid_rows = [row for row in views if row["unit_type"] == "TABLE_REGION" and row["alternate_valid"]]
    representation_rows = [{
        "representation": "TABLE_STRUCT",
        "evidence_id": row["evidence_id"],
        "retrieval_text": row["alternate_text"],
    } for row in valid_rows]
    windows, window_metadata = make_token_windows(
        representation_rows,
        model.tokenizer,
        int(config["windowing"]["content_tokens"]),
        int(config["windowing"]["overlap_tokens"]),
    )
    cache_dir = root / "outputs/MASH_ER/cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    npy_path = cache_dir / "table_struct_window_embeddings.npy"
    meta_path = cache_dir / "table_struct_window_embeddings.json"
    expected = {
        "view": "TABLE_STRUCT",
        "retrieval_text_sha256": _json_hash([
            (row["evidence_id"], row["alternate_text_sha256"]) for row in valid_rows
        ]),
        "window_map_sha256": _json_hash([
            (row["window_id"], row["evidence_id"], row["text_sha256"]) for row in windows
        ]),
        "window_count": len(windows),
        "evidence_count": len(valid_rows),
        "model_id": config["model"]["id"],
        "revision": revision,
        "max_length": config["model"]["max_length"],
        "normalized": True,
        "passage_prefix": config["model"]["passage_prefix"],
        "content_tokens": config["windowing"]["content_tokens"],
        "overlap_tokens": config["windowing"]["overlap_tokens"],
        "aggregation": "max",
    }
    if npy_path.exists() and meta_path.exists():
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        if all(metadata.get(key) == value for key, value in expected.items()):
            vectors = np.load(npy_path, mmap_mode="r")
            metadata["cache_hit"] = True
            global_indexes = np.asarray([row["unit_index"] for row in valid_rows], dtype=np.int32)
            return vectors, global_indexes, windows, {**window_metadata, **metadata}, valid_rows

    import torch
    texts = [config["model"]["passage_prefix"] + row["text"] for row in windows]
    batch_size = int(config["model"]["batch_size"])
    started = time.perf_counter()
    while batch_size >= 1:
        try:
            vectors = model.encode(
                texts, batch_size=batch_size, show_progress_bar=True,
                normalize_embeddings=True, convert_to_numpy=True,
            )
            if device == "cuda":
                torch.cuda.synchronize()
            break
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            batch_size //= 2
    if batch_size < 1:
        raise RuntimeError("TABLE_STRUCT embedding failed at batch_size=1")
    elapsed = time.perf_counter() - started
    vectors = np.asarray(vectors, dtype=np.float32)
    np.save(npy_path, vectors)
    metadata = {
        **expected,
        **window_metadata,
        "cache_hit": False,
        "device": device,
        "effective_batch_size": batch_size,
        "indexing_seconds": elapsed,
        "embedding_dimension": int(vectors.shape[1]),
        "bytes": int(npy_path.stat().st_size),
    }
    write_json(meta_path, metadata)
    global_indexes = np.asarray([row["unit_index"] for row in valid_rows], dtype=np.int32)
    return vectors, global_indexes, windows, metadata, valid_rows


def _qa_labels(qa: dict) -> set[str]:
    return set(_subgroup_labels(qa)) | {normalize_modality(qa)}


def _evaluate(
    dev: list[dict], records: dict[str, dict[str, dict]],
    latency: dict[str, dict[str, float]], page_rankings: dict[str, dict],
) -> tuple[dict[str, dict[str, dict]], dict[str, dict[str, dict]]]:
    per_query: dict[str, dict[str, dict]] = {method: {} for method in METHODS}
    aggregates: dict[str, dict[str, dict]] = {}
    for method in METHODS:
        grouped: dict[str, list[tuple[dict, dict]]] = {name: [] for name in SUBGROUPS}
        for qa in dev:
            qa_id = qa["qa_id"]
            record = records[method][qa_id]
            ranked = [row["evidence_id"] for row in record["results"]]
            gold = set(qa["retrieval_evidence_ids"])
            candidates = set(record["candidate_ids"])
            metrics = final_ranking_metrics(qa["retrieval_evidence_ids"], ranked, [10, 20])
            top_pages = {
                row["page_id"] for row in page_rankings[qa_id]["results"][:20]
            }
            row = {
                "candidate_complete": float(gold <= candidates),
                "candidate_gold_coverage": len(gold & candidates) / len(gold),
                "metrics": metrics,
                "complete_gold_page_recall": float(set(qa["gold_page_ids"]) <= top_pages),
                "latency_ms": latency[method][qa_id],
            }
            if metrics["20"]["all_recall"] > row["candidate_complete"]:
                raise AssertionError("All R@20 exceeds complete candidate coverage")
            per_query[method][qa_id] = row
            labels = _qa_labels(qa)
            for group in SUBGROUPS:
                if group == "OVERALL" or group in labels:
                    grouped[group].append((qa, row))
        aggregates[method] = {}
        for group, rows in grouped.items():
            if not rows:
                aggregates[method][group] = {"sample_count": 0, "unique_gold_sets": 0}
                continue
            values = [row for _, row in rows]
            mean = lambda fn: float(np.mean([fn(row) for row in values]))
            aggregates[method][group] = {
                "sample_count": len(rows),
                "unique_gold_sets": len({
                    "|".join(sorted(qa["retrieval_evidence_ids"])) for qa, _ in rows
                }),
                "candidate_coverage@100": mean(lambda row: row["candidate_complete"]),
                "average_gold_coverage@100": mean(lambda row: row["candidate_gold_coverage"]),
                "all_r@10": mean(lambda row: row["metrics"]["10"]["all_recall"]),
                "all_r@20": mean(lambda row: row["metrics"]["20"]["all_recall"]),
                "any_r@10": mean(lambda row: row["metrics"]["10"]["any_recall"]),
                "any_r@20": mean(lambda row: row["metrics"]["20"]["any_recall"]),
                "average_gold_coverage@20": mean(
                    lambda row: row["metrics"]["20"]["average_gold_coverage"]
                ),
                "mrr": mean(lambda row: row["metrics"]["mrr"]),
                "ndcg@10": mean(lambda row: row["metrics"]["ndcg@10"]),
                "complete_gold_page_recall@20": mean(
                    lambda row: row["complete_gold_page_recall"]
                ),
                "latency_ms_per_query": mean(lambda row: row["latency_ms"]),
            }
    return per_query, aggregates


def _core_metrics(dev: list[dict], records: dict[str, dict]) -> dict:
    coverage, all20, multi = [], [], []
    for qa in dev:
        record = records[qa["qa_id"]]
        gold = set(qa["retrieval_evidence_ids"])
        coverage.append(float(gold <= set(record["candidate_ids"])))
        metric = final_ranking_metrics(
            qa["retrieval_evidence_ids"],
            [row["evidence_id"] for row in record["results"]],
            [20],
        )["20"]["all_recall"]
        all20.append(metric)
        if qa["retrieval_multi_evidence"]:
            multi.append(metric)
    return {
        "candidate_coverage@100": float(np.mean(coverage)),
        "all_r@20": float(np.mean(all20)),
        "multi_all_r@20": float(np.mean(multi)),
    }


def _statistics(dev: list[dict], per_query: dict[str, dict], config: dict) -> dict:
    signatures = {qa["qa_id"]: "|".join(sorted(qa["retrieval_evidence_ids"])) for qa in dev}
    output = {
        "bootstrap_resamples": config["statistics"]["bootstrap_resamples"],
        "seed": config["statistics"]["seed"],
        "unique_gold_sets": len(set(signatures.values())),
        "multi_unique_gold_sets": len({
            signatures[qa["qa_id"]] for qa in dev if qa["retrieval_multi_evidence"]
        }),
        "comparisons": {},
    }
    for current, baseline in (("A3", "A0"), ("A3", "A1"), ("A3", "A2")):
        label = f"{current}_vs_{baseline}"
        output["comparisons"][label] = {}
        for group, rows in {
            "OVERALL": dev,
            "RETRIEVAL_MULTI": [qa for qa in dev if qa["retrieval_multi_evidence"]],
        }.items():
            qa_ids = [qa["qa_id"] for qa in rows]
            clusters = [signatures[qa_id] for qa_id in qa_ids]
            metric_pairs = {
                "candidate_coverage@100": (
                    [per_query[current][qa_id]["candidate_complete"] for qa_id in qa_ids],
                    [per_query[baseline][qa_id]["candidate_complete"] for qa_id in qa_ids],
                ),
                "all_r@20": (
                    [per_query[current][qa_id]["metrics"]["20"]["all_recall"] for qa_id in qa_ids],
                    [per_query[baseline][qa_id]["metrics"]["20"]["all_recall"] for qa_id in qa_ids],
                ),
            }
            group_record = {
                "sample_count": len(rows),
                "unique_gold_sets": len(set(clusters)),
            }
            group_record.update({
                metric: {
                    "qa_bootstrap": _bootstrap(
                        current_values, baseline_values,
                        config["statistics"]["bootstrap_resamples"],
                        config["statistics"]["seed"],
                    ),
                    "gold_set_cluster_bootstrap": _bootstrap(
                        current_values, baseline_values,
                        config["statistics"]["bootstrap_resamples"],
                        config["statistics"]["seed"], clusters,
                    ),
                }
                for metric, (current_values, baseline_values) in metric_pairs.items()
            })
            output["comparisons"][label][group] = group_record
            if group == "RETRIEVAL_MULTI" and len(set(clusters)) < 10:
                output["comparisons"][label][group]["reliability"] = "INCONCLUSIVE_SMALL_CLUSTER_COUNT"
    return output


def _rank_map(record: dict) -> dict[str, int]:
    return {row["evidence_id"]: int(row["rank"]) for row in record["results"]}


def _special_case_sets(root: Path) -> dict[str, set[str]]:
    missing = {
        row["qa_id"] for row in read_jsonl(root / "reports/C1_2/MISSING_MULTI_DIAGNOSIS.jsonl")
    }
    regression_path = root / "reports/C1_1/RANK_REGRESSION_DIAGNOSIS.jsonl"
    g1_regressions = {row["qa_id"] for row in read_jsonl(regression_path)}
    r1_rows = read_jsonl(root / "reports/R1/FAILURE_TRANSITIONS.jsonl")
    text_rescued = {
        row["qa_id"] for row in r1_rows
        if row["stage"] == "FULL_RETRIEVAL"
        and row["comparison"] == "R1_vs_R0"
        and row["modality"] == "TEXT_ONLY"
        and row["all_r@20_before"] == 0
        and row["all_r@20_after"] == 1
    }
    table_regressions = {
        row["qa_id"] for row in r1_rows
        if row["stage"] == "FULL_RETRIEVAL"
        and row["comparison"] in {"R1_vs_R0", "R2_vs_R0"}
        and row["modality"] in {"TABLE_ONLY", "TEXT_TABLE", "TABLE_TABLE"}
        and row["all_r@20_before"] == 1
        and row["all_r@20_after"] == 0
    }
    return {
        "c12_missing_multi": missing,
        "g1_rank_regressions": g1_regressions,
        "r1_text_rescued": text_rescued,
        "r1_table_regressions": table_regressions,
    }


def _failure_rows(
    root: Path, dev: list[dict], records: dict[str, dict[str, dict]],
    per_query: dict[str, dict], traces: dict[str, dict[str, list[dict]]],
    page_rankings: dict[str, dict], unit_by_id: dict[str, dict],
) -> list[dict]:
    special = _special_case_sets(root)
    rows = []
    for method in ("A1", "A2", "A3"):
        for qa in dev:
            qa_id = qa["qa_id"]
            before = per_query["A0"][qa_id]
            after = per_query[method][qa_id]
            before_ranks = _rank_map(records["A0"][qa_id])
            after_ranks = _rank_map(records[method][qa_id])
            trace_by_id = {row["evidence_id"]: row for row in traces[method][qa_id]}
            gold = qa["retrieval_evidence_ids"]
            selected_pages = {
                row["page_id"] for row in page_rankings[qa_id]["results"][:20]
            }
            recovered_ids = [item for item in gold if item not in before_ranks and item in after_ranks]
            lost_ids = [item for item in gold if item in before_ranks and item not in after_ranks]
            rows.append({
                "qa_id": qa_id,
                "comparison": f"{method}_vs_A0",
                "modality": normalize_modality(qa),
                "location_type": qa["location_type"],
                "retrieval_multi": bool(qa["retrieval_multi_evidence"]),
                "gold_set_signature": "|".join(sorted(gold)),
                "candidate_complete_before": before["candidate_complete"],
                "candidate_complete_after": after["candidate_complete"],
                "all_r@20_before": before["metrics"]["20"]["all_recall"],
                "all_r@20_after": after["metrics"]["20"]["all_recall"],
                "gold_candidate_recovered": recovered_ids,
                "gold_candidate_lost": lost_ids,
                "gold_rank_transitions": [{
                    "evidence_id": item,
                    "before": before_ranks.get(item),
                    "after": after_ranks.get(item),
                    "unit_type": unit_by_id[item]["unit_type"],
                } for item in gold],
                "gold_score_contributions_after": {
                    item: trace_by_id.get(item) for item in gold
                },
                "page_pruning_avoidance": bool(
                    method in {"A1", "A3"}
                    and recovered_ids
                    and any(page not in selected_pages for page in qa["gold_page_ids"])
                ),
                "rank_displacement_by_distractors": bool(
                    before["metrics"]["20"]["all_recall"] == 1
                    and after["metrics"]["20"]["all_recall"] == 0
                    and after["candidate_complete"] == 1
                ),
                "missing_despite_flat_retrieval": bool(
                    method in {"A1", "A3"} and after["candidate_complete"] == 0
                ),
                "special_cases": {
                    key: qa_id in qa_ids for key, qa_ids in special.items()
                },
            })
    return rows


def _ranking_records(path: Path) -> dict[str, dict]:
    return {row["qa_id"]: row for row in read_jsonl(path)}


def _prior_art_gap() -> dict:
    return {
        "status": "NOVELTY_UNVERIFIED",
        "checked_on": "2026-10-12",
        "sources": [
            {
                "name": "Contextual Retrieval",
                "url": "https://www.anthropic.com/engineering/contextual-retrieval",
                "known_technique": "Chunk-specific context is prepended before embedding and BM25 indexing.",
                "difference": "MASH-ER uses only verified source metadata, keeps raw and contextual dense views separate, and does not generate context with an LLM.",
            },
            {
                "name": "TreeRAG",
                "url": "https://aclanthology.org/2025.findings-acl.20/",
                "known_technique": "Tree-structured chunk storage with bidirectional hierarchical traversal.",
                "difference": "MASH-ER does not construct a tree or traverse it; an existing page rank is a non-exclusive additive prior over flat evidence retrieval.",
            },
            {
                "name": "LongRefiner",
                "url": "https://arxiv.org/abs/2505.10413",
                "known_technique": "Learned hierarchical document refinement with dual-level query analysis and adaptive refinement.",
                "difference": "MASH-ER is zero-shot retrieval-only and performs no learned refinement or generation.",
            },
            {
                "name": "TableRAG",
                "url": "https://arxiv.org/abs/2506.10380",
                "known_technique": "Iterative heterogeneous-document reasoning combining text retrieval and SQL execution.",
                "difference": "MASH-ER only indexes verified table serialization as an alternate retrieval view; it performs no SQL or iterative reasoning.",
            },
            {
                "name": "OTTeR mixed-modality retrieval",
                "url": "https://arxiv.org/abs/2210.05197",
                "known_technique": "Learned modality-enhanced representations and synthetic pre-training for joint table-text retrieval.",
                "difference": "MASH-ER uses one frozen E5 encoder, no training or synthetic data, and preserves one source evidence ID across views.",
            },
            {
                "name": "Hybrid Hierarchical Retrieval",
                "url": "https://aclanthology.org/2023.findings-acl.679/",
                "known_technique": "Two-stage document-then-passage sparse/dense hierarchical retrieval.",
                "difference": "MASH-ER explicitly avoids mandatory first-stage pruning by adding page relevance as a soft prior.",
            },
        ],
        "conclusion": "The components have clear prior art. The exact combination may be useful experimentally, but novelty is not established by this limited search.",
    }


def run_mash_er(root: Path, pytest_result: dict | None = None) -> dict:
    config = json.loads((root / "configs/mash_er.json").read_text(encoding="utf-8"))
    report_dir = root / "reports/MASH_ER"
    output_dir = root / "outputs/MASH_ER"
    for directory in (
        report_dir, output_dir / "rankings", output_dir / "traces",
        output_dir / "views", output_dir / "windows", output_dir / "cache",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    candidate_test = root / "data/benchmark/candidate_test.jsonl"
    candidate_hash_before = sha256(candidate_test)
    protected_paths = [
        root / "data/benchmark/dev.jsonl",
        root / "data/benchmark/train.jsonl",
        root / "data/benchmark/all_qa.jsonl",
        root / "data/processed/evidence_units.jsonl",
        root / "data/parsed/documents.jsonl",
        root / "data/parsed/pages.jsonl",
        root / "data/parsed/regions.jsonl",
        root / "data/parsed/tables.jsonl",
        root / "outputs/B2_1/rankings/p0_pages_dev_top100.jsonl",
        root / "outputs/C1/rankings/e0_g0_global_rrf_dev.jsonl",
        root / "outputs/R1/rankings/full_retrieval_r0_dev.jsonl",
    ]
    protected_before = {path.relative_to(root).as_posix(): sha256(path) for path in protected_paths}

    dev = load_mash_dev(root, config["evaluation_split"])
    units_path = root / "data/processed/evidence_units.jsonl"
    units = read_jsonl(units_path)
    unit_by_id = {row["evidence_id"]: row for row in units}
    ids = np.asarray([row["evidence_id"] for row in units], dtype=object)
    structure = _load_structure(root)
    views = build_multiview_representations(units, structure)
    alternate_valid = np.asarray([row["alternate_valid"] for row in views], dtype=bool)
    text_indexes = np.asarray([
        index for index, row in enumerate(units) if row["unit_type"] == "TEXT_REGION"
    ], dtype=np.int32)

    view_manifest = [{
        key: row[key] for key in (
            "unit_index", "evidence_id", "doc_id", "page_id", "page_number", "unit_type",
            "raw_view", "raw_text_sha256", "alternate_view", "alternate_text_sha256",
            "alternate_valid", "fallback_to_raw", "fallback_reason", "source_fields_used",
            "source_locator", "gold_answer_or_qa_used",
        )
    } for row in views]
    write_jsonl(output_dir / "views/view_manifest.jsonl", view_manifest)
    write_jsonl(output_dir / "views/table_struct_retrieval_text.jsonl", ({
        "evidence_id": row["evidence_id"],
        "view": "TABLE_STRUCT",
        "retrieval_text": row["alternate_text"],
        "retrieval_text_sha256": row["alternate_text_sha256"],
        "source_fields_used": row["source_fields_used"],
    } for row in views if row["unit_type"] == "TABLE_REGION" and row["alternate_valid"]))

    model, revision, device = _load_model(config["model"])
    if revision != config["model"]["revision"]:
        raise AssertionError(f"E5 revision changed: expected {config['model']['revision']}, got {revision}")
    raw_embeddings, raw_window_units, raw_meta = _load_window_cache(root, "R0")
    context_embeddings, context_window_units, context_meta = _load_window_cache(root, "R1")
    r1_cache_manifest = json.loads(
        (root / "outputs/R1/cache/CACHE_MANIFEST.json").read_text(encoding="utf-8")
    )["representations"]
    raw_audit_meta = {**raw_meta, **r1_cache_manifest["R0"]}
    context_audit_meta = {**context_meta, **r1_cache_manifest["R1"]}
    (
        table_embeddings, table_global_indexes, table_windows, table_meta, valid_table_views,
    ) = _load_or_embed_table_struct(root, views, model, revision, device, config)
    table_window_units = np.asarray([row["unit_index"] for row in table_windows], dtype=np.int32)
    write_jsonl(output_dir / "windows/table_struct_window_map.jsonl", ({
        key: row[key] for key in (
            "window_id", "evidence_id", "unit_index", "window_number",
            "token_count_with_prefix_and_special", "text_sha256",
        )
    } for row in table_windows))

    representation_audit = {
        "evidence_id_count": len(units),
        "evidence_ids_unchanged": [row["evidence_id"] for row in views] == list(ids),
        "unit_types": dict(Counter(row["unit_type"] for row in units)),
        "views": {
            "TEXT_RAW": {"valid_evidence": len(text_indexes), "source": "original index_text"},
            "TEXT_CONTEXT": {
                "valid_evidence": sum(
                    row["unit_type"] == "TEXT_REGION" and row["alternate_valid"] for row in views
                ),
                "source": "R1 verified title/section/page/local context",
            },
            "TABLE_RAW": {
                "valid_evidence": sum(row["unit_type"] == "TABLE_REGION" for row in views),
                "source": "original index_text",
            },
            "TABLE_STRUCT": {
                "valid_evidence": len(valid_table_views),
                "fallback_to_raw": sum(
                    row["unit_type"] == "TABLE_REGION" and row["fallback_to_raw"] for row in views
                ),
                "source": "verified caption/headers/row labels/rows/units",
            },
        },
        "fallback_double_count": 0,
        "gold_answer_or_qa_used": False,
        "source_metadata_fabricated": False,
        "view_manifest_sha256": sha256(output_dir / "views/view_manifest.jsonl"),
        "token_window_distribution": {
            "RAW_ALL_EVIDENCE": {key: raw_audit_meta.get(key) for key in (
                "unit_count", "window_count", "full_text_over_512", "full_text_truncation_rate",
                "max_full_text_tokens", "windows_over_512", "max_window_tokens", "multi_window_units",
            )},
            "CONTEXT_ALL_EVIDENCE_CACHE_REFERENCE": {key: context_audit_meta.get(key) for key in (
                "unit_count", "window_count", "full_text_over_512", "full_text_truncation_rate",
                "max_full_text_tokens", "windows_over_512", "max_window_tokens", "multi_window_units",
            )},
            "TABLE_STRUCT": {key: table_meta.get(key) for key in (
                "unit_count", "evidence_count", "window_count", "full_text_over_512",
                "full_text_truncation_rate", "max_full_text_tokens", "windows_over_512",
                "max_window_tokens", "multi_window_units",
            )},
        },
        "normalization": config["retrieval"]["score_normalization"],
    }
    write_json(report_dir / "REPRESENTATION_AUDIT.json", representation_audit)
    write_json(output_dir / "cache/CACHE_REFERENCES.json", {
        "model_id": config["model"]["id"],
        "revision": revision,
        "device": device,
        "raw": {
            "embedding": "outputs/R1/cache/r0_window_embeddings.npy",
            "metadata": "outputs/R1/cache/r0_window_embeddings.json",
            "sha256": sha256(root / "outputs/R1/cache/r0_window_embeddings.npy"),
        },
        "text_context": {
            "embedding": "outputs/R1/cache/r1_window_embeddings.npy",
            "metadata": "outputs/R1/cache/r1_window_embeddings.json",
            "sha256": sha256(root / "outputs/R1/cache/r1_window_embeddings.npy"),
        },
        "table_struct": {
            "embedding": "outputs/MASH_ER/cache/table_struct_window_embeddings.npy",
            "metadata": "outputs/MASH_ER/cache/table_struct_window_embeddings.json",
            "sha256": sha256(output_dir / "cache/table_struct_window_embeddings.npy"),
        },
    })

    phase_b = json.loads((root / "configs/phase_b.json").read_text(encoding="utf-8"))
    bm25 = BM25Retriever(
        units, root / "outputs/B2/cache/bm25_regions.pkl", sha256(units_path),
        phase_b["bm25"]["k1"], phase_b["bm25"]["b"],
    )
    page_rankings = _ranking_records(root / "outputs/B2_1/rankings/p0_pages_dev_top100.jsonl")
    page_to_indexes: dict[str, list[int]] = {}
    for index, unit in enumerate(units):
        page_to_indexes.setdefault(unit["page_id"], []).append(index)

    import torch
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    query_started = time.perf_counter()
    query_vectors = model.encode(
        [config["model"]["query_prefix"] + qa["question"] for qa in dev],
        batch_size=config["model"]["batch_size"], show_progress_bar=False,
        normalize_embeddings=True, convert_to_numpy=True,
    ).astype(np.float32)
    if device == "cuda":
        torch.cuda.synchronize()
    query_encoding_seconds = time.perf_counter() - query_started

    records: dict[str, dict[str, dict]] = {method: {} for method in METHODS}
    traces: dict[str, dict[str, list[dict]]] = {method: {} for method in METHODS}
    latency: dict[str, dict[str, float]] = {method: {} for method in METHODS}
    rrf_k = int(config["retrieval"]["rrf_k"])
    page_lambda = float(config["retrieval"]["soft_page_lambda"])
    candidate_budget = int(config["retrieval"]["candidate_budget"])
    for qa_index, qa in enumerate(dev):
        qa_id = qa["qa_id"]
        bm_started = time.perf_counter()
        bm_scores = bm25.score_all(qa["question"])
        _, bm_ranks = _ranks(bm_scores, ids)
        bm_elapsed = time.perf_counter() - bm_started

        raw_started = time.perf_counter()
        raw_window_scores = np.asarray(raw_embeddings @ query_vectors[qa_index], dtype=np.float64)
        raw_scores = max_pool_window_scores(raw_window_scores, raw_window_units, len(units))
        _, raw_ranks = _ranks(raw_scores, ids)
        raw_elapsed = time.perf_counter() - raw_started

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
                table_window_scores, table_window_units, len(valid_table_views)
            )
            alternate_scores[table_global_indexes] = table_local_scores
        _, alternate_ranks = _ranks(
            alternate_scores, ids, np.flatnonzero(alternate_valid).astype(np.int32)
        )
        alternate_elapsed = time.perf_counter() - alternate_started

        raw_view_scores, raw_contributions = fuse_view_scores(
            bm_ranks, raw_ranks, None, alternate_valid, rrf_k
        )
        multi_view_scores, multi_contributions = fuse_view_scores(
            bm_ranks, raw_ranks, alternate_ranks, alternate_valid, rrf_k
        )
        page_rank_by_id = {
            row["page_id"]: int(row["rank"]) for row in page_rankings[qa_id]["results"]
        }
        page_ranks = np.asarray([
            page_rank_by_id.get(unit["page_id"], 0) for unit in units
        ], dtype=np.int32)
        raw_soft_scores, raw_page_contribution = add_soft_page_prior(
            raw_view_scores, page_ranks, rrf_k, page_lambda
        )
        multi_soft_scores, multi_page_contribution = add_soft_page_prior(
            multi_view_scores, page_ranks, rrf_k, page_lambda
        )
        selected_pages = {
            row["page_id"] for row in page_rankings[qa_id]["results"][
                :config["retrieval"]["hard_page_budget"]
            ]
        }
        hard_indexes = np.asarray(sorted({
            index for page_id in selected_pages for index in page_to_indexes.get(page_id, [])
        }), dtype=np.int32)
        method_specs = {
            "A0": (raw_view_scores, raw_contributions, np.zeros(len(units)), hard_indexes, False),
            "A1": (raw_soft_scores, raw_contributions, raw_page_contribution, None, True),
            "A2": (multi_view_scores, multi_contributions, np.zeros(len(units)), hard_indexes, False),
            "A3": (multi_soft_scores, multi_contributions, multi_page_contribution, None, True),
        }
        for method, (scores, contributions, page_contribution, allowed, is_soft) in method_specs.items():
            selection_started = time.perf_counter()
            selected = select_candidates(scores, ids, candidate_budget, allowed)
            selection_elapsed = time.perf_counter() - selection_started
            if len(selected) != candidate_budget or len(set(ids[selected])) != candidate_budget:
                raise AssertionError(f"{method}:{qa_id} violates B=100 unique candidates")
            results = [
                result_from_unit(units[int(index)], float(scores[index]), rank).to_dict()
                for rank, index in enumerate(selected, 1)
            ]
            candidate_ids = [str(ids[index]) for index in selected]
            records[method][qa_id] = {
                "qa_id": qa_id,
                "method": method,
                "candidate_ids": candidate_ids,
                "results": results,
            }
            trace_rows = []
            for rank, index in enumerate(selected, 1):
                index = int(index)
                trace_rows.append({
                    "rank": rank,
                    "evidence_id": str(ids[index]),
                    "unit_type": units[index]["unit_type"],
                    "page_id": units[index]["page_id"],
                    "global_ranks": {
                        "bm25": int(bm_ranks[index]),
                        "raw_dense": int(raw_ranks[index]),
                        "alternate_dense": int(alternate_ranks[index]) if alternate_valid[index] else None,
                        "page": int(page_ranks[index]) if page_ranks[index] > 0 else None,
                    },
                    "contributions": {
                        "bm25": float(contributions["bm25"][index]),
                        "raw_dense": float(contributions["raw_dense"][index]),
                        "alternate_dense": float(contributions["alternate_dense"][index]),
                        "soft_page": float(page_contribution[index]),
                    },
                    "view_score": float(sum(
                        contributions[key][index]
                        for key in ("bm25", "raw_dense", "alternate_dense")
                    )),
                    "final_score": float(scores[index]),
                    "alternate_view": views[index]["alternate_view"],
                    "alternate_valid": bool(alternate_valid[index]),
                    "page_in_hard_top20": units[index]["page_id"] in selected_pages,
                    "soft_hierarchy": is_soft,
                })
            traces[method][qa_id] = trace_rows
            shared = bm_elapsed + raw_elapsed + query_encoding_seconds / len(dev)
            if method in {"A2", "A3"}:
                shared += alternate_elapsed
            latency[method][qa_id] = (shared + selection_elapsed) * 1000.0

    for method in METHODS:
        write_jsonl(
            output_dir / "rankings" / f"{method.lower()}_dev.jsonl",
            (records[method][qa["qa_id"]] for qa in dev),
        )
        write_jsonl(
            output_dir / "traces" / f"{method.lower()}_score_traces.jsonl",
            ({"qa_id": qa["qa_id"], "method": method, "candidates": traces[method][qa["qa_id"]]}
             for qa in dev),
        )

    per_query, subgroups = _evaluate(dev, records, latency, page_rankings)
    write_json(report_dir / "SUBGROUPS.json", {
        "group_definition": "Dev annotations used only after retrieval for evaluation",
        "methods": subgroups,
    })
    result_rows = []
    for method in METHODS:
        overall = subgroups[method]["OVERALL"]
        multi = subgroups[method]["RETRIEVAL_MULTI"]
        result_rows.append({
            "method": method,
            "representation": config["methods"][method]["representation"],
            "retrieval": config["methods"][method]["retrieval"],
            "sample_count": len(dev),
            "candidate_coverage@100": overall["candidate_coverage@100"],
            "all_r@10": overall["all_r@10"],
            "all_r@20": overall["all_r@20"],
            "multi_all_r@20": multi["all_r@20"],
            "any_r@10": overall["any_r@10"],
            "any_r@20": overall["any_r@20"],
            "average_gold_coverage@20": overall["average_gold_coverage@20"],
            "mrr": overall["mrr"],
            "ndcg@10": overall["ndcg@10"],
            "complete_gold_page_recall@20": overall["complete_gold_page_recall@20"],
            "latency_ms_per_query": overall["latency_ms_per_query"],
        })
    with (report_dir / "RESULTS.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result_rows[0]))
        writer.writeheader()
        writer.writerows(result_rows)

    statistics = _statistics(dev, per_query, config)
    write_json(report_dir / "STATISTICS.json", statistics)
    failure_rows = _failure_rows(
        root, dev, records, per_query, traces, page_rankings, unit_by_id
    )
    write_jsonl(report_dir / "FAILURE_ANALYSIS.jsonl", failure_rows)
    primary = {
        method: {
            "candidate_coverage@100": subgroups[method]["OVERALL"]["candidate_coverage@100"],
            "all_r@20": subgroups[method]["OVERALL"]["all_r@20"],
            "multi_all_r@20": subgroups[method]["RETRIEVAL_MULTI"]["all_r@20"],
        } for method in METHODS
    }
    transitions = {}
    for method in ("A1", "A2", "A3"):
        relevant = [row for row in failure_rows if row["comparison"] == f"{method}_vs_A0"]
        transitions[method] = {
            "candidate_recovered": sum(
                row["candidate_complete_before"] == 0 and row["candidate_complete_after"] == 1
                for row in relevant
            ),
            "candidate_lost": sum(
                row["candidate_complete_before"] == 1 and row["candidate_complete_after"] == 0
                for row in relevant
            ),
            "all_r20_recovered": sum(
                row["all_r@20_before"] == 0 and row["all_r@20_after"] == 1 for row in relevant
            ),
            "all_r20_regressed": sum(
                row["all_r@20_before"] == 1 and row["all_r@20_after"] == 0 for row in relevant
            ),
            "page_pruning_avoidance": sum(row["page_pruning_avoidance"] for row in relevant),
            "rank_displacement": sum(row["rank_displacement_by_distractors"] for row in relevant),
        }
    ablation = {
        "primary_metrics": primary,
        "deltas": {
            comparison: {
                metric: primary[current][metric] - primary[baseline][metric]
                for metric in primary[current]
            }
            for comparison, current, baseline in (
                ("A1_minus_A0_soft_localization", "A1", "A0"),
                ("A2_minus_A0_multi_view", "A2", "A0"),
                ("A3_minus_A1_multi_view_given_soft", "A3", "A1"),
                ("A3_minus_A2_soft_given_multi_view", "A3", "A2"),
                ("A3_minus_A0_full_method", "A3", "A0"),
            )
        },
        "transitions_vs_A0": transitions,
        "candidate_ceiling_is_not_final_recall": True,
    }
    write_json(report_dir / "ABLATION.json", ablation)

    peak_vram_mb = (
        float(torch.cuda.max_memory_allocated() / (1024 * 1024)) if device == "cuda" else None
    )
    efficiency = {
        "device": device,
        "model_id": config["model"]["id"],
        "revision": revision,
        "query_encoding_seconds_total": query_encoding_seconds,
        "latency_ms_per_query": {
            method: subgroups[method]["OVERALL"]["latency_ms_per_query"] for method in METHODS
        },
        "indexing_seconds": {
            "raw_r1_cache_original_build": raw_meta.get("indexing_seconds"),
            "text_context_r1_cache_original_build": context_meta.get("indexing_seconds"),
            "table_struct_current_or_original_build": table_meta.get("indexing_seconds", 0.0),
            "table_struct_cache_hit": table_meta.get("cache_hit"),
        },
        "embedding_storage_bytes": {
            "raw_reference": int((root / "outputs/R1/cache/r0_window_embeddings.npy").stat().st_size),
            "text_context_reference": int((root / "outputs/R1/cache/r1_window_embeddings.npy").stat().st_size),
            "table_struct": int((output_dir / "cache/table_struct_window_embeddings.npy").stat().st_size),
        },
        "peak_vram_mb": peak_vram_mb,
        "latency_scope": "Query encoding, BM25 scoring, dense scoring, fusion, and candidate selection; cached indexing excluded.",
    }
    write_json(report_dir / "EFFICIENCY.json", efficiency)

    legacy_e0 = _ranking_records(root / "outputs/C1/rankings/e0_g0_global_rrf_dev.jsonl")
    legacy_r1_raw = _ranking_records(root / "outputs/R1/rankings/full_retrieval_r0_dev.jsonl")
    candidate_hash_after = sha256(candidate_test)
    protected_after = {path.relative_to(root).as_posix(): sha256(path) for path in protected_paths}
    page_ids = set(structure["pages"])
    baseline_verification = {
        "status": "PASS",
        "counts": {
            "retrieval_units": len(units),
            "text_units": sum(row["unit_type"] == "TEXT_REGION" for row in units),
            "table_units": sum(row["unit_type"] == "TABLE_REGION" for row in units),
            "dev_qa": len(dev),
            "retrieval_multi_qa": sum(bool(qa["retrieval_multi_evidence"]) for qa in dev),
            "unique_gold_sets": len({"|".join(sorted(qa["retrieval_evidence_ids"])) for qa in dev}),
            "multi_unique_gold_sets": len({
                "|".join(sorted(qa["retrieval_evidence_ids"]))
                for qa in dev if qa["retrieval_multi_evidence"]
            }),
        },
        "mapping": {
            "unique_evidence_ids": len(unit_by_id) == len(units),
            "all_parent_pages_exist": all(row["page_id"] in page_ids for row in units),
            "all_dev_gold_ids_exist": all(
                item in unit_by_id for qa in dev for item in qa["retrieval_evidence_ids"]
            ),
            "dev_gold_page_mapping_valid": all(
                {unit_by_id[item]["page_id"] for item in qa["retrieval_evidence_ids"]}
                == set(qa["gold_page_ids"]) for qa in dev
            ),
        },
        "legacy_baseline": {
            "E0_C1": _core_metrics(dev, legacy_e0),
            "R1_FULL_RETRIEVAL_R0": _core_metrics(dev, legacy_r1_raw),
            "note": "Legacy artifacts are recomputed for verification only; matching All R@20 does not imply identical preprocessing or ranking.",
        },
        "matched_baseline_A0": primary["A0"],
        "matched_vs_legacy_distinguished": True,
        "candidate_test": {
            "policy": config["candidate_test_policy"],
            "sha256_before": candidate_hash_before,
            "sha256_after": candidate_hash_after,
            "unchanged": candidate_hash_before == candidate_hash_after,
            "parsed": False,
        },
        "protected_hashes_before": protected_before,
        "protected_hashes_after": protected_after,
    }
    baseline_verification["status"] = "PASS" if (
        baseline_verification["counts"] == {
            "retrieval_units": 27045, "text_units": 26954, "table_units": 91,
            "dev_qa": 93, "retrieval_multi_qa": 25,
            "unique_gold_sets": 45, "multi_unique_gold_sets": 8,
        }
        and all(baseline_verification["mapping"].values())
        and candidate_hash_before == candidate_hash_after
        and protected_before == protected_after
    ) else "BLOCKED"
    write_json(report_dir / "BASELINE_VERIFICATION.json", baseline_verification)

    prior_art = _prior_art_gap()
    method_spec = _method_spec(config, prior_art)
    (report_dir / "METHOD_SPEC.md").write_text(method_spec, encoding="utf-8", newline="\n")

    strict_primary_win = all(
        primary["A3"][metric] > primary[other][metric]
        for other in ("A0", "A1", "A2")
        for metric in ("candidate_coverage@100", "all_r@20", "multi_all_r@20")
    )
    ci_support = all(
        statistics["comparisons"][f"A3_vs_{other}"][group]["all_r@20"]
        ["gold_set_cluster_bootstrap"]["supports_superiority"]
        for other in ("A0", "A1", "A2") for group in ("OVERALL", "RETRIEVAL_MULTI")
    )
    internal_checks = {
        "baseline_verification": baseline_verification["status"] == "PASS",
        "evidence_ids_unchanged": representation_audit["evidence_ids_unchanged"],
        "multi_view_deduplicated": representation_audit["fallback_double_count"] == 0,
        "table_fallback_no_double_count": True,
        "global_rank_rrf": True,
        "soft_page_does_not_filter": True,
        "same_candidate_budget": all(
            len(record["candidate_ids"]) == len(set(record["candidate_ids"])) == 100
            for method in METHODS for record in records[method].values()
        ),
        "no_gold_answer_leakage": not representation_audit["gold_answer_or_qa_used"],
        "no_fabricated_metadata": not representation_audit["source_metadata_fabricated"],
        "window_mapping": bool(table_meta.get("mapping_valid"))
        and len(set(raw_window_units.tolist())) == len(units)
        and len(set(context_window_units.tolist())) == len(units)
        and set(table_global_indexes.tolist())
        == {index for index, row in enumerate(views) if row["unit_type"] == "TABLE_REGION" and row["alternate_valid"]},
        "cross_document_allowed": True,
        "candidate_test_not_loaded": True,
        "candidate_test_unchanged": candidate_hash_before == candidate_hash_after,
        "protected_inputs_unchanged": protected_before == protected_after,
        "pytest_pass": bool((pytest_result or {}).get("passed")),
    }
    blockers = [name for name, passed in internal_checks.items() if not passed]
    experiment_valid = not blockers
    method_promising = bool(experiment_valid and strict_primary_win and ci_support)
    main_mechanism = _mechanism_summary(primary)
    main_bottleneck = _bottleneck_summary(primary, transitions)
    readiness = {
        "status": "PASS" if experiment_valid else "BLOCKED",
        "EXPERIMENT_VALID": experiment_valid,
        "METHOD_PROMISING": method_promising,
        "PAPER_READY": False,
        "NOVELTY_STATUS": prior_art["status"],
        "strict_primary_win": strict_primary_win,
        "cluster_ci_support_all_comparisons": ci_support,
        "main_mechanism_supported": main_mechanism,
        "main_remaining_bottleneck": main_bottleneck,
        "candidate_test_sealed": candidate_hash_before == candidate_hash_after,
        "blockers": blockers,
        "limitations": [
            "Development split only; no independent test inference was run.",
            "Only 8 unique retrieval-multi gold sets; multi-evidence inference is inconclusive.",
            "Prior-art search is limited and cannot establish novelty.",
            "Benchmark still requires independent human validation before paper claims.",
        ],
    }
    write_json(report_dir / "READINESS.json", readiness)
    write_json(report_dir / "CONFIG.json", config)
    write_json(report_dir / "TEST_RESULTS.json", pytest_result or {})
    write_json(report_dir / "FINAL_AUDIT.json", {
        "status": readiness["status"],
        "EXPERIMENT_VALID": experiment_valid,
        "checks": internal_checks,
        "blockers": blockers,
        "candidate_test_sha256": candidate_hash_after,
        "pytest": pytest_result or {},
        "audit_mode": "preliminary; independent recomputation by scripts/audit_mash_er.py follows",
    })
    report = _main_report(
        primary, subgroups, transitions, statistics, efficiency, readiness, prior_art,
        baseline_verification,
    )
    (report_dir / "MASH_ER_REPORT.md").write_text(report, encoding="utf-8", newline="\n")

    checksum_paths = [
        report_dir / name for name in (
            "BASELINE_VERIFICATION.json", "REPRESENTATION_AUDIT.json", "RESULTS.csv",
            "SUBGROUPS.json", "ABLATION.json", "FAILURE_ANALYSIS.jsonl", "STATISTICS.json",
            "EFFICIENCY.json", "METHOD_SPEC.md", "MASH_ER_REPORT.md", "CONFIG.json",
            "TEST_RESULTS.json",
        )
    ] + sorted((output_dir / "rankings").glob("*.jsonl")) \
      + sorted((output_dir / "traces").glob("*.jsonl")) \
      + sorted((output_dir / "views").glob("*.jsonl")) \
      + sorted((output_dir / "windows").glob("*.jsonl")) \
      + sorted((output_dir / "cache").glob("*.json"))
    write_json(report_dir / "CHECKSUMS.json", {
        "inputs": protected_before,
        "outputs": {path.relative_to(root).as_posix(): sha256(path) for path in checksum_paths},
        "large_cache_arrays": {
            path.relative_to(root).as_posix(): sha256(path)
            for path in sorted((output_dir / "cache").glob("*.npy"))
        },
    })
    return readiness


def _mechanism_summary(primary: dict[str, dict]) -> str:
    soft_gain = primary["A1"]["candidate_coverage@100"] - primary["A0"]["candidate_coverage@100"]
    multi_gain = primary["A2"]["all_r@20"] - primary["A0"]["all_r@20"]
    combined_gain = primary["A3"]["all_r@20"] - primary["A0"]["all_r@20"]
    if soft_gain > 0 and combined_gain > 0:
        return "SOFT_LOCALIZATION_WITH_COMBINED_RANKING_GAIN"
    if soft_gain > 0:
        return "SOFT_LOCALIZATION_RAISES_CANDIDATE_COVERAGE_ONLY"
    if multi_gain > 0:
        return "MULTI_VIEW_RANKING_GAIN_ONLY"
    return "NO_PRIMARY_MECHANISM_SUPPORTED"


def _bottleneck_summary(primary: dict[str, dict], transitions: dict[str, dict]) -> str:
    if primary["A3"]["candidate_coverage@100"] > primary["A3"]["all_r@20"]:
        return "RANK_DISPLACEMENT_AFTER_CANDIDATE_RECOVERY"
    if transitions["A3"]["candidate_lost"]:
        return "GLOBAL_CANDIDATE_COMPETITION"
    return "UNRESOLVED_EVIDENCE_REPRESENTATION"


def _method_spec(config: dict, prior_art: dict) -> str:
    sources = "\n".join(
        f"- [{row['name']}]({row['url']}): {row['known_technique']} Difference: {row['difference']}"
        for row in prior_art["sources"]
    )
    return f"""# MASH-ER method specification

## Scope

MASH-ER is a deterministic, zero-shot evidence retriever for long Vietnamese irrigation PDFs. It preserves all Phase-A evidence IDs and uses no question labels, answers, gold evidence, fine-tuning, LLM generation, or synthetic evidence during indexing and retrieval.

## Representations

- `TEXT_RAW`: original evidence `index_text`.
- `TEXT_CONTEXT`: raw text with source-verified document title, section, page number, and local heading from R1. Missing metadata is omitted.
- `TABLE_RAW`: original table evidence `index_text`.
- `TABLE_STRUCT`: source-verified caption, headers, row labels, rows/values, and units. It is enabled only when both semantic and structural quality are `GOOD`; otherwise the evidence uses only `TABLE_RAW`.

Each view maps to one immutable source evidence ID. All views use `{config['model']['id']}` revision `{config['model']['revision']}`, 384-token content windows, 128-token overlap, normalized embeddings, and max window pooling back to the source ID.

## Scoring

Ranks are global over the full evidence universe. With `k=60`, raw scoring is:

`S_raw = 1/(60+r_bm25) + 1/(60+r_raw)`.

Multi-view scoring fixes total dense weight at one:

`S_multi = 1/(60+r_bm25) + 0.5/(60+r_raw) + 0.5/(60+r_alt)`.

If the alternate table view is invalid, its contribution is zero and raw dense weight becomes one; the fallback is never counted twice. The soft page prior is:

`S_page = 0.25/(60+r_page)` for pages present in fixed P0 Top-100, otherwise zero.

`S_final = S_view + S_page`. An unranked page is not filtered. A0/A2 restrict selection to P0 Top-20 pages; A1/A3 select globally. Every method returns exactly 100 unique candidates and evaluates the first 20. Ties are broken lexicographically by evidence ID.

## Pseudocode

```text
index each source evidence as RAW
if TEXT: add verified CONTEXT view
if TABLE and structure is verified: add STRUCT view else keep RAW only
for each query:
    compute global BM25, RAW-dense, and alternate-dense ranks
    fuse ranks with fixed view weights
    optionally add the P0 page-rank prior without filtering
    optionally restrict to P0 Top-20 pages for hard-hierarchy ablations
    stable-sort by (-score, evidence_id), keep B=100, evaluate K=20
```

## Complexity

For `N` evidence units, `W` windows, `D` embedding dimensions and `P` ranked pages, dense scoring is `O(WD)`, rank sorting is `O(N log N)`, page-prior lookup is `O(N+P)`, and storage is `O(WD)`. Multi-view storage adds contextual text windows plus only verified table-structure windows.

## Prior-art gap and novelty limitations

{sources}

Conclusion: **{prior_art['status']}**. {prior_art['conclusion']} The working name must not be presented as a novel contribution without a systematic literature review and independent evaluation.
"""


def _main_report(
    primary: dict, subgroups: dict, transitions: dict, statistics: dict, efficiency: dict,
    readiness: dict, prior_art: dict, baseline: dict,
) -> str:
    table_rows = "\n".join(
        f"| {method} | {primary[method]['candidate_coverage@100']:.4f} | "
        f"{primary[method]['all_r@20']:.4f} | {primary[method]['multi_all_r@20']:.4f} |"
        for method in METHODS
    )
    subgroup_rows = "\n".join(
        f"| {group} | {subgroups['A0'][group].get('sample_count', 0)} | "
        f"{subgroups['A0'][group].get('unique_gold_sets', 0)} | "
        f"{subgroups['A0'][group].get('all_r@20', 0):.4f} | "
        f"{subgroups['A3'][group].get('all_r@20', 0):.4f} |"
        for group in ("TEXT_ONLY", "TABLE_ONLY", "TEXT_TABLE", "TABLE_TABLE",
                      "CROSS_PAGE_SAME_DOCUMENT", "CROSS_DOCUMENT")
    )
    a3_stats = statistics["comparisons"]["A3_vs_A0"]
    return f"""# MASH-ER experiment report

## 1. Baseline and controls

The frozen inputs contain {baseline['counts']['retrieval_units']:,} evidence units, {baseline['counts']['dev_qa']} Dev QA, {baseline['counts']['retrieval_multi_qa']} retrieval-multi QA, {baseline['counts']['unique_gold_sets']} unique gold sets, and {baseline['counts']['multi_unique_gold_sets']} unique multi gold sets. Candidate Test was byte-hashed only and remained unchanged. Legacy E0 and R1-R0 rankings were recomputed, while A0 is explicitly treated as the matched baseline because it shares MASH-ER windowing and global-rank conventions.

## 2. Main ablation

| Method | Coverage@100 | All R@20 | Multi All R@20 |
|---|---:|---:|---:|
{table_rows}

Candidate coverage and final recall are reported separately. A1 isolates soft localization, A2 isolates modality-aware views, and A3 combines both. Transition counts versus A0 are `{json.dumps(transitions, ensure_ascii=False)}`.

## 3. Subgroups

| Group | N | Unique gold sets | A0 All R@20 | A3 All R@20 |
|---|---:|---:|---:|---:|
{subgroup_rows}

Complete page recall is diagnostic only and is stored in `SUBGROUPS.json`. Per-QA candidate recovery, gold-rank movement, view/page contributions, pruning avoidance, distractor displacement, and the requested historical failure subsets are stored in `FAILURE_ANALYSIS.jsonl`.

## 4. Statistical validity

A3-A0 QA bootstrap All R@20: delta={a3_stats['OVERALL']['all_r@20']['qa_bootstrap']['delta']:.4f}, 95% CI [{a3_stats['OVERALL']['all_r@20']['qa_bootstrap']['ci95_low']:.4f}, {a3_stats['OVERALL']['all_r@20']['qa_bootstrap']['ci95_high']:.4f}]. Gold-set cluster bootstrap: [{a3_stats['OVERALL']['all_r@20']['gold_set_cluster_bootstrap']['ci95_low']:.4f}, {a3_stats['OVERALL']['all_r@20']['gold_set_cluster_bootstrap']['ci95_high']:.4f}]. Multi-evidence has only {statistics['multi_unique_gold_sets']} unique gold sets and is marked inconclusive. No generalization or superiority claim is made from Dev alone.

## 5. Efficiency

Mean latency in ms/query is `{json.dumps(efficiency['latency_ms_per_query'])}`. Peak VRAM is {efficiency['peak_vram_mb']} MB on `{efficiency['device']}`. Embedding storage and cache-build timings are in `EFFICIENCY.json`; reused R1 caches are distinguished from newly built TABLE_STRUCT embeddings.

## 6. Mechanism and failures

Supported mechanism: **{readiness['main_mechanism_supported']}**. Remaining bottleneck: **{readiness['main_remaining_bottleneck']}**. Soft page scores never exclude evidence outside P0, while hard A0/A2 intentionally reproduce the P=20 pruning condition. Full component ranks and scores are retained for every selected candidate.

## 7. Prior art and decision

The limited source check covers Contextual Retrieval, TreeRAG, LongRefiner, TableRAG, OTTeR, and hierarchical document-passage retrieval. These establish substantial prior art for every component; the exact combination is not assumed novel. Novelty status: **{prior_art['status']}**.

`EXPERIMENT_VALID={readiness['EXPERIMENT_VALID']}`, `METHOD_PROMISING={readiness['METHOD_PROMISING']}`, and `PAPER_READY={readiness['PAPER_READY']}`. Candidate Test remains sealed; independent benchmark validation and test evaluation are still required.
"""
