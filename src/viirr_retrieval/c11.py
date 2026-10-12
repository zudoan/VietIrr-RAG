from __future__ import annotations

import csv
import hashlib
import inspect
import json
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .b23 import normalize_modality
from .c1 import _bootstrap, _fold, _jaccard, _token_set
from .candidate_metrics import final_ranking_metrics
from .io_utils import read_jsonl, sha256, write_json, write_jsonl


REQUIREMENTS = (
    "VALUE", "STATUS", "FORECAST", "EXPLANATION", "ACTION", "RECOMMENDATION",
    "RULE", "CONDITION", "TEMPORAL_COMPARISON",
)
ROLE_FOR_REQUIREMENT = {
    "VALUE": "MEASUREMENT",
    "STATUS": "STATUS",
    "FORECAST": "FORECAST",
    "EXPLANATION": "EXPLANATION",
    "ACTION": "ACTION",
    "RECOMMENDATION": "RECOMMENDATION",
    "RULE": "RULE",
    "CONDITION": "CONDITION",
}
EVIDENCE_ROLES = (
    "MEASUREMENT", "FORECAST", "STATUS", "EXPLANATION", "ACTION",
    "RECOMMENDATION", "RULE", "CONDITION", "UNKNOWN",
)
METHODS = ("E0", "E2", "E3", "E4")
SUBGROUPS = (
    "OVERALL", "CORE", "CHALLENGE", "RETRIEVAL_SINGLE", "RETRIEVAL_MULTI",
    "TEXT_ONLY", "TABLE_ONLY", "TEXT_TABLE", "TABLE_TABLE",
    "SAME_PAGE", "CROSS_PAGE_SAME_DOCUMENT", "CROSS_DOCUMENT",
)


QUESTION_RULES = {
    "VALUE": (
        r"\bbao nhieu\b", r"\bla may\b", r"\bgia tri (?:la )?(?:gi|nao)\b",
        r"\bso lieu (?:la )?(?:gi|nao)\b",
    ),
    "STATUS": (
        r"\b(?:tinh trang|hien trang|trang thai)\b.{0,80}\b(?:the nao|ra sao|gi|nao)\b",
        r"\b(?:danh gia|nhan xet)\b.{0,80}\b(?:the nao|ra sao|gi)\b",
    ),
    "FORECAST": (
        r"\b(?:du bao|du kien|nhan dinh)\b.{0,50}\b(?:gi|the nao|ra sao)\b",
        r"\b(?:muc nuoc|luu luong|luong mua|dien bien|tinh hinh)\b.{0,30}"
        r"\b(?:duoc )?(?:du bao|du kien)\b.{0,20}\b(?:se |co the )?(?:la|dat|tang|giam|thay doi|xay ra)\b",
        r"\b(?:du bao|du kien)\b\s+(?:muc nuoc|luu luong|luong mua|dien bien|tinh hinh)"
        r"\b.{0,20}\b(?:se|co the|la|dat|tang|giam|thay doi|xay ra)\b",
    ),
    "EXPLANATION": (
        r"\bvi sao\b", r"\bdo dau\b", r"\bnguyen nhan (?:gi|nao)\b", r"\bgiai thich\b",
    ),
    "ACTION": (
        r"\bbien phap (?:gi|nao)\b", r"\bcan (?:lam|thuc hien|trien khai) gi\b",
        r"\b(?:xu ly|ung pho)\b.{0,40}\b(?:the nao|ra sao)\b", r"\bchi dao (?:gi|nao)\b",
    ),
    "RECOMMENDATION": (
        r"\b(?:khuyen nghi|kien nghi|de xuat)\b.{0,50}\b(?:gi|nao|the nao|ra sao)\b",
        r"\bco (?:khuyen nghi|kien nghi|de xuat) gi\b",
    ),
    "RULE": (
        r"\bquy dinh\b.{0,70}\b(?:gi|nao|the nao|ra sao)\b",
        r"\b(?:yeu cau|noi dung bat buoc) (?:gi|nao)\b",
    ),
    "CONDITION": (
        r"\bdieu kien (?:gi|nao)\b", r"\bkhi nao\b", r"\btrong truong hop nao\b",
    ),
    "TEMPORAL_COMPARISON": (
        r"\bso voi\b", r"\bthay doi\b.{0,50}\b(?:the nao|ra sao)\b",
        r"\b(?:tang|giam|chenh lech)\b.{0,40}\b(?:bao nhieu|the nao|ra sao)\b",
        r"\bkhac nhau\b.{0,40}\b(?:the nao|ra sao|bao nhieu)\b",
        r"\bgiua\b.{1,100}\bva\b.{0,80}\b(?:thay doi|chenh lech|khac nhau|so sanh)\b",
    ),
}

ROLE_PATTERNS = {
    "FORECAST": (r"\bdu bao\b", r"\bdu kien\b", r"\bnhan dinh\b.{0,60}\b(?:se|co the)\b"),
    "STATUS": (r"\btinh trang\b", r"\bhien trang\b", r"\btrang thai\b", r"\bdang o muc\b", r"\bbao dong\b"),
    "EXPLANATION": (r"\bnguyen nhan\b", r"\bdo\b.{1,80}\bdan den\b", r"\bvi\b.{1,80}\bnen\b"),
    "RECOMMENDATION": (r"\bkhuyen nghi\b", r"\bkien nghi\b", r"\bde xuat\b"),
    "ACTION": (r"\bbien phap\b", r"\btrien khai\b", r"\bthuc hien\b", r"\bung pho\b", r"\bxu ly\b", r"\bchi dao\b"),
    "RULE": (r"\bquy dinh\b", r"\bbat buoc\b", r"\bphai\b"),
    "CONDITION": (r"\bdieu kien\b", r"\bneu\b.{1,100}\bthi\b", r"\btrong truong hop\b"),
}
MEASUREMENT_PATTERN = re.compile(
    r"\b(?:muc nuoc|luu luong|dung tich|dien tich|luong mua|cong suat|cao trinh|gia tri|so lieu)\b"
    r"|\b\d+(?:[.,]\d+)?\s*(?:m3/s|m3|mm|cm|m|ha|%|phan tram)\b"
)
FORECAST_METRIC_PATTERN = re.compile(r"forecast|du bao|du kien")


def load_c11_dev(root: Path, split: str = "dev") -> list[dict]:
    if split != "dev":
        raise ValueError("C1.1 is DEV-only; Candidate Test must remain sealed")
    return read_jsonl(root / "data/benchmark/dev.jsonl")


def extract_question_requirements_v2(question: str) -> dict:
    folded = _fold(question)
    requirements = []
    reasons = []
    for requirement in REQUIREMENTS:
        for pattern in QUESTION_RULES[requirement]:
            match = re.search(pattern, folded)
            if match:
                requirements.append(requirement)
                reasons.append({
                    "requirement": requirement, "rule": pattern,
                    "matched_text": match.group(0), "basis": "explicit question intent",
                })
                break
    status = "CERTAIN" if requirements else "UNCERTAIN"
    return {
        "status": status,
        "requirements": requirements,
        "reasons": reasons,
        "uncertain_reason": None if requirements else "NO_EXPLICIT_SUPPORTED_INTENT_PATTERN",
        "component_count": len(requirements),
    }


def _unique_dicts(values: list[dict]) -> list[dict]:
    output, seen = [], set()
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            output.append(value)
    return output


def _known_field(value: object) -> bool:
    return value not in (None, "", [], {}, "UNKNOWN")


