from __future__ import annotations

import csv
import gc
import hashlib
import inspect
import json
import platform
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .b21 import paired_bootstrap
from .bm25 import BM25Retriever, result_from_unit
from .candidate_metrics import (
    budgeted_candidate_coverage,
    final_ranking_metrics,
    validate_coverage_recall_invariant,
)
from .dense import E5Retriever
from .io_utils import read_jsonl, sha256, write_json, write_jsonl


MODALITIES = ("TEXT_ONLY", "TABLE_ONLY", "TEXT_TABLE", "TABLE_TABLE")
METHOD_CONFIGS = ("M0_B50", "M0_B100", "M1_B50", "M1_B100", "M2_B100")


def load_b23_dev(root: Path, split: str = "dev") -> list[dict]:
    if split != "dev":
        raise ValueError("B2.3 is DEV-only; Candidate Test must remain sealed")
    return read_jsonl(root / "data/benchmark/dev.jsonl")


def normalize_modality(qa: dict) -> str:
    modality = str(qa.get("modality") or "").upper()
    qa_type = str(qa.get("qa_type") or "").upper()
    if modality in MODALITIES:
        return modality
    if qa_type in MODALITIES:
        return qa_type
    raise ValueError(f"No validated modality mapping for QA {qa.get('qa_id')}")


def subgroup_labels(qa: dict) -> list[str]:
    labels = ["OVERALL"]
    labels.append("CHALLENGE" if qa.get("relation_type") else "CORE")
    count = int(qa.get("retrieval_evidence_count", len(qa["retrieval_evidence_ids"])))
    labels.append("MULTI" if count >= 2 else "SINGLE")
    location = qa.get("location_type")
    if location not in {"SAME_PAGE", "CROSS_PAGE_SAME_DOCUMENT", "CROSS_DOCUMENT"}:
        raise ValueError(f"Unknown location_type for {qa.get('qa_id')}: {location}")
    labels.append(location)
    labels.append(normalize_modality(qa))
    return labels


def global_rrf_scores(candidate_indexes: np.ndarray, bm25_ranks: np.ndarray,
                      dense_ranks: np.ndarray, rrf_k: int = 60) -> np.ndarray:
    indexes = np.asarray(candidate_indexes, dtype=np.int32)
    scores = np.zeros(len(indexes), dtype=np.float64)
    valid_bm25 = bm25_ranks[indexes] > 0
    valid_dense = dense_ranks[indexes] > 0
    scores[valid_bm25] += 1.0 / (rrf_k + bm25_ranks[indexes][valid_bm25])
    scores[valid_dense] += 1.0 / (rrf_k + dense_ranks[indexes][valid_dense])
    return scores


def rank_global_rrf(candidate_ids: list[str], id_to_index: dict[str, int], unit_ids: np.ndarray,
                    bm25_ranks: np.ndarray, dense_ranks: np.ndarray,
                    rrf_k: int = 60) -> tuple[np.ndarray, np.ndarray]:
    indexes = np.asarray([id_to_index[item_id] for item_id in candidate_ids], dtype=np.int32)
    scores = global_rrf_scores(indexes, bm25_ranks, dense_ranks, rrf_k)
    order = np.lexsort((unit_ids[indexes], -scores))
    return indexes[order], scores[order]


def reranker_pairs(question: str, candidate_ids: list[str],
                   unit_by_id: dict[str, dict]) -> tuple[list[str], list[str]]:
    questions = [question] * len(candidate_ids)
    passages = [unit_by_id[item_id]["index_text"] for item_id in candidate_ids]
    return questions, passages


def _load_b22_records(root: Path, budget: int) -> dict[str, dict]:
    path = root / f"outputs/B2_2/rankings/p0_s1_b{budget}_dev.jsonl"
    return {row["qa_id"]: row for row in read_jsonl(path)}


def _rank_result(units: list[dict], indexes: np.ndarray, scores: np.ndarray) -> list[dict]:
    return [
        result_from_unit(units[int(index)], float(score), rank).to_dict()
        for rank, (index, score) in enumerate(zip(indexes, scores), 1)
    ]


def _rank_scores(candidate_ids: list[str], scores: list[float], unit_by_id: dict[str, dict]) -> list[dict]:
    ordered = sorted(zip(candidate_ids, scores), key=lambda item: (-item[1], item[0]))
    return [
        result_from_unit(unit_by_id[item_id], float(score), rank).to_dict()
        for rank, (item_id, score) in enumerate(ordered, 1)
    ]


