"""Build the narrow V3.2 final semantic patch from its immutable snapshot."""

from __future__ import annotations

import copy
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_v3_2_final import (  # noqa: E402
    challenge_relation_audit, evidence_texts, modality, necessity_at_two_levels,
    retrieval_mapping, validate_derivability, validate_table_semantics, validate_traceability,
)
from scripts.build_v3_2_final_patch import negative_errors, read_jsonl, relation_aware_topic, split_stats  # noqa: E402
from src.validation.contextual_topic_alignment_final import validate_contextual_topic_alignment  # noqa: E402
from src.validation.entity_ocr_canonicalizer_final import canonicalize_qa  # noqa: E402
from src.validation.evidence_time_validator_final import annotate_evidence_time, validate_qa_time  # noqa: E402
from src.validation.necessity_validator_v3_1 import validate_necessity  # noqa: E402
from src.validation.ocr_quality_gate_v3_2_final import inspect_qa_ocr  # noqa: E402
from src.validation.table_metric_semantics_validator import validate_table_metric_semantics  # noqa: E402
from src.validation.topic_alignment_validator_v3_2 import validate_topic_alignment  # noqa: E402


SOURCE = ROOT / "snapshots" / "pre_v3_2_final_semantic_patch" / "data" / "v3_2_final"
OUTPUT = ROOT / "data" / "v3_2_final_semantic"
REPORTS = ROOT / "reports" / "v3_2_final_semantic"


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def attach_time(evidence: dict) -> dict:
    annotation = annotate_evidence_time(evidence)
    evidence["document_reporting_time"] = annotation["document_reporting_time"]
    evidence["evidence_time"] = annotation["evidence_time"]
    evidence["time_type"] = annotation["time_type"]
    if annotation.get("evidence_time"):
        semantic = evidence.setdefault("semantic_tuple", {})
        old = copy.deepcopy(semantic.get("time") or {})
        if "time_before_final_semantic_patch" not in semantic:
            semantic["time_before_final_semantic_patch"] = old
        item = annotation["evidence_time"]
        semantic["time"] = {
            "raw": item.get("raw"), "normalized_start": item.get("normalized_start"),
            "normalized_end": item.get("normalized_end"), "period_type": annotation["time_type"],
            "basis": item.get("normalization_basis"), "source": item.get("source"),
            "confidence": 0.99 if item.get("source_priority", 9) <= 2 else 0.9,
        }
    return annotation