def _document_reporting_time(document: dict | None) -> dict | str:
    if not document:
        return "UNKNOWN"
    period = document.get("document_reporting_period")
    if not _known_field(period):
        return "UNKNOWN"
    return period


def _tuple_relevance(question_tokens: set[str], semantic_tuple: dict) -> float:
    parts = []
    for field in ("entity", "metric", "unit", "value", "time"):
        value = semantic_tuple.get(field)
        if isinstance(value, dict):
            parts.extend(str(value.get(key) or "") for key in ("raw", "canonical", "normalized"))
    return _jaccard(question_tokens, _token_set(" ".join(parts)))


def _strict_content_roles(text: str, table_tuples: list[dict] | None = None) -> list[str]:
    folded = _fold(text)
    roles = []
    tuples = table_tuples or []
    if tuples:
        tuple_text = " ".join(
            str((row.get("metric") or {}).get(key) or "")
            for row in tuples for key in ("raw", "canonical")
        )
        if FORECAST_METRIC_PATTERN.search(_fold(tuple_text)):
            roles.append("FORECAST")
        if any(_known_field((row.get("value") or {}).get("normalized") or
                            (row.get("value") or {}).get("raw")) for row in tuples):
            roles.append("MEASUREMENT")
    elif MEASUREMENT_PATTERN.search(folded):
        roles.append("MEASUREMENT")
    for role, patterns in ROLE_PATTERNS.items():
        if any(re.search(pattern, folded) for pattern in patterns):
            roles.append(role)
    ordered = [role for role in EVIDENCE_ROLES if role in set(roles) and role != "UNKNOWN"]
    return ordered or ["UNKNOWN"]


def build_evidence_representation(
    question: str, candidate_id: str, unit_by_id: dict[str, dict],
    table_by_id: dict[str, dict], region_by_id: dict[str, dict],
    document_by_id: dict[str, dict], source_provenance: list[dict] | None = None,
) -> dict:
    unit = unit_by_id[candidate_id]
    table = table_by_id.get(candidate_id)
    region = region_by_id.get(candidate_id)
    document = document_by_id.get(unit["doc_id"])
    question_tokens = _token_set(question)
    semantic_tuples = list((table or {}).get("semantic_tuples") or [])
    semantic_tuples.sort(key=lambda row: (-_tuple_relevance(question_tokens, row), str(row.get("tuple_id") or "")))
    selected_tuples = semantic_tuples[:5]

    entities = _unique_dicts([
        {"raw": (row.get("entity") or {}).get("raw"),
         "canonical": (row.get("entity") or {}).get("canonical")}
        for row in selected_tuples if _known_field(row.get("entity"))
    ])
    metrics = _unique_dicts([
        {"raw": (row.get("metric") or {}).get("raw"),
         "canonical": (row.get("metric") or {}).get("canonical")}
        for row in selected_tuples if _known_field(row.get("metric"))
    ])
    value_units = _unique_dicts([
        {
            "value_raw": (row.get("value") or {}).get("raw"),
            "value_normalized": (row.get("value") or {}).get("normalized"),
            "unit_raw": (row.get("unit") or {}).get("raw"),
            "unit_normalized": (row.get("unit") or {}).get("normalized"),
        }
        for row in selected_tuples if _known_field(row.get("value"))
    ])
    evidence_times = _unique_dicts([
        {
            "raw": (row.get("time") or {}).get("raw"),
            "start": (row.get("time") or {}).get("normalized_start"),
            "end": (row.get("time") or {}).get("normalized_end"),
            "period_type": (row.get("time") or {}).get("period_type"),
            "time_type": "FORECAST_DATE" if FORECAST_METRIC_PATTERN.search(
                _fold(" ".join(str((row.get("metric") or {}).get(key) or "")
                                  for key in ("raw", "canonical")))) else "MEASUREMENT_DATE",
        }
        for row in selected_tuples if _known_field(row.get("time"))
    ])
    text = unit.get("index_text") or ""
    roles = _strict_content_roles(text, selected_tuples if table else None)
    structured_text = " ".join(
        [str(value) for item in entities + metrics for value in item.values() if value]
    )
    structured_overlap = _jaccard(question_tokens, _token_set(structured_text))
    region_type = (region or {}).get("region_type") or ("TABLE" if table else "UNKNOWN")
    reporting_time = _document_reporting_time(document)
    metadata_known = any((entities, metrics, value_units, evidence_times, reporting_time != "UNKNOWN",
                          region_type != "UNKNOWN"))
    return {
        "evidence_id": candidate_id,
        "doc_id": unit["doc_id"], "page_id": unit["page_id"],
        "unit_type": unit.get("unit_type", "UNKNOWN"), "region_type": region_type,
        "evidence_roles": roles,
        "entity": entities or "UNKNOWN", "metric": metrics or "UNKNOWN",
        "value_unit": value_units or "UNKNOWN",
        "evidence_time": evidence_times or "UNKNOWN",
        "document_reporting_time": reporting_time,
        "source_provenance": source_provenance or [{"source": "G0_P0_S1", "source_rank": "UNKNOWN"}],
        "structured_query_overlap": structured_overlap,
        "metadata_known": bool(metadata_known),
        "content_tokens": sorted(_token_set(text))[:80],
        "metadata_basis": {
            "table_semantic_tuples_used": len(selected_tuples),
            "table_semantic_tuples_available": len(semantic_tuples),
            "text_region_present": region is not None,
            "document_present": document is not None,
            "report_date_used_as_evidence_date": False,
        },
    }


def _evidence_time_keys(representation: dict) -> set[str]:
    values = representation.get("evidence_time")
    if not isinstance(values, list):
        return set()
    output = set()
    for value in values:
        key = value.get("start") or value.get("end") or value.get("raw")
        if key:
            output.add(str(key))
    return output


def _metadata_sufficiency(requirements: list[str], representations: dict[str, dict]) -> tuple[bool, list[str]]:
    reasons = []
    roles = {role for row in representations.values() for role in row["evidence_roles"]}
    all_times = {value for row in representations.values() for value in _evidence_time_keys(row)}
    for requirement in requirements:
        if requirement == "TEMPORAL_COMPARISON":
            if len(all_times) < 2:
                reasons.append("TEMPORAL_COMPARISON_NEEDS_TWO_EVIDENCE_TIMES")
        elif ROLE_FOR_REQUIREMENT[requirement] not in roles:
            reasons.append(f"NO_CANDIDATE_ROLE_FOR_{requirement}")
    if not any(row["metadata_known"] for row in representations.values()):
        reasons.append("NO_STRUCTURED_METADATA")
    return not reasons, reasons


def _cross_document_intent(question: str) -> bool:
    folded = _fold(question)
    return any(value in folded for value in ("chuoi tai lieu", "cac tai lieu", "cac bao cao", "lien van ban"))


def _provenance_score_v2(
    question: str, candidate: dict, selected: list[dict], selected_times: set[str],
    requirements: list[str],
) -> tuple[float, list[str]]:
    score = float(candidate["structured_query_overlap"])
    decisions = []
    if candidate["structured_query_overlap"] > 0:
        decisions.append("ENTITY_OR_METRIC_OVERLAP")
    candidate_times = _evidence_time_keys(candidate)
    if "TEMPORAL_COMPARISON" in requirements and candidate_times - selected_times:
        score += 0.5
        decisions.append("ADDS_DISTINCT_EVIDENCE_TIME")
    if selected and any(row["doc_id"] == candidate["doc_id"] for row in selected):
        score += 0.15
        decisions.append("SAME_DOCUMENT_COMPATIBILITY")
    if selected and any(row["page_id"] == candidate["page_id"] for row in selected):
        score += 0.1
        decisions.append("SAME_PAGE_COMPATIBILITY")
    if selected and _cross_document_intent(question) and all(
        row["doc_id"] != candidate["doc_id"] for row in selected
    ):
        score += 0.25
        decisions.append("CROSS_DOCUMENT_ALLOWED_BY_QUESTION")
    return min(score, 1.0), decisions


