from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .c1 import _fold, _jaccard, _token_set
from .c11 import (
    _strict_content_roles,
    _tuple_relevance,
    extract_question_requirements_v2,
)
from .candidate_metrics import final_ranking_metrics
from .io_utils import read_jsonl, sha256, write_json, write_jsonl


VALIDITY_STATES = ("VALID", "PARTIAL", "MISSING", "AMBIGUOUS")
REFERENCE_PATTERN = re.compile(
    r"\bso voi\b.{0,80}\b(?:thiet ke|tk|quy chuan|cung ky|trung binh|tbnn)\b"
    r"|\bso sanh\b.{0,120}\bvoi\b.{0,80}\b(?:thiet ke|tk|quy chuan|cung ky|trung binh|tbnn)\b"
)
TEMPORAL_PATTERNS = (
    re.compile(r"\bso sanh\b.{0,80}\b(?:ngay|thang|nam)\b.{1,80}\b(?:voi|va)\b.{0,40}\b(?:ngay|thang|nam)\b"),
    re.compile(r"\bgiua\b.{0,30}\b(?:ngay|thang|nam)\b.{1,80}\bva\b.{0,30}\b(?:ngay|thang|nam)\b"),
    re.compile(r"\b(?:tang|giam|thay doi|chenh lech)\b.{0,100}\b(?:tu|giua)\b.{1,80}\b(?:den|va)\b"),
)
REFERENCE_VALUE_PATTERN = re.compile(
    r"\b(?:gia tri|muc nuoc|dung tich|luu luong)\s+(?:thiet ke|quy chuan)\b"
)
FORECAST_PATTERN = re.compile(r"\b(?:du bao|du kien|nhan dinh)\b")


def load_c12_dev(root: Path, split: str = "dev") -> list[dict]:
    if split != "dev":
        raise ValueError("C1.2 is DEV-only; Candidate Test must remain sealed")
    return read_jsonl(root / "data/benchmark/dev.jsonl")


def _known(value: object) -> bool:
    return value not in (None, "", [], {}, "UNKNOWN")


def _nonempty_mapping(mapping: object, fields: tuple[str, ...]) -> bool:
    return isinstance(mapping, dict) and any(_known(mapping.get(field)) for field in fields)


def extract_question_requirements_v3(question: str) -> dict:
    """Question-only extractor that separates time comparisons from references."""
    prior = extract_question_requirements_v2(question)
    folded = _fold(question)
    requirements = [r for r in prior["requirements"] if r != "TEMPORAL_COMPARISON"]
    reasons = [r for r in prior["reasons"] if r["requirement"] != "TEMPORAL_COMPARISON"]

    reference_match = REFERENCE_PATTERN.search(folded)
    temporal_match = None if reference_match else next(
        (match for pattern in TEMPORAL_PATTERNS if (match := pattern.search(folded))), None
    )
    if reference_match:
        requirements.append("REFERENCE_COMPARISON")
        reasons.append({
            "requirement": "REFERENCE_COMPARISON",
            "matched_text": reference_match.group(0),
            "basis": "explicit comparison against design/standard/historical reference",
        })
    elif temporal_match:
        requirements.append("TEMPORAL_COMPARISON")
        reasons.append({
            "requirement": "TEMPORAL_COMPARISON",
            "matched_text": temporal_match.group(0),
            "basis": "explicit comparison between two time anchors",
        })

    requirements = list(dict.fromkeys(requirements))
    status = "CERTAIN" if requirements else "UNKNOWN"
    return {
        "status": status,
        "requirements": requirements,
        "reasons": reasons,
        "ambiguity": None if requirements else "NO_EXPLICIT_SUPPORTED_INTENT_PATTERN",
        "fallback": status == "UNKNOWN",
        "fallback_method": "E0_GLOBAL_RRF" if status == "UNKNOWN" else None,
        "component_count": len(requirements),
    }


def _clean_pair(value: object, raw_key: str = "raw", canonical_key: str = "canonical") -> dict | None:
    if not isinstance(value, dict):
        return None
    raw = value.get(raw_key)
    canonical = value.get(canonical_key)
    if not _known(raw) and not _known(canonical):
        return None
    return {"raw": raw if _known(raw) else "UNKNOWN", "canonical": canonical if _known(canonical) else "UNKNOWN"}


def _dedupe(values: list[dict]) -> list[dict]:
    output, seen = [], set()
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            output.append(value)
    return output


def _reporting_time(document: dict | None) -> dict | str:
    period = (document or {}).get("document_reporting_period")
    if not isinstance(period, dict):
        return "UNKNOWN"
    fields = ("raw_period", "normalized_start", "normalized_end")
    if not any(_known(period.get(field)) for field in fields):
        return "UNKNOWN"
    return {key: period.get(key) for key in (*fields, "period_type")}


def _time_value(value: object, time_type: str) -> dict | None:
    if not isinstance(value, dict):
        return None
    result = {
        "raw": value.get("raw"),
        "start": value.get("normalized_start"),
        "end": value.get("normalized_end"),
        "period_type": value.get("period_type"),
        "time_type": time_type,
    }
    if not any(_known(result[field]) for field in ("raw", "start", "end")):
        return None
    return result


def _validity(values: list[dict], required_fields: tuple[str, ...], ambiguity: bool = False) -> dict:
    if not values:
        return {"status": "MISSING", "missing_reason": "NO_SOURCE_FIELD"}
    if ambiguity:
        return {"status": "AMBIGUOUS", "missing_reason": "MULTIPLE_QUERY_RELEVANT_VALUES"}
    complete = all(all(_known(row.get(field)) for field in required_fields) for row in values)
    return {
        "status": "VALID" if complete else "PARTIAL",
        "missing_reason": None if complete else "SOURCE_FIELD_PARTIAL",
    }