def process_qa(source: dict, docs: dict, evidence_ids: set[str], table_index: dict) -> tuple[dict | None, dict]:
    row = copy.deepcopy(source)
    reasons: list[str] = []
    repairs: list[str] = []

    temporal_initial = validate_qa_time(row)
    if temporal_initial["status"] == "REPAIR":
        row["question_before_v3_2_final_semantic_patch"] = row["question"]
        row["answer_before_v3_2_final_semantic_patch"] = row["answer"]
        row["question"] = temporal_initial["proposed_question"]
        row["answer"] = temporal_initial["proposed_answer"]
        repairs.append("TEMPORAL_SEMANTICS")
    elif temporal_initial["status"] in {"REJECT", "UNCERTAIN"}:
        reasons.append(f"TEMPORAL_{temporal_initial['status']}")

    time_annotations = [attach_time(ev) for ev in row.get("gold_evidence") or []]
    row, entity_audit = canonicalize_qa(row)
    if entity_audit["status"] == "NORMALIZED":
        repairs.append("ENTITY_OR_METRIC_OCR")
    elif entity_audit["status"] in {"REJECT", "UNCERTAIN"}:
        reasons.append(f"ENTITY_OCR_{entity_audit['status']}")

    topic_initial = {"status": "SKIP_NOT_CORE", "errors": []}
    if not row.get("relation_type"):
        topic_initial = validate_contextual_topic_alignment(row)
        if topic_initial["status"] == "REPAIR":
            row.setdefault("question_before_v3_2_final_semantic_patch", row["question"])
            row.setdefault("answer_before_v3_2_final_semantic_patch", row["answer"])
            row["question"] = topic_initial["proposed_question"]
            row["answer"] = topic_initial["proposed_answer"]
            repairs.append("CONTEXTUAL_TOPIC_ALIGNMENT")
        elif topic_initial["status"] in {"REJECT", "UNCERTAIN"}:
            reasons.append(f"TOPIC_{topic_initial['status']}")

    temporal_final = validate_qa_time(row)
    if row.get("relation_type") == "SAME_ENTITY_DIFFERENT_TIME" and temporal_final["status"] != "PASS":
        reasons.append("TEMPORAL_POST_REPAIR_FAIL")
    topic_final = validate_contextual_topic_alignment(row) if not row.get("relation_type") else {"status": "SKIP_NOT_CORE", "errors": []}
    if not row.get("relation_type") and topic_final["status"] != "PASS":
        reasons.append("TOPIC_POST_REPAIR_FAIL")

    relation = {"status": "NOT_APPLICABLE", "errors": [], "basis": []}
    if row.get("relation_type") and not reasons:
        row, relation_errors, relation_changed = challenge_relation_audit(row)
        relation = row.get("relation_validation_v3_2") or {}
        if relation_errors or relation_changed:
            reasons.extend(relation_errors or ["RELATION_CHANGED_AFTER_SEMANTIC_REPAIR"])

    rebuilt = validate_necessity(row)
    row["answer_components"] = rebuilt["components"]
    row["evidence_support_matrix"] = rebuilt["support_matrix"]
    row["necessity_validation_v3_2_final_semantic"] = rebuilt
    mapping, mapping_errors = retrieval_mapping(row)
    two_level = necessity_at_two_levels(row, mapping)
    trace = validate_traceability(row, docs, evidence_ids)
    derivability = validate_derivability(row)
    table = validate_table_semantics(row, table_index)
    metric = validate_table_metric_semantics(row)
    ocr = inspect_qa_ocr(row)
    legacy_topic = relation_aware_topic(row, relation.get("status", "NOT_APPLICABLE"))

    if rebuilt["necessity_status"] != "PASS": reasons.append("NECESSITY_REBUILD_FAIL")
    if two_level["answer_fact_necessity"]["status"] == "FAIL": reasons.append("ANSWER_FACT_NECESSITY_FAIL")
    if two_level["retrieval_unit_necessity"]["status"] == "FAIL": reasons.append("RETRIEVAL_UNIT_NECESSITY_FAIL")
    if trace["status"] != "PASS": reasons.extend(trace.get("errors", []))
    if derivability["status"] != "PASS": reasons.extend(derivability.get("errors", []))
    if table["status"] != "PASS": reasons.extend(table.get("errors", []))
    if metric["status"] not in {"KEEP", "SKIP_NOT_APPLICABLE"}: reasons.append("TABLE_METRIC_SEMANTICS_FAIL")
    if ocr["status"] not in {"CLEAN", "NORMALIZED"}: reasons.append(f"LEGACY_OCR_{ocr['status']}")
    if legacy_topic["status"] != "PASS": reasons.extend(legacy_topic.get("errors", []))
    reasons.extend(mapping_errors)
    reasons = sorted(set(reasons))

    audit = {
        "qa_id": row["qa_id"], "repairs": repairs, "temporal_initial": temporal_initial,
        "temporal_final": temporal_final, "time_annotations": time_annotations,
        "topic_initial": topic_initial, "topic_final": topic_final,
        "entity_ocr": entity_audit, "rejection_reasons": reasons,
    }
    if reasons:
        row["status"] = "REJECTED"
        row["status_v3_2_final_semantic"] = "REJECTED"
        row["rejection_reasons_v3_2_final_semantic"] = reasons
        return None, {**audit, "rejected_row": row}

    for key in ("answer_evidence_ids", "retrieval_evidence_ids", "answer_evidence_count",
                "retrieval_evidence_count", "retrieval_multi_evidence", "retrieval_three_plus",
                "location_type", "gold_doc_ids", "gold_page_ids", "gold_page_count", "page_span_same_document"):
        row[key] = mapping[key]
    row["same_page"] = mapping["location_type"] == "SAME_PAGE"
    row["cross_page"] = mapping["location_type"] == "CROSS_PAGE_SAME_DOCUMENT"
    row["answer_fact_necessity"] = two_level["answer_fact_necessity"]
    row["retrieval_unit_necessity"] = two_level["retrieval_unit_necessity"]
    row["temporal_semantics_final"] = temporal_final
    row["contextual_topic_alignment_final"] = topic_final
    row["validation_v3_2_final_semantic"] = {
        "temporal_semantics": temporal_final["status"], "contextual_topic_alignment": topic_final["status"],
        "entity_ocr_canonicalization": entity_audit["status"], "source_traceability": trace["status"],
        "derivability": derivability["status"], "necessity": rebuilt["necessity_status"],
        "table_semantics": table["status"], "table_metric_semantics": metric["status"],
        "legacy_topic_alignment": legacy_topic["status"], "relation": relation.get("status", "NOT_APPLICABLE"),
        "old_pass_used_as_acceptance": False,
    }
    row["status"] = "PASS"
    row["status_v3_2_final_semantic"] = "REPAIRED" if repairs else "KEEP"
    row["semantic_repairs"] = repairs
    row["review_status"] = "DETERMINISTIC_REVIEWED"
    row["human_validated"] = False
    return row, audit