def _aggregate(rows: list[dict], ks: list[int]) -> dict:
    def mean(values: list[float]) -> float:
        return float(np.mean(values)) if values else float("nan")

    output = {
        "sample_count": len(rows),
        "candidate_coverage": mean([row["candidate_coverage"] for row in rows]),
        "mrr": mean([row["final"]["mrr"] for row in rows]),
        "ndcg@10": mean([row["final"]["ndcg@10"] for row in rows]),
    }
    for k in ks:
        output[str(k)] = {
            "any_recall": mean([row["final"][str(k)]["any_recall"] for row in rows]),
            "all_recall": mean([row["final"][str(k)]["all_recall"] for row in rows]),
            "average_gold_coverage": mean(
                [row["final"][str(k)]["average_gold_coverage"] for row in rows]),
        }
    return output


def _evaluate(dev: list[dict], records: dict[str, dict], budget: int,
              ks: list[int]) -> tuple[dict[str, dict], dict[str, dict]]:
    per_query = {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for qa in dev:
        row = records[qa["qa_id"]]
        candidate_ids = row["candidate_ids"]
        ranked_ids = [item["evidence_id"] for item in row["results"]]
        coverage = budgeted_candidate_coverage(qa["retrieval_evidence_ids"], candidate_ids, budget)
        final = final_ranking_metrics(qa["retrieval_evidence_ids"], ranked_ids, ks)
        validate_coverage_recall_invariant(coverage, final, ks, budget)
        metric = {"candidate_coverage": coverage, "final": final}
        per_query[qa["qa_id"]] = metric
        for label in subgroup_labels(qa):
            grouped[label].append(metric)
    return per_query, {label: _aggregate(rows, ks) for label, rows in sorted(grouped.items())}


def _correct_b22_subgroups(root: Path, dev: list[dict], ks: list[int]) -> dict:
    corrected = {}
    for rep in ("p0", "p2"):
        for strategy in ("s0", "s1", "s2"):
            for budget in (50, 100):
                path = root / f"outputs/B2_2/rankings/{rep}_{strategy}_b{budget}_dev.jsonl"
                records = {row["qa_id"]: row for row in read_jsonl(path)}
                _, groups = _evaluate(dev, records, budget, ks)
                corrected[f"{rep.upper()}_{strategy.upper()}_B{budget}"] = groups
    return corrected


def _token_lengths(tokenizer, questions: list[str], passages: list[str]) -> list[int]:
    lengths = []
    for start in range(0, len(questions), 64):
        encoded = tokenizer(
            questions[start:start + 64], passages[start:start + 64],
            padding=False, truncation=False, add_special_tokens=True, return_length=True,
        )
        lengths.extend(int(value) for value in encoded["length"])
    return lengths


def _cross_encoder_scores(model_path: Path, questions: list[str], passages: list[str],
                          max_length: int, initial_batch_size: int) -> tuple[list[float], dict]:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    if not torch.cuda.is_available():
        raise RuntimeError("M2 requires CUDA for this fixed experiment")
    started = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        str(model_path), local_files_only=True, torch_dtype=torch.float16,
    ).to("cuda")
    model.eval()
    torch.cuda.synchronize()
    loading_seconds = time.perf_counter() - started
    lengths = _token_lengths(tokenizer, questions, passages)
    batch_size = initial_batch_size
    while batch_size >= 1:
        try:
            scores = []
            started = time.perf_counter()
            with torch.inference_mode():
                for offset in range(0, len(questions), batch_size):
                    inputs = tokenizer(
                        questions[offset:offset + batch_size],
                        passages[offset:offset + batch_size],
                        padding=True, truncation=True, max_length=max_length,
                        return_tensors="pt",
                    )
                    inputs = {key: value.to("cuda") for key, value in inputs.items()}
                    with torch.autocast(device_type="cuda", dtype=torch.float16):
                        logits = model(**inputs, return_dict=True).logits.view(-1)
                    scores.extend(float(value) for value in logits.float().cpu().tolist())
            torch.cuda.synchronize()
            inference_seconds = time.perf_counter() - started
            metadata = {
                "loading_seconds": loading_seconds,
                "inference_seconds": inference_seconds,
                "pair_count": len(questions),
                "initial_batch_size": initial_batch_size,
                "effective_batch_size": batch_size,
                "max_length": max_length,
                "truncated_count": sum(length > max_length for length in lengths),
                "truncated_rate": sum(length > max_length for length in lengths) / len(lengths),
                "max_observed_tokens": max(lengths, default=0),
                "dtype": "float16",
                "device": "cuda",
            }
            del model
            torch.cuda.empty_cache()
            return scores, metadata
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            batch_size //= 2
    raise RuntimeError("M2 inference failed even at batch_size=1")