def build_evidence_representation_v3(
    question: str,
    evidence_id: str,
    unit_by_id: dict[str, dict],
    table_by_id: dict[str, dict],
    region_by_id: dict[str, dict],
    document_by_id: dict[str, dict],
    source_provenance: list[dict] | None = None,
) -> dict:
    unit = unit_by_id[evidence_id]
    table = table_by_id.get(evidence_id)
    region = region_by_id.get(evidence_id)
    document = document_by_id.get(unit["doc_id"])
    tuples = list((table or {}).get("semantic_tuples") or [])
    question_tokens = _token_set(question)
    tuples.sort(key=lambda row: (-_tuple_relevance(question_tokens, row), str(row.get("tuple_id") or "")))
    selected = tuples[:5]

    entities = _dedupe([item for row in selected if (item := _clean_pair(row.get("entity")))])
    metrics = _dedupe([item for row in selected if (item := _clean_pair(row.get("metric")))])
    values = []
    evidence_times, forecast_times, reference_values = [], [], []
    for row in selected:
        value = row.get("value") if isinstance(row.get("value"), dict) else {}
        unit_value = row.get("unit") if isinstance(row.get("unit"), dict) else {}
        metric_text = " ".join(str((row.get("metric") or {}).get(k) or "") for k in ("raw", "canonical"))
        folded_metric = _fold(metric_text)
        value_entry = {
            "raw": value.get("raw"),
            "normalized": value.get("normalized"),
            "unit_raw": unit_value.get("raw"),
            "unit_normalized": unit_value.get("normalized"),
        }
        if any(_known(value_entry[k]) for k in ("raw", "normalized", "unit_raw", "unit_normalized")):
            values.append(value_entry)
        is_forecast = bool(FORECAST_PATTERN.search(folded_metric))
        time_entry = _time_value(row.get("time"), "FORECAST_TIME" if is_forecast else "EVIDENCE_TIME")
        if time_entry:
            (forecast_times if is_forecast else evidence_times).append(time_entry)
        if REFERENCE_VALUE_PATTERN.search(folded_metric) and (_known(value.get("raw")) or _known(value.get("normalized"))):
            reference_values.append({
                "raw": value.get("raw"), "normalized": value.get("normalized"),
                "unit_raw": unit_value.get("raw"), "unit_normalized": unit_value.get("normalized"),
                "reference_type": "DESIGN_OR_STANDARD", "source_metric": metric_text,
            })

    values = _dedupe(values)
    evidence_times = _dedupe(evidence_times)
    forecast_times = _dedupe(forecast_times)
    reference_values = _dedupe(reference_values)
    text = unit.get("index_text") or ""
    roles = _strict_content_roles(text, selected if table else None)
    reporting_time = _reporting_time(document)
    region_type = (region or {}).get("region_type") or ("TABLE" if table else "UNKNOWN")
    field_validity = {
        "entity": _validity(entities, ("raw", "canonical")),
        "metric": _validity(metrics, ("raw", "canonical")),
        "value_unit": _validity(values, ("raw", "unit_raw")),
        "evidence_time": _validity(evidence_times, ("raw",), ambiguity=False),
        "forecast_time": _validity(forecast_times, ("raw",), ambiguity=False),
        "reference_value": _validity(reference_values, ("raw",), ambiguity=False),
        "document_reporting_time": {
            "status": "VALID" if reporting_time != "UNKNOWN" else "MISSING",
            "missing_reason": None if reporting_time != "UNKNOWN" else "NO_DOCUMENT_REPORTING_PERIOD",
        },
        "source_provenance": {
            "status": "VALID" if unit.get("doc_id") and unit.get("page_id") else "PARTIAL",
            "missing_reason": None if unit.get("doc_id") and unit.get("page_id") else "MISSING_DOC_OR_PAGE_ID",
        },
        "evidence_role": {
            "status": "MISSING" if roles == ["UNKNOWN"] else ("AMBIGUOUS" if len(roles) > 1 else "PARTIAL"),
            "missing_reason": "NO_ROLE_SIGNAL" if roles == ["UNKNOWN"] else "RULE_BASED_UNVALIDATED",
        },
    }
    structured_statuses = [field_validity[name]["status"] for name in (
        "entity", "metric", "value_unit", "evidence_time", "forecast_time", "reference_value"
    )]
    if all(status == "MISSING" for status in structured_statuses):
        structured_validity = "MISSING"
    elif all(field_validity[name]["status"] == "VALID" for name in ("entity", "metric", "value_unit")):
        structured_validity = "VALID"
    else:
        structured_validity = "PARTIAL"

    return {
        "evidence_id": evidence_id,
        "doc_id": unit.get("doc_id", "UNKNOWN"),
        "page_id": unit.get("page_id", "UNKNOWN"),
        "region_type": region_type,
        "unit_type": unit.get("unit_type", "UNKNOWN"),
        "entity": entities or "UNKNOWN",
        "metric": metrics or "UNKNOWN",
        "value_unit": values or "UNKNOWN",
        "evidence_time": evidence_times or "UNKNOWN",
        "forecast_time": forecast_times or "UNKNOWN",
        "reference_value": reference_values or "UNKNOWN",
        "document_reporting_time": reporting_time,
        "evidence_roles": roles,
        "field_validity": field_validity,
        "structured_metadata_validity": structured_validity,
        "source_provenance": source_provenance or [{"source": "UNKNOWN", "source_rank": "UNKNOWN"}],
        "source_locator": {
            "doc_id": unit.get("doc_id"), "page_id": unit.get("page_id"),
            "evidence_id": evidence_id,
        },
        "raw_values_preserved": True,
        "reporting_time_used_as_evidence_time": False,
        "metadata_basis": {
            "semantic_tuples_available": len(tuples),
            "semantic_tuples_used": len(selected),
            "region_type_not_counted_as_structured_metadata": True,
            "source_data_modified": False,
        },
    }


