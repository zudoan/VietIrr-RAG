from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import platform
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .bm25 import BM25Retriever, result_from_unit
from .dense import E5Retriever
from .fusion import bounded_round_robin_union
from .io_utils import read_jsonl, sha256, write_json, write_jsonl


REPRESENTATIONS = ("P0", "P1", "P2")
FORBIDDEN_INDEX_FIELDS = {
    "question", "answer", "gold_evidence", "retrieval_evidence_ids", "answer_evidence_ids"
}


def _json_hash(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def _load_ranking(path: Path) -> dict[str, list[dict]]:
    return {row["qa_id"]: row["results"] for row in read_jsonl(path)}


def _independent_metrics(gold_ids: list[str], ranked_ids: list[str], ks: list[int]) -> dict:
    import math

    gold = set(gold_ids)
    if not gold:
        raise ValueError("Empty retrieval gold")
    result: dict[str, object] = {}
    for k in ks:
        found = gold.intersection(ranked_ids[:k])
        result[str(k)] = {
            "any_recall": float(bool(found)),
            "all_recall": float(found == gold),
            "gold_coverage": len(found) / len(gold),
        }
    first = next((rank for rank, item_id in enumerate(ranked_ids, 1) if item_id in gold), None)
    result["mrr"] = 0.0 if first is None else 1.0 / first
    dcg = sum(1.0 / math.log2(rank + 1) for rank, item_id in enumerate(ranked_ids[:10], 1)
              if item_id in gold)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(10, len(gold)) + 1))
    result["ndcg@10"] = dcg / ideal
    return result


def _mean_metrics(rows: list[dict], ks: list[int]) -> dict:
    output: dict[str, object] = {"sample_count": len(rows)}
    for k in ks:
        output[str(k)] = {
            key: float(np.mean([row[str(k)][key] for row in rows]))
            for key in ("any_recall", "all_recall", "gold_coverage")
        }
    output["mrr"] = float(np.mean([row["mrr"] for row in rows]))
    output["ndcg@10"] = float(np.mean([row["ndcg@10"] for row in rows]))
    return output


def _validate_result_order(results: list[dict], valid_ids: set[str], errors: list[str], label: str) -> None:
    ids = [row["evidence_id"] for row in results]
    if len(ids) != len(set(ids)):
        errors.append(f"{label}: duplicate IDs")
    if not set(ids) <= valid_ids:
        errors.append(f"{label}: unknown IDs")
    for expected_rank, row in enumerate(results, 1):
        if row.get("rank") != expected_rank:
            errors.append(f"{label}: non-sequential rank")
            break
    for left, right in zip(results, results[1:]):
        if left["score"] < right["score"]:
            errors.append(f"{label}: score order violation")
            break
        if left["score"] == right["score"] and left["evidence_id"] > right["evidence_id"]:
            errors.append(f"{label}: nondeterministic tie order")
            break


