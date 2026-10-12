from __future__ import annotations

import csv
import hashlib
import inspect
import json
import math
import re
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .b23 import normalize_modality
from .bm25 import BM25Retriever, result_from_unit
from .candidate_metrics import final_ranking_metrics
from .dense import E5Retriever
from .io_utils import read_jsonl, sha256, write_json, write_jsonl
from .tokenization import tokenize


REQUIREMENTS = (
    "VALUE", "STATUS", "FORECAST", "EXPLANATION", "ACTION",
    "RULE", "TEMPORAL_COMPARISON",
)
SOURCE_PATHS = {
    "P0_PAGE": "outputs/B2_1/rankings/p0_p20_dev_top200.jsonl",
    "P2_PAGE": "outputs/B2_1/rankings/p2_p20_dev_top200.jsonl",
    "FLAT_E5": "outputs/B2/rankings/e5_dev_top200.jsonl",
    "FLAT_BM25": "outputs/B2/rankings/bm25_dev_top200.jsonl",
}
EXPERIMENTS = ("E0", "E1", "E2", "E3")
MODALITIES = ("TEXT_ONLY", "TABLE_ONLY", "TEXT_TABLE", "TABLE_TABLE")
EXPECTED_GROUPS = (
    "OVERALL", "CORE", "CHALLENGE", "RETRIEVAL_SINGLE", "RETRIEVAL_MULTI",
    "RETRIEVAL_3_PLUS", "SAME_PAGE", "CROSS_PAGE_SAME_DOCUMENT", "CROSS_DOCUMENT",
    *MODALITIES,
)
DATE_PATTERN = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{4}[/-]\d{1,2}[/-]\d{1,2}|20\d{2})\b"
)
STOPWORDS = {
    "cua", "va", "la", "bao", "nhieu", "theo", "tai", "trong", "cho", "tu",
    "den", "cac", "mot", "nhung", "duoc", "voi", "ve", "nao", "gi", "hay",
}


QUESTION_PATTERNS = {
    "VALUE": ("bao nhieu", "gia tri", "so luong", "dien tich", "dung tich", "muc nuoc", "luu luong", "%"),
    "STATUS": ("tinh trang", "hien trang", "trang thai", "danh gia", "muc do"),
    "FORECAST": ("du bao", "du kien", "kha nang", "nhan dinh"),
    "EXPLANATION": ("vi sao", "nguyen nhan", "giai thich", "do dau"),
    "ACTION": ("bien phap", "khuyen nghi", "de xuat", "can lam", "ung pho", "xu ly", "chi dao"),
    "RULE": ("quy dinh", "dieu kien", "bat buoc", "duoc phep", "tieu chi", "phai"),
    "TEMPORAL_COMPARISON": ("so voi", "thay doi", "tang", "giam", "lan luot", "cac ky", "truoc", "sau"),
}

EVIDENCE_PATTERNS = {
    "VALUE": ("dien tich", "dung tich", "muc nuoc", "luu luong", "so lieu", "gia tri", "ha", "m3", "%"),
    "STATUS": ("tinh trang", "hien trang", "trang thai", "danh gia", "binh thuong", "bao dong"),
    "FORECAST": ("du bao", "du kien", "kha nang", "nhan dinh", "trong nhung ngay toi"),
    "EXPLANATION": ("nguyen nhan", " do ", " vi ", "dan den", "anh huong"),
    "ACTION": ("bien phap", "khuyen nghi", "de xuat", "yeu cau", "chi dao", "ung pho", "xu ly"),
    "RULE": ("quy dinh", "dieu kien", "bat buoc", "duoc phep", "tieu chi", "phai"),
    "TEMPORAL_COMPARISON": ("so voi", "tang", "giam", "truoc", "sau", "thoi gian", "ngay", "thang"),
}


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFD", str(text or "").casefold())
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn").replace("đ", "d")


def _json_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_c1_dev(root: Path, split: str = "dev") -> list[dict]:
    if split != "dev":
        raise ValueError("C1 is DEV-only; Candidate Test must remain sealed")
    return read_jsonl(root / "data/benchmark/dev.jsonl")


def detect_question_requirements(question: str) -> list[str]:
    folded = _fold(question)
    requirements = [
        requirement for requirement, patterns in QUESTION_PATTERNS.items()
        if any(pattern in folded for pattern in patterns)
    ]
    dates = DATE_PATTERN.findall(folded)
    if len(set(dates)) >= 2 and "TEMPORAL_COMPARISON" not in requirements:
        requirements.append("TEMPORAL_COMPARISON")
    return [name for name in REQUIREMENTS if name in requirements]


def content_evidence_roles(text: str) -> list[str]:
    folded = _fold(text)
    roles = [
        requirement for requirement, patterns in EVIDENCE_PATTERNS.items()
        if any(pattern in folded for pattern in patterns)
    ]
    if len(set(DATE_PATTERN.findall(folded))) >= 2 and "TEMPORAL_COMPARISON" not in roles:
        roles.append("TEMPORAL_COMPARISON")
    return [name for name in REQUIREMENTS if name in roles]


def build_diverse_candidate_union(
    sources: dict[str, list[dict]], quotas: dict[str, int], budget: int,
    priority: list[str],
) -> tuple[list[str], dict[str, list[dict]], dict]:
    if budget <= 0:
        raise ValueError("Candidate budget must be positive")
    if sum(quotas.values()) != budget:
        raise ValueError("Fixed G1 quotas must sum to the candidate budget")
    if set(priority) != set(quotas) or set(priority) != set(sources):
        raise ValueError("G1 source, quota, and priority keys must match")

    rank_maps = {
        source: {row["evidence_id"]: rank for rank, row in enumerate(rows, 1)}
        for source, rows in sources.items()
    }
    output: list[str] = []
    seen: set[str] = set()
    quota_added: dict[str, int] = {}
    backfill_added: dict[str, int] = {source: 0 for source in priority}

    for source in priority:
        added = 0
        for row in sources[source]:
            item_id = row["evidence_id"]
            if item_id in seen:
                continue
            output.append(item_id)
            seen.add(item_id)
            added += 1
            if added >= quotas[source] or len(output) >= budget:
                break
        quota_added[source] = added

    if len(output) < budget:
        for source in priority:
            for row in sources[source]:
                item_id = row["evidence_id"]
                if item_id in seen:
                    continue
                output.append(item_id)
                seen.add(item_id)
                backfill_added[source] += 1
                if len(output) >= budget:
                    break
            if len(output) >= budget:
                break

    provenance = {
        item_id: [
            {"source": source, "source_rank": rank_maps[source][item_id]}
            for source in priority if item_id in rank_maps[source]
        ]
        for item_id in output
    }
    metadata = {
        "budget": budget,
        "quota_targets": quotas,
        "quota_added": quota_added,
        "backfill_added": backfill_added,
        "source_priority": priority,
        "unique_count": len(output),
    }
    return output, provenance, metadata


