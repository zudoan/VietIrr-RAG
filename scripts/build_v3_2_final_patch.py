"""Apply the narrow V3.2 final-freeze data patch.

Input is the immutable pre-patch snapshot.  The script creates no documents or
QA; it only audits/repairs existing records, filters affected negatives, and
reassigns whole leakage groups.
"""

from __future__ import annotations

import copy
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_v3_2_final import (  # noqa: E402
    ALLOWED_NEGATIVE_TYPES, challenge_relation_audit, evidence_texts, modality,
    necessity_at_two_levels, retrieval_mapping, validate_derivability,
    validate_table_semantics, validate_traceability,
)
from src.structure.semantic_table_parser import fold  # noqa: E402
from src.validation.necessity_validator_v3_1 import validate_necessity  # noqa: E402
from src.validation.ocr_quality_gate_v3_2_final import inspect_evidence, inspect_qa_ocr  # noqa: E402
from src.validation.table_metric_semantics_validator import (  # noqa: E402
    _signature, metric_raw, validate_table_metric_semantics,
)
from src.validation.topic_alignment_validator_v3_2 import validate_topic_alignment  # noqa: E402


SOURCE = ROOT / "snapshots" / "pre_v3_2_final_patch" / "data" / "v3_2_final"
OUTPUT = ROOT / "data" / "v3_2_final"
REPORTS = ROOT / "reports" / "v3_2_final"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def relation_aware_topic(row: dict, relation_status: str) -> dict:
    result = validate_topic_alignment(row.get("question", ""), row.get("answer", ""), evidence_texts(row))
    if result["status"] != "UNCERTAIN" or not row.get("relation_type") or relation_status != "PASS":
        return result
    match = re.search(r"(?:của|đối với)\s+(.+?)\s+và\s+", row.get("question", ""), re.I)
    entity = match.group(1).strip() if match else None
    source = " ".join(ev.get("claim_text") or ev.get("text") or "" for ev in row.get("gold_evidence", []))
    entity_aligned = bool(entity and fold(entity) in fold(row.get("answer", "")) and fold(entity) in fold(source))
    if entity_aligned:
        result.update({
            "status": "PASS", "errors": [], "primary_topic": "RELATION_STATE_ACTION",
            "entity": entity, "answer_topic_support": True, "evidence_topic_support": True,
            "validation_basis": "current relation intent plus explicit question/answer/evidence entity alignment",
        })
    return result


def apply_metric_repair(row: dict, metric_audit: dict) -> None:
    row["question_before_v3_2_final_patch"] = row["question"]
    row["question"] = metric_audit["proposed_question"]
    # For single-fact Core answers, the component validator uses metric_label.
    # Make that descriptive label exact while preserving raw/canonical source fields.
    if not row.get("relation_type"):
        index = 0
        for evidence in row.get("gold_evidence", []):
            if evidence.get("evidence_type") != "TABLE_CELL":
                continue
            phrase = metric_audit["signatures"][index]["phrase"]
            index += 1
            if evidence.get("metric_label") != phrase:
                evidence["metric_label_before_v3_2_final_patch"] = evidence.get("metric_label")
                evidence["metric_label"] = phrase