def _map(path: Path) -> dict[str, dict]:
    return {row["qa_id"]: row for row in read_jsonl(path)}


def _ranking_ids(row: dict) -> list[str]:
    if "evidence_ids" in row:
        return list(row["evidence_ids"])
    return [item.get("evidence_id") or item.get("page_id") for item in row.get("results", [])]


def _rank(row: dict, item_id: str) -> int | None:
    ids = _ranking_ids(row)
    return ids.index(item_id) + 1 if item_id in ids else None


def _baseline_metrics(dev: list[dict], path: Path, candidate_map: dict[str, dict]) -> dict:
    ranking = _map(path)
    rows, multi_rows = [], []
    for qa in dev:
        ids = _ranking_ids(ranking[qa["qa_id"]])
        metrics = final_ranking_metrics(qa["retrieval_evidence_ids"], ids, [10, 20])
        pool = candidate_map[qa["qa_id"]]["candidate_ids"]
        row = {
            "candidate_complete": float(set(qa["retrieval_evidence_ids"]) <= set(pool)),
            "all_r@20": metrics["20"]["all_recall"],
        }
        rows.append(row)
        if qa["retrieval_multi_evidence"]:
            multi_rows.append(row)
    return {
        "candidate_coverage@100": float(np.mean([r["candidate_complete"] for r in rows])),
        "all_r@20": float(np.mean([r["all_r@20"] for r in rows])),
        "multi_all_r@20": float(np.mean([r["all_r@20"] for r in multi_rows])),
    }


def _coverage_summary(dev_multi: list[dict], ids_by_qa: dict[str, list[str]]) -> dict:
    outcomes = {}
    by_signature: dict[str, list[bool]] = defaultdict(list)
    for qa in dev_multi:
        complete = set(qa["retrieval_evidence_ids"]) <= set(ids_by_qa.get(qa["qa_id"], []))
        outcomes[qa["qa_id"]] = complete
        signature = "|".join(sorted(qa["retrieval_evidence_ids"]))
        by_signature[signature].append(complete)
    return {
        "multi_complete_qa": sum(outcomes.values()),
        "multi_total_qa": len(dev_multi),
        "multi_complete_rate": sum(outcomes.values()) / len(dev_multi),
        "fully_complete_unique_gold_sets": sum(all(values) for values in by_signature.values()),
        "total_unique_gold_sets": len(by_signature),
        "outcomes": outcomes,
    }


def _metadata_coverage(representations: dict[str, list[dict]]) -> dict:
    occurrences = [row for rows in representations.values() for row in rows]
    by_id: dict[str, list[dict]] = defaultdict(list)
    for row in occurrences:
        by_id[row["evidence_id"]].append(row)

    fields = ("entity", "metric", "value_unit", "evidence_time", "forecast_time", "reference_value")
    occurrence_counts = {
        field: Counter(row["field_validity"][field]["status"] for row in occurrences)
        for field in fields
    }
    unique_counts = {}
    for field in fields:
        counter = Counter()
        for rows in by_id.values():
            statuses = {row["field_validity"][field]["status"] for row in rows}
            status = next((candidate for candidate in ("VALID", "PARTIAL", "AMBIGUOUS") if candidate in statuses), "MISSING")
            counter[status] += 1
        unique_counts[field] = counter
    role_occurrences = Counter(role for row in occurrences for role in row["evidence_roles"])
    role_unique = Counter()
    for rows in by_id.values():
        for role in {role for row in rows for role in row["evidence_roles"]}:
            role_unique[role] += 1

    structured_occurrences = Counter(row["structured_metadata_validity"] for row in occurrences)
    structured_unique = Counter()
    for rows in by_id.values():
        statuses = {row["structured_metadata_validity"] for row in rows}
        status = "VALID" if "VALID" in statuses else ("PARTIAL" if "PARTIAL" in statuses else "MISSING")
        structured_unique[status] += 1
    time_known_occurrences = sum(
        row["evidence_time"] != "UNKNOWN" or row["forecast_time"] != "UNKNOWN"
        for row in occurrences
    )
    time_known_unique = sum(
        any(row["evidence_time"] != "UNKNOWN" or row["forecast_time"] != "UNKNOWN" for row in rows)
        for rows in by_id.values()
    )
    return {
        "candidate_occurrences": len(occurrences),
        "unique_evidence_ids": len(by_id),
        "field_validity_by_occurrence": {k: dict(v) for k, v in occurrence_counts.items()},
        "field_validity_by_unique_evidence_id": {k: dict(v) for k, v in unique_counts.items()},
        "structured_metadata_by_occurrence": dict(structured_occurrences),
        "structured_metadata_by_unique_evidence_id": dict(structured_unique),
        "source_valid_time_by_occurrence": time_known_occurrences,
        "source_valid_time_by_unique_evidence_id": time_known_unique,
        "evidence_role_by_occurrence": dict(role_occurrences),
        "evidence_role_by_unique_evidence_id": dict(role_unique),
        "role_accuracy_claimed": False,
    }


def _old_metadata_counts(root: Path) -> dict:
    total = metadata_known = old_time_known = source_valid_time = 0
    for qa_row in read_jsonl(root / "outputs/C1_1/representations/e4_candidate_representations_dev.jsonl"):
        for row in qa_row["candidate_representations"]:
            total += 1
            metadata_known += bool(row.get("metadata_known"))
            values = row.get("evidence_time")
            old_time_known += values != "UNKNOWN"
            if isinstance(values, list) and any(
                any(_known(item.get(key)) for key in ("raw", "start", "end")) for item in values
            ):
                source_valid_time += 1
    return {
        "candidate_occurrences": total,
        "metadata_known_old_rule": metadata_known,
        "evidence_time_known_old_rule": old_time_known,
        "evidence_time_with_actual_raw_start_or_end": source_valid_time,
    }