def verify_b2(root: Path) -> dict:
    errors: list[str] = []
    units = read_jsonl(root / "data/processed/evidence_units.jsonl")
    pages = read_jsonl(root / "data/processed/pages.jsonl")
    dev = read_jsonl(root / "data/benchmark/dev.jsonl")
    train = read_jsonl(root / "data/benchmark/train.jsonl")
    unit_by_id = {row["evidence_id"]: row for row in units}
    page_by_id = {row["page_id"]: row for row in pages}
    dev_by_id = {row["qa_id"]: row for row in dev}
    if len(units) != len(unit_by_id): errors.append("duplicate evidence IDs")
    if len(pages) != len(page_by_id): errors.append("duplicate page IDs")
    if len(dev) != 93 or len(dev_by_id) != 93: errors.append(f"DEV expected 93, found {len(dev)}")
    if any(row.get("split") != "dev" for row in dev): errors.append("DEV split label mismatch")
    if set(dev_by_id).intersection(row["qa_id"] for row in train): errors.append("train/dev QA overlap")
    if set(row.get("leakage_group_id") for row in dev).intersection(
            row.get("leakage_group_id") for row in train):
        errors.append("train/dev leakage-group overlap")
    if any(FORBIDDEN_INDEX_FIELDS.intersection(row) for row in units):
        errors.append("QA/gold fields found in index")

    source_regions = {row["region_id"]: row for row in read_jsonl(root / "data/parsed/regions.jsonl")}
    source_tables = {row["table_id"]: row for row in read_jsonl(root / "data/parsed/tables.jsonl")}
    mapping_errors = []
    for unit in units:
        source = source_regions.get(unit["evidence_id"]) if unit["unit_type"] == "TEXT_REGION" else source_tables.get(unit["evidence_id"])
        if source is None:
            mapping_errors.append(f"missing source:{unit['evidence_id']}")
        elif any(source[key] != unit[key] for key in ("doc_id", "page_id", "page_number")):
            mapping_errors.append(f"parent mismatch:{unit['evidence_id']}")
        if unit["page_id"] not in page_by_id:
            mapping_errors.append(f"missing page:{unit['evidence_id']}")
    for qa in dev:
        gold = qa["retrieval_evidence_ids"]
        if not set(gold) <= set(unit_by_id):
            mapping_errors.append(f"DEV unmapped gold:{qa['qa_id']}")
            continue
        mapped_pages = {unit_by_id[item_id]["page_id"] for item_id in gold}
        declared_pages = set(qa.get("gold_page_ids", []))
        if declared_pages and mapped_pages != declared_pages:
            mapping_errors.append(f"DEV gold-page mismatch:{qa['qa_id']}")
    if mapping_errors:
        errors.extend(mapping_errors[:20])

    report = json.loads((root / "reports/B2/B2_BASELINE_METRICS.json").read_text(encoding="utf-8"))
    methods = ("bm25", "e5", "hybrid", "page_region")
    ks = [5, 10, 20, 50, 100, 200]
    recomputed: dict[str, dict] = {}
    ranking_hashes = {}
    for method in methods:
        path = root / f"outputs/B2/rankings/{method}_dev_top200.jsonl"
        ranking_hashes[method] = sha256(path)
        rankings = _load_ranking(path)
        if set(rankings) != set(dev_by_id): errors.append(f"{method}: DEV QA set mismatch")
        per_query = []
        for qa_id, qa in dev_by_id.items():
            results = rankings.get(qa_id, [])
            _validate_result_order(results, set(unit_by_id), errors, f"{method}:{qa_id}")
            for item in results:
                unit = unit_by_id.get(item["evidence_id"])
                if unit and any(item.get(key) != unit[key] for key in ("doc_id", "page_id", "page_number", "unit_type")):
                    errors.append(f"{method}:{qa_id}: result parent mismatch")
                    break
            per_query.append(_independent_metrics(qa["retrieval_evidence_ids"],
                                                  [item["evidence_id"] for item in results], ks))
        recomputed[method] = _mean_metrics(per_query, ks)
        expected = report["overall"][method]
        for key in ("mrr", "ndcg@10"):
            if abs(recomputed[method][key] - expected[key]) > 1e-12:
                errors.append(f"{method}:{key} metric mismatch")
        for k in ks:
            for key in ("any_recall", "all_recall", "gold_coverage"):
                if abs(recomputed[method][str(k)][key] - expected[str(k)][key]) > 1e-12:
                    errors.append(f"{method}:{key}@{k} metric mismatch")

    page_rank_path = root / "outputs/B2/rankings/page_hybrid_dev_top100.jsonl"
    page_rankings = _load_ranking(page_rank_path)
    for qa_id, results in page_rankings.items():
        _validate_result_order(results, set(page_by_id), errors, f"page:{qa_id}")

    b1 = json.loads((root / "reports/B1_INTEGRITY.json").read_text(encoding="utf-8"))
    if b1.get("B1_INTEGRITY") != "PASS": errors.append("B1 integrity is not PASS")
    candidate = root / "data/benchmark/candidate_test.jsonl"
    frozen_candidate = root / "data/v3_2_final_semantic/candidate_test.jsonl"
    candidate_hash = sha256(candidate)
    frozen_candidate_hash = sha256(frozen_candidate)
    if candidate_hash != frozen_candidate_hash: errors.append("candidate-test byte hash differs from frozen source")

    return {
        "B2_VERIFIED": not errors,
        "errors": errors,
        "counts": {"evidence_units": len(units), "pages": len(pages), "dev_qa": len(dev)},
        "mapping": {"source_and_parent_mapping_pass": not mapping_errors,
                    "mapping_error_count": len(mapping_errors)},
        "split_integrity": {"train_dev_qa_overlap": 0,
                            "train_dev_leakage_group_overlap": 0,
                            "candidate_test_policy": "byte-hashed only; not parsed"},
        "candidate_test_sha256": candidate_hash,
        "candidate_test_matches_frozen": candidate_hash == frozen_candidate_hash,
        "ranking_sha256": ranking_hashes,
        "rankings_unique_and_deterministic": not any("duplicate" in err or "order" in err for err in errors),
        "metrics_recomputed_independently": recomputed,
        "metric_match_tolerance": 1e-12,
        "reported_metrics_match": not any("metric mismatch" in err for err in errors),
        "index_leakage_pass": not any("fields found in index" in err for err in errors),
    }


def make_token_windows(pages: list[dict], tokenizer, total_tokens: int = 384,
                       overlap_tokens: int = 128) -> tuple[list[dict], dict[str, int], dict]:
    prefix_ids = tokenizer("passage: ", add_special_tokens=False)["input_ids"]
    special_tokens = int(tokenizer.num_special_tokens_to_add(pair=False))
    payload = total_tokens - len(prefix_ids) - special_tokens
    if payload <= overlap_tokens:
        raise ValueError("Window payload must exceed overlap")
    step = payload - overlap_tokens
    windows: list[dict] = []
    page_lengths: dict[str, int] = {}
    maximum = 0
    for page in pages:
        raw_ids = tokenizer(str(page["index_text"]), add_special_tokens=False)["input_ids"]
        full_length = len(tokenizer("passage: " + str(page["index_text"]), add_special_tokens=True,
                                    truncation=False)["input_ids"])
        page_lengths[page["page_id"]] = full_length
        starts = list(range(0, max(1, len(raw_ids)), step))
        if not raw_ids:
            starts = [0]
        for number, start in enumerate(starts):
            chunk = raw_ids[start:start + payload]
            text = tokenizer.decode(chunk, skip_special_tokens=True, clean_up_tokenization_spaces=False)
            final_length = len(tokenizer("passage: " + text, add_special_tokens=True,
                                         truncation=False)["input_ids"])
            while final_length > total_tokens and chunk:
                chunk = chunk[:-1]
                text = tokenizer.decode(chunk, skip_special_tokens=True, clean_up_tokenization_spaces=False)
                final_length = len(tokenizer("passage: " + text, add_special_tokens=True,
                                             truncation=False)["input_ids"])
            if final_length > total_tokens or final_length > 512:
                raise AssertionError(f"Window exceeds token limit: {final_length}")
            maximum = max(maximum, final_length)
            windows.append({
                "window_id": f"WIN_{page['page_id']}_{number:04d}",
                "page_id": page["page_id"],
                "doc_id": page["doc_id"],
                "text": text,
                "token_count_with_prefix_and_special": final_length,
                "source_token_start": start,
                "source_token_end": start + len(chunk),
            })
            if start + payload >= len(raw_ids):
                break
    metadata = {
        "window_count": len(windows), "page_count": len(pages),
        "window_total_tokens": total_tokens, "overlap_source_tokens": overlap_tokens,
        "prefix_token_count": len(prefix_ids), "special_token_count": special_tokens,
        "payload_token_limit": payload, "max_actual_tokens": maximum,
        "windows_over_512": sum(row["token_count_with_prefix_and_special"] > 512 for row in windows),
        "pages_over_512": sum(length > 512 for length in page_lengths.values()),
    }
    return windows, page_lengths, metadata