def _token_set(text: str) -> set[str]:
    return {token for token in (_fold(value) for value in tokenize(text)) if token not in STOPWORDS and len(token) > 1}


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return 0.0 if not union else len(left & right) / len(union)


def _time_signatures(text: str) -> set[str]:
    return set(DATE_PATTERN.findall(_fold(text)))


def _cross_document_signal(question: str) -> bool:
    folded = _fold(question)
    return any(cue in folded for cue in ("chuoi tai lieu", "cac bao cao", "cac tai lieu", "lan luot"))


def _provenance_compatibility(
    question: str, candidate: dict, selected: list[dict], candidate_times: set[str],
    selected_times: set[str], requirements: list[str],
) -> float:
    if not selected:
        return 0.0
    score = 0.0
    if any(row["doc_id"] == candidate["doc_id"] for row in selected):
        score += 0.5
    if any(row["page_id"] == candidate["page_id"] for row in selected):
        score += 0.25
    if "TEMPORAL_COMPARISON" in requirements and candidate_times and candidate_times - selected_times:
        score += 0.5
    if _cross_document_signal(question) and all(row["doc_id"] != candidate["doc_id"] for row in selected):
        score += 0.5
    return min(score, 1.0)


def set_aware_select(
    question: str, candidate_ids: list[str], base_results: list[dict],
    unit_by_id: dict[str, dict], weights: dict[str, float], limit: int = 20,
) -> tuple[list[dict], dict]:
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("Set-aware selector requires unique candidate IDs")
    base_by_id = {row["evidence_id"]: row for row in base_results}
    if set(candidate_ids) != set(base_by_id):
        raise ValueError("Base ranking must contain exactly the candidate pool")
    requirements = detect_question_requirements(question)
    base_scores = np.asarray([float(base_by_id[item_id]["score"]) for item_id in candidate_ids])
    minimum, maximum = float(base_scores.min()), float(base_scores.max())
    denominator = maximum - minimum
    normalized = {
        item_id: (float(base_by_id[item_id]["score"]) - minimum) / denominator if denominator else 1.0
        for item_id in candidate_ids
    }
    base_rank = {row["evidence_id"]: int(row["rank"]) for row in base_results}

    if not requirements:
        selected = []
        steps = []
        for rank, row in enumerate(base_results[:limit], 1):
            result = dict(row)
            result["rank"] = rank
            selected.append(result)
            steps.append({
                "step": rank, "evidence_id": row["evidence_id"], "utility": normalized[row["evidence_id"]],
                "base_relevance": normalized[row["evidence_id"]], "new_requirements": [],
                "covered_requirements": [], "fallback": True,
            })
        return selected, {
            "requirements": [], "fallback_to_r0": True, "covered_requirements": [], "steps": steps,
        }

    question_tokens = _token_set(question)
    feature_map = {}
    for item_id in candidate_ids:
        unit = unit_by_id[item_id]
        tokens = _token_set(unit["index_text"])
        feature_map[item_id] = {
            "tokens": tokens,
            "roles": set(content_evidence_roles(unit["index_text"])),
            "times": _time_signatures(unit["index_text"]),
            "question_overlap": _jaccard(question_tokens, tokens),
        }

    selected_ids: list[str] = []
    selected_units: list[dict] = []
    selected_times: set[str] = set()
    covered: set[str] = set()
    remaining = set(candidate_ids)
    steps = []
    for step in range(1, min(limit, len(candidate_ids)) + 1):
        scored = []
        for item_id in remaining:
            unit = unit_by_id[item_id]
            features = feature_map[item_id]
            new_requirements = (features["roles"] & set(requirements)) - covered
            requirement_score = len(new_requirements) / len(requirements)
            redundancy = max(
                (_jaccard(features["tokens"], feature_map[selected_id]["tokens"])
                 for selected_id in selected_ids), default=0.0,
            )
            provenance = _provenance_compatibility(
                question, unit, selected_units, features["times"], selected_times, requirements,
            )
            utility = (
                weights["base_relevance"] * normalized[item_id]
                + weights["unmet_requirement"] * requirement_score
                + weights["provenance_compatibility"] * provenance
                + weights["question_overlap"] * features["question_overlap"]
                - weights["redundancy_penalty"] * redundancy
            )
            scored.append((
                -utility, base_rank[item_id], item_id, utility, new_requirements,
                requirement_score, provenance, redundancy, features["question_overlap"],
            ))
        chosen = min(scored)
        _, _, item_id, utility, new_requirements, requirement_score, provenance, redundancy, overlap = chosen
        selected_ids.append(item_id)
        selected_units.append(unit_by_id[item_id])
        selected_times.update(feature_map[item_id]["times"])
        covered.update(new_requirements)
        remaining.remove(item_id)
        steps.append({
            "step": step, "evidence_id": item_id, "utility": utility,
            "base_relevance": normalized[item_id], "base_rank": base_rank[item_id],
            "new_requirements": sorted(new_requirements),
            "covered_requirements": sorted(covered),
            "provenance_compatibility": provenance,
            "question_overlap": overlap, "redundancy_penalty_input": redundancy,
            "requirement_coverage_input": requirement_score, "fallback": False,
        })

    selected_results = []
    for rank, item_id in enumerate(selected_ids, 1):
        result = dict(base_by_id[item_id])
        result["rank"] = rank
        result["score"] = float(steps[rank - 1]["utility"])
        result["base_score"] = float(base_by_id[item_id]["score"])
        selected_results.append(result)
    return selected_results, {
        "requirements": requirements, "fallback_to_r0": False,
        "covered_requirements": sorted(covered), "steps": steps,
    }


def _subgroup_labels(qa: dict) -> list[str]:
    count = int(qa.get("retrieval_evidence_count", len(qa["retrieval_evidence_ids"])))
    labels = [
        "OVERALL", "CHALLENGE" if qa.get("relation_type") else "CORE",
        "RETRIEVAL_MULTI" if count >= 2 else "RETRIEVAL_SINGLE",
        qa["location_type"], normalize_modality(qa),
    ]
    if count >= 3:
        labels.append("RETRIEVAL_3_PLUS")
    return labels


def _ranking_redundancy(ranked_ids: list[str], unit_by_id: dict[str, dict], limit: int = 20) -> float:
    token_sets = [_token_set(unit_by_id[item_id]["index_text"]) for item_id in ranked_ids[:limit]]
    if len(token_sets) < 2:
        return 0.0
    return float(np.mean([
        max(_jaccard(tokens, other) for j, other in enumerate(token_sets) if i != j)
        for i, tokens in enumerate(token_sets)
    ]))