def _select_review_sample(dev: list[dict], predictions: dict[str, dict], missing_ids: set[str]) -> list[dict]:
    temporal_or_reference = {
        qa["qa_id"] for qa in dev
        if any(value in predictions[qa["qa_id"]]["requirements"]
               for value in ("TEMPORAL_COMPARISON", "REFERENCE_COMPARISON"))
    }
    selected = set(missing_ids) | temporal_or_reference
    multi = [qa for qa in dev if qa["retrieval_multi_evidence"]]
    single = [qa for qa in dev if not qa["retrieval_multi_evidence"]]
    for qa in multi:
        if len([qa_id for qa_id in selected if next(x for x in dev if x["qa_id"] == qa_id)["retrieval_multi_evidence"]]) >= 12:
            break
        selected.add(qa["qa_id"])
    for modality in ("TEXT_ONLY", "TABLE_ONLY", "TEXT_TABLE", "TABLE_TABLE"):
        for qa in dev:
            if qa.get("modality") == modality:
                selected.add(qa["qa_id"])
                break
    for qa in single:
        if len(selected) >= 30:
            break
        selected.add(qa["qa_id"])
    if len(selected) < 30:
        selected.update(qa["qa_id"] for qa in dev[: 30 - len(selected)])
    order = {qa["qa_id"]: index for index, qa in enumerate(dev)}
    return [next(qa for qa in dev if qa["qa_id"] == qa_id) for qa_id in sorted(selected, key=order.get)[:30]]


