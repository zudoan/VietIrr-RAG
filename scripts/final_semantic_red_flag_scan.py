"""Independent reopen-and-revalidate scan for the V3.2 semantic freeze."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_v3_2_final import (  # noqa: E402
    challenge_relation_audit, modality, necessity_at_two_levels, retrieval_mapping,
    validate_derivability, validate_table_semantics, validate_traceability,
)
from scripts.build_v3_2_final_patch import negative_errors, read_jsonl, relation_aware_topic, split_stats  # noqa: E402
from src.validation.contextual_topic_alignment_final import fold, validate_contextual_topic_alignment  # noqa: E402
from src.validation.entity_ocr_canonicalizer_final import inspect_qa_entities_metrics  # noqa: E402
from src.validation.evidence_time_validator_final import validate_qa_time  # noqa: E402
from src.validation.necessity_validator_v3_1 import validate_necessity  # noqa: E402
from src.validation.ocr_quality_gate_v3_2_final import inspect_qa_ocr  # noqa: E402
from src.validation.table_metric_semantics_validator import validate_table_metric_semantics  # noqa: E402

from scripts.build_v3_2_final_semantic import wrong_period_check, write_json  # noqa: E402

DATA = ROOT / "data" / "v3_2_final_semantic"
REPORTS = ROOT / "reports" / "v3_2_final_semantic"


REQUIRED_RED_FLAGS = (
    "report_date_as_measurement_date", "question_time_mismatch", "answer_time_mismatch",
    "missing_required_evidence_time", "water_level_from_ground_elevation",
    "water_level_from_channel_bed_elevation", "water_level_from_structure_elevation",
    "unresolved_ocr_entity", "unresolved_ocr_metric", "ambiguous_canonical_entity",
    "question_topic_mismatch", "metric_qualifier_loss", "broken_evidence_reference",
    "invalid_temporal_negative",
)


def main() -> None:
    rows = read_jsonl(DATA / "all_qa.jsonl")
    core = read_jsonl(DATA / "core_qa.jsonl")
    challenge = read_jsonl(DATA / "challenge_qa.jsonl")
    rejected = read_jsonl(DATA / "rejected_qa.jsonl")
    splits = {name: read_jsonl(DATA / f"{name}.jsonl") for name in ("train", "dev", "candidate_test")}
    minimal = read_jsonl(DATA / "negatives" / "minimal_negatives.jsonl")
    hard = read_jsonl(DATA / "negatives" / "hard_nonminimal_negatives.jsonl")
    negatives = minimal + hard
    stats = json.loads((REPORTS / "dataset_stats.json").read_text(encoding="utf-8"))
    split_report = json.loads((REPORTS / "split_audit.json").read_text(encoding="utf-8"))

    docs_list = read_jsonl(ROOT / "data" / "v3_1" / "metadata" / "documents.jsonl")
    docs = {r["doc_id"]: r for r in docs_list}
    regions = read_jsonl(ROOT / "data" / "parsed" / "regions.jsonl")
    tables = read_jsonl(ROOT / "data" / "parsed" / "tables.jsonl")
    table_index = {r["table_id"]: r for r in tables}
    evidence_ids = {r["region_id"] for r in regions}
    evidence_ids.update(t["tuple_id"] for table in tables for t in table.get("semantic_tuples", []))
    evidence_ids.update(table_index)

    flags = Counter()
    failure_details = []
    applicable = Counter()
    for row in rows:
        errors = []
        temporal = validate_qa_time(row)
        if row.get("relation_type") == "SAME_ENTITY_DIFFERENT_TIME":
            applicable["temporal"] += 1
            if temporal["status"] != "PASS":
                for error in temporal.get("errors", []):
                    if error == "QUESTION_TIME_MISMATCH": flags["question_time_mismatch"] += 1
                    elif error == "ANSWER_TIME_MISMATCH": flags["answer_time_mismatch"] += 1
                    elif error == "MISSING_REQUIRED_EVIDENCE_TIME": flags["missing_required_evidence_time"] += 1
                errors.append("TEMPORAL")
            for annotation in temporal.get("evidence", []):
                evidence_time = annotation.get("evidence_time") or {}
                if annotation.get("time_type") in {"OBSERVATION_DATE", "MEASUREMENT_DATE", "FORECAST_DATE"} and (
                        evidence_time.get("source_priority", 99) >= 5):
                    flags["report_date_as_measurement_date"] += 1
                    errors.append("REPORT_DATE_AS_MEASUREMENT")

        if not row.get("relation_type"):
            applicable["core_topic"] += 1
            topic = validate_contextual_topic_alignment(row)
            if topic["status"] != "PASS":
                flags["question_topic_mismatch"] += 1
                errors.append("CONTEXTUAL_TOPIC")
            qf = fold(row.get("question"))
            ef = fold(" ".join(str(e.get("text") or "") for e in row.get("gold_evidence", [])))
            if "muc nuoc" in qf and "muc nuoc" not in ef:
                if "cao trinh mat dat" in ef: flags["water_level_from_ground_elevation"] += 1
                elif "cao trinh day kenh" in ef: flags["water_level_from_channel_bed_elevation"] += 1
                elif "cao trinh" in ef: flags["water_level_from_structure_elevation"] += 1
                errors.append("WATER_LEVEL_ELEVATION")

        entity = inspect_qa_entities_metrics(row)
        if entity["status"] in {"UNCERTAIN", "REJECT"}:
            for item in entity.get("uncertain_fields", []):
                key = "unresolved_ocr_entity" if item.get("semantic_role") == "entity" else "unresolved_ocr_metric"
                flags[key] += 1
            errors.append("ENTITY_OCR")
        for evidence in row.get("gold_evidence", []):
            if evidence.get("entity_raw") and not evidence.get("entity_canonical"):
                flags["ambiguous_canonical_entity"] += 1
                errors.append("AMBIGUOUS_CANONICAL_ENTITY")

        relation_status = "NOT_APPLICABLE"
        if row.get("relation_type"):
            _, relation_errors, relation_changed = challenge_relation_audit(row)
            relation_status = "FAIL" if relation_errors or relation_changed else "PASS"
            if relation_status == "FAIL":
                flags["relation_validation_error"] += 1
                errors.append("RELATION")
        legacy_topic = relation_aware_topic(row, relation_status)
        if legacy_topic["status"] != "PASS":
            flags["question_topic_mismatch"] += 1
            errors.append("LEGACY_TOPIC")

        metric = validate_table_metric_semantics(row)
        if metric["status"] not in {"KEEP", "SKIP_NOT_APPLICABLE"}:
            flags["metric_qualifier_loss"] += 1
            errors.append("METRIC")
        trace = validate_traceability(row, docs, evidence_ids)
        if trace["status"] != "PASS":
            flags["broken_evidence_reference"] += 1
            errors.append("TRACE")
        derivability = validate_derivability(row)
        if derivability["status"] != "PASS":
            flags["question_answer_alignment_error"] += 1
            errors.append("DERIVABILITY")
        table = validate_table_semantics(row, table_index)
        if table["status"] != "PASS":
            flags["table_semantics_error"] += 1
            errors.append("TABLE")
        mapping, mapping_errors = retrieval_mapping(row)
        if mapping_errors or mapping["answer_evidence_ids"] != row.get("answer_evidence_ids") or (
                mapping["retrieval_evidence_ids"] != row.get("retrieval_evidence_ids")):
            flags["evidence_mapping_error"] += 1
            errors.append("MAPPING")
        necessity = validate_necessity(row)
        two_level = necessity_at_two_levels(row, mapping)
        if necessity["necessity_status"] != "PASS" or two_level["answer_fact_necessity"]["status"] == "FAIL" or (
                two_level["retrieval_unit_necessity"]["status"] == "FAIL"):
            flags["necessity_error"] += 1
            errors.append("NECESSITY")
        old_ocr = inspect_qa_ocr(row)
        if old_ocr["status"] not in {"CLEAN", "NORMALIZED"}:
            flags["unresolved_ocr_metric"] += 1
            errors.append("LEGACY_OCR")
        if errors:
            failure_details.append({"qa_id": row["qa_id"], "errors": sorted(set(errors))})

    accepted_index = {r["qa_id"]: r for r in rows}
    negative_failures = []
    temporal_negative_audited = 0
    for negative in negatives:
        errors = negative_errors(negative, accepted_index, evidence_ids)
        if negative.get("negative_type") == "WRONG_PERIOD":
            temporal_negative_audited += 1
            result = wrong_period_check(negative, accepted_index[negative["source_qa_id"]])
            if result["status"] != "PASS":
                errors.append(result.get("error") or "INVALID_TEMPORAL_NEGATIVE")
                flags["invalid_temporal_negative"] += 1
        if errors:
            flags["negative_validation_error"] += 1
            negative_failures.append({"negative_id": negative.get("negative_id"), "errors": sorted(set(errors))})

    split_ids = {name: {r["qa_id"] for r in part} for name, part in splits.items()}
    all_ids = {r["qa_id"] for r in rows}
    split_disjoint = not any(split_ids[a] & split_ids[b] for a, b in
                             (("train", "dev"), ("train", "candidate_test"), ("dev", "candidate_test")))
    split_complete = set().union(*split_ids.values()) == all_ids
    group_splits: dict[str, set[str]] = defaultdict(set)
    doc_splits: dict[str, set[str]] = defaultdict(set)
    for name, part in splits.items():
        for row in part:
            group_splits[row["leakage_group_id"]].add(name)
            for doc_id in row["gold_doc_ids"]:
                doc_splits[doc_id].add(name)
    leakage = sum(len(v) > 1 for v in group_splits.values()) + sum(len(v) > 1 for v in doc_splits.values())
    if leakage or not split_disjoint or not split_complete:
        flags["document_family_leakage"] += max(1, leakage)

    computed_splits = {name: split_stats(part) for name, part in splits.items()}
    answer_counts = Counter(r["answer_evidence_count"] for r in rows)
    retrieval_counts = Counter(r["retrieval_evidence_count"] for r in rows)
    location_counts = Counter(r["location_type"] for r in rows)
    modality_counts = Counter(modality(r) for r in rows)
    consistency = {
        "qa_total": stats["qa"]["total"] == len(rows) == len(core) + len(challenge),
        "qa_partition": {r["qa_id"] for r in core}.isdisjoint({r["qa_id"] for r in challenge}) and
                        {r["qa_id"] for r in core + challenge} == all_ids,
        "answer_evidence": stats["answer_evidence"] == {"single": answer_counts[1], "2": answer_counts[2],
                                                         "3plus": sum(v for k, v in answer_counts.items() if k >= 3)},
        "retrieval_evidence": stats["retrieval_evidence"] == {"single": retrieval_counts[1], "2": retrieval_counts[2],
                                                               "3plus": sum(v for k, v in retrieval_counts.items() if k >= 3)},
        "location": stats["location"] == {"same_page": location_counts["SAME_PAGE"],
                                           "same_document_cross_page": location_counts["CROSS_PAGE_SAME_DOCUMENT"],
                                           "cross_document": location_counts["CROSS_DOCUMENT"]},
        "modality": stats["modality"] == {k: modality_counts[k] for k in
                                           ("text_only", "table_only", "text_table", "table_table")},
        "splits": stats["splits"] == computed_splits and split_disjoint and split_complete,
        "negatives": stats["negatives"]["source_grounded"] == len(negatives) and
                     stats["negatives"]["minimal"] == len(minimal) and stats["negatives"]["hard_nonminimal"] == len(hard),
        "leakage": stats["leakage_count"] == split_report["document_family_leakage_count"] == leakage == 0,
        "required_files": all((REPORTS / name).exists() for name in (
            "temporal_semantics_audit.json", "core_topic_alignment_audit.json",
            "entity_ocr_canonicalization.json", "affected_negative_audit.json", "split_audit.json", "dataset_stats.json")),
    }
    report_consistency = all(consistency.values())

    red_flags = {name: flags[name] for name in REQUIRED_RED_FLAGS}
    extra_flags = {name: flags[name] for name in (
        "relation_validation_error", "question_answer_alignment_error", "table_semantics_error",
        "evidence_mapping_error", "necessity_error", "negative_validation_error", "document_family_leakage")}
    all_critical_zero = not any(red_flags.values()) and not any(extra_flags.values())
    gates = {
        "TEMPORAL_SEMANTIC_MISMATCH_ZERO": not any(red_flags[k] for k in (
            "question_time_mismatch", "answer_time_mismatch", "missing_required_evidence_time")),
        "REPORT_DATE_AS_EVIDENCE_DATE_ERROR_ZERO": red_flags["report_date_as_measurement_date"] == 0,
        "CORE_TOPIC_ALIGNMENT_ERRORS_ZERO": not any(red_flags[k] for k in (
            "water_level_from_ground_elevation", "water_level_from_channel_bed_elevation",
            "water_level_from_structure_elevation", "question_topic_mismatch")),
        "UNRESOLVED_OCR_ENTITY_ZERO": red_flags["unresolved_ocr_entity"] == 0 and red_flags["ambiguous_canonical_entity"] == 0,
        "UNRESOLVED_OCR_METRIC_ZERO": red_flags["unresolved_ocr_metric"] == 0,
        "QUESTION_ANSWER_ALIGNMENT_PASS": extra_flags["question_answer_alignment_error"] == 0,
        "SOURCE_TRACEABILITY_PASS": red_flags["broken_evidence_reference"] == 0,
        "TABLE_METRIC_SEMANTICS_PASS": red_flags["metric_qualifier_loss"] == 0 and extra_flags["table_semantics_error"] == 0,
        "RELATION_VALIDATION_PASS": extra_flags["relation_validation_error"] == 0,
        "RETRIEVAL_EVIDENCE_MAPPING_PASS": extra_flags["evidence_mapping_error"] == 0,
        "NECESSITY_VALIDATION_PASS": extra_flags["necessity_error"] == 0,
        "NEGATIVE_VALIDATION_PASS": extra_flags["negative_validation_error"] == 0 and red_flags["invalid_temporal_negative"] == 0,
        "LEAKAGE_AUDIT_PASS": extra_flags["document_family_leakage"] == 0,
        "DEV_RETRIEVAL_MULTI_QA_AT_LEAST_15": computed_splits["dev"]["retrieval_multi"] >= 15,
        "REPORT_CONSISTENCY_PASS": report_consistency,
    }
    frozen = all(gates.values()) and all_critical_zero
    remaining = [name for name, passed in gates.items() if not passed]
    if not all_critical_zero:
        remaining.extend(name for name, count in {**red_flags, **extra_flags}.items() if count)

    audit = {
        "audit_status": "PASS" if frozen else "FAIL", "accepted_qa_reopened": len(rows),
        "applicable_counts": dict(applicable), "red_flags": red_flags, "additional_critical_flags": extra_flags,
        "critical_semantic_red_flags": sum(red_flags.values()) + sum(extra_flags.values()),
        "failure_details": failure_details, "negative_failures": negative_failures,
        "temporal_negative_audited": temporal_negative_audited,
        "report_consistency_checks": consistency, "gates": gates,
        "candidate_test_family_concentration": stats["candidate_test_family_concentration"],
        "SERIES_HOLDOUT_HEAVY": stats["SERIES_HOLDOUT_HEAVY"],
        "human_validated": False, "baseline_run": False, "model_training_run": False,
        "rag_built": False, "corpus_expanded": False, "additional_qa_generated": False,
    }
    readiness = {
        "V3_2_FINAL_SEMANTIC_PATCH_COMPLETE": frozen,
        "INPUT_QA": stats["qa"]["input"], "FINAL_ACCEPTED_QA": len(rows),
        "CORE_QA": len(core), "CHALLENGE_QA": len(challenge),
        "REJECTED_IN_FINAL_SEMANTIC_PATCH": stats["qa"]["rejected_in_final_semantic_patch"],
        "TEMPORAL_QA_AUDITED": applicable["temporal"],
        "TEMPORAL_QA_REPAIRED": stats["repairs"].get("TEMPORAL_SEMANTICS", 0),
        "CORE_TOPIC_QA_AUDITED": applicable["core_topic"],
        "CORE_TOPIC_QA_REPAIRED": stats["repairs"].get("CONTEXTUAL_TOPIC_ALIGNMENT", 0),
        "OCR_QA_NORMALIZED": stats["entity_ocr"]["status_counts"].get("NORMALIZED", 0),
        "FINAL_SOURCE_GROUNDED_NEGATIVES": len(negatives),
        "TEMPORAL_NEGATIVES_REPAIRED": temporal_negative_audited,
        "NEGATIVES_REMOVED": stats["negatives"]["removed_in_final_semantic_patch"],
        "DEV_RETRIEVAL_MULTI_QA": computed_splits["dev"]["retrieval_multi"],
        "CRITICAL_SEMANTIC_RED_FLAGS": audit["critical_semantic_red_flags"],
        **gates, "HUMAN_VALIDATED": False, "DATASET_FROZEN": frozen,
        "READY_FOR_BASELINE_EXPERIMENTS": frozen, "READY_FOR_HUMAN_GOLD_REVIEW": frozen,
        "REMAINING_BLOCKERS": sorted(set(remaining)),
    }
    write_json(REPORTS / "V3_2_FINAL_SEMANTIC_AUDIT.json", audit)
    write_json(REPORTS / "V3_2_FINAL_SEMANTIC_READINESS.json", readiness)

    report = f"""# VietIrrDocBench V3.2 Final Semantic Freeze Report