def process_qa(source: dict, docs: dict, evidence_ids: set[str], table_index: dict) -> tuple[dict | None, dict]:
    row = copy.deepcopy(source)
    initial_ocr = inspect_qa_ocr(row)
    metric_audit = validate_table_metric_semantics(row)
    reasons: list[str] = []
    if initial_ocr["status"] in {"REJECT", "UNCERTAIN"}:
        reasons.append(f"OCR_{initial_ocr['status']}")
    if metric_audit["status"] == "REJECT":
        reasons.extend(metric_audit.get("errors") or ["TABLE_METRIC_SEMANTICS_REJECT"])
    if metric_audit["status"] == "REPAIR" and not reasons:
        apply_metric_repair(row, metric_audit)

    relation = {"status": "NOT_APPLICABLE", "errors": [], "basis": []}
    if row.get("relation_type") and not reasons:
        row, relation_errors, _ = challenge_relation_audit(row)
        relation = row["relation_validation_v3_2"]
        reasons.extend(relation_errors)

    # Rebuild components and support from the current question, never from an old PASS.
    rebuilt = validate_necessity(row)
    row["answer_components"] = rebuilt["components"]
    row["evidence_support_matrix"] = rebuilt["support_matrix"]
    row["necessity_validation_v3_2_final"] = rebuilt
    mapping, mapping_errors = retrieval_mapping(row)
    two_level_necessity = necessity_at_two_levels(row, mapping)
    final_ocr = inspect_qa_ocr(row)
    post_metric = validate_table_metric_semantics(row)
    trace = validate_traceability(row, docs, evidence_ids)
    derivability = validate_derivability(row)
    table = validate_table_semantics(row, table_index)
    topic = relation_aware_topic(row, relation["status"])

    if final_ocr["status"] in {"REJECT", "UNCERTAIN"} and not any(x.startswith("OCR_") for x in reasons):
        reasons.append(f"OCR_{final_ocr['status']}")
    if post_metric["status"] not in {"KEEP", "SKIP_NOT_APPLICABLE"}:
        reasons.append("TABLE_METRIC_SEMANTICS_POST_REPAIR_FAIL")
    if trace["status"] != "PASS": reasons.extend(trace["errors"])
    if derivability["status"] != "PASS": reasons.extend(derivability["errors"])
    if table["status"] != "PASS": reasons.extend(table["errors"])
    if topic["status"] != "PASS": reasons.extend(topic["errors"])
    if rebuilt["necessity_status"] != "PASS": reasons.append("NECESSITY_REBUILD_FAIL")
    if two_level_necessity["answer_fact_necessity"]["status"] == "FAIL": reasons.append("ANSWER_FACT_NECESSITY_FAIL")
    if two_level_necessity["retrieval_unit_necessity"]["status"] == "FAIL": reasons.append("RETRIEVAL_UNIT_NECESSITY_FAIL")
    reasons.extend(mapping_errors)

    audit = {"qa_id": row["qa_id"], "ocr": initial_ocr, "metric": metric_audit,
             "metric_post_repair": post_metric, "rejection_reasons": sorted(set(reasons))}
    if reasons:
        row["status"] = "REJECTED"
        row["status_v3_2_final"] = "REJECTED_IN_FINAL_PATCH"
        row["rejection_reasons_v3_2_final"] = sorted(set(reasons))
        row["ocr_validation_v3_2_final"] = initial_ocr
        row["table_metric_semantics_v3_2_final"] = metric_audit
        row["human_validated"] = False
        return None, {**audit, "rejected_row": row}

    for key in ("answer_evidence_ids", "retrieval_evidence_ids", "answer_evidence_count",
                "retrieval_evidence_count", "retrieval_multi_evidence", "retrieval_three_plus",
                "location_type", "gold_doc_ids", "gold_page_ids", "gold_page_count", "page_span_same_document"):
        row[key] = mapping[key]
    row["same_page"] = mapping["location_type"] == "SAME_PAGE"
    row["cross_page"] = mapping["location_type"] == "CROSS_PAGE_SAME_DOCUMENT"
    row["answer_fact_necessity"] = two_level_necessity["answer_fact_necessity"]
    row["retrieval_unit_necessity"] = two_level_necessity["retrieval_unit_necessity"]
    row["ocr_status"] = final_ocr["status"]
    row["ocr_normalizations"] = final_ocr["normalizations"]
    row["ocr_validation_v3_2_final"] = final_ocr
    row["table_metric_semantics_v3_2_final"] = metric_audit
    row["validation_v3_2_final"] = {
        "source_traceability": trace, "question_answer_alignment": derivability,
        "topic_alignment": topic, "ocr_quality": {"status": final_ocr["status"]},
        "table_metric_semantics": post_metric, "table_semantics": table,
        "relation_intent": relation, "answer_evidence_mapping": {"status": "PASS"},
        "retrieval_evidence_mapping": {"status": "PASS", "errors": []},
        "necessity": {"status": "PASS", "rebuilt": rebuilt["necessity_status"]},
        "old_pass_used_as_acceptance": False,
    }
    row["status"] = "PASS"
    row["status_v3_2_final"] = "REPAIRED" if metric_audit["status"] == "REPAIR" else "KEEP"
    row["review_status"] = "DETERMINISTIC_REVIEWED"
    row["human_validated"] = False
    return row, audit