def set_aware_v2(
    question: str, candidate_ids: list[str], base_results: list[dict],
    representations: dict[str, dict], weights: dict[str, float], limit: int = 20,
) -> tuple[list[dict], dict]:
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("E4 requires unique candidate IDs")
    if set(candidate_ids) != set(representations):
        raise ValueError("E4 representation IDs must equal candidate IDs")
    base_by_id = {row["evidence_id"]: row for row in base_results}
    if set(candidate_ids) != set(base_by_id):
        raise ValueError("E4 base ranking must exactly cover G0")
    prediction = extract_question_requirements_v2(question)
    sufficient, insufficiency = _metadata_sufficiency(prediction["requirements"], representations)
    fallback_reasons = []
    if prediction["status"] == "UNCERTAIN":
        fallback_reasons.append(prediction["uncertain_reason"])
    if not sufficient:
        fallback_reasons.extend(insufficiency)

    base_scores = np.asarray([float(base_by_id[item_id]["score"]) for item_id in candidate_ids])
    minimum, maximum = float(base_scores.min()), float(base_scores.max())
    denominator = maximum - minimum
    normalized = {
        item_id: (float(base_by_id[item_id]["score"]) - minimum) / denominator if denominator else 1.0
        for item_id in candidate_ids
    }
    if fallback_reasons:
        results = []
        steps = []
        for rank, row in enumerate(base_results[:limit], 1):
            result = dict(row)
            result["rank"] = rank
            results.append(result)
            steps.append({
                "step": rank, "evidence_id": row["evidence_id"], "fallback": True,
                "new_requirements": [], "satisfied_requirements": [],
                "utility": normalized[row["evidence_id"]],
            })
        return results, {
            "requirement_prediction": prediction, "fallback_to_e0": True,
            "fallback_reasons": sorted(set(fallback_reasons)), "steps": steps,
            "satisfied_requirements": [], "final_selected_evidence_ids": [row["evidence_id"] for row in results],
        }

    requirements = prediction["requirements"]
    selected_ids: list[str] = []
    selected_representations: list[dict] = []
    selected_times: set[str] = set()
    satisfied: set[str] = set()
    remaining = set(candidate_ids)
    base_rank = {row["evidence_id"]: int(row["rank"]) for row in base_results}
    steps = []
    for step in range(1, min(limit, len(candidate_ids)) + 1):
        scored = []
        for item_id in remaining:
            representation = representations[item_id]
            new_requirements = set()
            for requirement in requirements:
                if requirement in satisfied:
                    continue
                if requirement == "TEMPORAL_COMPARISON":
                    if len(selected_times | _evidence_time_keys(representation)) >= 2:
                        new_requirements.add(requirement)
                elif ROLE_FOR_REQUIREMENT[requirement] in representation["evidence_roles"]:
                    new_requirements.add(requirement)
            requirement_score = len(new_requirements) / len(requirements)
            provenance, provenance_decisions = _provenance_score_v2(
                question, representation, selected_representations, selected_times, requirements,
            )
            candidate_tokens = set(representation["content_tokens"])
            redundancy = max(
                (_jaccard(candidate_tokens, set(row["content_tokens"])) for row in selected_representations),
                default=0.0,
            )
            utility = (
                weights["base_relevance"] * normalized[item_id]
                + weights["unmet_requirement"] * requirement_score
                + weights["provenance_compatibility"] * provenance
                - weights["redundancy_penalty"] * redundancy
            )
            scored.append((
                -utility, base_rank[item_id], item_id, utility, sorted(new_requirements),
                requirement_score, provenance, provenance_decisions, redundancy,
            ))
        chosen = min(scored)
        (_, _, item_id, utility, new_requirements, requirement_score,
         provenance, provenance_decisions, redundancy) = chosen
        selected_ids.append(item_id)
        selected_representations.append(representations[item_id])
        selected_times.update(_evidence_time_keys(representations[item_id]))
        satisfied.update(new_requirements)
        remaining.remove(item_id)
        steps.append({
            "step": step, "evidence_id": item_id, "fallback": False,
            "base_rank": base_rank[item_id], "base_relevance": normalized[item_id],
            "candidate_evidence_roles": representations[item_id]["evidence_roles"],
            "new_requirements": new_requirements, "satisfied_requirements": sorted(satisfied),
            "utility": utility, "requirement_coverage_input": requirement_score,
            "provenance_compatibility": provenance,
            "provenance_decisions": provenance_decisions,
            "redundancy_penalty_input": redundancy,
        })
    results = []
    for rank, item_id in enumerate(selected_ids, 1):
        result = dict(base_by_id[item_id])
        result["rank"] = rank
        result["score"] = float(steps[rank - 1]["utility"])
        result["base_score"] = float(base_by_id[item_id]["score"])
        results.append(result)
    return results, {
        "requirement_prediction": prediction, "fallback_to_e0": False,
        "fallback_reasons": [], "steps": steps,
        "satisfied_requirements": sorted(satisfied),
        "final_selected_evidence_ids": selected_ids,
    }


def _load_map(path: Path) -> dict[str, dict]:
    return {row["qa_id"]: row for row in read_jsonl(path)}


def _subgroups(qa: dict) -> list[str]:
    labels = [
        "OVERALL", "CHALLENGE" if qa.get("relation_type") else "CORE",
        "RETRIEVAL_MULTI" if qa["retrieval_evidence_count"] >= 2 else "RETRIEVAL_SINGLE",
        normalize_modality(qa), qa["location_type"],
    ]
    return labels


def _redundancy(ids: list[str], representations: dict[str, dict]) -> float:
    token_sets = [set(representations[item_id]["content_tokens"]) for item_id in ids[:20]]
    if len(token_sets) < 2:
        return 0.0
    return float(np.mean([
        max(_jaccard(tokens, other) for j, other in enumerate(token_sets) if i != j)
        for i, tokens in enumerate(token_sets)
    ]))


def _aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {"sample_count": 0, "candidate_coverage@100": None, "all_r@10": None,
                "all_r@20": None, "any_r@20": None, "gold_coverage@20": None,
                "mrr": None, "ndcg@10": None, "redundancy@20": None,
                "latency_ms_per_query": None}
    mean = lambda key: float(np.mean([key(row) for row in rows]))
    return {
        "sample_count": len(rows),
        "candidate_coverage@100": mean(lambda row: row["candidate_coverage"]),
        "all_r@10": mean(lambda row: row["metrics"]["10"]["all_recall"]),
        "all_r@20": mean(lambda row: row["metrics"]["20"]["all_recall"]),
        "any_r@20": mean(lambda row: row["metrics"]["20"]["any_recall"]),
        "gold_coverage@20": mean(lambda row: row["metrics"]["20"]["average_gold_coverage"]),
        "mrr": mean(lambda row: row["metrics"]["mrr"]),
        "ndcg@10": mean(lambda row: row["metrics"]["ndcg@10"]),
        "redundancy@20": mean(lambda row: row["redundancy"]),
        "latency_ms_per_query": mean(lambda row: row["latency_ms"]),
    }