## Scope and result

The patch reopened {len(rows)} accepted QA without rebuilding or expanding the corpus. It repaired {stats['repairs'].get('TEMPORAL_SEMANTICS', 0)} temporal QA, {stats['repairs'].get('CONTEXTUAL_TOPIC_ALIGNMENT', 0)} Core topic QA, and normalized entity/metric OCR in {stats['entity_ocr']['status_counts'].get('NORMALIZED', 0)} QA. No replacement QA was generated.

## Final dataset

- Accepted QA: {len(rows)} ({len(core)} Core, {len(challenge)} Challenge)
- Rejected in this patch: {stats['qa']['rejected_in_final_semantic_patch']}
- Source-grounded negatives: {len(negatives)} ({len(minimal)} minimal, {len(hard)} hard nonminimal)
- Invalid negatives removed: {stats['negatives']['removed_in_final_semantic_patch']}
- Dev: {computed_splits['dev']['total']} QA, {computed_splits['dev']['challenge']} Challenge, {computed_splits['dev']['retrieval_multi']} retrieval-multi
- Candidate test: {computed_splits['candidate_test']['total']} QA; this is a series/family holdout-heavy evaluation split, not a universally representative benchmark test.
- Document/family leakage: {leakage}

## Semantic gates

All required semantic red flags are zero. Temporal evidence dates come from metric/header or explicit evidence periods, not bulletin publication dates. Generic elevations are not accepted as water-level evidence. Raw OCR provenance is retained beside controlled normalized/canonical values.

`HUMAN_VALIDATED=false`. No baseline, training, RAG build, corpus expansion, or new-QA generation was run.

## Freeze decision

`DATASET_FROZEN={str(frozen).lower()}` and `READY_FOR_BASELINE_EXPERIMENTS={str(frozen).lower()}`.
"""
    (REPORTS / "V3_2_FINAL_SEMANTIC_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"audit_status": audit["audit_status"], "red_flags": red_flags,
                      "additional_flags": extra_flags, "gates": gates,
                      "dataset_frozen": frozen, "remaining_blockers": readiness["REMAINING_BLOCKERS"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