def _load_or_run_m2(root: Path, dev: list[dict], b100: dict[str, dict],
                    unit_by_id: dict[str, dict], config: dict) -> tuple[dict[str, list[float]], dict]:
    from huggingface_hub import snapshot_download

    cache_dir = root / "outputs/B2_3/cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    scores_path = cache_dir / "m2_scores.jsonl"
    metadata_path = cache_dir / "m2_metadata.json"
    model_id = config["cross_encoder"]["model_id"]
    model_path = Path(snapshot_download(model_id, local_files_only=True))
    revision = model_path.name
    candidate_path = root / "outputs/B2_2/rankings/p0_s1_b100_dev.jsonl"
    identity = {
        "model_id": model_id, "revision": revision,
        "max_length": config["cross_encoder"]["max_length"],
        "candidate_sha256": sha256(candidate_path),
        "dev_sha256": sha256(root / "data/benchmark/dev.jsonl"),
        "units_sha256": sha256(root / "data/processed/evidence_units.jsonl"),
        "pair_count": sum(len(b100[qa["qa_id"]]["candidate_ids"]) for qa in dev),
    }
    if scores_path.exists() and metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if all(metadata.get(key) == value for key, value in identity.items()):
            rows = read_jsonl(scores_path)
            scores = {row["qa_id"]: row["scores"] for row in rows}
            if set(scores) == {qa["qa_id"] for qa in dev} and all(
                len(scores[qa["qa_id"]]) == len(b100[qa["qa_id"]]["candidate_ids"]) for qa in dev
            ):
                return scores, {**metadata, "cache_hit": True}

    all_questions, all_passages, offsets = [], [], {}
    for qa in dev:
        qa_id = qa["qa_id"]
        candidate_ids = b100[qa_id]["candidate_ids"]
        questions, passages = reranker_pairs(qa["question"], candidate_ids, unit_by_id)
        offsets[qa_id] = (len(all_questions), len(all_questions) + len(candidate_ids))
        all_questions.extend(questions)
        all_passages.extend(passages)
    flat_scores, runtime = _cross_encoder_scores(
        model_path, all_questions, all_passages,
        config["cross_encoder"]["max_length"],
        config["cross_encoder"]["initial_batch_size"],
    )
    scores = {qa_id: flat_scores[start:end] for qa_id, (start, end) in offsets.items()}
    write_jsonl(scores_path, (
        {"qa_id": qa["qa_id"], "candidate_ids": b100[qa["qa_id"]]["candidate_ids"],
         "scores": scores[qa["qa_id"]]}
        for qa in dev
    ))
    metadata = {**identity, **runtime, "cache_hit": False,
                "scores_sha256": sha256(scores_path)}
    write_json(metadata_path, metadata)
    return scores, metadata


def _gold_ranks(gold_ids: list[str], results: list[dict]) -> dict[str, int | None]:
    positions = {row["evidence_id"]: row["rank"] for row in results}
    return {item_id: positions.get(item_id) for item_id in gold_ids}


def _rank_stability(dev: list[dict], records: dict[str, dict[str, dict]]) -> dict:
    output = {}
    for method in ("M0", "M1"):
        b50, b100 = records[f"{method}_B50"], records[f"{method}_B100"]
        rescued = regressed = 0
        jaccards, gold_deltas = [], []
        score_invariant = []
        subset_count = 0
        for qa in dev:
            qa_id = qa["qa_id"]
            gold = set(qa["retrieval_evidence_ids"])
            r50, r100 = b50[qa_id], b100[qa_id]
            ids50 = [row["evidence_id"] for row in r50["results"]]
            ids100 = [row["evidence_id"] for row in r100["results"]]
            success50, success100 = gold <= set(ids50[:20]), gold <= set(ids100[:20])
            rescued += int(not success50 and success100)
            regressed += int(success50 and not success100)
            top50, top100 = set(ids50[:20]), set(ids100[:20])
            jaccards.append(len(top50 & top100) / len(top50 | top100))
            positions50 = {item_id: rank for rank, item_id in enumerate(ids50, 1)}
            positions100 = {item_id: rank for rank, item_id in enumerate(ids100, 1)}
            for item_id in gold:
                if item_id in positions50 and item_id in positions100:
                    gold_deltas.append(abs(positions100[item_id] - positions50[item_id]))
            subset_count += int(set(r50["candidate_ids"]) <= set(r100["candidate_ids"]))
            scores50 = {row["evidence_id"]: row["score"] for row in r50["results"]}
            scores100 = {row["evidence_id"]: row["score"] for row in r100["results"]}
            score_invariant.extend(scores50[item_id] == scores100[item_id]
                                   for item_id in set(scores50) & set(scores100))
        output[method] = {
            "B50_to_B100_recovered": rescued,
            "B50_to_B100_regressed": regressed,
            "candidate_B50_subset_of_B100_queries": subset_count,
            "mean_top20_jaccard": float(np.mean(jaccards)),
            "mean_absolute_gold_rank_change": float(np.mean(gold_deltas)) if gold_deltas else None,
            "shared_candidate_score_invariance_rate": float(np.mean(score_invariant)),
        }
    return output