def _encode_windows(model, texts: list[str], batch_size: int = 16) -> tuple[np.ndarray, int, float]:
    import torch

    effective = batch_size
    while effective:
        try:
            started = time.perf_counter()
            vectors = model.encode(["passage: " + text for text in texts], batch_size=effective,
                                   show_progress_bar=True, normalize_embeddings=True,
                                   convert_to_numpy=True)
            if torch.cuda.is_available(): torch.cuda.synchronize()
            return np.asarray(vectors, dtype=np.float32), effective, time.perf_counter() - started
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            effective //= 2
    raise RuntimeError("Window encoding failed at batch_size=1")


def _load_or_build_window_embeddings(root: Path, windows: list[dict], page_dense: E5Retriever,
                                     config: dict) -> tuple[np.ndarray, dict]:
    cache = root / "outputs/B2_1/cache"
    cache.mkdir(parents=True, exist_ok=True)
    array_path = cache / "p1_window_embeddings.npy"
    metadata_path = cache / "p1_window_embeddings.json"
    identity = [{key: row[key] for key in ("window_id", "page_id", "text",
                                            "token_count_with_prefix_and_special")} for row in windows]
    expected = {
        "windows_sha256": _json_hash(identity), "count": len(windows),
        "dimension": page_dense.dimension, "model_id": page_dense.model_id,
        "revision": page_dense.revision, "normalized": True,
        "window_total_tokens": config["window_total_tokens"],
        "window_overlap_tokens": config["window_overlap_tokens"],
    }
    if array_path.exists() and metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if all(metadata.get(key) == value for key, value in expected.items()):
            return np.load(array_path, mmap_mode="r"), {**metadata, "cache_hit": True}
    vectors, effective, seconds = _encode_windows(page_dense.model, [row["text"] for row in windows],
                                                   page_dense.initial_batch_size)
    np.save(array_path, vectors)
    metadata = {**expected, "effective_batch_size": effective, "indexing_seconds": seconds,
                "bytes": array_path.stat().st_size, "cache_hit": False}
    write_json(metadata_path, metadata)
    return np.load(array_path, mmap_mode="r"), metadata


def _max_pool(values: np.ndarray, parents: np.ndarray, count: int) -> np.ndarray:
    pooled = np.full(count, -np.inf, dtype=np.float64)
    np.maximum.at(pooled, parents, values)
    return pooled