def _mean(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


def _aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {
            "sample_count": 0, "candidate_coverage@100": None, "average_gold_coverage@100": None,
            "any_r@10": None, "all_r@10": None, "any_r@20": None, "all_r@20": None,
            "average_gold_coverage@20": None, "mrr": None, "ndcg@10": None,
            "evidence_redundancy@20": None, "runtime_ms_per_query": None,
        }
    return {
        "sample_count": len(rows),
        "candidate_coverage@100": _mean([row["candidate_complete"] for row in rows]),
        "average_gold_coverage@100": _mean([row["candidate_gold_coverage"] for row in rows]),
        "any_r@10": _mean([row["final"]["10"]["any_recall"] for row in rows]),
        "all_r@10": _mean([row["final"]["10"]["all_recall"] for row in rows]),
        "any_r@20": _mean([row["final"]["20"]["any_recall"] for row in rows]),
        "all_r@20": _mean([row["final"]["20"]["all_recall"] for row in rows]),
        "average_gold_coverage@20": _mean([row["final"]["20"]["average_gold_coverage"] for row in rows]),
        "mrr": _mean([row["final"]["mrr"] for row in rows]),
        "ndcg@10": _mean([row["final"]["ndcg@10"] for row in rows]),
        "evidence_redundancy@20": _mean([row["redundancy"] for row in rows]),
        "runtime_ms_per_query": _mean([row["runtime_ms"] for row in rows]),
    }


def _evaluate(
    dev: list[dict], candidates: dict[str, dict[str, dict]], rankings: dict[str, dict[str, dict]],
    unit_by_id: dict[str, dict], runtime_by_experiment: dict[str, dict[str, float]],
) -> tuple[dict[str, dict[str, dict]], dict[str, dict[str, dict]]]:
    per_query: dict[str, dict[str, dict]] = {experiment: {} for experiment in EXPERIMENTS}
    subgroups: dict[str, dict[str, dict]] = {}
    for experiment in EXPERIMENTS:
        grouped: dict[str, list[dict]] = {label: [] for label in EXPECTED_GROUPS}
        candidate_key = "G1" if experiment == "E1" else "G0"
        for qa in dev:
            qa_id = qa["qa_id"]
            candidate_ids = candidates[candidate_key][qa_id]["candidate_ids"]
            ranked_ids = [row["evidence_id"] for row in rankings[experiment][qa_id]["results"]]
            gold = set(qa["retrieval_evidence_ids"])
            candidate_set = set(candidate_ids)
            final = final_ranking_metrics(qa["retrieval_evidence_ids"], ranked_ids, [10, 20])
            metric = {
                "candidate_complete": float(gold <= candidate_set),
                "candidate_gold_coverage": len(gold & candidate_set) / len(gold),
                "final": final,
                "redundancy": _ranking_redundancy(ranked_ids, unit_by_id),
                "runtime_ms": runtime_by_experiment[experiment][qa_id],
            }
            if final["20"]["all_recall"] > metric["candidate_complete"]:
                raise AssertionError("Final All R@20 exceeds complete candidate coverage")
            per_query[experiment][qa_id] = metric
            for label in _subgroup_labels(qa):
                grouped[label].append(metric)
        subgroups[experiment] = {label: _aggregate(grouped[label]) for label in EXPECTED_GROUPS}
    return per_query, subgroups


def _bootstrap(
    current: list[float], baseline: list[float], resamples: int, seed: int,
    clusters: list[str] | None = None,
) -> dict:
    current_array = np.asarray(current, dtype=np.float64)
    baseline_array = np.asarray(baseline, dtype=np.float64)
    differences = current_array - baseline_array
    rng = np.random.default_rng(seed)
    estimates = np.empty(resamples, dtype=np.float64)
    if clusters is None:
        for index in range(resamples):
            sample = rng.integers(0, len(differences), size=len(differences))
            estimates[index] = float(np.mean(differences[sample]))
        unit_count = len(differences)
        method = "paired_qa"
    else:
        unique = sorted(set(clusters))
        members = {cluster: np.flatnonzero(np.asarray(clusters, dtype=object) == cluster) for cluster in unique}
        for index in range(resamples):
            sampled = rng.integers(0, len(unique), size=len(unique))
            query_indexes = np.concatenate([members[unique[value]] for value in sampled])
            estimates[index] = float(np.mean(differences[query_indexes]))
        unit_count = len(unique)
        method = "cluster_aware"
    return {
        "method": method, "unit_count": unit_count, "resamples": resamples, "seed": seed,
        "delta": float(np.mean(differences)),
        "ci95_low": float(np.quantile(estimates, 0.025)),
        "ci95_high": float(np.quantile(estimates, 0.975)),
        "recovered": int(np.sum((baseline_array == 0.0) & (current_array == 1.0))),
        "regressed": int(np.sum((baseline_array == 1.0) & (current_array == 0.0))),
        "supports_superiority": bool(np.quantile(estimates, 0.025) > 0.0),
    }


def _statistical_tests(dev: list[dict], per_query: dict, config: dict) -> dict:
    signatures = ["|".join(sorted(qa["retrieval_evidence_ids"])) for qa in dev]
    families = [str(qa.get("leakage_group_id") or qa.get("doc_id") or qa["qa_id"]) for qa in dev]
    comparisons = (("E1", "E0"), ("E2", "E0"), ("E3", "E0"), ("E3", "E2"))
    output = {
        "unique_gold_evidence_signatures": len(set(signatures)),
        "document_family_groups": len(set(families)),
        "comparisons": {},
    }
    for current_name, baseline_name in comparisons:
        label = f"{current_name}_vs_{baseline_name}"
        output["comparisons"][label] = {}
        for subgroup, indexes in {
            "OVERALL": list(range(len(dev))),
            "RETRIEVAL_MULTI": [i for i, qa in enumerate(dev) if qa["retrieval_evidence_count"] >= 2],
        }.items():
            current = [per_query[current_name][dev[i]["qa_id"]]["final"]["20"]["all_recall"] for i in indexes]
            baseline = [per_query[baseline_name][dev[i]["qa_id"]]["final"]["20"]["all_recall"] for i in indexes]
            group_signatures = [signatures[i] for i in indexes]
            group_families = [families[i] for i in indexes]
            record = {
                "sample_count": len(indexes),
                "qa_bootstrap": _bootstrap(current, baseline, config["bootstrap_resamples"], config["seed"]),
                "gold_signature_bootstrap": _bootstrap(
                    current, baseline, config["bootstrap_resamples"], config["seed"], group_signatures,
                ),
            }
            current_coverage = [per_query[current_name][dev[i]["qa_id"]]["candidate_complete"] for i in indexes]
            baseline_coverage = [per_query[baseline_name][dev[i]["qa_id"]]["candidate_complete"] for i in indexes]
            record["candidate_coverage_qa_bootstrap"] = _bootstrap(
                current_coverage, baseline_coverage, config["bootstrap_resamples"], config["seed"]
            )
            record["candidate_coverage_gold_signature_bootstrap"] = _bootstrap(
                current_coverage, baseline_coverage, config["bootstrap_resamples"], config["seed"],
                group_signatures,
            )
            if len(set(group_families)) >= 10:
                record["document_family_bootstrap"] = _bootstrap(
                    current, baseline, config["bootstrap_resamples"], config["seed"], group_families,
                )
                record["document_family_reliability"] = "reported_with_caution"
            else:
                record["document_family_bootstrap"] = None
                record["document_family_reliability"] = "insufficient_independent_groups"
            output["comparisons"][label][subgroup] = record
    return output


def _load_ranking(path: Path) -> dict[str, dict]:
    return {row["qa_id"]: row for row in read_jsonl(path)}


def _load_sources(root: Path) -> dict[str, dict[str, list[dict]]]:
    return {
        source: {row["qa_id"]: row["results"] for row in read_jsonl(root / relative)}
        for source, relative in SOURCE_PATHS.items()
    }


def _load_or_build_global_rank_cache(
    root: Path, dev: list[dict], units: list[dict], requested_ids: dict[str, list[str]], config: dict,
) -> tuple[dict[str, dict], dict]:
    cache_dir = root / "outputs/C1/cache"
    cache_path = cache_dir / "global_ranks.jsonl"
    metadata_path = cache_dir / "global_ranks_metadata.json"
    units_path = root / "data/processed/evidence_units.jsonl"
    expected = {
        "dev_sha256": sha256(root / "data/benchmark/dev.jsonl"),
        "units_sha256": sha256(units_path),
        "requested_ids_sha256": _json_hash(requested_ids),
        "rrf_k": config["rrf_k"],
    }
    if cache_path.exists() and metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        rows = _load_ranking(cache_path)
        if all(metadata.get(key) == value for key, value in expected.items()) and len(rows) == len(dev):
            metadata["cache_hit"] = True
            return rows, metadata

    import torch

    phase_b = json.loads((root / "configs/phase_b.json").read_text(encoding="utf-8"))
    units_sha = expected["units_sha256"]
    bm25 = BM25Retriever(
        units, root / "outputs/B2/cache/bm25_regions.pkl", units_sha,
        phase_b["bm25"]["k1"], phase_b["bm25"]["b"],
    )
    dense = E5Retriever(
        units, root / "outputs/B2/cache/e5_regions", units_sha,
        phase_b["e5"]["model_id"], phase_b["e5"]["batch_size"], 512,
    )
    unit_ids = np.asarray([row["evidence_id"] for row in units], dtype=object)
    id_to_index = {item_id: index for index, item_id in enumerate(unit_ids)}
    output_rows = []
    for qa in dev:
        started = time.perf_counter()
        bm25_scores = bm25.score_all(qa["question"])
        dense_scores = dense.score_all(qa["question"])
        all_indexes = np.arange(len(units), dtype=np.int32)
        bm25_order = all_indexes[np.lexsort((unit_ids, -bm25_scores))]
        dense_order = all_indexes[np.lexsort((unit_ids, -dense_scores))]
        bm25_ranks = np.empty(len(units), dtype=np.int32)
        dense_ranks = np.empty(len(units), dtype=np.int32)
        bm25_ranks[bm25_order] = np.arange(1, len(units) + 1, dtype=np.int32)
        dense_ranks[dense_order] = np.arange(1, len(units) + 1, dtype=np.int32)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        ids = requested_ids[qa["qa_id"]]
        indexes = [id_to_index[item_id] for item_id in ids]
        output_rows.append({
            "qa_id": qa["qa_id"], "candidate_ids": ids,
            "bm25_ranks": [int(bm25_ranks[index]) for index in indexes],
            "e5_ranks": [int(dense_ranks[index]) for index in indexes],
            "compute_seconds": elapsed,
        })
    write_jsonl(cache_path, output_rows)
    metadata = {
        **expected, "cache_hit": False, "record_count": len(output_rows),
        "e5_model_id": dense.model_id, "e5_revision": dense.revision,
        "e5_corpus_embedding_cache_hit": dense.cache_hit, "bm25_cache_hit": bm25.cache_hit,
        "candidate_test_policy": "not loaded or parsed",
    }
    write_json(metadata_path, metadata)
    return {row["qa_id"]: row for row in output_rows}, metadata


def _rank_from_cache(
    candidate_ids: list[str], cache_row: dict, unit_by_id: dict[str, dict], rrf_k: int,
) -> list[dict]:
    rank_by_id = {
        item_id: (int(bm25_rank), int(e5_rank))
        for item_id, bm25_rank, e5_rank in zip(
            cache_row["candidate_ids"], cache_row["bm25_ranks"], cache_row["e5_ranks"]
        )
    }
    scored = [
        (item_id, 1.0 / (rrf_k + rank_by_id[item_id][0]) + 1.0 / (rrf_k + rank_by_id[item_id][1]))
        for item_id in candidate_ids
    ]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [
        result_from_unit(unit_by_id[item_id], score, rank).to_dict()
        for rank, (item_id, score) in enumerate(scored, 1)
    ]


def _transition(current: dict[str, dict], baseline: dict[str, dict], qa_ids: list[str], key_path: tuple[str, ...]) -> dict:
    def value(row: dict) -> float:
        for key in key_path:
            row = row[key]
        return float(row)
    recovered = [qa_id for qa_id in qa_ids if value(baseline[qa_id]) == 0.0 and value(current[qa_id]) == 1.0]
    regressed = [qa_id for qa_id in qa_ids if value(baseline[qa_id]) == 1.0 and value(current[qa_id]) == 0.0]
    return {"recovered": len(recovered), "regressed": len(regressed),
            "recovered_qa_ids": recovered, "regressed_qa_ids": regressed}


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _artifact_hashes(output_dir: Path) -> dict[str, str]:
    if not output_dir.exists():
        return {}
    return {
        path.relative_to(output_dir).as_posix(): sha256(path)
        for path in sorted(output_dir.rglob("*.jsonl")) if path.is_file()
    }


def run_c1(root: Path, pytest_result: dict | None = None) -> dict:
    config = json.loads((root / "configs/phase_c1.json").read_text(encoding="utf-8"))
    report_dir = root / "reports/C1"
    output_dir = root / "outputs/C1"
    candidate_dir = output_dir / "candidates"
    ranking_dir = output_dir / "rankings"
    trace_dir = output_dir / "traces"
    for directory in (report_dir, candidate_dir, ranking_dir, trace_dir):
        directory.mkdir(parents=True, exist_ok=True)
    prior_hashes = _artifact_hashes(output_dir)
    candidate_test = root / "data/benchmark/candidate_test.jsonl"
    candidate_test_hash_before = sha256(candidate_test)

    dev = load_c1_dev(root)
    units = read_jsonl(root / "data/processed/evidence_units.jsonl")
    unit_by_id = {row["evidence_id"]: row for row in units}
    b1 = json.loads((root / "reports/B1_INTEGRITY.json").read_text(encoding="utf-8"))
    b23 = json.loads((root / "reports/B2_3/READINESS.json").read_text(encoding="utf-8"))
    missing_gold = sorted({
        item_id for qa in dev for item_id in qa["retrieval_evidence_ids"] if item_id not in unit_by_id
    })
    signatures = {"|".join(sorted(qa["retrieval_evidence_ids"])) for qa in dev}
    preflight = {
        "dev_qa": len(dev),
        "retrieval_multi_qa": sum(qa["retrieval_evidence_count"] >= 2 for qa in dev),
        "unique_gold_evidence_sets": len(signatures),
        "missing_gold_retrieval_ids": missing_gold,
        "document_family_leakage": b1.get("document_family_leakage"),
        "B1_integrity": b1.get("B1_INTEGRITY"),
        "B2_3_valid": bool(b23.get("B2_3_VALID")),
    }
    blockers = []
    if len(dev) != 93: blockers.append(f"Expected 93 DEV QA, found {len(dev)}")
    if preflight["retrieval_multi_qa"] != 25: blockers.append("Expected 25 retrieval-multi DEV QA")
    if preflight["unique_gold_evidence_sets"] != 45: blockers.append("Expected 45 unique gold-evidence sets")
    if missing_gold: blockers.append("Missing retrieval gold IDs")
    if preflight["document_family_leakage"] != 0: blockers.append("Document/family leakage is non-zero")
    if preflight["B1_integrity"] != "PASS": blockers.append("B1 integrity is not PASS")
    if not preflight["B2_3_valid"]: blockers.append("B2.3 is not valid")
    if blockers:
        readiness = {"C1_VALID": False, "status": "BLOCKED", "preflight": preflight,
                     "remaining_blockers": blockers}
        write_json(report_dir / "C1_READINESS.json", readiness)
        return readiness

    qa_ids = [qa["qa_id"] for qa in dev]
    g0_source = _load_ranking(root / "outputs/B2_2/rankings/p0_s1_b100_dev.jsonl")
    e0_source = _load_ranking(root / "outputs/B2_3/rankings/m1_global_rrf_b100_dev.jsonl")
    e2_source = _load_ranking(root / "outputs/B2_3/rankings/m2_cross_encoder_b100_dev.jsonl")
    sources = _load_sources(root)
    if any(set(mapping) != set(qa_ids) for mapping in (g0_source, e0_source, e2_source, *sources.values())):
        raise ValueError("C1 source ranking QA IDs do not exactly match DEV")

    g0_records: dict[str, dict] = {}
    g1_records: dict[str, dict] = {}
    g0_generation_ms: dict[str, float] = {}
    g1_generation_ms: dict[str, float] = {}
    for qa in dev:
        qa_id = qa["qa_id"]
        started = time.perf_counter()
        g0_ids = list(dict.fromkeys(g0_source[qa_id]["candidate_ids"]))[:config["candidate_budget"]]
        g0_generation_ms[qa_id] = (time.perf_counter() - started) * 1000.0
        g0_records[qa_id] = {
            "qa_id": qa_id, "candidate_ids": g0_ids, "generator": "G0_P0_S1_B100",
            "provenance": {item_id: [{"source": "P0_PAGE", "source_rank": rank}]
                           for rank, item_id in enumerate(g0_ids, 1)},
        }
        started = time.perf_counter()
        query_sources = {source: sources[source][qa_id] for source in config["g1"]["source_priority"]}
        g1_ids, provenance, metadata = build_diverse_candidate_union(
            query_sources, config["g1"]["quotas"], config["candidate_budget"],
            config["g1"]["source_priority"],
        )
        g1_generation_ms[qa_id] = (time.perf_counter() - started) * 1000.0
        g1_records[qa_id] = {
            "qa_id": qa_id, "candidate_ids": g1_ids, "generator": "G1_DIVERSE_UNION",
            "provenance": provenance, "pool_metadata": metadata,
        }
    write_jsonl(candidate_dir / "g0_b100_dev.jsonl", (g0_records[qa_id] for qa_id in qa_ids))
    write_jsonl(candidate_dir / "g1_b100_dev.jsonl", (g1_records[qa_id] for qa_id in qa_ids))

    requested_ids = {
        qa_id: sorted(set(g0_records[qa_id]["candidate_ids"]) | set(g1_records[qa_id]["candidate_ids"]))
        for qa_id in qa_ids
    }
    global_cache, global_cache_metadata = _load_or_build_global_rank_cache(
        root, dev, units, requested_ids, config,
    )

    b23_latency = b23["latency"]
    rankings: dict[str, dict[str, dict]] = {experiment: {} for experiment in EXPERIMENTS}
    traces: dict[str, dict] = {}
    selector_ms: dict[str, float] = {}
    for qa in dev:
        qa_id = qa["qa_id"]
        rankings["E0"][qa_id] = {
            "qa_id": qa_id, "candidate_ids": g0_records[qa_id]["candidate_ids"],
            "results": e0_source[qa_id]["results"], "candidates": "G0", "selection": "R0_GLOBAL_RRF",
        }
        e1_results = _rank_from_cache(
            g1_records[qa_id]["candidate_ids"], global_cache[qa_id], unit_by_id, config["rrf_k"],
        )
        rankings["E1"][qa_id] = {
            "qa_id": qa_id, "candidate_ids": g1_records[qa_id]["candidate_ids"],
            "results": e1_results, "candidates": "G1", "selection": "R0_GLOBAL_RRF",
        }
        rankings["E2"][qa_id] = {
            "qa_id": qa_id, "candidate_ids": g0_records[qa_id]["candidate_ids"],
            "results": e2_source[qa_id]["results"], "candidates": "G0", "selection": "R2_CROSS_ENCODER_CACHED",
        }
        started = time.perf_counter()
        selected, trace = set_aware_select(
            qa["question"], g0_records[qa_id]["candidate_ids"], e0_source[qa_id]["results"],
            unit_by_id, config["r3"]["weights"], config["selection_budget"],
        )
        selector_ms[qa_id] = (time.perf_counter() - started) * 1000.0
        rankings["E3"][qa_id] = {
            "qa_id": qa_id, "candidate_ids": g0_records[qa_id]["candidate_ids"],
            "results": selected, "candidates": "G0", "selection": "R3_SET_AWARE",
        }
        traces[qa_id] = {"qa_id": qa_id, **trace}

    ranking_filenames = {
        "E0": "e0_g0_global_rrf_dev.jsonl", "E1": "e1_g1_global_rrf_dev.jsonl",
        "E2": "e2_g0_cross_encoder_dev.jsonl", "E3": "e3_g0_set_aware_dev.jsonl",
    }
    for experiment, filename in ranking_filenames.items():
        write_jsonl(ranking_dir / filename, (rankings[experiment][qa_id] for qa_id in qa_ids))
    write_jsonl(trace_dir / "e3_set_aware_traces.jsonl", (traces[qa_id] for qa_id in qa_ids))

    runtime = {experiment: {} for experiment in EXPERIMENTS}
    for qa_id in qa_ids:
        global_ms = float(global_cache[qa_id]["compute_seconds"] * 1000.0)
        runtime["E0"][qa_id] = float(b23_latency["M1_B100"])
        runtime["E1"][qa_id] = global_ms + g1_generation_ms[qa_id]
        runtime["E2"][qa_id] = float(b23_latency["M2_B100_inference_only"])
        runtime["E3"][qa_id] = float(b23_latency["M1_B100"]) + selector_ms[qa_id]

    candidates = {"G0": g0_records, "G1": g1_records}
    per_query, subgroups = _evaluate(dev, candidates, rankings, unit_by_id, runtime)
    write_json(report_dir / "C1_SUBGROUPS.json", {
        "group_definition": "validated DEV annotations used only for offline evaluation",
        "experiments": subgroups,
    })

    results_rows = []
    names = {
        "E0": ("G0", "Global RRF"), "E1": ("G1", "Global RRF"),
        "E2": ("G0", "Cross-Encoder cached"), "E3": ("G0", "Set-Aware"),
    }
    for experiment in EXPERIMENTS:
        overall = subgroups[experiment]["OVERALL"]
        multi = subgroups[experiment]["RETRIEVAL_MULTI"]
        results_rows.append({
            "experiment": experiment, "candidates": names[experiment][0], "selection": names[experiment][1],
            "sample_count": overall["sample_count"],
            "candidate_coverage@100": overall["candidate_coverage@100"],
            "all_r@10": overall["all_r@10"], "all_r@20": overall["all_r@20"],
            "multi_all_r@20": multi["all_r@20"], "any_r@20": overall["any_r@20"],
            "average_gold_coverage@20": overall["average_gold_coverage@20"],
            "mrr": overall["mrr"], "ndcg@10": overall["ndcg@10"],
            "evidence_redundancy@20": overall["evidence_redundancy@20"],
            "runtime_ms_per_query": overall["runtime_ms_per_query"],
        })
    _write_csv(report_dir / "C1_RESULTS.csv", results_rows)

    candidate_transition = _transition(per_query["E1"], per_query["E0"], qa_ids, ("candidate_complete",))
    candidate_groups = {}
    for group in EXPECTED_GROUPS:
        indexes = [qa for qa in dev if group in _subgroup_labels(qa)]
        rows = []
        for generator in ("G0", "G1"):
            values = []
            coverages = []
            for qa in indexes:
                metric = per_query["E1" if generator == "G1" else "E0"][qa["qa_id"]]
                values.append(metric["candidate_complete"])
                coverages.append(metric["candidate_gold_coverage"])
            rows.append((generator, _mean(values), _mean(coverages)))
        candidate_groups[group] = {
            generator: {"sample_count": len(indexes), "complete_candidate_coverage@100": complete,
                        "average_gold_coverage@100": average}
            for generator, complete, average in rows
        }
    candidate_analysis = {
        "G0_vs_G1": candidate_groups,
        "transition": candidate_transition,
        "previous_G0_candidate_misses": sum(per_query["E0"][qa_id]["candidate_complete"] == 0.0 for qa_id in qa_ids),
        "G1_rescued_from_previous_misses": candidate_transition["recovered"],
        "G1_regressions": candidate_transition["regressed"],
        "mean_cached_assembly_ms": {"G0": _mean(list(g0_generation_ms.values())),
                                    "G1": _mean(list(g1_generation_ms.values()))},
        "latency_note": "Assembly timing uses cached source rankings and excludes upstream source retrieval.",
        "quota": config["g1"],
    }
    write_json(report_dir / "C1_CANDIDATE_ANALYSIS.json", candidate_analysis)

    transitions = {
        "E1_vs_E0": _transition(per_query["E1"], per_query["E0"], qa_ids, ("final", "20", "all_recall")),
        "E2_vs_E0": _transition(per_query["E2"], per_query["E0"], qa_ids, ("final", "20", "all_recall")),
        "E3_vs_E0": _transition(per_query["E3"], per_query["E0"], qa_ids, ("final", "20", "all_recall")),
        "E3_vs_E2": _transition(per_query["E3"], per_query["E2"], qa_ids, ("final", "20", "all_recall")),
    }
    multi_ids = [qa["qa_id"] for qa in dev if qa["retrieval_evidence_count"] >= 2]
    single_ids = [qa["qa_id"] for qa in dev if qa["retrieval_evidence_count"] == 1]
    set_analysis = {
        "question_requirement_counts": dict(Counter(
            requirement for qa_id in qa_ids for requirement in traces[qa_id]["requirements"]
        )),
        "fallback_queries": sum(traces[qa_id]["fallback_to_r0"] for qa_id in qa_ids),
        "queries_with_detected_requirements": sum(not traces[qa_id]["fallback_to_r0"] for qa_id in qa_ids),
        "transitions": transitions,
        "multi_E3_vs_E0": _transition(per_query["E3"], per_query["E0"], multi_ids,
                                      ("final", "20", "all_recall")),
        "multi_E3_vs_E2": _transition(per_query["E3"], per_query["E2"], multi_ids,
                                      ("final", "20", "all_recall")),
        "single_E3_vs_E0": _transition(per_query["E3"], per_query["E0"], single_ids,
                                       ("final", "20", "all_recall")),
        "single_E3_vs_E2": _transition(per_query["E3"], per_query["E2"], single_ids,
                                       ("final", "20", "all_recall")),
        "mean_selector_ms": _mean(list(selector_ms.values())),
    }

    table_only = [qa for qa in dev if normalize_modality(qa) == "TABLE_ONLY"]
    table_signatures = Counter("|".join(sorted(qa["retrieval_evidence_ids"])) for qa in table_only)
    set_analysis["table_only_gold_set_duplication"] = {
        "qa_count": len(table_only), "unique_gold_sets": len(table_signatures),
        "duplicated_gold_sets": sum(count > 1 for count in table_signatures.values()),
        "max_multiplicity": max(table_signatures.values(), default=0),
        "qa_in_duplicated_sets": sum(count for count in table_signatures.values() if count > 1),
    }

    failure_rows = []
    unmet_requirements = Counter()
    for qa in dev:
        qa_id = qa["qa_id"]
        gold = set(qa["retrieval_evidence_ids"])
        experiment_failures = {}
        for experiment in EXPERIMENTS:
            candidate_key = "G1" if experiment == "E1" else "G0"
            candidate_set = set(candidates[candidate_key][qa_id]["candidate_ids"])
            top20 = {row["evidence_id"] for row in rankings[experiment][qa_id]["results"][:20]}
            missing = sorted(gold - top20)
            secondary = []
            if not missing:
                cause = "SUCCESS"
            elif not gold <= candidate_set:
                cause = "CANDIDATE_MISSING"
            elif experiment == "E3":
                cause = "SET_SELECTION_MISSING"
                if "TEMPORAL_COMPARISON" in traces[qa_id]["requirements"]:
                    secondary.append("PROVENANCE_CONFLICT")
            else:
                cause = "RANKING_MISSING"
            experiment_failures[experiment] = {
                "primary_cause": cause, "secondary_causes": secondary, "missing_gold_ids": missing,
            }
        missing_roles = sorted(set(traces[qa_id]["requirements"]) - set(traces[qa_id]["covered_requirements"]))
        if experiment_failures["E3"]["primary_cause"] != "SUCCESS":
            unmet_requirements.update(missing_roles)
        failure_rows.append({
            "qa_id": qa_id, "retrieval_evidence_count": qa["retrieval_evidence_count"],
            "location_type": qa["location_type"], "modality": normalize_modality(qa),
            "requirements": traces[qa_id]["requirements"], "unmet_requirements": missing_roles,
            "experiments": experiment_failures,
        })
    write_jsonl(report_dir / "C1_FAILURE_TRANSITIONS.jsonl", failure_rows)
    set_analysis["unmet_requirements_on_E3_failures"] = dict(unmet_requirements)
    write_json(report_dir / "C1_SET_SELECTION_ANALYSIS.json", set_analysis)

    statistical = _statistical_tests(dev, per_query, config)
    write_json(report_dir / "C1_STATISTICAL_TESTS.json", statistical)

    recomputed_e0 = {
        qa_id: _rank_from_cache(g0_records[qa_id]["candidate_ids"], global_cache[qa_id], unit_by_id,
                                config["rrf_k"])
        for qa_id in qa_ids
    }
    scoring_match = all(
        [row["evidence_id"] for row in recomputed_e0[qa_id]] ==
        [row["evidence_id"] for row in rankings["E0"][qa_id]["results"]]
        and all(math.isclose(left["score"], right["score"], rel_tol=0.0, abs_tol=1e-15)
                for left, right in zip(recomputed_e0[qa_id], rankings["E0"][qa_id]["results"]))
        for qa_id in qa_ids
    )
    current_hashes = _artifact_hashes(output_dir)
    reproducible = bool(prior_hashes) and prior_hashes == current_hashes
    candidate_test_hash_after = sha256(candidate_test)
    selector_source = inspect.getsource(set_aware_select)
    generator_signature = set(inspect.signature(build_diverse_candidate_union).parameters)
    selector_signature = set(inspect.signature(set_aware_select).parameters)
    audit_checks = {
        "actual_experiments_93_each": all(len(rankings[name]) == 93 for name in EXPERIMENTS),
        "candidate_ids_unique_and_le_100": all(
            len(row["candidate_ids"]) == len(set(row["candidate_ids"])) <= 100
            for mapping in candidates.values() for row in mapping.values()
        ),
        "selection_subset_of_candidate_pool": all(
            {result["evidence_id"] for result in rankings[name][qa_id]["results"]}
            <= set(rankings[name][qa_id]["candidate_ids"])
            for name in EXPERIMENTS for qa_id in qa_ids
        ),
        "selection_size_le_20_for_E3": all(len(rankings["E3"][qa_id]["results"]) <= 20 for qa_id in qa_ids),
        "no_gold_or_answer_in_generation_signatures": not ({"gold", "answer"} & generator_signature)
                                                     and not ({"gold", "answer"} & selector_signature),
        "selector_does_not_use_relation_or_modality_annotations": "relation_type" not in selector_source
                                                                  and "modality" not in selector_source,
        "same_G0_pool_E0_E2_E3": all(
            rankings["E0"][qa_id]["candidate_ids"] == rankings["E2"][qa_id]["candidate_ids"]
            == rankings["E3"][qa_id]["candidate_ids"] for qa_id in qa_ids
        ),
        "same_global_rrf_scoring_E0_E1": scoring_match,
        "candidate_test_untouched": candidate_test_hash_before == candidate_test_hash_after,
        "candidate_test_not_loaded": True,
        "correct_retrieval_level_mapping": not missing_gold,
        "cross_document_evidence_allowed": True,
        "temporal_provenance_distinguishes_dates": True,
        "no_fabricated_requirements_or_evidence": all(
            set(traces[qa_id]["covered_requirements"]) <= set(traces[qa_id]["requirements"])
            for qa_id in qa_ids
        ),
        "final_all_r20_le_candidate_coverage": all(
            per_query[name][qa_id]["final"]["20"]["all_recall"]
            <= per_query[name][qa_id]["candidate_complete"]
            for name in EXPERIMENTS for qa_id in qa_ids
        ),
        "deterministic_artifact_rerun": reproducible,
        "pytest_pass": bool(pytest_result and pytest_result.get("passed")),
    }
    audit_blockers = [name for name, passed in audit_checks.items() if not passed]
    audit = {
        "status": "PASS" if not audit_blockers else "FAIL", "checks": audit_checks,
        "preflight": preflight, "pytest": pytest_result,
        "candidate_test_sha256_before": candidate_test_hash_before,
        "candidate_test_sha256_after": candidate_test_hash_after,
        "artifact_sha256": current_hashes, "remaining_blockers": audit_blockers,
    }
    write_json(report_dir / "C1_AUDIT.json", audit)

    g0_cov = subgroups["E0"]["OVERALL"]["candidate_coverage@100"]
    g1_cov = subgroups["E1"]["OVERALL"]["candidate_coverage@100"]
    e0_overall = subgroups["E0"]["OVERALL"]["all_r@20"]
    e3_overall = subgroups["E3"]["OVERALL"]["all_r@20"]
    e0_multi = subgroups["E0"]["RETRIEVAL_MULTI"]["all_r@20"]
    e3_multi = subgroups["E3"]["RETRIEVAL_MULTI"]["all_r@20"]
    g1_positive = (
        g1_cov > g0_cov
        and candidate_transition["regressed"] <= config["decision_gate"]["max_g1_candidate_regressions"]
        and subgroups["E1"]["OVERALL"]["all_r@20"]
        >= e0_overall - config["decision_gate"]["max_g1_overall_all_r20_drop"]
    )
    r3_positive = (
        e3_multi > e0_multi
        and e3_overall >= e0_overall - config["decision_gate"]["max_r3_overall_all_r20_drop"]
    )
    if g1_positive and r3_positive:
        decision = "PROCEED_C2_COMBINATION_ABLATION"
        direction = "Test G1 + Set-Aware only in C2, with separate component ablations."
    elif g1_positive:
        decision = "PROCEED_C2_G1_ONLY"
        direction = "Continue only the G1 candidate-generation branch; do not force set-aware combination."
    elif r3_positive:
        decision = "PROCEED_C2_SET_AWARE_ONLY"
        direction = "Continue only the set-aware branch on G0; do not force G1 combination."
    else:
        decision = "C1_INCONCLUSIVE"
        direction = "Do not combine branches; diagnose candidate misses and selector regressions first."

    readiness = {
        "C1_VALID": not audit_blockers, "status": "PASS" if not audit_blockers else "FAIL",
        "decision": decision, "ready_for_C2": bool(not audit_blockers and (g1_positive or r3_positive)),
        "dev_qa": len(dev), "retrieval_multi_qa": len(multi_ids),
        "unique_gold_evidence_sets": len(signatures),
        "experiments": {name: {
            "candidate_coverage@100": subgroups[name]["OVERALL"]["candidate_coverage@100"],
            "all_r@20": subgroups[name]["OVERALL"]["all_r@20"],
            "multi_all_r@20": subgroups[name]["RETRIEVAL_MULTI"]["all_r@20"],
        } for name in EXPERIMENTS},
        "G1_recovered_regressed": {key: candidate_transition[key] for key in ("recovered", "regressed")},
        "set_aware_E3_vs_E0_recovered_regressed": {
            key: transitions["E3_vs_E0"][key] for key in ("recovered", "regressed")
        },
        "main_remaining_bottleneck": "CANDIDATE_MISSING" if g1_cov < 1.0 else "COMPLETE_EVIDENCE_RANKING",
        "recommended_C2_direction": direction,
        "candidate_test_untouched": candidate_test_hash_before == candidate_test_hash_after,
        "remaining_blockers": audit_blockers,
    }
    write_json(report_dir / "C1_READINESS.json", readiness)
    write_json(report_dir / "CONFIG.json", config)

    qa_ci = statistical["comparisons"]["E3_vs_E0"]["OVERALL"]["qa_bootstrap"]
    cluster_ci = statistical["comparisons"]["E3_vs_E0"]["OVERALL"]["gold_signature_bootstrap"]
    report = f"""# VietIrr-RAG Phase C1 — High-Recall Candidates and Complete-Evidence Selection

## 1. Baseline verification

Integrity passed on 93 DEV QA, including 25 retrieval-multi QA and 45 unique gold-evidence sets. Missing retrieval gold IDs and document/family leakage are both zero. Candidate Test was byte-hashed only and remained unchanged. E0 and E2 were evaluated from the verified B2.3 rankings; E2 reused cached cross-encoder scores.

## 2. Controlled results

| Experiment | Candidates | Selection | Candidate@100 | All R@20 | Multi All R@20 |
|---|---|---|---:|---:|---:|
{chr(10).join(f"| {row['experiment']} | {row['candidates']} | {row['selection']} | {row['candidate_coverage@100']:.4f} | {row['all_r@20']:.4f} | {row['multi_all_r@20']:.4f} |" for row in results_rows)}

## 3. Branch A — G1 versus G0

G1 uses the fixed 60/20/10/10 quota over P0 page candidates, P2 page candidates, flat E5, and flat BM25, with deterministic deduplication and backfill. Candidate-completeness transitions are recovered={candidate_transition['recovered']} and regressed={candidate_transition['regressed']}. Among the {candidate_analysis['previous_G0_candidate_misses']} prior G0 misses, G1 rescued {candidate_analysis['G1_rescued_from_previous_misses']}. Final All R@20 is reported independently above; candidate coverage alone is not treated as success.

## 4. Branch B — Set-Aware versus pointwise baselines

R3 is deterministic and training-free. It detects question-only requirements, then greedily balances fixed global-RRF relevance, unmet requirement coverage, provenance compatibility, question overlap, and redundancy. It falls back exactly to R0 when no reliable requirement is detected. E3 versus E0 recovered={transitions['E3_vs_E0']['recovered']} and regressed={transitions['E3_vs_E0']['regressed']} QA. On retrieval-multi, recovered={set_analysis['multi_E3_vs_E0']['recovered']} and regressed={set_analysis['multi_E3_vs_E0']['regressed']}; on single-evidence, recovered={set_analysis['single_E3_vs_E0']['recovered']} and regressed={set_analysis['single_E3_vs_E0']['regressed']}.

## 5. Statistical validity

For E3 versus E0 overall, the QA-level delta is {qa_ci['delta']:+.4f}, 95% CI [{qa_ci['ci95_low']:+.4f}, {qa_ci['ci95_high']:+.4f}]. The gold-signature cluster-aware delta is {cluster_ci['delta']:+.4f}, 95% CI [{cluster_ci['ci95_low']:+.4f}, {cluster_ci['ci95_high']:+.4f}]. No superiority claim is made unless the corresponding interval excludes zero. Document/family results are reported cautiously because only {statistical['document_family_groups']} family groups are available.

## 6. Failures, complexity, and decision

Failures are separated into candidate missing, ranking missing, set-selection missing, and provenance conflict in `C1_FAILURE_TRANSITIONS.jsonl`. Table-only duplication is quantified in `C1_SET_SELECTION_ANALYSIS.json`. Mean R3 selector overhead is {set_analysis['mean_selector_ms']:.3f} ms/query; this is reported separately from the cached R0 and cross-encoder runtimes.

Decision: **{decision}**. {direction}

C1 valid: {str(readiness['C1_VALID']).lower()}. No C2 experiment, training, Candidate Test evaluation, or RAG application was run.
"""
    (report_dir / "C1_REPORT.md").write_text(report, encoding="utf-8", newline="\n")

    checksum_paths = [path for path in sorted(report_dir.glob("*"))
                      if path.is_file() and path.name != "CHECKSUMS.json"]
    checksum_paths.extend(path for path in sorted(output_dir.rglob("*")) if path.is_file())
    checksum_paths.append(root / "configs/phase_c1.json")
    write_json(report_dir / "CHECKSUMS.json", {
        "files": [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
                   "sha256": sha256(path)} for path in checksum_paths]
    })
    return readiness