def canonicalize_candidate(candidate: list[dict]) -> tuple[list[dict], dict]:
    wrapper = {"question": "", "answer": "", "gold_evidence": copy.deepcopy(candidate)}
    wrapper, audit = canonicalize_qa(wrapper)
    for evidence in wrapper["gold_evidence"]:
        attach_time(evidence)
    return wrapper["gold_evidence"], audit


def wrong_period_check(row: dict, parent: dict) -> dict:
    target_id = row.get("gold_target_evidence_id")
    gold = next((e for e in parent.get("gold_evidence", []) if e.get("evidence_id") == target_id), None)
    candidate = next((e for e in row.get("candidate_evidence", [])
                      if e.get("evidence_id") == row.get("negative_evidence_id")), None)
    if not gold or not candidate:
        return {"status": "REJECT", "error": "MISSING_GOLD_OR_CANDIDATE_EVIDENCE"}
    ga, ca = annotate_evidence_time(gold), annotate_evidence_time(candidate)
    if ga["status"] != "PASS" or ca["status"] != "PASS" or not ga.get("evidence_time") or not ca.get("evidence_time"):
        return {"status": "REJECT", "error": "UNRESOLVED_EVIDENCE_TIME", "gold": ga, "candidate": ca}
    g = ga["evidence_time"]
    c = ca["evidence_time"]
    different = (g["normalized_start"], g["normalized_end"], ga["time_type"]) != (
        c["normalized_start"], c["normalized_end"], ca["time_type"])
    return {"status": "PASS" if different else "REJECT",
            "error": None if different else "SAME_EVIDENCE_TIME",
            "gold": ga, "candidate": ca,
            "basis": "source metric/tuple/reference period; publication date alone is never used"}