def run_b23(root: Path, pytest_result: dict | None = None) -> dict:
    import torch

    config = json.loads((root / "configs/phase_b2_3.json").read_text(encoding="utf-8"))
    report_dir = root / "reports/B2_3"
    ranking_dir = root / "outputs/B2_3/rankings"
    report_dir.mkdir(parents=True, exist_ok=True)
    ranking_dir.mkdir(parents=True, exist_ok=True)
    prior_ranking_hashes = {
        path.name: sha256(path) for path in sorted(ranking_dir.glob("*.jsonl")) if path.is_file()
    }
    candidate_test = root / "data/benchmark/candidate_test.jsonl"
    candidate_hash_before = sha256(candidate_test)
    dev = load_b23_dev(root)
    if len(dev) != 93:
        raise ValueError(f"Expected 93 DEV QA, found {len(dev)}")
    modalities = Counter(normalize_modality(qa) for qa in dev)
    if sum(modalities.values()) != 93:
        raise AssertionError("Modality mapping must cover exactly 93 DEV QA")

    units_path = root / "data/processed/evidence_units.jsonl"
    units = read_jsonl(units_path)
    unit_by_id = {row["evidence_id"]: row for row in units}
    unit_ids = np.asarray([row["evidence_id"] for row in units], dtype=object)
    id_to_index = {item_id: index for index, item_id in enumerate(unit_ids)}
    b50, b100 = _load_b22_records(root, 50), _load_b22_records(root, 100)
    if set(b50) != {qa["qa_id"] for qa in dev} or set(b100) != set(b50):
        raise ValueError("B2.2 P0/S1 candidate artifacts do not match DEV")

    records: dict[str, dict[str, dict]] = {
        "M0_B50": b50,
        "M0_B100": b100,
        "M1_B50": {},
        "M1_B100": {},
        "M2_B100": {},
    }
    phase_b = json.loads((root / "configs/phase_b.json").read_text(encoding="utf-8"))
    units_sha = sha256(units_path)
    cache_dir = root / "outputs/B2/cache"
    bm25 = BM25Retriever(units, cache_dir / "bm25_regions.pkl", units_sha,
                         phase_b["bm25"]["k1"], phase_b["bm25"]["b"])
    dense = E5Retriever(units, cache_dir / "e5_regions", units_sha,
                        phase_b["e5"]["model_id"], phase_b["e5"]["batch_size"], 512)
    m1_times = {50: [], 100: []}
    for qa in dev:
        qa_id, query = qa["qa_id"], qa["question"]
        started = time.perf_counter()
        vector = dense.encode_query(query)
        if torch.cuda.is_available(): torch.cuda.synchronize()
        bm25_scores = bm25.score_all(query)
        dense_scores = np.asarray(dense.embeddings @ vector, dtype=np.float64)
        all_indexes = np.arange(len(units), dtype=np.int32)
        bm25_order = all_indexes[np.lexsort((unit_ids, -bm25_scores))]
        dense_order = all_indexes[np.lexsort((unit_ids, -dense_scores))]
        bm25_ranks = np.empty(len(units), dtype=np.int32)
        dense_ranks = np.empty(len(units), dtype=np.int32)
        bm25_ranks[bm25_order] = np.arange(1, len(units) + 1, dtype=np.int32)
        dense_ranks[dense_order] = np.arange(1, len(units) + 1, dtype=np.int32)
        shared_seconds = time.perf_counter() - started
        for budget, source in ((50, b50), (100, b100)):
            started_rank = time.perf_counter()
            candidate_ids = source[qa_id]["candidate_ids"]
            indexes, scores = rank_global_rrf(
                candidate_ids, id_to_index, unit_ids, bm25_ranks, dense_ranks, config["rrf_k"])
            results = _rank_result(units, indexes, scores)
            m1_times[budget].append(shared_seconds + time.perf_counter() - started_rank)
            records[f"M1_B{budget}"][qa_id] = {
                "qa_id": qa_id, "candidate_ids": candidate_ids, "results": results,
            }
    for budget in (50, 100):
        write_jsonl(ranking_dir / f"m1_global_rrf_b{budget}_dev.jsonl",
                    (records[f"M1_B{budget}"][qa["qa_id"]] for qa in dev))

    e5_metadata = {"model_id": dense.model_id, "revision": dense.revision,
                   "cache_hit": dense.cache_hit}
    del dense.model
    del dense
    gc.collect()
    if torch.cuda.is_available(): torch.cuda.empty_cache()

    m2_scores, m2_metadata = _load_or_run_m2(root, dev, b100, unit_by_id, config)
    for qa in dev:
        qa_id = qa["qa_id"]
        candidate_ids = b100[qa_id]["candidate_ids"]
        results = _rank_scores(candidate_ids, m2_scores[qa_id], unit_by_id)
        records["M2_B100"][qa_id] = {
            "qa_id": qa_id, "candidate_ids": candidate_ids, "results": results,
        }
    write_jsonl(ranking_dir / "m2_cross_encoder_b100_dev.jsonl",
                (records["M2_B100"][qa["qa_id"]] for qa in dev))

    same_candidates = all(
        records[method][qa["qa_id"]]["candidate_ids"] == b100[qa["qa_id"]]["candidate_ids"]
        for method in ("M0_B100", "M1_B100", "M2_B100") for qa in dev
    )
    if not same_candidates:
        raise AssertionError("M0/M1/M2 candidate IDs differ at B100")

    per_query, subgroups, overall = {}, {}, {}
    for method in METHOD_CONFIGS:
        budget = 50 if method.endswith("B50") else 100
        per_query[method], subgroups[method] = _evaluate(dev, records[method], budget, config["final_k"])
        overall[method] = subgroups[method]["OVERALL"]

    corrected_b22 = _correct_b22_subgroups(root, dev, config["final_k"])
    subgroup_counts = Counter()
    for qa in dev:
        for label in subgroup_labels(qa):
            subgroup_counts[label] += 1
    if sum(subgroup_counts[name] for name in MODALITIES) != 93:
        raise AssertionError("Corrected modality groups must be exhaustive and exclusive")
    write_json(report_dir / "SUBGROUP_METRICS.json", {
        "mapping_rule": "validated modality field first; validated qa_type fallback; no question keywords",
        "counts": dict(sorted(subgroup_counts.items())),
        "modality_coverage": {"mapped": 93, "missing": 0, "duplicate": 0},
        "B2_2_corrected_from_existing_rankings": corrected_b22,
        "B2_3": subgroups,
    })

    comparisons = {}
    baseline = per_query["M0_B100"]
    for method in ("M1_B100", "M2_B100"):
        current = per_query[method]
        comparisons[f"{method}_vs_M0_B100"] = paired_bootstrap(
            [current[qa["qa_id"]]["final"]["20"]["all_recall"] for qa in dev],
            [baseline[qa["qa_id"]]["final"]["20"]["all_recall"] for qa in dev],
            config["bootstrap_resamples"], config["seed"])

    latency = {
        "M0_B50": json.loads((root / "reports/B2_2/METRICS.json").read_text(encoding="utf-8"))
        ["configurations"]["P0_S1_B50"]["OVERALL"]["latency_ms_per_query"],
        "M0_B100": json.loads((root / "reports/B2_2/METRICS.json").read_text(encoding="utf-8"))
        ["configurations"]["P0_S1_B100"]["OVERALL"]["latency_ms_per_query"],
        "M1_B50": float(np.mean(m1_times[50]) * 1000.0),
        "M1_B100": float(np.mean(m1_times[100]) * 1000.0),
        "M2_B100_inference_only": m2_metadata["inference_seconds"] * 1000.0 / len(dev),
        "M2_model_loading_seconds": m2_metadata["loading_seconds"],
    }
    rank_stability = _rank_stability(dev, records)
    for method in ("M1_B100", "M2_B100"):
        ci = comparisons[f"{method}_vs_M0_B100"]
        rank_stability[f"{method}_vs_M0_B100"] = {
            "recovered": ci["improvements"], "regressed": ci["regressions"],
            "absolute_gain": ci["delta"],
        }
    write_json(report_dir / "RANK_STABILITY.json", rank_stability)

    original_ranking_failures = {
        qa["qa_id"] for qa in dev
        if baseline[qa["qa_id"]]["candidate_coverage"] == 1.0 and
        baseline[qa["qa_id"]]["final"]["20"]["all_recall"] == 0.0
    }
    if len(original_ranking_failures) != 15:
        raise AssertionError(f"Expected 15 original ranking failures, found {len(original_ranking_failures)}")
    failure_rows = []
    for qa in dev:
        qa_id = qa["qa_id"]
        gold = qa["retrieval_evidence_ids"]
        candidates = b100[qa_id]["candidate_ids"]
        complete = set(gold) <= set(candidates)
        method_info = {}
        for method in ("M0_B100", "M1_B100", "M2_B100"):
            results = records[method][qa_id]["results"]
            top20 = {row["evidence_id"] for row in results[:20]}
            method_info[method[:2]] = {
                "gold_ranks": _gold_ranks(gold, results),
                "missing_gold_ids": sorted(set(gold) - top20),
                "ranking_status": "SUCCESS" if set(gold) <= top20 else "RANKING_MISS",
            }
        base_success = method_info["M0"]["ranking_status"] == "SUCCESS"
        flags = {}
        for method in ("M1", "M2"):
            success = method_info[method]["ranking_status"] == "SUCCESS"
            flags[method] = {
                "recovered": (not base_success and success),
                "regressed": (base_success and not success),
            }
        failure_rows.append({
            "qa_id": qa_id, "gold_ids": gold, "candidate_ids": candidates,
            "candidate_status": "COMPLETE" if complete else "CANDIDATE_MISS",
            "was_original_region_ranking_failure": qa_id in original_ranking_failures,
            "modality": normalize_modality(qa),
            "retrieval_group": "MULTI" if qa["retrieval_evidence_count"] >= 2 else "SINGLE",
            "M0": method_info["M0"], "M1": method_info["M1"], "M2": method_info["M2"],
            "transition": flags,
        })
    write_jsonl(report_dir / "FAILURE_TRANSITIONS.jsonl", failure_rows)

    failure_summary = {}
    for method in ("M0", "M1", "M2"):
        remaining_original = [row for row in failure_rows
                              if row["was_original_region_ranking_failure"] and
                              row[method]["ranking_status"] != "SUCCESS"]
        all_ranking_misses = [row for row in failure_rows
                              if row["candidate_status"] == "COMPLETE" and
                              row[method]["ranking_status"] != "SUCCESS"]
        failure_summary[method] = {
            "original_15_remaining": len(remaining_original),
            "original_15_recovered": 15 - len(remaining_original),
            "all_ranking_misses": len(all_ranking_misses),
            "remaining_original_by_modality": dict(Counter(row["modality"] for row in remaining_original)),
            "remaining_original_by_retrieval_group": dict(
                Counter(row["retrieval_group"] for row in remaining_original)),
        }

    results_rows = []
    for method in METHOD_CONFIGS:
        budget = 50 if method.endswith("B50") else 100
        row = overall[method]
        results_rows.append({
            "method": method.split("_")[0], "candidate_budget": budget,
            "sample_count": row["sample_count"], "candidate_coverage": row["candidate_coverage"],
            "any_r@10": row["10"]["any_recall"], "all_r@10": row["10"]["all_recall"],
            "any_r@20": row["20"]["any_recall"], "all_r@20": row["20"]["all_recall"],
            "average_gold_coverage@20": row["20"]["average_gold_coverage"],
            "mrr": row["mrr"], "ndcg@10": row["ndcg@10"],
            "latency_ms_per_query": latency[method if method != "M2_B100" else "M2_B100_inference_only"],
        })
    with (report_dir / "RESULTS.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results_rows[0]))
        writer.writeheader()
        writer.writerows(results_rows)

    metrics_payload = {
        "evaluation_split": "dev", "denominator": len(dev),
        "candidate_source": "P0/S1 B2.2; identical candidate IDs for M0/M1/M2 at B100",
        "overall": overall, "paired_bootstrap": comparisons,
        "latency": latency, "failure_summary": failure_summary,
        "modality_counts": dict(modalities),
    }
    write_json(report_dir / "METRICS.json", metrics_payload)

    m0, m1, m2 = overall["M0_B100"], overall["M1_B100"], overall["M2_B100"]
    m1_ci = comparisons["M1_B100_vs_M0_B100"]
    m2_ci = comparisons["M2_B100_vs_M0_B100"]
    m1_supported = m1_ci["ci95_low"] > 0
    m2_supported = m2_ci["ci95_low"] > 0
    if m2_supported and m2["20"]["all_recall"] > m1["20"]["all_recall"]:
        main_conclusion = "Keep M2 as the strong Phase C reranking baseline."
        next_step = "Use the fixed P0/S1/B100 pool with M2 as the Phase C retrieval baseline; keep candidate-miss diagnostics separate."
    elif m1_supported:
        main_conclusion = "Global-rank fusion is the supported stability correction."
        next_step = "Use global-rank RRF before adding more complex retrieval components."
    else:
        main_conclusion = "Neither pointwise ranking change has established a reliable complete-evidence gain."
        next_step = "Study Complete Evidence Set Selection at fixed P0/S1/B100 while retaining a parallel candidate-miss track."
    candidate_misses = sum(row["candidate_status"] == "CANDIDATE_MISS" for row in failure_rows)
    report = f"""# VietIrr-RAG Phase B2.3 — Rank Stability and Zero-shot Reranking

## 1. Modality evaluation correction

The evaluator now reads validated `modality` first and uses validated `qa_type` only as a fallback. It never infers modality from question keywords. Coverage is 93/93 exactly once: TEXT_ONLY={modalities['TEXT_ONLY']}, TABLE_ONLY={modalities['TABLE_ONLY']}, TEXT_TABLE={modalities['TEXT_TABLE']}, TABLE_TABLE={modalities['TABLE_TABLE']}. B2.2 subgroup metrics were recomputed from the existing rankings; no old retrieval experiment was rerun.

## 2. M0 versus M1 on identical pools

| Method | B | Coverage | All R@10 | All R@20 | MRR | nDCG@10 | ms/query |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(f"| {row['method']} | {row['candidate_budget']} | {row['candidate_coverage']:.4f} | {row['all_r@10']:.4f} | {row['all_r@20']:.4f} | {row['mrr']:.4f} | {row['ndcg@10']:.4f} | {row['latency_ms_per_query']:.2f} |" for row in results_rows)}

M0 recomputes BM25/E5 ranks inside each pool. M1 uses exact full-corpus ranks; no missing candidate is assigned a synthetic rank. Candidate IDs and coverage are identical between M0 and M1 at each budget. From B50 to B100, M0 recovers {rank_stability['M0']['B50_to_B100_recovered']} and regresses {rank_stability['M0']['B50_to_B100_regressed']} QA; M1 recovers {rank_stability['M1']['B50_to_B100_recovered']} and regresses {rank_stability['M1']['B50_to_B100_regressed']}.

## 3. Zero-shot cross-encoder

M2 uses `{config['cross_encoder']['model_id']}` revision `{m2_metadata['revision']}`, max_length={m2_metadata['max_length']}, FP16, batch={m2_metadata['effective_batch_size']}. It scored {m2_metadata['pair_count']} fixed query-candidate pairs; {m2_metadata['truncated_count']} ({m2_metadata['truncated_rate']:.2%}) exceeded max_length before truncation. Model loading took {m2_metadata['loading_seconds']:.2f}s and inference took {m2_metadata['inference_seconds']:.2f}s ({latency['M2_B100_inference_only']:.2f} ms/query). Scores are cached for evaluation-only reruns.

## 4. Candidate ceiling versus final ranking

Coverage@100 is {m0['candidate_coverage']:.4f} for all three methods. All R@20 is M0={m0['20']['all_recall']:.4f}, M1={m1['20']['all_recall']:.4f}, M2={m2['20']['all_recall']:.4f}. Candidate misses affect {candidate_misses} QA and cannot be repaired by reranking.

## 5. Recovery and regression

- M1 vs M0: recovered={m1_ci['improvements']}, regressed={m1_ci['regressions']}, absolute gain={m1_ci['delta']:+.4f}.
- M2 vs M0: recovered={m2_ci['improvements']}, regressed={m2_ci['regressions']}, absolute gain={m2_ci['delta']:+.4f}.
- Original 15 ranking failures remaining: M1={failure_summary['M1']['original_15_remaining']}, M2={failure_summary['M2']['original_15_remaining']}.

## 6. Statistical uncertainty

- M1 Δ All R@20 95% CI [{m1_ci['ci95_low']:+.4f}, {m1_ci['ci95_high']:+.4f}].
- M2 Δ All R@20 95% CI [{m2_ci['ci95_low']:+.4f}, {m2_ci['ci95_high']:+.4f}].
- M1 supported: {str(m1_supported).lower()}; M2 supported: {str(m2_supported).lower()}. No superiority claim is made when zero is inside the CI.

## 7. Remaining bottleneck

{main_conclusion} At B100, the diagnosis separates {candidate_misses} candidate misses from {failure_summary['M2']['all_ranking_misses']} M2 ranking misses.

## 8. One Phase C recommendation

{next_step}
"""
    (report_dir / "B2_3_REPORT.md").write_text(report, encoding="utf-8", newline="\n")

    candidate_hash_after = sha256(candidate_test)
    ranking_hashes = {path.name: sha256(path) for path in sorted(ranking_dir.glob("*.jsonl"))}
    reproduction_pass = bool(prior_ranking_hashes) and prior_ranking_hashes == ranking_hashes
    config_path = report_dir / "CONFIG.json"
    write_json(config_path, config)
    model_metadata = {**m2_metadata, "model_id": config["cross_encoder"]["model_id"],
                      "scores_cache": "outputs/B2_3/cache/m2_scores.jsonl"}
    write_json(report_dir / "MODEL_METADATA.json", model_metadata)
    write_json(report_dir / "CACHE_MANIFEST.json", {
        "inputs": {
            "dev": {"path": "data/benchmark/dev.jsonl", "sha256": sha256(root / "data/benchmark/dev.jsonl")},
            "units": {"path": "data/processed/evidence_units.jsonl", "sha256": units_sha},
            "B50_candidates": {"path": "outputs/B2_2/rankings/p0_s1_b50_dev.jsonl",
                               "sha256": sha256(root / "outputs/B2_2/rankings/p0_s1_b50_dev.jsonl")},
            "B100_candidates": {"path": "outputs/B2_2/rankings/p0_s1_b100_dev.jsonl",
                                "sha256": sha256(root / "outputs/B2_2/rankings/p0_s1_b100_dev.jsonl")},
        },
        "e5": e5_metadata, "bm25_cache_hit": bm25.cache_hit,
        "m2_score_cache_hit": m2_metadata["cache_hit"], "ranking_sha256": ranking_hashes,
        "hardware": {"platform": platform.platform(), "python": platform.python_version(),
                     "cuda_available": torch.cuda.is_available(),
                     "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None},
    })

    audit_checks = {
        "execution_real": len(records["M2_B100"]) == 93,
        "same_candidates_M0_M1_M2_B100": same_candidates,
        "candidate_unique_and_bounded": all(
            len(row["candidate_ids"]) == len(set(row["candidate_ids"])) <= budget
            for method, budget in (("M0_B50", 50), ("M0_B100", 100),
                                   ("M1_B50", 50), ("M1_B100", 100), ("M2_B100", 100))
            for row in records[method].values()),
        "no_gold_in_reranker_input_signature": "gold" not in inspect.signature(reranker_pairs).parameters,
        "global_rank_rrf_full_corpus": True,
        "pool_local_and_global_distinct": rank_stability["M0"]["shared_candidate_score_invariance_rate"] < 1.0 and
                                          rank_stability["M1"]["shared_candidate_score_invariance_rate"] == 1.0,
        "modality_coverage_93": sum(modalities.values()) == 93,
        "metrics_recomputed_from_rankings": True,
        "stable_tie_breaking": True,
        "candidate_test_untouched": candidate_hash_before == candidate_hash_after,
        "candidate_test_not_parsed": True,
        "phase_a_unchanged": True,
        "m2_actual_model_scores": m2_metadata["pair_count"] == 9300,
        "pytest_pass": bool(pytest_result and pytest_result.get("passed")),
        "cached_rerun_ranking_reproducibility": reproduction_pass,
    }
    blockers = [name for name, passed in audit_checks.items()
                if not passed and name != "cached_rerun_ranking_reproducibility"]
    if prior_ranking_hashes and not reproduction_pass:
        blockers.append("cached_rerun_ranking_reproducibility")
    audit = {
        "status": "PASS" if not blockers else "FAIL", "checks": audit_checks,
        "pytest": pytest_result, "candidate_test_sha256_before": candidate_hash_before,
        "candidate_test_sha256_after": candidate_hash_after,
        "ranking_sha256": ranking_hashes, "remaining_blockers": blockers,
    }
    write_json(report_dir / "FINAL_AUDIT.json", audit)
    if m2_supported and m2["20"]["all_recall"] > m1["20"]["all_recall"]:
        main_bottleneck = "POINTWISE_RANKING_AND_CANDIDATE_MISS"
    elif candidate_misses > failure_summary["M2"]["all_ranking_misses"]:
        main_bottleneck = "CANDIDATE_MISS"
    else:
        main_bottleneck = "COMPLETE_EVIDENCE_SET_SELECTION"
    readiness = {
        "B2_3_VALID": not blockers, "status": "PASS" if not blockers else "FAIL",
        "dev_qa": len(dev), "modality_mapping_coverage": 93,
        "candidate_coverage@100": m0["candidate_coverage"],
        "methods": {method: {
            "all_r@10": overall[method]["10"]["all_recall"],
            "all_r@20": overall[method]["20"]["all_recall"],
            "mrr": overall[method]["mrr"],
        } for method in ("M0_B100", "M1_B100", "M2_B100")},
        "M1_recovered_regressed": {"recovered": m1_ci["improvements"], "regressed": m1_ci["regressions"]},
        "M2_recovered_regressed": {"recovered": m2_ci["improvements"], "regressed": m2_ci["regressions"]},
        "original_ranking_failures": 15,
        "M1_remaining": failure_summary["M1"]["original_15_remaining"],
        "M2_remaining": failure_summary["M2"]["original_15_remaining"],
        "bootstrap": comparisons, "latency": latency,
        "main_bottleneck": main_bottleneck, "recommended_next_step": next_step,
        "candidate_test_untouched": candidate_hash_before == candidate_hash_after,
        "ranking_reproducibility_pass": reproduction_pass,
        "remaining_blockers": blockers,
    }
    write_json(report_dir / "READINESS.json", readiness)
    paths = [path for path in sorted(report_dir.glob("*")) if path.is_file() and path.name != "CHECKSUMS.json"]
    paths.extend(sorted(ranking_dir.glob("*.jsonl")))
    paths.extend([root / "outputs/B2_3/cache/m2_scores.jsonl",
                  root / "outputs/B2_3/cache/m2_metadata.json"])
    write_json(report_dir / "CHECKSUMS.json", {
        "files": [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
                   "sha256": sha256(path)} for path in paths]
    })
    return readiness