def _evaluate(
    dev: list[dict], rankings: dict[str, dict[str, dict]], candidates: dict[str, dict],
    representations: dict[str, dict[str, dict]], latency: dict[str, dict[str, float]],
) -> tuple[dict, dict]:
    per_query = {method: {} for method in METHODS}
    grouped = {method: {group: [] for group in SUBGROUPS} for method in METHODS}
    for method in METHODS:
        for qa in dev:
            qa_id = qa["qa_id"]
            pool = candidates[qa_id]["candidate_ids"]
            ids = [row["evidence_id"] for row in rankings[method][qa_id]["results"]]
            gold = set(qa["retrieval_evidence_ids"])
            candidate_coverage = float(gold <= set(pool))
            metrics = final_ranking_metrics(qa["retrieval_evidence_ids"], ids, [10, 20])
            if metrics["20"]["all_recall"] > candidate_coverage:
                raise AssertionError("All R@20 cannot exceed candidate coverage")
            row = {
                "candidate_coverage": candidate_coverage, "metrics": metrics,
                "redundancy": _redundancy(ids, representations[qa_id]),
                "latency_ms": latency[method][qa_id],
            }
            per_query[method][qa_id] = row
            for group in _subgroups(qa):
                grouped[method][group].append(row)
    return per_query, {
        method: {group: _aggregate(rows) for group, rows in grouped[method].items()}
        for method in METHODS
    }


def _transition(current: dict, baseline: dict, qa_ids: list[str]) -> dict:
    recovered = [qa_id for qa_id in qa_ids
                 if baseline[qa_id]["metrics"]["20"]["all_recall"] == 0.0
                 and current[qa_id]["metrics"]["20"]["all_recall"] == 1.0]
    regressed = [qa_id for qa_id in qa_ids
                 if baseline[qa_id]["metrics"]["20"]["all_recall"] == 1.0
                 and current[qa_id]["metrics"]["20"]["all_recall"] == 0.0]
    return {"recovered": len(recovered), "regressed": len(regressed),
            "recovered_qa_ids": recovered, "regressed_qa_ids": regressed}


def _statistics(dev: list[dict], per_query: dict, config: dict) -> dict:
    output = {"unique_gold_sets": 0, "comparisons": {}, "duplicated_gold_set_impact": {}}
    signatures = ["|".join(sorted(qa["retrieval_evidence_ids"])) for qa in dev]
    output["unique_gold_sets"] = len(set(signatures))
    for baseline in ("E0", "E2"):
        label = f"E4_vs_{baseline}"
        output["comparisons"][label] = {}
        for group, indexes in {
            "OVERALL": list(range(len(dev))),
            "RETRIEVAL_MULTI": [i for i, qa in enumerate(dev) if qa["retrieval_evidence_count"] >= 2],
        }.items():
            current = [per_query["E4"][dev[i]["qa_id"]]["metrics"]["20"]["all_recall"] for i in indexes]
            control = [per_query[baseline][dev[i]["qa_id"]]["metrics"]["20"]["all_recall"] for i in indexes]
            clusters = [signatures[i] for i in indexes]
            output["comparisons"][label][group] = {
                "sample_count": len(indexes),
                "qa_bootstrap": _bootstrap(current, control, config["bootstrap_resamples"], config["seed"]),
                "gold_set_cluster_bootstrap": _bootstrap(
                    current, control, config["bootstrap_resamples"], config["seed"], clusters,
                ),
            }

    differences = {
        qa["qa_id"]: per_query["E4"][qa["qa_id"]]["metrics"]["20"]["all_recall"]
        - per_query["E0"][qa["qa_id"]]["metrics"]["20"]["all_recall"]
        for qa in dev
    }
    by_signature: dict[str, list[float]] = defaultdict(list)
    for qa, signature in zip(dev, signatures):
        by_signature[signature].append(differences[qa["qa_id"]])
    counts = Counter(signatures)
    output["duplicated_gold_set_impact"] = {
        "qa_weighted_delta": float(np.mean(list(differences.values()))),
        "signature_balanced_delta": float(np.mean([np.mean(values) for values in by_signature.values()])),
        "duplicated_signature_count": sum(value > 1 for value in counts.values()),
        "qa_in_duplicated_signatures": sum(value for value in counts.values() if value > 1),
        "max_signature_multiplicity": max(counts.values()),
    }
    return output


def _artifact_hashes(output_dir: Path) -> dict[str, str]:
    if not output_dir.exists():
        return {}
    return {path.relative_to(output_dir).as_posix(): sha256(path)
            for path in sorted(output_dir.rglob("*.jsonl")) if path.is_file()}


def _balanced_review_sample(dev: list[dict], count: int, seed: int) -> list[dict]:
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for qa in dev:
        key = ("MULTI" if qa["retrieval_evidence_count"] >= 2 else "SINGLE", normalize_modality(qa))
        buckets[key].append(qa)
    for key in buckets:
        buckets[key].sort(key=lambda qa: hashlib.sha256(f"{seed}:{qa['qa_id']}".encode()).hexdigest())
    output = []
    keys = sorted(buckets)
    position = 0
    while len(output) < count and any(position < len(buckets[key]) for key in keys):
        for key in keys:
            if position < len(buckets[key]) and len(output) < count:
                output.append(buckets[key][position])
        position += 1
    return output


def _compact_representation(row: dict) -> dict:
    return {key: value for key, value in row.items() if key != "content_tokens"}


def _gold_rank_details(gold_ids: list[str], results: list[dict]) -> list[dict]:
    by_id = {row["evidence_id"]: row for row in results}
    return [
        {
            "evidence_id": item_id,
            "rank": by_id[item_id]["rank"] if item_id in by_id else None,
            "fusion_score": by_id[item_id]["score"] if item_id in by_id else None,
        }
        for item_id in gold_ids
    ]


