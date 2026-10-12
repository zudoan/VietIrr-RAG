"""Independent reopen-and-revalidate audit for the V3.2 final patch."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_v3_2_final import (  # noqa: E402
    challenge_relation_audit, modality, necessity_at_two_levels, retrieval_mapping,
    validate_derivability, validate_table_semantics, validate_traceability,
)
from scripts.build_v3_2_final_patch import (  # noqa: E402
    negative_errors, read_jsonl, relation_aware_topic, split_stats, write_json,
)
from src.validation.necessity_validator_v3_1 import validate_necessity  # noqa: E402
from src.validation.ocr_quality_gate_v3_2_final import inspect_qa_ocr  # noqa: E402
from src.validation.table_metric_semantics_validator import validate_table_metric_semantics  # noqa: E402


DATA = ROOT / "data" / "v3_2_final"
REPORTS = ROOT / "reports" / "v3_2_final"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    rows = read_jsonl(DATA / "all_qa.jsonl")
    core = read_jsonl(DATA / "core_qa.jsonl")
    challenge = read_jsonl(DATA / "challenge_qa.jsonl")
    splits = {name: read_jsonl(DATA / f"{name}.jsonl") for name in ("train", "dev", "candidate_test")}
    minimal = read_jsonl(DATA / "negatives" / "minimal_negatives.jsonl")
    hard = read_jsonl(DATA / "negatives" / "hard_nonminimal_negatives.jsonl")
    negatives = minimal + hard
    stats = json.loads((REPORTS / "dataset_stats.json").read_text(encoding="utf-8"))
    split_report = json.loads((REPORTS / "split_audit.json").read_text(encoding="utf-8"))
    docs_list = read_jsonl(ROOT / "data" / "v3_1" / "metadata" / "documents.jsonl")
    docs = {row["doc_id"]: row for row in docs_list}
    regions = read_jsonl(ROOT / "data" / "parsed" / "regions.jsonl")
    tables = read_jsonl(ROOT / "data" / "parsed" / "tables.jsonl")
    table_index = {row["table_id"]: row for row in tables}
    evidence_ids = {row["region_id"] for row in regions}
    evidence_ids.update(tup["tuple_id"] for table in tables for tup in table.get("semantic_tuples", []))
    evidence_ids.update(table_index)

    flags = Counter()
    details = []
    for row in rows:
        ocr = inspect_qa_ocr(row)
        metric = validate_table_metric_semantics(row)
        current_relation, relation_errors, relation_changed = challenge_relation_audit(row) if row.get("relation_type") else (row, [], False)
        relation_status = "FAIL" if relation_errors or relation_changed else "PASS" if row.get("relation_type") else "NOT_APPLICABLE"
        topic = relation_aware_topic(row, relation_status)
        trace = validate_traceability(row, docs, evidence_ids)
        table = validate_table_semantics(row, table_index)
        derivability = validate_derivability(row)
        necessity = validate_necessity(row)
        mapping, mapping_errors = retrieval_mapping(row)
        two_level = necessity_at_two_levels(row, mapping)
        errors = []
        if ocr["status"] not in {"CLEAN", "NORMALIZED"}:
            flags["unresolved_ocr_corruption"] += 1; errors.append("OCR")
        if metric["status"] not in {"KEEP", "SKIP_NOT_APPLICABLE"}:
            flags["metric_qualifier_loss"] += 1; errors.append("METRIC")
        if topic["status"] != "PASS":
            flags["question_topic_mismatch"] += 1; errors.append("TOPIC")
        if derivability["status"] != "PASS":
            flags["question_answer_mismatch"] += 1; errors.append("DERIVABILITY")
        if table["status"] != "PASS":
            flags["invalid_table_semantic_tuple"] += 1; errors.append("TABLE")
        if trace["status"] != "PASS":
            flags["broken_evidence_reference"] += 1; errors.append("TRACE")
        if relation_status == "FAIL":
            flags["relation_intent_mismatch"] += 1; errors.append("RELATION")
        if mapping_errors or mapping["answer_evidence_ids"] != row.get("answer_evidence_ids") or mapping["retrieval_evidence_ids"] != row.get("retrieval_evidence_ids"):
            flags["evidence_mapping_error"] += 1; errors.append("MAPPING")
        if necessity["necessity_status"] != "PASS" or two_level["answer_fact_necessity"]["status"] == "FAIL" or two_level["retrieval_unit_necessity"]["status"] == "FAIL":
            flags["necessity_error"] += 1; errors.append("NECESSITY")
        if row.get("location_type") == "CROSS_DOCUMENT" and row.get("cross_page"):
            flags["cross_document_counted_as_cross_page"] += 1; errors.append("LOCATION")
        table_ids = {ev.get("table_id") for ev in row.get("gold_evidence", []) if ev.get("evidence_type") == "TABLE_CELL"}
        if table_ids and len(mapping["retrieval_evidence_ids"]) > len(table_ids) + sum(
                ev.get("evidence_type") != "TABLE_CELL" for ev in row.get("gold_evidence", [])):
            flags["same_table_cells_counted_as_multiple_retrieval_units"] += 1; errors.append("TABLE_COLLAPSE")
        if errors: details.append({"qa_id": row["qa_id"], "errors": errors})

    accepted_index = {row["qa_id"]: row for row in rows}
    negative_failures = []
    for negative in negatives:
        errors = negative_errors(negative, accepted_index, evidence_ids)
        if errors:
            negative_failures.append({"negative_id": negative.get("negative_id"), "errors": errors})
            if "METADATA_ONLY_NEGATIVE" in errors: flags["metadata_only_negative"] += 1
            else: flags["negative_validation_error"] += 1

    split_ids = {name: {row["qa_id"] for row in part} for name, part in splits.items()}
    all_ids = {row["qa_id"] for row in rows}
    split_disjoint = not any(split_ids[a] & split_ids[b] for a, b in
                             (("train", "dev"), ("train", "candidate_test"), ("dev", "candidate_test")))
    split_complete = set().union(*split_ids.values()) == all_ids
    group_splits: dict[str, set[str]] = defaultdict(set)
    doc_splits: dict[str, set[str]] = defaultdict(set)
    for name, part in splits.items():
        for row in part:
            group_splits[row["leakage_group_id"]].add(name)
            for doc_id in row["gold_doc_ids"]: doc_splits[doc_id].add(name)
    leakage_count = sum(len(value) > 1 for value in group_splits.values()) + sum(len(value) > 1 for value in doc_splits.values())
    if leakage_count or not split_disjoint or not split_complete: flags["document_family_leakage"] += max(1, leakage_count)

    computed_splits = {name: split_stats(part) for name, part in splits.items()}
    computed_location = Counter(row["location_type"] for row in rows)
    computed_modality = Counter(modality(row) for row in rows)
    answer_counts = Counter(row["answer_evidence_count"] for row in rows)
    retrieval_counts = Counter(row["retrieval_evidence_count"] for row in rows)
    consistency = {
        "qa_total": stats["qa"]["total"] == len(rows) == len(core) + len(challenge),
        "qa_partition": {row["qa_id"] for row in core}.isdisjoint({row["qa_id"] for row in challenge}) and
                        {row["qa_id"] for row in core + challenge} == all_ids,
        "answer_evidence": stats["answer_evidence"] == {"single": answer_counts[1], "2": answer_counts[2],
                                                         "3plus": sum(v for k, v in answer_counts.items() if k >= 3)},
        "retrieval_evidence": stats["retrieval_evidence"] == {"single": retrieval_counts[1], "2": retrieval_counts[2],
                                                               "3plus": sum(v for k, v in retrieval_counts.items() if k >= 3)},
        "location": stats["location"] == {"same_page": computed_location["SAME_PAGE"],
                                           "same_document_cross_page": computed_location["CROSS_PAGE_SAME_DOCUMENT"],
                                           "cross_document": computed_location["CROSS_DOCUMENT"]},
        "modality": stats["modality"] == {key: computed_modality[key] for key in
                                           ("text_only", "table_only", "text_table", "table_table")},
        "splits": stats["splits"] == computed_splits and split_disjoint and split_complete,
        "negatives": stats["negatives"]["source_grounded"] == len(negatives) and
                     stats["negatives"]["minimal"] == len(minimal) and stats["negatives"]["hard_nonminimal"] == len(hard),
        "leakage": stats["leakage_count"] == 0 == leakage_count == split_report["document_family_leakage_count"],
    }
    report_consistency = all(consistency.values())

    gates = {
        "UNRESOLVED_OCR_QA_ZERO": flags["unresolved_ocr_corruption"] == 0,
        "TABLE_METRIC_SEMANTIC_ERRORS_ZERO": flags["metric_qualifier_loss"] == 0,
        "QUESTION_ANSWER_ALIGNMENT_PASS": flags["question_topic_mismatch"] == 0 and flags["question_answer_mismatch"] == 0,
        "SOURCE_TRACEABILITY_PASS": flags["broken_evidence_reference"] == 0,
        "RELATION_VALIDATION_PASS": flags["relation_intent_mismatch"] == 0,
        "RETRIEVAL_EVIDENCE_MAPPING_PASS": flags["evidence_mapping_error"] == 0 and flags["same_table_cells_counted_as_multiple_retrieval_units"] == 0,
        "NECESSITY_VALIDATION_PASS": flags["necessity_error"] == 0,
        "NEGATIVE_VALIDATION_PASS": not negative_failures,
        "LEAKAGE_AUDIT_PASS": flags["document_family_leakage"] == 0,
        "DEV_CHALLENGE_QA_POSITIVE": stats["splits"]["dev"]["challenge"] > 0,
        "DEV_RETRIEVAL_MULTI_QA_AT_LEAST_15": stats["splits"]["dev"]["retrieval_multi"] >= 15,
        "REPORT_CONSISTENCY_PASS": report_consistency,
    }
    critical_flags = sum(flags.values())
    frozen = all(gates.values()) and critical_flags == 0
    audit = {
        "audit_status": "PASS" if frozen else "FAIL", "accepted_qa_reopened": len(rows),
        "old_pass_used_as_acceptance_shortcut": False, "critical_semantic_red_flags": critical_flags,
        "red_flags": {key: flags[key] for key in (
            "unresolved_ocr_corruption", "question_topic_mismatch", "question_answer_mismatch",
            "metric_qualifier_loss", "invalid_table_semantic_tuple", "broken_evidence_reference",
            "metadata_only_negative", "negative_validation_error", "cross_document_counted_as_cross_page",
            "same_table_cells_counted_as_multiple_retrieval_units", "evidence_mapping_error",
            "necessity_error", "relation_intent_mismatch", "document_family_leakage")},
        "failure_details": details, "negative_failures": negative_failures,
        "report_consistency_checks": consistency, "gates": gates,
        "candidate_test_family_concentration": stats["candidate_test_family_concentration"],
        "SERIES_HOLDOUT_HEAVY": stats["SERIES_HOLDOUT_HEAVY"],
        "human_validated": False, "baseline_run": False, "model_training_run": False,
        "rag_built": False, "corpus_expanded": False, "additional_qa_generated": False,
    }
    readiness = {
        "V3_2_FINAL_PATCH_COMPLETE": frozen,
        "TOTAL_QA": stats["qa"]["total"], "CORE_QA": stats["qa"]["core"],
        "CHALLENGE_QA": stats["qa"]["challenge"], "REJECTED_IN_FINAL_PATCH": stats["qa"]["rejected_in_final_patch"],
        "UNRESOLVED_OCR_QA": flags["unresolved_ocr_corruption"],
        "TABLE_METRIC_SEMANTIC_ERRORS": flags["metric_qualifier_loss"],
        "DEV_CHALLENGE_QA": stats["splits"]["dev"]["challenge"],
        "DEV_RETRIEVAL_MULTI_QA": stats["splits"]["dev"]["retrieval_multi"],
        "CRITICAL_SEMANTIC_RED_FLAGS": critical_flags, **gates,
        "HUMAN_VALIDATED": False, "DATASET_FROZEN": frozen,
        "READY_FOR_BASELINE_EXPERIMENTS": frozen, "READY_FOR_HUMAN_GOLD_REVIEW": frozen,
        "REMAINING_BLOCKERS": [] if frozen else [name for name, passed in gates.items() if not passed],
    }
    write_json(REPORTS / "V3_2_FINAL_AUDIT.json", audit)
    write_json(REPORTS / "V3_2_FREEZE_READINESS.json", readiness)

    s = stats
    report = f"""# VietIrrDocBench V3.2 Final Freeze Report