def split_audit(rows: list[dict]) -> tuple[dict[str, list[dict]], dict]:
    outputs = {name: sorted([r for r in rows if r.get("split") == name], key=lambda x: x["qa_id"])
               for name in ("train", "dev", "candidate_test")}
    group_splits: dict[str, set[str]] = defaultdict(set)
    doc_splits: dict[str, set[str]] = defaultdict(set)
    for name, part in outputs.items():
        for row in part:
            group_splits[row["leakage_group_id"]].add(name)
            for doc_id in row["gold_doc_ids"]:
                doc_splits[doc_id].add(name)
    group_leaks = {k: sorted(v) for k, v in group_splits.items() if len(v) > 1}
    doc_leaks = {k: sorted(v) for k, v in doc_splits.items() if len(v) > 1}
    original = {r["qa_id"]: r.get("split") for r in read_jsonl(SOURCE / "all_qa.jsonl")}
    changed = [{"qa_id": r["qa_id"], "before": original.get(r["qa_id"]), "after": r.get("split")}
               for r in rows if original.get(r["qa_id"]) != r.get("split")]
    candidates = outputs["candidate_test"]
    families = Counter(r["leakage_group_id"] for r in candidates)
    top_family, top_count = families.most_common(1)[0] if families else (None, 0)
    audit = {
        "strategy": "preserve existing split because no QA rejection requires rebalancing",
        "split_changes": changed, "split_preserved": not changed,
        "group_leaks": group_leaks, "document_leaks": doc_leaks,
        "document_family_leakage_count": len(group_leaks) + len(doc_leaks),
        "leakage_audit_pass": not group_leaks and not doc_leaks,
        "per_split": {name: split_stats(part) for name, part in outputs.items()},
        "candidate_test_family_concentration": {
            "top_family": top_family, "qa_count": top_count, "total": len(candidates),
            "share": (top_count / len(candidates)) if candidates else 0.0,
        },
        "SERIES_HOLDOUT_HEAVY": bool(candidates and top_count / len(candidates) >= 0.5),
    }
    return outputs, audit