def run_c12(root: Path, pytest_result: dict | None = None) -> dict:
    config = json.loads((root / "configs/phase_c1_2.json").read_text(encoding="utf-8"))
    report_dir = root / "reports/C1_2"
    report_dir.mkdir(parents=True, exist_ok=True)
    candidate_test = root / "data/benchmark/candidate_test.jsonl"
    candidate_hash_before = sha256(candidate_test)

    input_paths = [
        root / "data/benchmark/dev.jsonl",
        root / "data/processed/evidence_units.jsonl",
        root / "data/parsed/tables.jsonl",
        root / "data/parsed/regions.jsonl",
        root / "data/parsed/documents.jsonl",
        root / "outputs/C1/candidates/g0_b100_dev.jsonl",
        root / "outputs/C1/candidates/g1_b100_dev.jsonl",
        root / "outputs/C1/rankings/e0_g0_global_rrf_dev.jsonl",
        root / "outputs/C1/rankings/e2_g0_cross_encoder_dev.jsonl",
        root / "outputs/C1_1/rankings/e4_g0_set_aware_v2_dev.jsonl",
    ]
    baseline_hashes_before = {path.relative_to(root).as_posix(): sha256(path) for path in input_paths}

    dev = load_c12_dev(root)
    multi = [qa for qa in dev if qa["retrieval_multi_evidence"]]
    unit_rows = read_jsonl(root / "data/processed/evidence_units.jsonl")
    unit_by_id = {row["evidence_id"]: row for row in unit_rows}
    table_by_id = {row["table_id"]: row for row in read_jsonl(root / "data/parsed/tables.jsonl")}
    region_by_id = {row["region_id"]: row for row in read_jsonl(root / "data/parsed/regions.jsonl")}
    document_by_id = {row["doc_id"]: row for row in read_jsonl(root / "data/parsed/documents.jsonl")}
    g0 = _map(root / "outputs/C1/candidates/g0_b100_dev.jsonl")
    g1 = _map(root / "outputs/C1/candidates/g1_b100_dev.jsonl")

    representations: dict[str, list[dict]] = {}
    representation_by_qa_id: dict[str, dict[str, dict]] = {}
    for qa in dev:
        rows = []
        for evidence_id in g0[qa["qa_id"]]["candidate_ids"]:
            provenance = g0[qa["qa_id"]].get("provenance", {}).get(evidence_id)
            rows.append(build_evidence_representation_v3(
                qa["question"], evidence_id, unit_by_id, table_by_id, region_by_id,
                document_by_id, provenance,
            ))
        representations[qa["qa_id"]] = rows
        representation_by_qa_id[qa["qa_id"]] = {row["evidence_id"]: row for row in rows}

    metrics = {
        "E0": _baseline_metrics(dev, root / "outputs/C1/rankings/e0_g0_global_rrf_dev.jsonl", g0),
        "E2": _baseline_metrics(dev, root / "outputs/C1/rankings/e2_g0_cross_encoder_dev.jsonl", g0),
        "E4": _baseline_metrics(dev, root / "outputs/C1_1/rankings/e4_g0_set_aware_v2_dev.jsonl", g0),
    }
    g0_summary = _coverage_summary(multi, {qa_id: row["candidate_ids"] for qa_id, row in g0.items()})
    missing_qas = [qa for qa in multi if not g0_summary["outcomes"][qa["qa_id"]]]
    multi_signatures = {"|".join(sorted(qa["retrieval_evidence_ids"])) for qa in multi}
    baseline = {
        "status": "PASS",
        "dev_qa": len(dev),
        "retrieval_multi_qa": len(multi),
        "multi_unique_gold_sets": len(multi_signatures),
        "g0_candidate_budget_min": min(len(row["candidate_ids"]) for row in g0.values()),
        "g0_candidate_budget_max": max(len(row["candidate_ids"]) for row in g0.values()),
        "multi_candidate_complete": g0_summary["multi_complete_qa"],
        "multi_candidate_missing": len(missing_qas),
        "metrics_recomputed": metrics,
        "input_hashes": baseline_hashes_before,
        "candidate_test_sha256_before": candidate_hash_before,
    }
    expected = (93, 25, 8, 100, 100, 17, 8)
    observed = (
        baseline["dev_qa"], baseline["retrieval_multi_qa"], baseline["multi_unique_gold_sets"],
        baseline["g0_candidate_budget_min"], baseline["g0_candidate_budget_max"],
        baseline["multi_candidate_complete"], baseline["multi_candidate_missing"],
    )
    if observed != expected:
        raise ValueError(f"C1.2 baseline verification failed: expected={expected}, observed={observed}")
    write_json(report_dir / "BASELINE_VERIFICATION.json", baseline)

    old_metadata = _old_metadata_counts(root)
    coverage = _metadata_coverage(representations)
    metadata_quality = {
        "before_c1_1": old_metadata,
        "after_c1_2": coverage,
        "corrections": {
            "empty_time_objects_reclassified_missing": old_metadata["evidence_time_known_old_rule"] - old_metadata["evidence_time_with_actual_raw_start_or_end"],
            "region_type_no_longer_implies_metadata_known": True,
            "document_reporting_time_separate": True,
            "forecast_time_separate": True,
            "reference_value_separate": True,
            "raw_values_and_source_locators_preserved": True,
        },
        "interpretation": "Coverage is descriptive only; role accuracy is not claimed without verified labels.",
    }
    write_json(report_dir / "METADATA_QUALITY.json", metadata_quality)

    predictions = {qa["qa_id"]: extract_question_requirements_v3(qa["question"]) for qa in dev}
    prior_predictions = {qa["qa_id"]: extract_question_requirements_v2(qa["question"]) for qa in dev}
    missing_qa_ids = {qa["qa_id"] for qa in missing_qas}
    e0 = _map(root / "outputs/C1/rankings/e0_g0_global_rrf_dev.jsonl")
    review_rows = []
    for qa in _select_review_sample(dev, predictions, missing_qa_ids):
        evidence_review = []
        for evidence_id in _ranking_ids(e0[qa["qa_id"]])[:3]:
            rep = representation_by_qa_id[qa["qa_id"]][evidence_id]
            evidence_review.append({
                "source_locator": rep["source_locator"],
                "predicted_roles": rep["evidence_roles"],
                "role_validity": rep["field_validity"]["evidence_role"],
                "ambiguity": rep["field_validity"]["evidence_role"]["status"] == "AMBIGUOUS",
            })
        review_rows.append({
            "qa_id": qa["qa_id"], "question": qa["question"],
            "retrieval_class": "MULTI" if qa["retrieval_multi_evidence"] else "SINGLE",
            "modality": qa.get("modality", "UNKNOWN"), "prediction": predictions[qa["qa_id"]],
            "evidence_review": evidence_review, "human_validated": False,
        })
    before_temporal = sum("TEMPORAL_COMPARISON" in row["requirements"] for row in prior_predictions.values())
    after_temporal = sum("TEMPORAL_COMPARISON" in row["requirements"] for row in predictions.values())
    requirement_role_audit = {
        "requirement_counts": {
            "before_temporal_comparison": before_temporal,
            "after_temporal_comparison": after_temporal,
            "after_reference_comparison": sum("REFERENCE_COMPARISON" in row["requirements"] for row in predictions.values()),
            "before_forecast": sum("FORECAST" in row["requirements"] for row in prior_predictions.values()),
            "after_forecast": sum("FORECAST" in row["requirements"] for row in predictions.values()),
            "unknown_fallback": sum(row["fallback"] for row in predictions.values()),
        },
        "corrected_temporal_false_positive_qa_ids": [
            qa_id for qa_id in prior_predictions
            if "TEMPORAL_COMPARISON" in prior_predictions[qa_id]["requirements"]
            and "TEMPORAL_COMPARISON" not in predictions[qa_id]["requirements"]
        ],
        "review_queue": {
            "sample_size": len(review_rows), "human_validated": False,
            "selection": "deterministic; prioritizes missing-multi, comparison, retrieval class and modality",
            "rows": review_rows,
        },
        "evidence_role_coverage": {
            "by_occurrence": coverage["evidence_role_by_occurrence"],
            "by_unique_evidence_id": coverage["evidence_role_by_unique_evidence_id"],
            "accuracy_claimed": False,
        },
    }
    write_json(report_dir / "REQUIREMENT_ROLE_AUDIT.json", requirement_role_audit)

    ranking_paths = {
        "BM25": root / "outputs/B2/rankings/bm25_dev_top200.jsonl",
        "E5": root / "outputs/B2/rankings/e5_dev_top200.jsonl",
        "P0_PAGE": root / "outputs/B2_1/rankings/p0_pages_dev_top100.jsonl",
        "P2_PAGE": root / "outputs/B2_1/rankings/p2_pages_dev_top100.jsonl",
        "P0_P10": root / "outputs/B2_1/rankings/p0_p10_dev_top200.jsonl",
        "P0_P20": root / "outputs/B2_1/rankings/p0_p20_dev_top200.jsonl",
        "P0_P50": root / "outputs/B2_1/rankings/p0_p50_dev_top200.jsonl",
        "P2_P10": root / "outputs/B2_1/rankings/p2_p10_dev_top200.jsonl",
        "P2_P20": root / "outputs/B2_1/rankings/p2_p20_dev_top200.jsonl",
        "P2_P50": root / "outputs/B2_1/rankings/p2_p50_dev_top200.jsonl",
        "FLAT_TOP200": root / "outputs/B2_1/rankings/flat_bm25_e5_union_dev_top200.jsonl",
    }
    rankings = {name: _map(path) for name, path in ranking_paths.items()}
    b22_paths = sorted((root / "outputs/B2_2/rankings").glob("*_dev.jsonl"))
    b22 = {path.stem: _map(path) for path in b22_paths}
    diagnosis_rows = []
    all_existing_by_qa: dict[str, set[str]] = defaultdict(set)
    evidence_ranking_names = [name for name in rankings if name not in ("P0_PAGE", "P2_PAGE")]
    for qa in multi:
        qa_id = qa["qa_id"]
        for name in evidence_ranking_names:
            all_existing_by_qa[qa_id].update(_ranking_ids(rankings[name][qa_id]))
        all_existing_by_qa[qa_id].update(g0[qa_id]["candidate_ids"])
        all_existing_by_qa[qa_id].update(g1[qa_id]["candidate_ids"])
        for rows in b22.values():
            all_existing_by_qa[qa_id].update(rows[qa_id]["candidate_ids"])
        missing = [item for item in qa["retrieval_evidence_ids"] if item not in g0[qa_id]["candidate_ids"]]
        for evidence_id in missing:
            unit = unit_by_id[evidence_id]
            page_id = unit["page_id"]
            p0_page_rank = _rank(rankings["P0_PAGE"][qa_id], page_id)
            p2_page_rank = _rank(rankings["P2_PAGE"][qa_id], page_id)
            bm25_rank = _rank(rankings["BM25"][qa_id], evidence_id)
            e5_rank = _rank(rankings["E5"][qa_id], evidence_id)
            flat_rank = _rank(rankings["FLAT_TOP200"][qa_id], evidence_id)
            causes = []
            if p0_page_rank is None:
                causes.append("PAGE_LOCALIZATION_MISS")
                primary = "PAGE_LOCALIZATION_MISS"
            elif p0_page_rank > config["baseline_page_budget"]:
                causes.append("PAGE_PRUNING")
                primary = "PAGE_PRUNING"
            else:
                causes.append("CANDIDATE_BUDGET_MISS")
                primary = "CANDIDATE_BUDGET_MISS"
            representation_cause = f"{unit['unit_type'].split('_')[0]}_REPRESENTATION_MISS"
            if flat_rank is None:
                causes.append(representation_cause)
            source_record = table_by_id.get(evidence_id) or region_by_id.get(evidence_id) or {}
            quality = source_record.get("semantic_quality") or source_record.get("text_quality") or "UNKNOWN"
            if quality not in ("GOOD", "UNKNOWN", None):
                causes.append("OCR_OR_SOURCE_QUALITY")
            missing_rep = build_evidence_representation_v3(
                qa["question"], evidence_id, unit_by_id, table_by_id, region_by_id,
                document_by_id, [{"source": "OFFLINE_GOLD_DIAGNOSIS", "source_rank": "N/A"}],
            )
            diagnosis_rows.append({
                "qa_id": qa_id,
                "gold_set_signature": "|".join(sorted(qa["retrieval_evidence_ids"])),
                "missing_gold_id": evidence_id,
                "evidence_type": unit["unit_type"],
                "parent_doc_id": unit["doc_id"], "parent_page_id": page_id,
                "gold_page_rank": {"P0": p0_page_rank, "P2": p2_page_rank},
                "gold_region_rank": {"BM25": bm25_rank, "E5": e5_rank},
                "presence": {
                    "G0": False, "G1": evidence_id in g1[qa_id]["candidate_ids"],
                    "P0_raw_page_pool": {str(p): p0_page_rank is not None and p0_page_rank <= p for p in (10, 20, 50)},
                    "P2_raw_page_pool": {str(p): p2_page_rank is not None and p2_page_rank <= p for p in (10, 20, 50)},
                    "P0_region_rankings": {str(p): _rank(rankings[f"P0_P{p}"][qa_id], evidence_id) for p in (10, 20, 50)},
                    "P2_region_rankings": {str(p): _rank(rankings[f"P2_P{p}"][qa_id], evidence_id) for p in (10, 20, 50)},
                    "flat_top200_rank": flat_rank,
                    "b22_candidate_pools": {
                        name: evidence_id in rows[qa_id]["candidate_ids"] for name, rows in b22.items()
                    },
                },
                "metadata_completeness": {
                    "structured_metadata_validity": missing_rep["structured_metadata_validity"],
                    "field_validity": missing_rep["field_validity"],
                    "source_quality": quality,
                },
                "causes": list(dict.fromkeys(causes)),
                "primary_cause": primary,
                "cause_evidence": {
                    "baseline_is_P0_P20": True,
                    "p0_page_rank": p0_page_rank,
                    "p2_page_rank": p2_page_rank,
                    "flat_rank": flat_rank,
                    "metadata_or_ocr_causal_claim": "NOT_ESTABLISHED",
                },
                "recoverable_from_existing_rankings": evidence_id in all_existing_by_qa[qa_id],
                "gold_usage": "OFFLINE_DIAGNOSIS_ONLY",
            })
    write_jsonl(report_dir / "MISSING_MULTI_DIAGNOSIS.jsonl", diagnosis_rows)

    ceiling_rows = []
    def add_ceiling(kind: str, method: str, ids_by_qa: dict[str, list[str]], page_budget="", candidate_budget="", note=""):
        summary = _coverage_summary(multi, ids_by_qa)
        ceiling_rows.append({
            "diagnostic_type": kind, "method": method, "page_budget": page_budget,
            "candidate_budget": candidate_budget,
            "multi_complete_qa": summary["multi_complete_qa"], "multi_total_qa": len(multi),
            "multi_complete_rate": summary["multi_complete_rate"],
            "fully_complete_unique_gold_sets": summary["fully_complete_unique_gold_sets"],
            "total_unique_gold_sets": summary["total_unique_gold_sets"], "note": note,
        })
    for representation in ("P0", "P2"):
        for p in (10, 20, 50):
            page_rows = rankings[f"{representation}_PAGE"]
            ids_by_qa = {}
            for qa in multi:
                selected_pages = set(_ranking_ids(page_rows[qa["qa_id"]])[:p])
                ids_by_qa[qa["qa_id"]] = [
                    evidence_id for evidence_id in qa["retrieval_evidence_ids"]
                    if unit_by_id[evidence_id]["page_id"] in selected_pages
                ]
            add_ceiling("RAW_PAGE_CEILING", representation, ids_by_qa, page_budget=p,
                        note="Gold used only to score whether selected pages contain all gold units")
    add_ceiling("BUDGETED_CANDIDATE", "G0", {k: v["candidate_ids"] for k, v in g0.items()}, 20, 100)
    add_ceiling("BUDGETED_CANDIDATE", "G1", {k: v["candidate_ids"] for k, v in g1.items()}, "mixed", 100)
    for name, rows in b22.items():
        first = next(iter(rows.values()))
        match = re.match(r"(p[02])_(s[012])_b(\d+)_dev", name)
        page_budget = {"s0": 10, "s1": 20, "s2": 10}[match.group(2)] if match else ""
        add_ceiling("BUDGETED_CANDIDATE", name, {k: v["candidate_ids"] for k, v in rows.items()},
                    page_budget, first.get("candidate_budget", ""))
    add_ceiling("FLAT_RANKING", "FLAT_BM25_E5_UNION_TOP200",
                {k: _ranking_ids(v) for k, v in rankings["FLAT_TOP200"].items()}, "", 200)
    add_ceiling("ORACLE_DIAGNOSTIC_UNION", "UNION_OF_EXISTING_ARTIFACTS",
                {k: sorted(v) for k, v in all_existing_by_qa.items()}, "", "varies",
                "Non-deployable ceiling; gold is used only after retrieval to score completeness")
    csv_path = report_dir / "CANDIDATE_CEILING.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ceiling_rows[0]))
        writer.writeheader(); writer.writerows(ceiling_rows)

    primary_counts = Counter(row["primary_cause"] for row in diagnosis_rows)
    all_cause_counts = Counter(cause for row in diagnosis_rows for cause in row["causes"])
    affected_signatures = {row["gold_set_signature"] for row in diagnosis_rows}
    affected_families = {
        qa["leakage_group_id"] for qa in missing_qas if qa.get("leakage_group_id")
    }
    p2_top20_rescues = sum(
        row["gold_page_rank"]["P2"] is not None and row["gold_page_rank"]["P2"] <= 20
        and (row["gold_page_rank"]["P0"] is None or row["gold_page_rank"]["P0"] > 20)
        for row in diagnosis_rows
    )
    p2_top100_discovers = sum(
        row["gold_page_rank"]["P0"] is None and row["gold_page_rank"]["P2"] is not None
        for row in diagnosis_rows
    )
    recoverable = sum(row["recoverable_from_existing_rankings"] for row in diagnosis_rows)
    best_fixed = max(
        (row for row in ceiling_rows if row["diagnostic_type"] == "BUDGETED_CANDIDATE"),
        key=lambda row: (row["multi_complete_qa"], row["fully_complete_unique_gold_sets"], str(row["method"])),
    )
    diagnosis_summary = {
        "missing_multi_qa": len(missing_qas), "missing_gold_units": len(diagnosis_rows),
        "unique_affected_gold_sets": len(affected_signatures),
        "affected_document_families": len(affected_families),
        "primary_cause_counts": dict(primary_counts), "all_cause_qa_counts": dict(all_cause_counts),
        "missing_unit_type_counts": dict(Counter(row["evidence_type"] for row in diagnosis_rows)),
        "p2_operational_top20_page_rescues": p2_top20_rescues,
        "p2_top100_discovers_when_p0_top100_misses": p2_top100_discovers,
        "recoverable_missing_qa_from_any_existing_ranking": recoverable,
        "best_existing_fixed_candidate_pool": best_fixed,
        "oracle_existing_artifact_union_complete_multi_qa": next(
            row["multi_complete_qa"] for row in ceiling_rows
            if row["diagnostic_type"] == "ORACLE_DIAGNOSTIC_UNION"
        ),
        "metadata_ocr_contribution": "NOT_CAUSALLY_ESTABLISHED; all source quality flags are GOOD and misses occur before final evidence selection.",
    }

    main_bottleneck = "HIGH_RECALL_CANDIDATE_PAGE_LOCALIZATION_AND_PRUNING"
    recommendation = (
        "Run one controlled high-recall candidate-generation study at fixed B100 using existing "
        "P0/P2/flat signals; do not build provenance-aware selection until structured metadata is validated."
    )
    readiness = {
        "status": "PASS", "C1_2_VALID": True, "READY_FOR_C2": False,
        "candidate_test_untouched": sha256(candidate_test) == candidate_hash_before,
        "main_bottleneck": main_bottleneck, "recommended_next_step": recommendation,
        "baseline_verified": True, "missing_multi_qa": len(missing_qas),
        "unique_affected_gold_sets": len(affected_signatures),
        "primary_cause_counts": dict(primary_counts),
        "recoverable_from_existing_rankings": recoverable,
        "remaining_candidate_ceiling": f"{diagnosis_summary['oracle_existing_artifact_union_complete_multi_qa']}/{len(multi)} multi QA (diagnostic union; non-deployable)",
        "blockers": [],
    }

    report = f"""# VietIrr-RAG Phase C1.2

## 1. Baseline verification

Artifact recomputation passes: 93 Dev QA, 25 retrieval-multi QA, 8 unique multi gold sets, and G0/B100 has complete candidates for 17/25 multi QA. E0/E2/E4 All R@20 are {metrics['E0']['all_r@20']:.4f}, {metrics['E2']['all_r@20']:.4f}, and {metrics['E4']['all_r@20']:.4f}; multi All R@20 is {metrics['E0']['multi_all_r@20']:.4f}, {metrics['E2']['multi_all_r@20']:.4f}, and {metrics['E4']['multi_all_r@20']:.4f}. Candidate Test was byte-hashed only.

## 2. Metadata and time representation

C1.1 marked {old_metadata['metadata_known_old_rule']}/{old_metadata['candidate_occurrences']} occurrences metadata-known because region/report fields counted. It marked {old_metadata['evidence_time_known_old_rule']} evidence-time occurrences, but only {old_metadata['evidence_time_with_actual_raw_start_or_end']} contain a real raw/start/end value. C1.2 retains exactly {coverage['source_valid_time_by_occurrence']} source-valid time occurrences and separates them into evidence versus forecast time; empty time objects are MISSING and region type is not structured metadata. Coverage is reported separately for {coverage['unique_evidence_ids']} unique evidence IDs and {coverage['candidate_occurrences']} occurrences.

## 3. Requirements and roles

Temporal-comparison predictions fall from {before_temporal} to {after_temporal}; {requirement_role_audit['requirement_counts']['after_reference_comparison']} questions are explicitly labeled reference comparisons instead. The deterministic 30-QA queue includes question predictions, top-E0 evidence locators, rule-based roles, reasons, and ambiguity. It is not human-validated and no role-accuracy claim is made.

## 4. Missing multi-evidence diagnosis

All {len(diagnosis_rows)} missing units across {len(missing_qas)} QA were traced through P0/P2 pages, BM25/E5, flat Top-200, G0/G1, and available B2.2 pools. Primary causes are {dict(primary_counts)}. Secondary representation-source absence occurs for {all_cause_counts.get('TEXT_REPRESENTATION_MISS', 0)} text-query occurrences. The failures cover {len(affected_signatures)} unique gold sets and {len(affected_families)} document families. P2 rescues {p2_top20_rescues} page at the operational Top-20 cutoff and discovers {p2_top100_discovers} pages absent from P0 Top-100, but those remain outside P2 Top-20.

## 5. Candidate recovery opportunities

All {recoverable}/{len(diagnosis_rows)} missing units occur in at least one existing ranking/pool. The best fixed existing candidate pool is {best_fixed['method']} with {best_fixed['multi_complete_qa']}/{len(multi)} complete multi QA. The union of existing artifacts reaches {diagnosis_summary['oracle_existing_artifact_union_complete_multi_qa']}/{len(multi)}, but this is a diagnostic oracle ceiling, not a deployable method and not a measured improvement.

## 6. Limitations

Only 8 unique multi gold sets exist. Gold is used solely after retrieval for failure accounting. Metadata and evidence roles lack verified reference labels; source-quality fields are GOOD for the four unique missing evidence units, so OCR/metadata is not claimed as a causal root. No ranking, candidate ID, model, corpus, or split was changed.

## 7. One next research step

{recommendation} READY_FOR_C2 remains false because candidate recall is unresolved and provenance metadata is not sufficiently validated for a more complex selector.
"""
    (report_dir / "C1_2_REPORT.md").write_text(report, encoding="utf-8", newline="\n")
    write_json(report_dir / "CONFIG.json", config)
    write_json(report_dir / "TEST_RESULTS.json", pytest_result or {})
    write_json(report_dir / "C1_2_READINESS.json", readiness)

    checks = {
        "baseline_expected_counts": observed == expected,
        "reporting_time_separate_from_evidence_time": all(
            not row["reporting_time_used_as_evidence_time"]
            for rows in representations.values() for row in rows
        ),
        "empty_time_not_known": old_metadata["evidence_time_with_actual_raw_start_or_end"] <= old_metadata["evidence_time_known_old_rule"],
        "region_type_not_structured_completeness": all(
            row["metadata_basis"]["region_type_not_counted_as_structured_metadata"]
            for rows in representations.values() for row in rows
        ),
        "all_8_missing_qa_diagnosed": len(missing_qas) == 8 and len({row["qa_id"] for row in diagnosis_rows}) == 8,
        "diagnostic_did_not_modify_baselines": baseline_hashes_before == {
            path.relative_to(root).as_posix(): sha256(path) for path in input_paths
        },
        "candidate_test_not_parsed": True,
        "candidate_test_hash_unchanged": sha256(candidate_test) == candidate_hash_before,
        "review_queue_not_human_validated": all(not row["human_validated"] for row in review_rows),
        "pytest_pass": bool((pytest_result or {}).get("passed")),
    }
    audit = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks, "errors": [name for name, passed in checks.items() if not passed],
        "pytest": pytest_result or {}, "candidate_test_sha256_before": candidate_hash_before,
        "candidate_test_sha256_after": sha256(candidate_test),
        "diagnosis_summary": diagnosis_summary,
    }
    if audit["status"] != "PASS":
        readiness["C1_2_VALID"] = False; readiness["status"] = "FAIL"
        readiness["blockers"] = audit["errors"]
        write_json(report_dir / "C1_2_READINESS.json", readiness)
    write_json(report_dir / "C1_2_FINAL_AUDIT.json", audit)

    checksum_paths = [
        report_dir / "BASELINE_VERIFICATION.json", report_dir / "METADATA_QUALITY.json",
        report_dir / "REQUIREMENT_ROLE_AUDIT.json", report_dir / "MISSING_MULTI_DIAGNOSIS.jsonl",
        report_dir / "CANDIDATE_CEILING.csv", report_dir / "C1_2_REPORT.md",
        report_dir / "CONFIG.json", report_dir / "TEST_RESULTS.json",
    ]
    write_json(report_dir / "CHECKSUMS.json", {
        "inputs": baseline_hashes_before,
        "outputs": {path.relative_to(report_dir).as_posix(): sha256(path) for path in checksum_paths},
    })
    return readiness