def negative_errors(row: dict, accepted: dict[str, dict], evidence_ids: set[str]) -> list[str]:
    errors = []
    parent = accepted.get(row.get("source_qa_id"))
    if not parent: errors.append("PARENT_QA_REJECTED")
    if not row.get("source_grounded"): errors.append("NOT_SOURCE_GROUNDED")
    if row.get("negative_type") not in ALLOWED_NEGATIVE_TYPES: errors.append("INVALID_NEGATIVE_TYPE")
    if not row.get("negative_evidence_id") or row.get("negative_evidence_id") not in evidence_ids:
        errors.append("UNRESOLVED_NEGATIVE_EVIDENCE")
    candidate = row.get("candidate_evidence") or []
    if not candidate: errors.append("METADATA_ONLY_NEGATIVE")
    listed = row.get("candidate_evidence_ids") or []
    actual = [item.get("evidence_id") for item in candidate]
    if listed != actual: errors.append("CANDIDATE_EVIDENCE_ID_MISMATCH")
    if any(eid not in evidence_ids for eid in listed): errors.append("UNRESOLVED_CANDIDATE_EVIDENCE")
    if any(inspect_evidence(item, f"candidate_evidence[{i}]")["status"] in {"REJECT", "UNCERTAIN"}
           for i, item in enumerate(candidate)):
        errors.append("OCR_CONTAMINATION")
    if parent and row.get("negative_type") not in {"PARTIAL_EVIDENCE_SET", "REDUNDANT_EVIDENCE_SET"}:
        if row.get("negative_evidence_id") in set(parent["answer_evidence_ids"]):
            errors.append("NEGATIVE_CONTAMINATED_BY_GOLD")
    # Once raw metric qualifiers become part of the target meaning, an alleged
    # WRONG_ENTITY/WRONG_UNIT negative may not silently mutate the metric too.
    # Temporal header changes remain legitimate WRONG_PERIOD mutations.
    if parent and row.get("negative_type") in {"WRONG_ENTITY", "WRONG_UNIT"}:
        parent_metrics = {_signature(metric_raw(ev))["key"] for ev in parent.get("gold_evidence", [])
                          if ev.get("evidence_type") == "TABLE_CELL"}
        candidate_metrics = {_signature(metric_raw(ev))["key"] for ev in candidate
                             if ev.get("evidence_type") == "TABLE_CELL"}
        if parent_metrics and candidate_metrics and parent_metrics != candidate_metrics:
            errors.append("NEGATIVE_LABEL_INVALID_AFTER_FULL_METRIC_SEMANTICS")
    if parent and row.get("negative_type") == "WRONG_METRIC":
        parent_metrics = {_signature(metric_raw(ev))["key"] for ev in parent.get("gold_evidence", [])
                          if ev.get("evidence_type") == "TABLE_CELL"}
        candidate_metrics = {_signature(metric_raw(ev))["key"] for ev in candidate
                             if ev.get("evidence_type") == "TABLE_CELL"}
        if parent_metrics and candidate_metrics and parent_metrics == candidate_metrics:
            errors.append("WRONG_METRIC_LABEL_WITH_SAME_FULL_METRIC")
    if row.get("negative_type") == "PARTIAL_EVIDENCE_SET" and parent:
        if not set(listed) < set(parent["answer_evidence_ids"]): errors.append("INVALID_PARTIAL_SET")
    return sorted(set(errors))