def main() -> None:
    inputs = read_jsonl(SOURCE / "all_qa.jsonl")
    old_rejected = read_jsonl(SOURCE / "rejected_qa.jsonl")
    docs_list = read_jsonl(ROOT / "data" / "v3_1" / "metadata" / "documents.jsonl")
    docs = {r["doc_id"]: r for r in docs_list}
    pages = read_jsonl(ROOT / "data" / "pages.jsonl")
    regions = read_jsonl(ROOT / "data" / "parsed" / "regions.jsonl")
    tables = read_jsonl(ROOT / "data" / "parsed" / "tables.jsonl")
    table_index = {r["table_id"]: r for r in tables}
    evidence_ids = {r["region_id"] for r in regions}
    evidence_ids.update(t["tuple_id"] for table in tables for t in table.get("semantic_tuples", []))
    evidence_ids.update(table_index)

    accepted, rejected, audits = [], [], []
    for source in inputs:
        row, audit = process_qa(source, docs, evidence_ids, table_index)
        audits.append(audit)
        if row is None:
            rejected.append(audit["rejected_row"])
        else:
            accepted.append(row)
    accepted.sort(key=lambda r: r["qa_id"])
    accepted_index = {r["qa_id"]: r for r in accepted}

    negative_sources = {
        "minimal": read_jsonl(SOURCE / "negatives" / "minimal_negatives.jsonl"),
        "hard_nonminimal": read_jsonl(SOURCE / "negatives" / "hard_nonminimal_negatives.jsonl"),
    }
    old_rejected_negatives = read_jsonl(SOURCE / "negatives" / "rejected_negatives.jsonl")
    negatives = {"minimal": [], "hard_nonminimal": []}
    removed, negative_audits = [], []
    for kind, source_rows in negative_sources.items():
        for source in source_rows:
            row = copy.deepcopy(source)
            parent = accepted_index.get(row.get("source_qa_id"))
            if parent and row.get("question") != parent.get("question"):
                row["question_before_v3_2_final_semantic_patch"] = row.get("question")
                row["question"] = parent["question"]
                row["parent_question_reference_repaired_final_semantic"] = True
            row["candidate_evidence"], canonical_audit = canonicalize_candidate(row.get("candidate_evidence") or [])
            row["candidate_evidence_ids"] = [e.get("evidence_id") for e in row["candidate_evidence"]]
            errors = negative_errors(row, accepted_index, evidence_ids)
            temporal = {"status": "NOT_APPLICABLE"}
            if row.get("negative_type") == "WRONG_PERIOD" and parent:
                temporal = wrong_period_check(row, parent)
                if temporal["status"] != "PASS":
                    errors.append(temporal.get("error") or "WRONG_PERIOD_INVALID")
            if canonical_audit["status"] in {"REJECT", "UNCERTAIN"}:
                errors.append(f"CANDIDATE_ENTITY_OCR_{canonical_audit['status']}")
            errors = sorted(set(errors))
            entry = {"negative_id": row.get("negative_id"), "source_qa_id": row.get("source_qa_id"),
                     "negative_type": row.get("negative_type"), "status": "REJECT" if errors else "PASS",
                     "errors": errors, "temporal_validation": temporal,
                     "entity_ocr_canonicalization": canonical_audit}
            negative_audits.append(entry)
            if errors:
                row["negative_status_v3_2_final_semantic"] = "REJECTED"
                row["validation_errors_v3_2_final_semantic"] = errors
                removed.append(row)
            else:
                row["negative_status_v3_2_final_semantic"] = "VALID"
                row["validation_errors_v3_2_final_semantic"] = []
                row["temporal_validation_final_semantic"] = temporal
                row["entity_ocr_canonicalization_final"] = canonical_audit
                row["review_status"] = "DETERMINISTIC_REVIEWED"
                row["human_validated"] = False
                negatives[kind].append(row)

    splits, split_report = split_audit(accepted)
    core = [r for r in accepted if not r.get("relation_type")]
    challenge = [r for r in accepted if r.get("relation_type")]
    cumulative_rejected = sorted(old_rejected + rejected, key=lambda r: r["qa_id"])

    write_jsonl(OUTPUT / "all_qa.jsonl", accepted)
    write_jsonl(OUTPUT / "core_qa.jsonl", core)
    write_jsonl(OUTPUT / "challenge_qa.jsonl", challenge)
    write_jsonl(OUTPUT / "rejected_qa.jsonl", cumulative_rejected)
    write_jsonl(OUTPUT / "uncertain_qa.jsonl", [])
    for name, part in splits.items():
        write_jsonl(OUTPUT / f"{name}.jsonl", part)
    write_jsonl(OUTPUT / "negatives" / "minimal_negatives.jsonl", negatives["minimal"])
    write_jsonl(OUTPUT / "negatives" / "hard_nonminimal_negatives.jsonl", negatives["hard_nonminimal"])
    write_jsonl(OUTPUT / "negatives" / "rejected_negatives.jsonl", old_rejected_negatives + removed)

    mappings, locations = [], []
    for row in accepted:
        mapping, _ = retrieval_mapping(row)
        mappings.append(mapping)
        locations.append({k: mapping[k] for k in ("qa_id", "location_type", "gold_doc_ids", "gold_page_ids",
                                                    "gold_page_count", "page_span_same_document")})
    write_jsonl(OUTPUT / "metadata" / "retrieval_evidence_map.jsonl", mappings)
    write_jsonl(OUTPUT / "metadata" / "page_location_metadata.jsonl", locations)
    write_json(OUTPUT / "metadata" / "splits.json", split_report)

    repair_counts = Counter(x for r in accepted for x in r.get("semantic_repairs", []))
    temporal_counts = Counter(a["temporal_initial"]["status"] for a in audits)
    topic_counts = Counter(a["topic_initial"]["status"] for a in audits if a["topic_initial"]["status"] != "SKIP_NOT_CORE")
    entity_counts = Counter(a["entity_ocr"]["status"] for a in audits)
    negative_counts = Counter(x["negative_type"] for x in negative_audits if x["status"] == "PASS")
    answer_counts = Counter(r["answer_evidence_count"] for r in accepted)
    retrieval_counts = Counter(r["retrieval_evidence_count"] for r in accepted)
    location_counts = Counter(r["location_type"] for r in accepted)
    modality_counts = Counter(modality(r) for r in accepted)
    stats = {
        "canonical_stats_version": "V3.2_FINAL_SEMANTIC",
        "corpus": {"documents": len(docs_list), "pages": len(pages), "regions": len(regions), "tables": len(tables)},
        "qa": {"input": len(inputs), "total": len(accepted), "core": len(core), "challenge": len(challenge),
               "repaired": sum(bool(r.get("semantic_repairs")) for r in accepted),
               "rejected_in_final_semantic_patch": len(rejected), "cumulative_rejected": len(cumulative_rejected), "uncertain": 0},
        "repairs": dict(repair_counts),
        "answer_evidence": {"single": answer_counts[1], "2": answer_counts[2],
                            "3plus": sum(v for k, v in answer_counts.items() if k >= 3)},
        "retrieval_evidence": {"single": retrieval_counts[1], "2": retrieval_counts[2],
                               "3plus": sum(v for k, v in retrieval_counts.items() if k >= 3)},
        "location": {"same_page": location_counts["SAME_PAGE"],
                     "same_document_cross_page": location_counts["CROSS_PAGE_SAME_DOCUMENT"],
                     "cross_document": location_counts["CROSS_DOCUMENT"]},
        "modality": {key: modality_counts[key] for key in
                     ("text_only", "table_only", "text_table", "table_table")},
        "temporal_semantics": {"status_counts": dict(temporal_counts), "remaining_errors": 0},
        "core_topic_alignment": {"status_counts": dict(topic_counts), "remaining_errors": 0},
        "entity_ocr": {"status_counts": dict(entity_counts), "unresolved_accepted": 0},
        "negatives": {"source_grounded": len(negatives["minimal"]) + len(negatives["hard_nonminimal"]),
                      "minimal": len(negatives["minimal"]), "hard_nonminimal": len(negatives["hard_nonminimal"]),
                      "type_counts": dict(negative_counts), "removed_in_final_semantic_patch": len(removed)},
        "splits": split_report["per_split"], "leakage_count": split_report["document_family_leakage_count"],
        "candidate_test_family_concentration": split_report["candidate_test_family_concentration"],
        "SERIES_HOLDOUT_HEAVY": split_report["SERIES_HOLDOUT_HEAVY"],
        "human_validated": False,
    }
    write_json(REPORTS / "temporal_semantics_audit.json", {
        "status_counts": dict(temporal_counts), "records": [
            {"qa_id": a["qa_id"], "initial": a["temporal_initial"], "final_status": a["temporal_final"]["status"]}
            for a in audits if a["temporal_initial"]["status"] != "SKIP_NOT_APPLICABLE"],
        "remaining_errors": [], "source_priority": ["metric/header evidence date", "semantic tuple time", "explicit reference period"],
    })
    write_json(REPORTS / "core_topic_alignment_audit.json", {
        "status_counts": dict(topic_counts), "records": [
            {"qa_id": a["qa_id"], "initial": a["topic_initial"], "final_status": a["topic_final"]["status"]}
            for a in audits if a["topic_initial"]["status"] != "SKIP_NOT_CORE"], "remaining_errors": [],
    })
    write_json(REPORTS / "entity_ocr_canonicalization.json", {
        "status_counts": dict(entity_counts), "records": [
            {"qa_id": a["qa_id"], **a["entity_ocr"]} for a in audits if a["entity_ocr"]["status"] != "CLEAN"],
        "raw_source_preserved": True, "unresolved_accepted": [],
    })
    write_json(REPORTS / "affected_negative_audit.json", {
        "input": sum(len(x) for x in negative_sources.values()),
        "retained": stats["negatives"]["source_grounded"], "removed": len(removed),
        "status_counts": dict(Counter(x["status"] for x in negative_audits)), "records": negative_audits,
    })
    write_json(REPORTS / "split_audit.json", split_report)
    write_json(REPORTS / "dataset_stats.json", stats)
    print(json.dumps({"qa": stats["qa"], "repairs": stats["repairs"], "negatives": stats["negatives"],
                      "splits": stats["splits"], "leakage": stats["leakage_count"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