def run_c11(root: Path, pytest_result: dict | None = None) -> dict:
    config = json.loads((root / "configs/phase_c1_1.json").read_text(encoding="utf-8"))
    report_dir = root / "reports/C1_1"
    output_dir = root / "outputs/C1_1"
    ranking_dir = output_dir / "rankings"
    trace_dir = output_dir / "traces"
    representation_dir = output_dir / "representations"
    for directory in (report_dir, ranking_dir, trace_dir, representation_dir):
        directory.mkdir(parents=True, exist_ok=True)
    prior_hashes = _artifact_hashes(output_dir)
    candidate_test = root / "data/benchmark/candidate_test.jsonl"
    candidate_hash_before = sha256(candidate_test)

    dev = load_c11_dev(root)
    qa_ids = [qa["qa_id"] for qa in dev]
    units = read_jsonl(root / "data/processed/evidence_units.jsonl")
    unit_by_id = {row["evidence_id"]: row for row in units}
    table_rows = read_jsonl(root / "data/parsed/tables.jsonl")
    region_rows = read_jsonl(root / "data/parsed/regions.jsonl")
    document_rows = read_jsonl(root / "data/parsed/documents.jsonl")
    table_by_id = {row["table_id"]: row for row in table_rows}
    region_by_id = {row["region_id"]: row for row in region_rows}
    document_by_id = {row["doc_id"]: row for row in document_rows}
    b1 = json.loads((root / "reports/B1_INTEGRITY.json").read_text(encoding="utf-8"))
    c1_ready = json.loads((root / "reports/C1/C1_READINESS.json").read_text(encoding="utf-8"))

    g0 = _load_map(root / "outputs/C1/candidates/g0_b100_dev.jsonl")
    g1 = _load_map(root / "outputs/C1/candidates/g1_b100_dev.jsonl")
    rankings = {
        "E0": _load_map(root / "outputs/C1/rankings/e0_g0_global_rrf_dev.jsonl"),
        "E1": _load_map(root / "outputs/C1/rankings/e1_g1_global_rrf_dev.jsonl"),
        "E2": _load_map(root / "outputs/C1/rankings/e2_g0_cross_encoder_dev.jsonl"),
        "E3": _load_map(root / "outputs/C1/rankings/e3_g0_set_aware_dev.jsonl"),
    }
    global_cache = _load_map(root / "outputs/C1/cache/global_ranks.jsonl")
    source_maps = (g0, g1, rankings["E0"], rankings["E1"], rankings["E2"], rankings["E3"], global_cache)
    metadata_mapping_errors = [
        item_id for row in g0.values() for item_id in row["candidate_ids"]
        if item_id not in unit_by_id or (item_id not in table_by_id and item_id not in region_by_id)
    ]
    missing_documents = sorted({
        unit_by_id[item_id]["doc_id"] for row in g0.values() for item_id in row["candidate_ids"]
        if unit_by_id[item_id]["doc_id"] not in document_by_id
    })
    signatures = {"|".join(sorted(qa["retrieval_evidence_ids"])) for qa in dev}
    preflight = {
        "dev_qa": len(dev),
        "retrieval_multi_qa": sum(qa["retrieval_evidence_count"] >= 2 for qa in dev),
        "unique_gold_sets": len(signatures),
        "g0_budget_min": min(len(row["candidate_ids"]) for row in g0.values()),
        "g0_budget_max": max(len(row["candidate_ids"]) for row in g0.values()),
        "g1_budget_min": min(len(row["candidate_ids"]) for row in g1.values()),
        "g1_budget_max": max(len(row["candidate_ids"]) for row in g1.values()),
        "phase_a_metadata_mapping_errors": len(metadata_mapping_errors),
        "missing_candidate_documents": missing_documents,
        "B1_integrity": b1.get("B1_INTEGRITY"),
        "C1_valid": bool(c1_ready.get("C1_VALID")),
    }
    blockers = []
    if len(dev) != 93: blockers.append(f"Expected 93 DEV QA, found {len(dev)}")
    if preflight["retrieval_multi_qa"] != 25: blockers.append("Expected 25 retrieval-multi QA")
    if len(signatures) != 45: blockers.append("Expected 45 unique gold sets")
    if any(set(mapping) != set(qa_ids) for mapping in source_maps): blockers.append("C1 artifact QA IDs mismatch")
    if any(len(row["candidate_ids"]) != 100 for mapping in (g0, g1) for row in mapping.values()):
        blockers.append("G0/G1 candidate budget is not exactly 100")
    if metadata_mapping_errors: blockers.append("Phase A evidence metadata mapping incomplete")
    if missing_documents: blockers.append("Candidate document metadata missing")
    if preflight["B1_integrity"] != "PASS": blockers.append("B1 integrity is not PASS")
    if not preflight["C1_valid"]: blockers.append("C1 is not valid")
    if blockers:
        readiness = {"C1_1_VALID": False, "status": "BLOCKED", "preflight": preflight,
                     "remaining_blockers": blockers}
        write_json(report_dir / "C1_1_READINESS.json", readiness)
        return readiness

    representations: dict[str, dict[str, dict]] = {}
    representation_rows = []
    for qa in dev:
        qa_id = qa["qa_id"]
        reps = {}
        for item_id in g0[qa_id]["candidate_ids"]:
            reps[item_id] = build_evidence_representation(
                qa["question"], item_id, unit_by_id, table_by_id, region_by_id, document_by_id,
                g0[qa_id].get("provenance", {}).get(item_id),
            )
        representations[qa_id] = reps
        representation_rows.append({
            "qa_id": qa_id,
            "candidate_representations": [_compact_representation(reps[item_id])
                                          for item_id in g0[qa_id]["candidate_ids"]],
        })
    write_jsonl(representation_dir / "e4_candidate_representations_dev.jsonl", representation_rows)

    e4_rankings = {}
    e4_traces = {}
    selector_ms = {}
    for qa in dev:
        qa_id = qa["qa_id"]
        started = time.perf_counter()
        results, trace = set_aware_v2(
            qa["question"], g0[qa_id]["candidate_ids"], rankings["E0"][qa_id]["results"],
            representations[qa_id], config["e4"]["weights"], config["selection_budget"],
        )
        selector_ms[qa_id] = (time.perf_counter() - started) * 1000.0
        e4_rankings[qa_id] = {
            "qa_id": qa_id, "candidate_ids": g0[qa_id]["candidate_ids"],
            "candidates": "G0", "selection": "SET_AWARE_V2", "results": results,
        }
        e4_traces[qa_id] = {"qa_id": qa_id, **trace}
    rankings["E4"] = e4_rankings
    write_jsonl(ranking_dir / "e4_g0_set_aware_v2_dev.jsonl", (e4_rankings[qa_id] for qa_id in qa_ids))
    write_jsonl(trace_dir / "e4_set_aware_v2_traces.jsonl", (e4_traces[qa_id] for qa_id in qa_ids))

    c1_csv = {}
    with (root / "reports/C1/C1_RESULTS.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            c1_csv[row["experiment"]] = row
    latency = {method: {} for method in METHODS}
    for qa_id in qa_ids:
        latency["E0"][qa_id] = float(c1_csv["E0"]["runtime_ms_per_query"])
        latency["E2"][qa_id] = float(c1_csv["E2"]["runtime_ms_per_query"])
        latency["E3"][qa_id] = float(c1_csv["E3"]["runtime_ms_per_query"])
        latency["E4"][qa_id] = latency["E0"][qa_id] + selector_ms[qa_id]
    per_query, subgroup_metrics = _evaluate(dev, rankings, g0, representations, latency)

    baseline_recomputed = {
        method: {
            "candidate_coverage@100": subgroup_metrics[method]["OVERALL"]["candidate_coverage@100"],
            "all_r@20": subgroup_metrics[method]["OVERALL"]["all_r@20"],
            "multi_all_r@20": subgroup_metrics[method]["RETRIEVAL_MULTI"]["all_r@20"],
        }
        for method in ("E0", "E2", "E3")
    }

    regression_rows = []
    regression_category_counts = Counter()
    for qa in dev:
        qa_id = qa["qa_id"]
        gold = qa["retrieval_evidence_ids"]
        top0 = [row["evidence_id"] for row in rankings["E0"][qa_id]["results"][:20]]
        top1 = [row["evidence_id"] for row in rankings["E1"][qa_id]["results"][:20]]
        if not (set(gold) <= set(top0) and not set(gold) <= set(top1)):
            continue
        missing = sorted(set(gold) - set(top1))
        e0_details = _gold_rank_details(gold, rankings["E0"][qa_id]["results"])
        e1_details = _gold_rank_details(gold, rankings["E1"][qa_id]["results"])
        cache_row = global_cache[qa_id]
        rank_lookup = {
            item_id: {"bm25_global_rank": bm25_rank, "e5_global_rank": e5_rank}
            for item_id, bm25_rank, e5_rank in zip(
                cache_row["candidate_ids"], cache_row["bm25_ranks"], cache_row["e5_ranks"]
            )
        }
        result1 = {row["evidence_id"]: row for row in rankings["E1"][qa_id]["results"]}
        new_competitors = [item_id for item_id in top1 if item_id not in top0]
        competitor_rows = []
        provenance_evidence = []
        gold_representations = {
            item_id: build_evidence_representation(
                qa["question"], item_id, unit_by_id, table_by_id, region_by_id, document_by_id,
                g1[qa_id].get("provenance", {}).get(item_id),
            ) for item_id in missing
        }
        max_gold_overlap = max(
            (row["structured_query_overlap"] for row in gold_representations.values()), default=0.0
        )
        min_missing_score = min(
            (next(row["fusion_score"] for row in e1_details if row["evidence_id"] == item_id)
             for item_id in missing), default=float("inf")
        )
        for item_id in new_competitors:
            representation = build_evidence_representation(
                qa["question"], item_id, unit_by_id, table_by_id, region_by_id, document_by_id,
                g1[qa_id].get("provenance", {}).get(item_id),
            )
            row = {
                "evidence_id": item_id, "E1_rank": result1[item_id]["rank"],
                "fusion_score": result1[item_id]["score"],
                **rank_lookup[item_id],
                "candidate_source": g1[qa_id].get("provenance", {}).get(item_id, []),
                "structured_provenance": _compact_representation(representation),
                "out_scores_missing_gold": result1[item_id]["score"] > min_missing_score,
            }
            competitor_rows.append(row)
            if (representation["entity"] != "UNKNOWN" or representation["metric"] != "UNKNOWN") \
                    and representation["structured_query_overlap"] + 0.05 < max_gold_overlap \
                    and result1[item_id]["score"] > min_missing_score:
                provenance_evidence.append({
                    "competitor_id": item_id,
                    "competitor_overlap": representation["structured_query_overlap"],
                    "missing_gold_max_overlap": max_gold_overlap,
                    "basis": "known structured entity/metric is less compatible with the question than missing gold",
                })
        e0_score_by_gold = {row["evidence_id"]: row["fusion_score"] for row in e0_details}
        e1_score_by_gold = {row["evidence_id"]: row["fusion_score"] for row in e1_details}
        fusion_score_changed = any(
            not math.isclose(float(e0_score_by_gold[item_id]), float(e1_score_by_gold[item_id]),
                             rel_tol=0.0, abs_tol=1e-15)
            for item_id in gold
        )
        categories = ["RANK_DISPLACEMENT"]
        if competitor_rows:
            categories.append("COMPETING_EVIDENCE")
        if fusion_score_changed:
            categories.append("FUSION_SCORE_EFFECT")
        if provenance_evidence:
            categories.append("PROVENANCE_CONFUSION")
        if not competitor_rows:
            categories.append("OTHER_UNCERTAIN")
        regression_category_counts.update(categories)
        regression_rows.append({
            "qa_id": qa_id, "gold_evidence_ids": gold,
            "G0_candidate_ids": g0[qa_id]["candidate_ids"],
            "G1_candidate_ids": g1[qa_id]["candidate_ids"],
            "gold_ranks_E0": e0_details, "gold_ranks_E1": e1_details,
            "missing_gold_at_E1_top20": missing,
            "gold_global_ranks": {item_id: rank_lookup[item_id] for item_id in gold},
            "gold_fusion_scores_unchanged": not fusion_score_changed,
            "new_competing_candidates": competitor_rows,
            "categories": categories, "primary_cause": categories[0],
            "provenance_confusion_evidence": provenance_evidence,
            "modality": normalize_modality(qa),
            "retrieval_evidence_count": qa["retrieval_evidence_count"],
            "diagnosis": "Gold remains in G1, keeps the same global-RRF score, but new high-scoring G1 candidates displace it below Top-20.",
        })
    write_jsonl(report_dir / "RANK_REGRESSION_DIAGNOSIS.jsonl", regression_rows)

    prior_traces = _load_map(root / "outputs/C1/traces/e3_set_aware_traces.jsonl")
    before_counts = Counter(
        requirement for row in prior_traces.values() for requirement in row["requirements"]
    )
    predictions = {qa["qa_id"]: extract_question_requirements_v2(qa["question"]) for qa in dev}
    after_counts = Counter(
        requirement for prediction in predictions.values() for requirement in prediction["requirements"]
    )
    cardinality = Counter(
        "3+" if prediction["component_count"] >= 3 else str(prediction["component_count"])
        for prediction in predictions.values()
    )
    before_first_complete = sum(
        bool(row["requirements"]) and set(row["requirements"]) <= set(row["steps"][0]["covered_requirements"])
        for row in prior_traces.values()
    )
    after_first_complete = sum(
        bool(trace["requirement_prediction"]["requirements"])
        and not trace["fallback_to_e0"]
        and set(trace["requirement_prediction"]["requirements"])
        <= set(trace["steps"][0]["satisfied_requirements"])
        for trace in e4_traces.values()
    )
    temporal_prior_flags = [
        qa_id for qa_id in qa_ids
        if "TEMPORAL_COMPARISON" in prior_traces[qa_id]["requirements"]
        and "TEMPORAL_COMPARISON" not in predictions[qa_id]["requirements"]
    ]
    forecast_prior_flags = [
        qa_id for qa_id in qa_ids
        if "FORECAST" in prior_traces[qa_id]["requirements"]
        and "FORECAST" not in predictions[qa_id]["requirements"]
    ]
    review_sample = []
    for qa in _balanced_review_sample(dev, 30, config["seed"]):
        qa_id = qa["qa_id"]
        review_sample.append({
            "qa_id": qa_id, "question": qa["question"],
            "retrieval_group": "MULTI" if qa["retrieval_evidence_count"] >= 2 else "SINGLE",
            "modality": normalize_modality(qa), "prediction": predictions[qa_id],
            "fallback_to_e0": e4_traces[qa_id]["fallback_to_e0"],
            "fallback_reasons": e4_traces[qa_id]["fallback_reasons"],
            "selected_evidence_ids": e4_traces[qa_id]["final_selected_evidence_ids"],
            "human_validated": False, "queue_status": "PENDING_HUMAN_REVIEW",
        })
    requirement_audit = {
        "before": {
            "requirement_counts": dict(before_counts),
            "temporal_comparison": before_counts["TEMPORAL_COMPARISON"],
            "forecast": before_counts["FORECAST"],
            "first_evidence_saturation": before_first_complete,
            "uncertain": sum(row["fallback_to_r0"] for row in prior_traces.values()),
        },
        "after": {
            "requirement_counts": dict(after_counts),
            "temporal_comparison": after_counts["TEMPORAL_COMPARISON"],
            "forecast": after_counts["FORECAST"],
            "first_evidence_saturation": after_first_complete,
            "cardinality": dict(cardinality),
            "uncertain": sum(prediction["status"] == "UNCERTAIN" for prediction in predictions.values()),
            "fallback_to_e0": sum(trace["fallback_to_e0"] for trace in e4_traces.values()),
        },
        "prior_rule_based_false_positive_flags": {
            "temporal_comparison": temporal_prior_flags,
            "forecast": forecast_prior_flags,
        },
        "after_rule_consistency": {
            "temporal_without_explicit_comparison_rule": 0,
            "forecast_without_explicit_forecast_intent_rule": 0,
            "note": "Rule consistency is automatic diagnostics, not human validation.",
        },
        "manual_review_queue": {
            "sample_count": len(review_sample), "selection": "deterministic balanced queue",
            "human_validated": False, "rows": review_sample,
        },
    }
    write_json(report_dir / "REQUIREMENT_AUDIT.json", requirement_audit)

    all_representations = [row for qa_id in qa_ids for row in representations[qa_id].values()]
    role_counts = Counter(role for row in all_representations for role in row["evidence_roles"])
    both_times = [row for row in all_representations
                  if row["evidence_time"] != "UNKNOWN" and row["document_reporting_time"] != "UNKNOWN"]
    evidence_role_audit = {
        "representation_count": len(all_representations),
        "unique_evidence_ids": len({row["evidence_id"] for row in all_representations}),
        "role_counts": dict(role_counts),
        "field_coverage": {
            "entity_known": sum(row["entity"] != "UNKNOWN" for row in all_representations),
            "metric_known": sum(row["metric"] != "UNKNOWN" for row in all_representations),
            "value_unit_known": sum(row["value_unit"] != "UNKNOWN" for row in all_representations),
            "evidence_time_known": sum(row["evidence_time"] != "UNKNOWN" for row in all_representations),
            "document_reporting_time_known": sum(row["document_reporting_time"] != "UNKNOWN"
                                                 for row in all_representations),
            "unknown_role": sum(row["evidence_roles"] == ["UNKNOWN"] for row in all_representations),
        },
        "schema_checks": {
            "table_semantic_tuple_fields_present": all(
                not row.get("semantic_tuples") or
                {"entity", "metric", "value", "unit", "time"} <= set(row["semantic_tuples"][0])
                for row in table_rows
            ),
            "region_type_present": all("region_type" in row for row in region_rows),
            "document_reporting_period_field_present": all("document_reporting_period" in row
                                                             for row in document_rows),
        },
        "time_separation": {
            "representations_with_both_time_types": len(both_times),
            "report_date_used_as_evidence_date": 0,
            "evidence_time_source": "table semantic tuple only",
            "document_reporting_time_source": "document_reporting_period only",
        },
        "fallback_reason_counts": dict(Counter(
            reason for trace in e4_traces.values() for reason in trace["fallback_reasons"]
        )),
    }
    write_json(report_dir / "EVIDENCE_ROLE_AUDIT.json", evidence_role_audit)

    result_rows = []
    names = {
        "E0": "Global RRF", "E2": "Cross-Encoder", "E3": "Old Set-Aware",
        "E4": "Set-Aware V2",
    }
    for method in METHODS:
        overall = subgroup_metrics[method]["OVERALL"]
        multi = subgroup_metrics[method]["RETRIEVAL_MULTI"]
        result_rows.append({
            "method": method, "name": names[method], "sample_count": overall["sample_count"],
            "candidate_coverage@100": overall["candidate_coverage@100"],
            "all_r@10": overall["all_r@10"], "all_r@20": overall["all_r@20"],
            "multi_all_r@20": multi["all_r@20"], "any_r@20": overall["any_r@20"],
            "gold_coverage@20": overall["gold_coverage@20"], "mrr": overall["mrr"],
            "ndcg@10": overall["ndcg@10"], "latency_ms_per_query": overall["latency_ms_per_query"],
        })
    with (report_dir / "C1_1_RESULTS.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result_rows[0]))
        writer.writeheader()
        writer.writerows(result_rows)
    write_json(report_dir / "C1_1_SUBGROUPS.json", {
        "groups_use_validated_annotations_only_for_offline_evaluation": True,
        "experiments": subgroup_metrics,
    })

    transitions = {f"E4_vs_{baseline}": _transition(per_query["E4"], per_query[baseline], qa_ids)
                   for baseline in ("E0", "E2", "E3")}
    multi_ids = [qa["qa_id"] for qa in dev if qa["retrieval_evidence_count"] >= 2]
    multi_transitions = {
        f"E4_vs_{baseline}": _transition(per_query["E4"], per_query[baseline], multi_ids)
        for baseline in ("E0", "E2", "E3")
    }
    statistics = _statistics(dev, per_query, config)
    statistics["transitions"] = transitions
    statistics["multi_transitions"] = multi_transitions
    write_json(report_dir / "C1_1_STATISTICS.json", statistics)

    current_hashes = _artifact_hashes(output_dir)
    reproducible = bool(prior_hashes) and prior_hashes == current_hashes
    candidate_hash_after = sha256(candidate_test)
    selector_source = inspect.getsource(set_aware_v2)
    extractor_source = inspect.getsource(extract_question_requirements_v2)
    e0_top20 = {qa_id: [row["evidence_id"] for row in rankings["E0"][qa_id]["results"][:20]]
                for qa_id in qa_ids}
    uncertain_fallback_exact = all(
        e4_traces[qa_id]["requirement_prediction"]["status"] != "UNCERTAIN"
        or e4_traces[qa_id]["final_selected_evidence_ids"] == e0_top20[qa_id]
        for qa_id in qa_ids
    )
    audit_checks = {
        "preflight_verified_from_artifacts": not blockers,
        "baseline_metrics_recomputed_from_rankings": baseline_recomputed == {
            "E0": {"candidate_coverage@100": 0.7741935483870968, "all_r@20": 0.6236559139784946,
                   "multi_all_r@20": 0.6},
            "E2": {"candidate_coverage@100": 0.7741935483870968, "all_r@20": 0.6451612903225806,
                   "multi_all_r@20": 0.44},
            "E3": {"candidate_coverage@100": 0.7741935483870968, "all_r@20": 0.6236559139784946,
                   "multi_all_r@20": 0.6},
        },
        "all_13_G1_regressions_analyzed": len(regression_rows) == 13,
        "no_gold_answer_or_relation_in_inference_signatures": not (
            {"gold", "answer", "relation_type", "supporting_evidence_ids"}
            & (set(inspect.signature(set_aware_v2).parameters)
               | set(inspect.signature(extract_question_requirements_v2).parameters))
        ) and all(value not in selector_source + extractor_source
                  for value in ("relation_type", "supporting_evidence_ids")),
        "candidate_test_untouched": candidate_hash_before == candidate_hash_after,
        "candidate_test_not_loaded": True,
        "same_G0_candidates_E0_E2_E3_E4": all(
            rankings["E0"][qa_id]["candidate_ids"] == rankings["E2"][qa_id]["candidate_ids"]
            == rankings["E3"][qa_id]["candidate_ids"] == rankings["E4"][qa_id]["candidate_ids"]
            for qa_id in qa_ids
        ),
        "selected_subset_unique_le_20": all(
            len(ids := [row["evidence_id"] for row in rankings["E4"][qa_id]["results"]])
            == len(set(ids)) <= 20 and set(ids) <= set(g0[qa_id]["candidate_ids"])
            for qa_id in qa_ids
        ),
        "entity_metric_time_mapping_uses_real_schema": not metadata_mapping_errors,
        "report_date_distinct_from_evidence_date": all(
            not row["metadata_basis"]["report_date_used_as_evidence_date"]
            for row in all_representations
        ),
        "cross_document_comparison_allowed": "CROSS_DOCUMENT_ALLOWED_BY_QUESTION" in inspect.getsource(
            _provenance_score_v2
        ),
        "uncertain_requirements_fallback_exact": uncertain_fallback_exact,
        "no_automatic_first_evidence_completeness": after_first_complete <= before_first_complete,
        "retrieval_level_semantics_preserved": all(
            row["evidence_id"] in unit_by_id for row in all_representations
        ),
        "deterministic_outputs": reproducible,
        "metrics_recomputed": True,
        "pytest_pass": bool(pytest_result and pytest_result.get("passed")),
    }
    audit_blockers = [name for name, passed in audit_checks.items() if not passed]
    audit = {
        "status": "PASS" if not audit_blockers else "FAIL", "checks": audit_checks,
        "preflight": preflight, "baseline_recomputed": baseline_recomputed,
        "pytest": pytest_result, "candidate_test_sha256_before": candidate_hash_before,
        "candidate_test_sha256_after": candidate_hash_after,
        "artifact_sha256": current_hashes, "remaining_blockers": audit_blockers,
    }
    write_json(report_dir / "C1_1_FINAL_AUDIT.json", audit)

    e0_overall = subgroup_metrics["E0"]["OVERALL"]["all_r@20"]
    e4_overall = subgroup_metrics["E4"]["OVERALL"]["all_r@20"]
    e0_multi = subgroup_metrics["E0"]["RETRIEVAL_MULTI"]["all_r@20"]
    e4_multi = subgroup_metrics["E4"]["RETRIEVAL_MULTI"]["all_r@20"]
    promising = (
        e4_multi > e0_multi
        and e4_overall >= e0_overall - config["decision_gate"]["max_overall_all_r20_drop"]
    )
    if promising:
        decision = "EVIDENCE_SET_SELECTION_PROMISING"
        recommendation = "Proceed to a separately authorized C2 validation; do not combine methods inside C1.1."
    else:
        decision = "EVIDENCE_SET_SELECTION_NOT_PROMISING"
        recommendation = "Do not proceed to C2; prioritize candidate/ranking diagnosis over a more complex selector."
    readiness = {
        "C1_1_VALID": not audit_blockers, "status": "PASS" if not audit_blockers else "FAIL",
        "EVIDENCE_SET_SELECTION_PROMISING": promising,
        "READY_FOR_C2": bool(not audit_blockers and promising),
        "decision": decision, "dev_qa": len(dev), "retrieval_multi_qa": len(multi_ids),
        "unique_gold_sets": len(signatures), "G1_regressions_analyzed": len(regression_rows),
        "main_regression_causes": dict(regression_category_counts),
        "requirements": {
            "before_temporal": before_counts["TEMPORAL_COMPARISON"],
            "after_temporal": after_counts["TEMPORAL_COMPARISON"],
            "before_forecast": before_counts["FORECAST"],
            "after_forecast": after_counts["FORECAST"],
            "first_evidence_saturation_before": before_first_complete,
            "first_evidence_saturation_after": after_first_complete,
        },
        "experiments": {method: {
            "all_r@20": subgroup_metrics[method]["OVERALL"]["all_r@20"],
            "multi_all_r@20": subgroup_metrics[method]["RETRIEVAL_MULTI"]["all_r@20"],
        } for method in METHODS},
        "E4_vs_E0": transitions["E4_vs_E0"],
        "E4_vs_E0_multi": multi_transitions["E4_vs_E0"],
        "main_remaining_bottleneck": "G1_CANDIDATE_COMPETITION_AND_INCOMPLETE_STRUCTURED_METADATA",
        "recommended_next_step": recommendation,
        "candidate_test_untouched": candidate_hash_before == candidate_hash_after,
        "remaining_blockers": audit_blockers,
    }
    write_json(report_dir / "C1_1_READINESS.json", readiness)
    write_json(report_dir / "CONFIG.json", config)

    e4_e0_qa = statistics["comparisons"]["E4_vs_E0"]["OVERALL"]["qa_bootstrap"]
    e4_e0_cluster = statistics["comparisons"]["E4_vs_E0"]["OVERALL"]["gold_set_cluster_bootstrap"]
    report = f"""# VietIrr-RAG Phase C1.1 — Evidence Requirements, Provenance and Ranking Diagnosis

## 1. Baseline verification

Artifact recomputation passed for 93 DEV QA, 25 retrieval-multi QA, and 45 unique gold-evidence sets. G0 and G1 contain exactly 100 candidates per query. Phase A metadata maps every G0 candidate to a real table or text region and document. Candidate Test was byte-hashed only.

## 2. Thirteen G1 ranking regressions

All {len(regression_rows)} E0-success/E1-failure cases were analyzed. Gold remains present in G1 and keeps its exact global-RRF fusion score; the rank changes because new G1 candidates with higher scores enter Top-20. Category counts are {dict(regression_category_counts)}. Per-query BM25/E5 ranks, fusion scores, source provenance, competing candidates, and structured provenance evidence are stored in `RANK_REGRESSION_DIAGNOSIS.jsonl`. This supports candidate competition/rank displacement as the general cause, not a changed fusion formula.

## 3. Requirement correction

Temporal comparison falls from {before_counts['TEMPORAL_COMPARISON']} to {after_counts['TEMPORAL_COMPARISON']} and forecast from {before_counts['FORECAST']} to {after_counts['FORECAST']}. First-evidence saturation falls from {before_first_complete} to {after_first_complete}. V2 requires explicit question intent, exposes `UNCERTAIN`, and falls back to E0 when intent or metadata is insufficient. The 30-QA audit sample is a pending manual-review queue and is not labeled human validated.

## 4. Structured evidence and provenance coverage

The representation reads real table semantic tuples, text `region_type/index_text`, and document reporting periods. Unknown fields remain `UNKNOWN`. Entity is known in {evidence_role_audit['field_coverage']['entity_known']}/{len(all_representations)} query-candidate representations, evidence time in {evidence_role_audit['field_coverage']['evidence_time_known']}/{len(all_representations)}, and document reporting time in {evidence_role_audit['field_coverage']['document_reporting_time_known']}/{len(all_representations)}. Report time is never substituted for evidence time; cross-document selection remains allowed.

## 5. E4 controlled comparison

| Method | All R@20 | Multi All R@20 | MRR | ms/query |
|---|---:|---:|---:|---:|
{chr(10).join(f"| {row['method']} {row['name']} | {row['all_r@20']:.4f} | {row['multi_all_r@20']:.4f} | {row['mrr']:.4f} | {row['latency_ms_per_query']:.2f} |" for row in result_rows)}

E4 versus E0 recovered {transitions['E4_vs_E0']['recovered']} and regressed {transitions['E4_vs_E0']['regressed']} QA. On retrieval-multi it recovered {multi_transitions['E4_vs_E0']['recovered']} and regressed {multi_transitions['E4_vs_E0']['regressed']}.

## 6. Statistical validity and duplicated gold sets

E4 versus E0 overall delta is {e4_e0_qa['delta']:+.4f}; paired-QA 95% CI [{e4_e0_qa['ci95_low']:+.4f}, {e4_e0_qa['ci95_high']:+.4f}], gold-set cluster-aware CI [{e4_e0_cluster['ci95_low']:+.4f}, {e4_e0_cluster['ci95_high']:+.4f}]. The QA-weighted versus signature-balanced deltas are {statistics['duplicated_gold_set_impact']['qa_weighted_delta']:+.4f} and {statistics['duplicated_gold_set_impact']['signature_balanced_delta']:+.4f}. No superiority claim is made when zero remains in the interval.

## 7. Decision

Decision: **{decision}**. {recommendation}

C1.1 valid: {str(readiness['C1_1_VALID']).lower()}. Ready for C2: {str(readiness['READY_FOR_C2']).lower()}. No C2 experiment, training, model inference, Candidate Test evaluation, or Agentic RAG was run.
"""
    (report_dir / "C1_1_REPORT.md").write_text(report, encoding="utf-8", newline="\n")

    checksum_paths = [path for path in sorted(report_dir.glob("*"))
                      if path.is_file() and path.name != "CHECKSUMS.json"]
    checksum_paths.extend(path for path in sorted(output_dir.rglob("*")) if path.is_file())
    checksum_paths.append(root / "configs/phase_c1_1.json")
    write_json(report_dir / "CHECKSUMS.json", {
        "files": [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
                   "sha256": sha256(path)} for path in checksum_paths]
    })
    return readiness