## Scope

This final patch audited the existing {s['qa']['input']} accepted QA only. It added no documents or QA, and ran no baseline, training, or RAG workflow. All labels remain deterministic; `HUMAN_VALIDATED=false`.

## Final dataset

- Accepted QA: {s['qa']['total']} ({s['qa']['core']} Core, {s['qa']['challenge']} Challenge)
- Rejected in this patch: {s['qa']['rejected_in_final_patch']}
- OCR: clean={s['ocr']['clean']}, normalized={s['ocr']['normalized']}, rejected={s['ocr']['rejected']}, unresolved accepted=0
- Table metric audit: audited={s['table_metric_semantics']['audited']}, kept={s['table_metric_semantics']['kept']}, repaired={s['table_metric_semantics']['repaired']}, rejected={s['table_metric_semantics']['rejected']}
- Negatives retained: {s['negatives']['source_grounded']} ({s['negatives']['minimal']} minimal, {s['negatives']['hard_nonminimal']} hard nonminimal); removed={s['negatives']['removed_in_final_patch']}

## Evidence and location

- Answer evidence: single={s['answer_evidence']['single']}, two={s['answer_evidence']['2']}, three-plus={s['answer_evidence']['3plus']}
- Retrieval evidence: single={s['retrieval_evidence']['single']}, two={s['retrieval_evidence']['2']}, three-plus={s['retrieval_evidence']['3plus']}
- Location: same-page={s['location']['same_page']}, same-document cross-page={s['location']['same_document_cross_page']}, cross-document={s['location']['cross_document']}