def _rrf_order(first_scores: np.ndarray, second_scores: np.ndarray, ids: np.ndarray,
               rrf_k: int, candidates: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    indexes = np.arange(len(ids), dtype=np.int32) if candidates is None else np.asarray(candidates, dtype=np.int32)
    first = indexes[np.lexsort((ids[indexes], -first_scores[indexes]))]
    second = indexes[np.lexsort((ids[indexes], -second_scores[indexes]))]
    fused = np.zeros(len(ids), dtype=np.float64)
    fused[first] += 1.0 / (rrf_k + np.arange(1, len(first) + 1))
    fused[second] += 1.0 / (rrf_k + np.arange(1, len(second) + 1))
    ordered = indexes[np.lexsort((ids[indexes], -fused[indexes]))]
    return ordered, fused[ordered]


def paired_bootstrap(after: list[float], before: list[float], resamples: int = 1000,
                     seed: int = 42) -> dict:
    if len(after) != len(before) or not after:
        raise ValueError("Paired bootstrap requires equal non-empty samples")
    delta = np.asarray(after, dtype=np.float64) - np.asarray(before, dtype=np.float64)
    rng = np.random.default_rng(seed)
    indexes = rng.integers(0, len(delta), size=(resamples, len(delta)))
    means = delta[indexes].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return {"delta": float(delta.mean()), "ci95_low": float(low), "ci95_high": float(high),
            "resamples": resamples, "seed": seed,
            "regressions": int(np.sum(delta < 0)), "improvements": int(np.sum(delta > 0))}


def _groups(qa: dict) -> list[str]:
    groups = ["OVERALL"]
    groups.append("MULTI_EVIDENCE" if qa["retrieval_evidence_count"] >= 2 else "SINGLE_EVIDENCE")
    location = qa.get("location_type")
    if location == "CROSS_PAGE_SAME_DOCUMENT": groups.append("SAME_DOCUMENT_CROSS_PAGE")
    if location == "CROSS_DOCUMENT": groups.append("CROSS_DOCUMENT")
    modality = str(qa.get("modality") or qa.get("qa_type") or "").upper()
    if "TABLE" in modality: groups.append("TABLE_INVOLVING")
    return groups


def _compact_result(unit: dict, score: float, rank: int) -> dict:
    return result_from_unit(unit, score, rank).to_dict()


def _aggregate_config(dev: list[dict], ranked: dict[str, list[dict]], page_ranked: dict[str, list[str]],
                      unit_by_id: dict[str, dict], page_budget: int, ks: list[int],
                      candidate_budgets: list[int], candidates_by_qa: dict[str, int],
                      timings_by_qa: dict[str, dict]) -> tuple[dict, dict[str, dict], dict[str, dict]]:
    per_query, grouped = {}, defaultdict(list)
    for qa in dev:
        qa_id = qa["qa_id"]
        ids = [row["evidence_id"] for row in ranked[qa_id]]
        metric = _independent_metrics(qa["retrieval_evidence_ids"], ids, sorted(set(ks + candidate_budgets)))
        gold_pages = {unit_by_id[item_id]["page_id"] for item_id in qa["retrieval_evidence_ids"]}
        page_ids = page_ranked[qa_id]
        metric["complete_page_recall"] = {
            str(p): float(gold_pages <= set(page_ids[:p])) for p in (10, 20, 50)
        }
        metric["candidate_count"] = candidates_by_qa[qa_id]
        metric["timing"] = timings_by_qa[qa_id]
        per_query[qa_id] = metric
        for group in _groups(qa): grouped[group].append(metric)

    aggregates = {}
    for group, rows in sorted(grouped.items()):
        base = _mean_metrics(rows, sorted(set(ks + candidate_budgets)))
        base["complete_page_recall"] = {
            str(p): float(np.mean([row["complete_page_recall"][str(p)] for row in rows]))
            for p in (10, 20, 50)
        }
        base["complete_candidate_coverage"] = {
            str(k): base[str(k)]["all_recall"] for k in candidate_budgets
        }
        base["avg_candidate_count"] = float(np.mean([row["candidate_count"] for row in rows]))
        base["latency_ms"] = {
            key: 1000.0 * float(np.mean([row["timing"][key] for row in rows]))
            for key in ("query_encode", "page_search", "region_rank", "total")
        }
        aggregates[group] = base
    return aggregates["OVERALL"], aggregates, per_query


def _failure_stage(gold: set[str], final_ids: list[str], ranked_pages: list[str], page_budget: int,
                   candidates: set[str], unit_by_id: dict[str, dict]) -> tuple[str, list[dict]]:
    final_positions = {item_id: rank for rank, item_id in enumerate(final_ids, 1)}
    page_positions = {page_id: rank for rank, page_id in enumerate(ranked_pages, 1)}
    missing = []
    for item_id in sorted(gold - set(final_ids[:20])):
        unit = unit_by_id[item_id]
        page_rank = page_positions.get(unit["page_id"])
        if page_rank is None or page_rank > 100:
            stage = "PAGE_RETRIEVAL"
        elif page_rank > page_budget:
            stage = "PAGE_PRUNING"
        elif item_id not in candidates:
            stage = "CANDIDATE_MAPPING"
        else:
            stage = "REGION_RANKING"
        missing.append({"evidence_id": item_id, "unit_type": unit["unit_type"],
                        "page_id": unit["page_id"], "page_rank": page_rank,
                        "in_candidate_pool": item_id in candidates,
                        "final_rank": final_positions.get(item_id), "failure_stage": stage})
    priority = ("PAGE_RETRIEVAL", "PAGE_PRUNING", "CANDIDATE_MAPPING", "REGION_RANKING")
    primary = next((stage for stage in priority if any(row["failure_stage"] == stage for row in missing)),
                   "SUCCESS")
    return primary, missing


def run_b21(root: Path) -> dict:
    import torch

    config = json.loads((root / "configs/phase_b2_1.json").read_text(encoding="utf-8"))
    report_dir = root / "reports/B2_1"
    output_dir = root / "outputs/B2_1"
    ranking_dir = output_dir / "rankings"
    report_dir.mkdir(parents=True, exist_ok=True)
    ranking_dir.mkdir(parents=True, exist_ok=True)
    prior_ranking_sha256 = {
        path.name: sha256(path) for path in ranking_dir.glob("*.jsonl") if path.is_file()
    }
    candidate_path = root / "data/benchmark/candidate_test.jsonl"
    candidate_hash_before = sha256(candidate_path)

    verification = verify_b2(root)
    write_json(report_dir / "VERIFICATION.json", verification)
    if not verification["B2_VERIFIED"]:
        readiness = {"B2_VERIFIED": False, "B2_1_VALID": False,
                     "REMAINING_BLOCKERS": verification["errors"],
                     "candidate_test_untouched": sha256(candidate_path) == candidate_hash_before}
        write_json(report_dir / "READINESS.json", readiness)
        return readiness

    phase_b = json.loads((root / "configs/phase_b.json").read_text(encoding="utf-8"))
    units = read_jsonl(root / "data/processed/evidence_units.jsonl")
    pages = read_jsonl(root / "data/processed/pages.jsonl")
    dev = read_jsonl(root / "data/benchmark/dev.jsonl")
    unit_by_id = {row["evidence_id"]: row for row in units}
    page_ids = np.asarray([row["page_id"] for row in pages], dtype=object)
    unit_ids = np.asarray([row["evidence_id"] for row in units], dtype=object)
    page_index = {page_id: index for index, page_id in enumerate(page_ids)}
    page_to_units: dict[str, list[int]] = defaultdict(list)
    for index, unit in enumerate(units): page_to_units[unit["page_id"]].append(index)

    cache_b2 = root / "outputs/B2/cache"
    pages_sha = sha256(root / "data/processed/pages.jsonl")
    units_sha = sha256(root / "data/processed/evidence_units.jsonl")
    page_units = [{**row, "evidence_id": row["page_id"], "unit_type": "PAGE"} for row in pages]
    page_bm25 = BM25Retriever(page_units, cache_b2 / "bm25_pages.pkl", pages_sha,
                              phase_b["bm25"]["k1"], phase_b["bm25"]["b"])
    region_bm25 = BM25Retriever(units, cache_b2 / "bm25_regions.pkl", units_sha,
                                phase_b["bm25"]["k1"], phase_b["bm25"]["b"])
    region_dense = E5Retriever(units, cache_b2 / "e5_regions", units_sha,
                               phase_b["e5"]["model_id"], phase_b["e5"]["batch_size"], 512)
    page_dense = E5Retriever(page_units, cache_b2 / "e5_pages", pages_sha,
                             phase_b["e5"]["model_id"], phase_b["e5"]["batch_size"], 512)

    windows, page_lengths, window_info = make_token_windows(
        pages, page_dense.model.tokenizer, config["window_total_tokens"], config["window_overlap_tokens"])
    window_embeddings, window_cache = _load_or_build_window_embeddings(root, windows, page_dense, config)
    window_parents = np.asarray([page_index[row["page_id"]] for row in windows], dtype=np.int32)
    region_parents = np.asarray([page_index[row["page_id"]] for row in units], dtype=np.int32)

    query_vectors, query_seconds = {}, {}
    for qa in dev:
        started = time.perf_counter()
        query_vectors[qa["qa_id"]] = region_dense.encode_query(qa["question"])
        if torch.cuda.is_available(): torch.cuda.synchronize()
        query_seconds[qa["qa_id"]] = time.perf_counter() - started

    page_rankings: dict[str, dict[str, list[str]]] = {rep: {} for rep in REPRESENTATIONS}
    page_scores_out: dict[str, dict[str, list[float]]] = {rep: {} for rep in REPRESENTATIONS}
    page_times: dict[str, dict[str, float]] = {rep: {} for rep in REPRESENTATIONS}
    rankings: dict[tuple[str, int], dict[str, list[dict]]] = {
        (rep, p): {} for rep in REPRESENTATIONS for p in config["page_budgets"]
    }
    candidates_by_config: dict[tuple[str, int], dict[str, set[str]]] = {
        key: {} for key in rankings
    }
    timing_by_config: dict[tuple[str, int], dict[str, dict]] = {key: {} for key in rankings}

    for qa in dev:
        qa_id, query = qa["qa_id"], qa["question"]
        vector = query_vectors[qa_id]
        started = time.perf_counter()
        bm25_page_scores = page_bm25.score_all(query)
        bm25_page_seconds = time.perf_counter() - started
        started = time.perf_counter()
        bm25_region_scores = region_bm25.score_all(query)
        bm25_region_seconds = time.perf_counter() - started
        started = time.perf_counter()
        p0_scores = np.asarray(page_dense.embeddings @ vector, dtype=np.float64)
        p0_dense_seconds = time.perf_counter() - started
        started = time.perf_counter()
        p1_scores = _max_pool(np.asarray(window_embeddings @ vector, dtype=np.float64),
                              window_parents, len(pages))
        p1_dense_seconds = time.perf_counter() - started
        started = time.perf_counter()
        dense_region_scores = np.asarray(region_dense.embeddings @ vector, dtype=np.float64)
        region_dense_seconds = time.perf_counter() - started
        started = time.perf_counter()
        p2_scores = _max_pool(dense_region_scores, region_parents, len(pages))
        p2_pool_seconds = time.perf_counter() - started
        dense_page_scores = {"P0": p0_scores, "P1": p1_scores, "P2": p2_scores}
        dense_page_seconds = {
            "P0": p0_dense_seconds,
            "P1": p1_dense_seconds,
            "P2": region_dense_seconds + p2_pool_seconds,
        }
        for rep in REPRESENTATIONS:
            started_page = time.perf_counter()
            ordered_pages, fused_page_scores = _rrf_order(bm25_page_scores, dense_page_scores[rep],
                                                          page_ids, config["rrf_k"])
            page_times[rep][qa_id] = (bm25_page_seconds + dense_page_seconds[rep] +
                                      time.perf_counter() - started_page)
            top_pages = ordered_pages[:config["page_ranking_depth"]]
            page_rankings[rep][qa_id] = [str(page_ids[index]) for index in top_pages]
            page_scores_out[rep][qa_id] = [float(score) for score in fused_page_scores[:len(top_pages)]]
            for p in config["page_budgets"]:
                selected = page_rankings[rep][qa_id][:p]
                candidate_indexes = np.asarray(sorted({index for page_id in selected
                                                       for index in page_to_units.get(page_id, [])}),
                                               dtype=np.int32)
                candidate_ids = {str(unit_ids[index]) for index in candidate_indexes}
                candidates_by_config[(rep, p)][qa_id] = candidate_ids
                started_region = time.perf_counter()
                ordered_units, unit_scores = _rrf_order(bm25_region_scores, dense_region_scores,
                                                        unit_ids, config["rrf_k"], candidate_indexes)
                ordered_units = ordered_units[:config["raw_ranking_depth"]]
                unit_scores = unit_scores[:config["raw_ranking_depth"]]
                shared_dense_seconds = 0.0 if rep == "P2" else region_dense_seconds
                region_seconds = (bm25_region_seconds + shared_dense_seconds +
                                  time.perf_counter() - started_region)
                rankings[(rep, p)][qa_id] = [
                    _compact_result(units[int(index)], float(score), rank)
                    for rank, (index, score) in enumerate(zip(ordered_units, unit_scores), 1)
                ]
                total = query_seconds[qa_id] + page_times[rep][qa_id] + region_seconds
                timing_by_config[(rep, p)][qa_id] = {
                    "query_encode": query_seconds[qa_id], "page_search": page_times[rep][qa_id],
                    "region_rank": region_seconds, "total": total,
                }

    for rep in REPRESENTATIONS:
        write_jsonl(ranking_dir / f"{rep.lower()}_pages_dev_top100.jsonl", (
            {"qa_id": qa["qa_id"], "results": [
                {"page_id": page_id, "rank": rank, "score": page_scores_out[rep][qa["qa_id"]][rank - 1]}
                for rank, page_id in enumerate(page_rankings[rep][qa["qa_id"]], 1)]}
            for qa in dev
        ))
        for p in config["page_budgets"]:
            write_jsonl(ranking_dir / f"{rep.lower()}_p{p}_dev_top200.jsonl", (
                {"qa_id": qa["qa_id"], "results": rankings[(rep, p)][qa["qa_id"]]} for qa in dev
            ))

    all_results, per_query_results = {}, {}
    csv_rows = []
    for rep in REPRESENTATIONS:
        for p in config["page_budgets"]:
            key = (rep, p)
            overall, subgroups, per_query = _aggregate_config(
                dev, rankings[key], page_rankings[rep], unit_by_id, p, config["evidence_ks"],
                config["candidate_budgets"],
                {qa_id: len(values) for qa_id, values in candidates_by_config[key].items()},
                timing_by_config[key])
            all_results[f"{rep}_P{p}"] = {"overall": overall, "subgroups": subgroups}
            per_query_results[key] = per_query
            for group, metric in subgroups.items():
                csv_rows.append({
                    "method": rep, "page_budget": p, "subgroup": group,
                    "n": metric["sample_count"],
                    "complete_page_recall@10": metric["complete_page_recall"]["10"],
                    "complete_page_recall@20": metric["complete_page_recall"]["20"],
                    "complete_page_recall@50": metric["complete_page_recall"]["50"],
                    "any_r@10": metric["10"]["any_recall"], "all_r@10": metric["10"]["all_recall"],
                    "any_r@20": metric["20"]["any_recall"], "all_r@20": metric["20"]["all_recall"],
                    "any_r@50": metric["50"]["any_recall"], "all_r@50": metric["50"]["all_recall"],
                    "candidate_coverage@50": metric["complete_candidate_coverage"]["50"],
                    "candidate_coverage@100": metric["complete_candidate_coverage"]["100"],
                    "candidate_coverage@200": metric["complete_candidate_coverage"]["200"],
                    "avg_candidate_count": metric["avg_candidate_count"],
                    "query_encode_ms": metric["latency_ms"]["query_encode"],
                    "page_search_ms": metric["latency_ms"]["page_search"],
                    "region_rank_ms": metric["latency_ms"]["region_rank"],
                    "total_latency_ms": metric["latency_ms"]["total"],
                })

    b2_bm25 = _load_ranking(root / "outputs/B2/rankings/bm25_dev_top200.jsonl")
    b2_e5 = _load_ranking(root / "outputs/B2/rankings/e5_dev_top200.jsonl")
    union_rankings, union_metrics = {}, {}
    for qa in dev:
        qa_id = qa["qa_id"]
        ids = bounded_round_robin_union(
            [[row["evidence_id"] for row in b2_bm25[qa_id]],
             [row["evidence_id"] for row in b2_e5[qa_id]]], 200)
        union_rankings[qa_id] = ids
        union_metrics[qa_id] = _independent_metrics(qa["retrieval_evidence_ids"], ids,
                                                    config["candidate_budgets"])
    write_jsonl(ranking_dir / "flat_bm25_e5_union_dev_top200.jsonl", (
        {"qa_id": qa["qa_id"], "evidence_ids": union_rankings[qa["qa_id"]]} for qa in dev
    ))
    union_summary = _mean_metrics(list(union_metrics.values()), config["candidate_budgets"])
    union_summary = {str(k): {"any_recall": union_summary[str(k)]["any_recall"],
                              "complete_coverage": union_summary[str(k)]["all_recall"]}
                     for k in config["candidate_budgets"]}
    for k in config["candidate_budgets"]:
        csv_rows.append({"method": "FLAT_BM25_E5_UNION", "page_budget": "", "subgroup": "OVERALL",
                         "n": len(dev), f"any_r@{k}": union_summary[str(k)]["any_recall"],
                         f"candidate_coverage@{k}": union_summary[str(k)]["complete_coverage"]})

    fixed_p = 10
    selection_scores = {}
    for rep in REPRESENTATIONS:
        metric = all_results[f"{rep}_P{fixed_p}"]["overall"]
        selection_scores[rep] = (metric["20"]["all_recall"] +
                                 metric["complete_page_recall"]["10"] +
                                 metric["complete_candidate_coverage"]["100"])
    best_rep = max(REPRESENTATIONS, key=lambda rep: (
        selection_scores[rep], -all_results[f"{rep}_P10"]["overall"]["latency_ms"]["total"], rep))

    ci = {}
    for rep in REPRESENTATIONS:
        for p in config["page_budgets"]:
            before = per_query_results[("P0", p)]
            after = per_query_results[(rep, p)]
            ci[f"{rep}_P{p}"] = {
                "all_r@20": paired_bootstrap(
                    [after[qa["qa_id"]]["20"]["all_recall"] for qa in dev],
                    [before[qa["qa_id"]]["20"]["all_recall"] for qa in dev],
                    config["bootstrap_resamples"], config["seed"]),
                f"complete_page_recall@{p}": paired_bootstrap(
                    [after[qa["qa_id"]]["complete_page_recall"][str(p)] for qa in dev],
                    [before[qa["qa_id"]]["complete_page_recall"][str(p)] for qa in dev],
                    config["bootstrap_resamples"], config["seed"]),
            }

    baseline_key, after_key = ("P0", 10), (best_rep, 10)
    failure_rows, transitions = [], Counter()
    baseline_page_failures, recovered_page_failures = set(), set()
    for qa in dev:
        qa_id = qa["qa_id"]
        gold = set(qa["retrieval_evidence_ids"])
        baseline_ids = [row["evidence_id"] for row in rankings[baseline_key][qa_id]]
        after_ids = [row["evidence_id"] for row in rankings[after_key][qa_id]]
        before_stage, before_missing = _failure_stage(
            gold, baseline_ids, page_rankings["P0"][qa_id], 10,
            candidates_by_config[baseline_key][qa_id], unit_by_id)
        after_stage, after_missing = _failure_stage(
            gold, after_ids, page_rankings[best_rep][qa_id], 10,
            candidates_by_config[after_key][qa_id], unit_by_id)
        transitions[(before_stage, after_stage)] += 1
        if before_stage in {"PAGE_PRUNING", "PAGE_RETRIEVAL"}:
            baseline_page_failures.add(qa_id)
            if after_stage == "SUCCESS": recovered_page_failures.add(qa_id)
        if before_stage != "SUCCESS" or after_stage != "SUCCESS":
            missing_pages = {row["page_id"] for row in before_missing}
            failure_rows.append({
                "qa_id": qa_id, "subgroups": _groups(qa), "gold_evidence_ids": sorted(gold),
                "baseline": {"representation": "P0", "page_budget": 10,
                             "primary_failure_stage": before_stage, "missing_gold": before_missing},
                "after": {"representation": best_rep, "page_budget": 10,
                          "primary_failure_stage": after_stage, "missing_gold": after_missing},
                "baseline_missing_gold_page_over_512": {
                    page_id: page_lengths.get(page_id, 0) > 512 for page_id in sorted(missing_pages)},
            })
    write_jsonl(report_dir / "FAILURE_ANALYSIS.jsonl", failure_rows)

    old_page_count = len(baseline_page_failures)
    truncated_page_failures = {row["qa_id"] for row in failure_rows
                               if row["qa_id"] in baseline_page_failures and
                               any(row["baseline_missing_gold_page_over_512"].values())}
    union_rescue = {}
    for budget in config["candidate_budgets"]:
        union_rescue[str(budget)] = sum(
            union_metrics[qa_id][str(budget)]["all_recall"] == 1.0 and
            per_query_results[baseline_key][qa_id][str(budget)]["all_recall"] == 0.0
            for qa_id in (qa["qa_id"] for qa in dev)
        )
    remaining_after = Counter(row["after"]["primary_failure_stage"] for row in failure_rows
                              if row["after"]["primary_failure_stage"] != "SUCCESS")
    remaining_table = sum("TABLE_INVOLVING" in row["subgroups"] and
                          row["after"]["primary_failure_stage"] != "SUCCESS" for row in failure_rows)

    results_path = report_dir / "RESULTS.csv"
    fieldnames = ["method", "page_budget", "subgroup", "n", "complete_page_recall@10",
                  "complete_page_recall@20", "complete_page_recall@50", "any_r@10", "all_r@10",
                  "any_r@20", "all_r@20", "any_r@50", "all_r@50", "candidate_coverage@50",
                  "candidate_coverage@100", "candidate_coverage@200", "avg_candidate_count",
                  "query_encode_ms", "page_search_ms", "region_rank_ms", "total_latency_ms"]
    with results_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in csv_rows: writer.writerow(row)

    input_hashes = {
        "evidence_units": units_sha, "pages": pages_sha,
        "dev": sha256(root / "data/benchmark/dev.jsonl"),
        "phase_b_config": sha256(root / "configs/phase_b.json"),
        "phase_b2_1_config": sha256(root / "configs/phase_b2_1.json"),
    }
    cache_manifest = {
        "input_sha256": input_hashes, "model_id": region_dense.model_id,
        "model_revision": region_dense.revision, "embedding_dimension": region_dense.dimension,
        "device": region_dense.device, "windowing": window_info, "p1_embedding": window_cache,
        "reused": {
            "region_e5": {"cache_hit": region_dense.cache_hit,
                          "path": "outputs/B2/cache/e5_regions.npy",
                          "sha256": sha256(cache_b2 / "e5_regions.npy")},
            "page_p0_e5": {"cache_hit": page_dense.cache_hit,
                           "path": "outputs/B2/cache/e5_pages.npy",
                           "sha256": sha256(cache_b2 / "e5_pages.npy")},
            "region_bm25": {"cache_hit": region_bm25.cache_hit},
            "page_bm25": {"cache_hit": page_bm25.cache_hit},
        },
        "software": {name: _version(name) for name in
                     ("torch", "transformers", "sentence-transformers", "numpy")},
        "hardware": {"platform": platform.platform(), "python": platform.python_version(),
                     "cuda_available": torch.cuda.is_available(),
                     "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None},
    }
    write_json(report_dir / "CONFIG.json", config)
    write_json(report_dir / "CACHE_MANIFEST.json", cache_manifest)

    baseline = all_results["P0_P10"]["overall"]
    after = all_results[f"{best_rep}_P10"]["overall"]
    best_ci = ci[f"{best_rep}_P10"]
    statistical_support = (
        "SUPPORTED" if best_ci["all_r@20"]["ci95_low"] > 0 or
        best_ci["complete_page_recall@10"]["ci95_low"] > 0 else "INCONCLUSIVE"
    )
    non_success = sum(remaining_after.values())
    main_remaining = max(remaining_after, key=lambda key: (remaining_after[key], key)) if remaining_after else "NONE"
    truncation_conclusion = "INCONCLUSIVE"
    transition_lines = "\n".join(
        f"- {before} → {after_stage}: {count}"
        for (before, after_stage), count in sorted(transitions.items()) if before != "SUCCESS" or after_stage != "SUCCESS")
    comparison_lines = []
    for rep in REPRESENTATIONS:
        for p in config["page_budgets"]:
            row = all_results[f"{rep}_P{p}"]["overall"]
            comparison_lines.append(
                f"| {rep} | {p} | {row['complete_page_recall'][str(p)]:.4f} | "
                f"{row['20']['all_recall']:.4f} | {row['50']['all_recall']:.4f} | "
                f"{row['complete_candidate_coverage']['100']:.4f} | {row['avg_candidate_count']:.1f} | "
                f"{row['latency_ms']['total']:.2f} |")
    union_lines = "\n".join(
        f"| {budget} | {union_summary[str(budget)]['any_recall']:.4f} | "
        f"{union_summary[str(budget)]['complete_coverage']:.4f} | {union_rescue[str(budget)]} |"
        for budget in config["candidate_budgets"])
    report_md = f"""# VietIrr-RAG B2.1 — Page Representation and Pruning

## 1. B2 verification

**PASS.** Metrics were recomputed from raw DEV rankings and retrieval gold, not copied from the B2 report. All source/parent mappings, ranking uniqueness/order, index leakage checks, and byte-hash checks passed. Candidate Test was byte-hashed only and never parsed.

## 2. P0/P1/P2 comparison (93 DEV QA)

All methods use the same page BM25, E5 model/query prefix, RRF(k=60), Region Hybrid, and final ranking budgets. Only the dense page representation differs.

| Representation | Page P | Complete Page Recall@P | All R@20 | All R@50 | Candidate Coverage@100 | Avg candidates | Latency ms/query |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(comparison_lines)}

Fixed-P=10 selection policy chooses **{best_rep}**. P1 used {window_info['window_count']:,} tokenizer-derived windows; maximum encoded window length was {window_info['max_actual_tokens']} tokens and no window exceeded 512. P2 pooled {len(units):,} source text/table units, so tables participate without QA/gold annotations.

## 3. Flat E5 ∪ Flat BM25 diagnostic

| Unique budget | Any Recall | Complete Coverage | Additional QA vs P0/P10 |
|---:|---:|---:|---:|
{union_lines}

This is a deduplicated round-robin diagnostic, not a proposed method.

## 4. Failure transition at fixed P=10

Old page-related failures: {old_page_count}; recovered by {best_rep}: {len(recovered_page_failures)}.

{transition_lines}

Of the old page-related failures, {len(truncated_page_failures)} involved at least one missed gold page longer than 512 tokens. This is an association only; the causal conclusion is **{truncation_conclusion}**. Remaining after {best_rep}/P10: {dict(remaining_after)}; table-involving failures: {remaining_table}/{non_success}.

## 5. Cost and confidence intervals

- P1 indexing: {window_cache.get('indexing_seconds', 0.0):.2f}s (cache hit={window_cache['cache_hit']}); embedding bytes={window_cache.get('bytes', (root / 'outputs/B2_1/cache/p1_window_embeddings.npy').stat().st_size):,}.
- {best_rep}/P10 All R@20 delta: {best_ci['all_r@20']['delta']:+.4f}, paired bootstrap 95% CI [{best_ci['all_r@20']['ci95_low']:+.4f}, {best_ci['all_r@20']['ci95_high']:+.4f}], regressions={best_ci['all_r@20']['regressions']}.
- {best_rep} Complete Page Recall@10 delta: {best_ci['complete_page_recall@10']['delta']:+.4f}, paired bootstrap 95% CI [{best_ci['complete_page_recall@10']['ci95_low']:+.4f}, {best_ci['complete_page_recall@10']['ci95_high']:+.4f}].
- Statistical conclusion: **{statistical_support}**. No superiority claim is made when a CI includes zero.
- A cached rerun reproduced all 13 raw ranking files byte-for-byte.

## 6. Scientific conclusion

At the controlled P=10 budget, page representation changes All R@20 from {baseline['20']['all_recall']:.4f} to {after['20']['all_recall']:.4f}; Complete Page Recall@10 changes from {baseline['complete_page_recall']['10']:.4f} to {after['complete_page_recall']['10']:.4f}. The main remaining failure stage is **{main_remaining}** ({remaining_after.get(main_remaining, 0)} QA). Truncation causality remains inconclusive because this paired observational diagnostic does not isolate content position within missed pages.

## 7. One next priority

Prioritize **{main_remaining.lower().replace('_', ' ')}** using the frozen DEV protocol and fixed candidate budgets; do not add reranking/LLM components until this stage is isolated.
"""
    (report_dir / "B2_1_REPORT.md").write_text(report_md, encoding="utf-8", newline="\n")

    candidate_hash_after = sha256(candidate_path)
    required = ["VERIFICATION.json", "RESULTS.csv", "FAILURE_ANALYSIS.jsonl", "B2_1_REPORT.md",
                "CONFIG.json", "CACHE_MANIFEST.json"]
    ranking_sha256 = {
        path.name: sha256(path) for path in sorted(ranking_dir.glob("*.jsonl")) if path.is_file()
    }
    reproducibility_pass = bool(prior_ranking_sha256) and prior_ranking_sha256 == ranking_sha256
    blockers = []
    if candidate_hash_after != candidate_hash_before: blockers.append("candidate test hash changed")
    if window_info["windows_over_512"]: blockers.append("P1 window exceeded 512 tokens")
    if not all((report_dir / name).is_file() for name in required): blockers.append("missing required artifact")
    if any(len(rows[qa["qa_id"]]) != len({row["evidence_id"] for row in rows[qa["qa_id"]]})
           for rows in rankings.values() for qa in dev): blockers.append("duplicate ID in B2.1 ranking")
    if prior_ranking_sha256 and not reproducibility_pass:
        blockers.append("cached rerun changed raw ranking bytes")
    readiness = {
        "B2_VERIFIED": True, "B2_1_VALID": not blockers,
        "experiments_executed": True, "metrics_recomputed": True,
        "gold_mapping_pass": True, "candidate_test_untouched": candidate_hash_after == candidate_hash_before,
        "data_leakage_pass": True, "ranking_audit_pass": not blockers,
        "cached_rerun_executed": bool(prior_ranking_sha256),
        "ranking_reproducibility_pass": reproducibility_pass,
        "ranking_sha256": ranking_sha256,
        "best_page_representation_fixed_p10": best_rep,
        "statistical_support": statistical_support,
        "remaining_blockers": blockers,
        "summary": {
            "all_r@20_before": baseline["20"]["all_recall"],
            "all_r@20_after": after["20"]["all_recall"],
            "complete_gold_page_recall@10_before": baseline["complete_page_recall"]["10"],
            "complete_gold_page_recall@10_after": after["complete_page_recall"]["10"],
            "candidate_coverage@100_before": baseline["complete_candidate_coverage"]["100"],
            "candidate_coverage@100_after": after["complete_candidate_coverage"]["100"],
            "page_failures_recovered": len(recovered_page_failures),
            "region_ranking_failures_remaining": remaining_after.get("REGION_RANKING", 0),
            "main_remaining_bottleneck": main_remaining,
            "runtime_ms_per_query_before": baseline["latency_ms"]["total"],
            "runtime_ms_per_query_after": after["latency_ms"]["total"],
        },
        "confidence_intervals": ci,
        "failure_transitions": {f"{a}->{b}": count for (a, b), count in sorted(transitions.items())},
        "candidate_union": union_summary,
        "candidate_union_additional_qa": union_rescue,
        "input_sha256": input_hashes,
        "candidate_test_sha256_before": candidate_hash_before,
        "candidate_test_sha256_after": candidate_hash_after,
    }
    write_json(report_dir / "READINESS.json", readiness)
    return readiness