def optimize_splits(rows: list[dict]) -> tuple[dict[str, list[dict]], dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows: groups[row["leakage_group_id"]].append(row)
    candidate_groups = {gid for gid, members in groups.items() if any(r.get("split") == "candidate_test" for r in members)}
    remaining = [(gid, members) for gid, members in sorted(groups.items()) if gid not in candidate_groups]
    target_total, target_multi = round(len(rows) * 0.17), 25
    # State retains the most stratified selection for each (size, retrieval-multi).
    states: dict[tuple[int, int], tuple[float, tuple[str, ...]]] = {(0, 0): (0.0, ())}
    for gid, members in remaining:
        n = len(members); multi = sum(r["retrieval_evidence_count"] >= 2 for r in members)
        challenge = sum(bool(r.get("relation_type")) for r in members)
        three = sum(r["retrieval_evidence_count"] >= 3 for r in members)
        cross = sum(r["location_type"] != "SAME_PAGE" for r in members)
        modalities = len({modality(r) for r in members})
        feature = challenge + three * 3 + cross * 2 + modalities * 2
        for (total, old_multi), (score, selected) in list(states.items())[::-1]:
            key = total + n, old_multi + multi
            if key[0] > round(len(rows) * .21) or key[1] > 30: continue
            candidate = (score + feature, selected + (gid,))
            if key not in states or candidate[0] > states[key][0]: states[key] = candidate
    viable = [(key, value) for key, value in states.items()
              if round(len(rows) * .14) <= key[0] <= round(len(rows) * .21) and 20 <= key[1] <= 30]
    if not viable:
        viable = [(key, value) for key, value in states.items() if key[1] >= 15]
    if not viable: raise RuntimeError("No leakage-safe dev grouping reaches 15 retrieval-multi QA")
    (dev_total, dev_multi), (_, chosen) = min(
        viable, key=lambda item: (abs(item[0][0] - target_total) * 5 + abs(item[0][1] - target_multi) * 12,
                                  -item[1][0], len(item[1][1])))
    dev_groups = set(chosen)
    outputs = {"train": [], "dev": [], "candidate_test": []}
    assignments = []
    for gid, members in sorted(groups.items()):
        split = "candidate_test" if gid in candidate_groups else "dev" if gid in dev_groups else "train"
        doc_ids = sorted({doc for row in members for doc in row["gold_doc_ids"]})
        assignments.append({"leakage_group_id": gid, "split": split, "qa_count": len(members),
                            "retrieval_multi": sum(r["retrieval_evidence_count"] >= 2 for r in members),
                            "challenge": sum(bool(r.get("relation_type")) for r in members), "doc_ids": doc_ids})
        for source in members:
            row = copy.deepcopy(source); row["split"] = split; outputs[split].append(row)
    doc_sets = {name: {doc for row in part for doc in row["gold_doc_ids"]} for name, part in outputs.items()}
    overlaps = {f"{a}__{b}": sorted(doc_sets[a] & doc_sets[b]) for a, b in
                (("train", "dev"), ("train", "candidate_test"), ("dev", "candidate_test"))}
    candidate_counts = Counter(row["leakage_group_id"] for row in outputs["candidate_test"])
    top_gid, top_count = candidate_counts.most_common(1)[0]
    concentration = top_count / len(outputs["candidate_test"])
    audit = {
        "optimizer": "whole leakage-group dynamic programming",
        "optimizer_strata": ["core/challenge", "retrieval single/multi/3+", "same/cross page/cross document",
                              "text/table/text+table/table+table", "document/report/temporal family"],
        "dev_target_total": target_total, "dev_target_retrieval_multi": target_multi,
        "dev_achieved_total": dev_total, "dev_achieved_retrieval_multi": dev_multi,
        "assignments": assignments, "document_overlaps": overlaps,
        "document_family_leakage_count": sum(len(v) for v in overlaps.values()),
        "leakage_audit_pass": not any(overlaps.values()),
        "candidate_test_family_concentration": {"top_family": top_gid, "qa_count": top_count,
                                                   "total": len(outputs["candidate_test"]),
                                                   "share": concentration},
        "SERIES_HOLDOUT_HEAVY": concentration >= 0.5,
    }
    return outputs, audit


def evidence_buckets(rows: list[dict], key: str) -> dict:
    values = Counter(row[key] for row in rows)
    return {"single": values[1], "2": values[2], "3plus": sum(n for k, n in values.items() if k >= 3)}


def split_stats(rows: list[dict]) -> dict:
    return {"total": len(rows), "core": sum(not r.get("relation_type") for r in rows),
            "challenge": sum(bool(r.get("relation_type")) for r in rows),
            "retrieval_multi": sum(r["retrieval_evidence_count"] >= 2 for r in rows),
            "retrieval_three_plus": sum(r["retrieval_evidence_count"] >= 3 for r in rows),
            "same_page": sum(r["location_type"] == "SAME_PAGE" for r in rows),
            "same_document_cross_page": sum(r["location_type"] == "CROSS_PAGE_SAME_DOCUMENT" for r in rows),
            "cross_document": sum(r["location_type"] == "CROSS_DOCUMENT" for r in rows),
            "modalities": dict(Counter(modality(r) for r in rows))}


def main() -> None:
    inputs = read_jsonl(SOURCE / "all_qa.jsonl")
    old_rejected = read_jsonl(SOURCE / "rejected_qa.jsonl")
    docs_list = read_jsonl(ROOT / "data" / "v3_1" / "metadata" / "documents.jsonl")
    docs = {row["doc_id"]: row for row in docs_list}
    pages = read_jsonl(ROOT / "data" / "pages.jsonl")
    regions = read_jsonl(ROOT / "data" / "parsed" / "regions.jsonl")
    tables = read_jsonl(ROOT / "data" / "parsed" / "tables.jsonl")
    table_index = {row["table_id"]: row for row in tables}
    evidence_ids = {row["region_id"] for row in regions}
    evidence_ids.update(tup["tuple_id"] for table in tables for tup in table.get("semantic_tuples", []))
    evidence_ids.update(table_index)

    accepted, patch_rejected, audit_rows = [], [], []
    for source in inputs:
        row, audit = process_qa(source, docs, evidence_ids, table_index)
        audit_rows.append(audit)
        if row is None: patch_rejected.append(audit.pop("rejected_row"))
        else: accepted.append(row)
    accepted_index = {row["qa_id"]: row for row in accepted}

    negative_inputs = {
        "minimal": read_jsonl(SOURCE / "negatives" / "minimal_negatives.jsonl"),
        "hard_nonminimal": read_jsonl(SOURCE / "negatives" / "hard_nonminimal_negatives.jsonl"),
    }
    old_rejected_negatives = read_jsonl(SOURCE / "negatives" / "rejected_negatives.jsonl")
    negatives = {"minimal": [], "hard_nonminimal": []}
    removed_negatives = []
    repaired_parent_refs = 0
    for kind, source_rows in negative_inputs.items():
        for source in source_rows:
            row = copy.deepcopy(source)
            parent = accepted_index.get(row.get("source_qa_id"))
            if parent and row.get("question") != parent.get("question"):
                row["question_before_v3_2_final_patch"] = row.get("question")
                row["question"] = parent["question"]
                row["parent_question_reference_repaired"] = True
                repaired_parent_refs += 1
            errors = negative_errors(row, accepted_index, evidence_ids)
            if errors:
                row["negative_status_v3_2_final"] = "REJECTED"
                row["validation_errors_v3_2_final"] = errors
                removed_negatives.append(row)
            else:
                row["negative_status_v3_2_final"] = "VALID"
                row["validation_errors_v3_2_final"] = []
                row["review_status"] = "DETERMINISTIC_REVIEWED"
                row["human_validated"] = False
                negatives[kind].append(row)

    splits, split_audit = optimize_splits(accepted)
    split_lookup = {row["qa_id"]: (name, row["leakage_group_id"]) for name, rows in splits.items() for row in rows}
    for row in accepted: row["split"], row["leakage_group_id"] = split_lookup[row["qa_id"]]
    accepted.sort(key=lambda r: r["qa_id"])
    core = [r for r in accepted if not r.get("relation_type")]
    challenge = [r for r in accepted if r.get("relation_type")]
    cumulative_rejected = sorted(old_rejected + patch_rejected, key=lambda r: r["qa_id"])

    write_jsonl(OUTPUT / "all_qa.jsonl", accepted)
    write_jsonl(OUTPUT / "core_qa.jsonl", core)
    write_jsonl(OUTPUT / "challenge_qa.jsonl", challenge)
    write_jsonl(OUTPUT / "rejected_qa.jsonl", cumulative_rejected)
    write_jsonl(OUTPUT / "uncertain_qa.jsonl", [])
    for name, rows in splits.items(): write_jsonl(OUTPUT / f"{name}.jsonl", sorted(rows, key=lambda r: r["qa_id"]))
    write_jsonl(OUTPUT / "negatives" / "minimal_negatives.jsonl", negatives["minimal"])
    write_jsonl(OUTPUT / "negatives" / "hard_nonminimal_negatives.jsonl", negatives["hard_nonminimal"])
    write_jsonl(OUTPUT / "negatives" / "rejected_negatives.jsonl", old_rejected_negatives + removed_negatives)

    mappings, locations = [], []
    for row in accepted:
        mapping, _ = retrieval_mapping(row); mappings.append(mapping)
        locations.append({k: mapping[k] for k in ("qa_id", "location_type", "gold_doc_ids", "gold_page_ids",
                                                   "gold_page_count", "page_span_same_document")})
    write_jsonl(OUTPUT / "metadata" / "retrieval_evidence_map.jsonl", mappings)
    write_jsonl(OUTPUT / "metadata" / "page_location_metadata.jsonl", locations)
    write_json(OUTPUT / "metadata" / "splits.json", split_audit)

    ocr_counts = Counter(item["ocr"]["status"] for item in audit_rows)
    metric_rows = [item for item in audit_rows if item["metric"]["status"] != "SKIP_NOT_APPLICABLE"]
    metric_counts = Counter(item["metric"]["status"] for item in metric_rows)
    location = Counter(row["location_type"] for row in accepted)
    modalities = Counter(modality(row) for row in accepted)
    answer = evidence_buckets(accepted, "answer_evidence_count")
    retrieval = evidence_buckets(accepted, "retrieval_evidence_count")
    per_split = {name: split_stats(rows) for name, rows in splits.items()}
    stats = {
        "canonical_stats_version": "V3.2_FINAL_PATCH",
        "corpus": {"documents": len(docs_list), "pages": len(pages), "regions": len(regions), "tables": len(tables)},
        "qa": {"input": len(inputs), "total": len(accepted), "core": len(core), "challenge": len(challenge),
               "rejected_in_final_patch": len(patch_rejected), "cumulative_rejected": len(cumulative_rejected), "uncertain": 0},
        "answer_evidence": answer, "retrieval_evidence": retrieval,
        "location": {"same_page": location["SAME_PAGE"],
                     "same_document_cross_page": location["CROSS_PAGE_SAME_DOCUMENT"],
                     "cross_document": location["CROSS_DOCUMENT"]},
        "modality": {key: modalities[key] for key in ("text_only", "table_only", "text_table", "table_table")},
        "ocr": {"clean": ocr_counts["CLEAN"], "normalized": ocr_counts["NORMALIZED"],
                "rejected": ocr_counts["REJECT"], "uncertain": ocr_counts["UNCERTAIN"], "unresolved_accepted": 0},
        "table_metric_semantics": {"audited": len(metric_rows), "kept": metric_counts["KEEP"],
                                   "repaired": metric_counts["REPAIR"], "rejected": metric_counts["REJECT"],
                                   "repairs_in_final_accepted": sum(r["table_metric_semantics_v3_2_final"]["status"] == "REPAIR" for r in accepted),
                                   "remaining_semantic_errors": 0},
        "negatives": {"source_grounded": len(negatives["minimal"]) + len(negatives["hard_nonminimal"]),
                      "minimal": len(negatives["minimal"]), "hard_nonminimal": len(negatives["hard_nonminimal"]),
                      "removed_in_final_patch": len(removed_negatives), "parent_references_repaired": repaired_parent_refs},
        "splits": per_split, "leakage_count": split_audit["document_family_leakage_count"],
        "candidate_test_family_concentration": split_audit["candidate_test_family_concentration"],
        "SERIES_HOLDOUT_HEAVY": split_audit["SERIES_HOLDOUT_HEAVY"],
        "human_validated": False,
    }
    write_json(REPORTS / "dataset_stats.json", stats)
    write_json(REPORTS / "ocr_cleanup.json", {
        "counts": stats["ocr"], "accepted_normalizations": [
            {"qa_id": row["qa_id"], "normalizations": row["ocr_normalizations"]}
            for row in accepted if row["ocr_status"] == "NORMALIZED"],
        "rejected": [{"qa_id": row["qa_id"], "reasons": row["rejection_reasons_v3_2_final"]}
                     for row in patch_rejected if any(x.startswith("OCR_") for x in row["rejection_reasons_v3_2_final"])],
        "unresolved_accepted": [], "human_validated": False,
    })
    write_json(REPORTS / "table_metric_repair.json", {
        "counts": stats["table_metric_semantics"],
        "records": [{"qa_id": item["qa_id"], "classification": item["metric"]["status"],
                     "source_signatures": item["metric"].get("signatures", []),
                     "missing_qualifiers": item["metric"].get("missing_qualifiers", []),
                     "proposed_question": item["metric"].get("proposed_question"),
                     "rejection_errors": item["metric"].get("errors", [])} for item in metric_rows],
        "answer_values_changed": 0, "evidence_ids_changed": 0, "human_validated": False,
    })
    write_json(REPORTS / "split_audit.json", split_audit)
    print(json.dumps({"qa": stats["qa"], "ocr": stats["ocr"],
                      "table_metric_semantics": stats["table_metric_semantics"],
                      "negatives": stats["negatives"], "splits": stats["splits"],
                      "leakage": stats["leakage_count"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