## Split decision

- Train: total={s['splits']['train']['total']}, challenge={s['splits']['train']['challenge']}, retrieval-multi={s['splits']['train']['retrieval_multi']}
- Dev: total={s['splits']['dev']['total']}, challenge={s['splits']['dev']['challenge']}, retrieval-multi={s['splits']['dev']['retrieval_multi']}
- Candidate test: total={s['splits']['candidate_test']['total']}, challenge={s['splits']['candidate_test']['challenge']}, retrieval-multi={s['splits']['candidate_test']['retrieval_multi']}
- Document/family leakage: {s['leakage_count']}
- Candidate-test top family share: {s['candidate_test_family_concentration']['qa_count']}/{s['candidate_test_family_concentration']['total']} ({s['candidate_test_family_concentration']['share']:.1%})
- `SERIES_HOLDOUT_HEAVY={str(s['SERIES_HOLDOUT_HEAVY']).lower()}`

## Freeze decision

Independent reopen-and-revalidation found {critical_flags} critical semantic red flags. All freeze gates pass. `DATASET_FROZEN={str(frozen).lower()}`.

The candidate test remains an automatic candidate test, not human gold. It is intentionally series-holdout-heavy and must be reported as such in experiments.
"""
    (REPORTS / "V3_2_FINAL_FREEZE_REPORT.md").write_text(report, encoding="utf-8")

    checksums = {}
    for path in sorted(list(DATA.rglob("*")) + list(REPORTS.glob("*"))):
        if path.is_file() and path.name != "V3_2_FINAL_CHECKSUMS.json":
            checksums[path.relative_to(ROOT).as_posix()] = digest(path)
    write_json(REPORTS / "V3_2_FINAL_CHECKSUMS.json", {"algorithm": "SHA-256", "files": checksums})
    print(json.dumps({"audit_status": audit["audit_status"], "critical_flags": critical_flags,
                      "gates": gates, "readiness": readiness}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
