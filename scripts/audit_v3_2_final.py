"""Independent, read-back verification of the frozen V3.2 artifacts."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_v3_2_final import classify_text_intent, negative_has_broken_ocr, table_red_flag
from src.validation.ocr_quality_gate_v3_2 import inspect_qa_ocr
from src.validation.topic_alignment_validator_v3_2 import validate_topic_alignment

DATA = ROOT / "data" / "v3_2_final"
REPORTS = ROOT / "reports" / "v3_2"


def load_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    core = load_lines(DATA / "core_qa.jsonl")
    challenge = load_lines(DATA / "challenge_qa.jsonl")
    all_qa = load_lines(DATA / "all_qa.jsonl")
    rejected = load_lines(DATA / "rejected_qa.jsonl")
    uncertain = load_lines(DATA / "uncertain_qa.jsonl")
    maps = load_lines(DATA / "metadata" / "retrieval_evidence_map.jsonl")
    minimal = load_lines(DATA / "negatives" / "minimal_negatives.jsonl")
    hard = load_lines(DATA / "negatives" / "hard_nonminimal_negatives.jsonl")
    stats = json.loads((REPORTS / "dataset_stats.json").read_text(encoding="utf-8"))
    ready = json.loads((REPORTS / "V3_2_FREEZE_READINESS.json").read_text(encoding="utf-8"))
    split_meta = json.loads((DATA / "metadata" / "splits.json").read_text(encoding="utf-8"))
    regions = load_lines(ROOT / "data" / "parsed" / "regions.jsonl")
    tables = load_lines(ROOT / "data" / "parsed" / "tables.jsonl")
    evidence_ids = {r["region_id"] for r in regions} | {t["table_id"] for t in tables}
    evidence_ids |= {x["tuple_id"] for t in tables for x in t.get("semantic_tuples", [])}
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition: errors.append(message)

    accepted_ids = [row["qa_id"] for row in all_qa]
    require(len(core) + len(challenge) == len(all_qa), "CORE_CHALLENGE_TOTAL_MISMATCH")
    require(len(set(accepted_ids)) == len(accepted_ids), "DUPLICATE_ACCEPTED_QA_ID")
    require({r["qa_id"] for r in core + challenge} == set(accepted_ids), "CANONICAL_QA_SET_MISMATCH")
    require(not set(accepted_ids) & {r["qa_id"] for r in rejected + uncertain}, "ACCEPTED_REJECTED_OVERLAP")
    require(len(all_qa) + len(rejected) + len(uncertain) == stats["input_qa"], "INPUT_ACCOUNTING_MISMATCH")
    require(len(maps) == len(all_qa), "MAPPING_CARDINALITY_MISMATCH")
    map_index = {row["qa_id"]: row for row in maps}

    for row in all_qa:
        qid = row["qa_id"]
        mapping = map_index.get(qid, {})
        answer_ids = [ev.get("evidence_id") for ev in row.get("gold_evidence", [])]
        retrieval_ids = []
        for ev in row.get("gold_evidence", []):
            rid = ev.get("table_id") if ev.get("evidence_type") == "TABLE_CELL" else ev.get("region_id") or ev.get("evidence_id")
            if rid not in retrieval_ids: retrieval_ids.append(rid)
            require(ev.get("evidence_id") in evidence_ids, f"{qid}:UNRESOLVED_EVIDENCE")
            if ev.get("evidence_type") == "TABLE_CELL":
                require(table_red_flag(ev.get("entity"), True) is None, f"{qid}:BAD_ENTITY")
                require(table_red_flag(ev.get("metric_raw") or ev.get("metric"), False) is None, f"{qid}:BAD_METRIC")
        require(answer_ids == row["answer_evidence_ids"] == mapping.get("answer_evidence_ids"), f"{qid}:ANSWER_MAPPING")
        require(retrieval_ids == row["retrieval_evidence_ids"] == mapping.get("retrieval_evidence_ids"), f"{qid}:RETRIEVAL_MAPPING")
        require(len(answer_ids) == row["answer_evidence_count"], f"{qid}:ANSWER_COUNT")
        require(len(retrieval_ids) == row["retrieval_evidence_count"], f"{qid}:RETRIEVAL_COUNT")
        docs = {ev.get("doc_id") for ev in row["gold_evidence"]}; pages = {ev.get("page_id") for ev in row["gold_evidence"]}
        expected = "CROSS_DOCUMENT" if len(docs) > 1 else "CROSS_PAGE_SAME_DOCUMENT" if len(pages) > 1 else "SAME_PAGE"
        require(row["location_type"] == expected, f"{qid}:LOCATION")
        require(not (expected == "CROSS_DOCUMENT" and row.get("cross_page")), f"{qid}:CROSS_DOCUMENT_AS_CROSS_PAGE")
        require(inspect_qa_ocr(row)["status"] != "BROKEN", f"{qid}:BROKEN_OCR")
        require(row["answer_fact_necessity"]["status"] != "FAIL", f"{qid}:ANSWER_NECESSITY")
        require(row["retrieval_unit_necessity"]["status"] != "FAIL", f"{qid}:RETRIEVAL_NECESSITY")

    for row in core:
        result = validate_topic_alignment(row["question"], row["answer"], [" | ".join(str(ev.get(k) or "") for k in ("text", "entity", "metric_raw", "metric_label", "metric", "unit", "value")) for ev in row["gold_evidence"]])
        require(result["status"] == "PASS", f"{row['qa_id']}:TOPIC_ALIGNMENT")
    relation_suffix = {
        "TABLE_TO_TEXT_ACTION": "ACTION", "TABLE_TO_TEXT_RECOMMENDATION": "RECOMMENDATION",
        "TABLE_TO_TEXT_EXPLANATION": "EXPLANATION", "TABLE_TO_TEXT_FORECAST": "FORECAST",
        "TABLE_TO_TEXT_EXCEPTION": "EXCEPTION", "OTHER_VALID_RELATION": "OTHER_VALID_RELATION",
    }
    for row in challenge:
        if row.get("relation_type") in relation_suffix and any(ev.get("evidence_type") == "TABLE_CELL" for ev in row["gold_evidence"]):
            text = " ".join(ev.get("claim_text") or ev.get("text") or "" for ev in row["gold_evidence"] if ev.get("evidence_type") != "TABLE_CELL")
            require(classify_text_intent(text) == relation_suffix[row["relation_type"]], f"{row['qa_id']}:RELATION_INTENT")
        require((row.get("necessity_validation_v3_2") or {}).get("necessity_status") == "PASS", f"{row['qa_id']}:REBUILT_NECESSITY")

    accepted = set(accepted_ids)
    for row in minimal + hard:
        require(row.get("source_qa_id") in accepted, f"{row['negative_id']}:BAD_PARENT")
        require(row.get("source_grounded") is True, f"{row['negative_id']}:NOT_GROUNDED")
        require(row.get("negative_evidence_id") in evidence_ids, f"{row['negative_id']}:BAD_EVIDENCE")
        require(not negative_has_broken_ocr(row), f"{row['negative_id']}:OCR")

    split_rows = {name: load_lines(DATA / f"{name}.jsonl") for name in ("train", "dev", "candidate_test")}
    split_ids = [r["qa_id"] for rows in split_rows.values() for r in rows]
    require(len(split_ids) == len(set(split_ids)) == len(all_qa), "SPLIT_QA_CARDINALITY")
    require(set(split_ids) == set(accepted_ids), "SPLIT_QA_SET")
    require(sum(bool(r.get("relation_type")) for r in split_rows["dev"]) > 0, "DEV_HAS_NO_CHALLENGE")
    require(split_meta["document_family_leakage_count"] == 0 and split_meta["leakage_audit_pass"], "FAMILY_LEAKAGE")

    answer_counts = Counter(r["answer_evidence_count"] for r in all_qa)
    retrieval_counts = Counter(r["retrieval_evidence_count"] for r in all_qa)
    require(stats["answer_level_evidence"] == {"single": answer_counts[1], "2": answer_counts[2], "3plus": sum(v for k, v in answer_counts.items() if k >= 3)}, "ANSWER_STATS")
    require(stats["retrieval_level_evidence"] == {"single": retrieval_counts[1], "2": retrieval_counts[2], "3plus": sum(v for k, v in retrieval_counts.items() if k >= 3)}, "RETRIEVAL_STATS")
    require(all(ready.get(key) is True for key in ("QA_SEMANTIC_ALIGNMENT_PASS", "RELATION_INTENT_PASS", "RETRIEVAL_EVIDENCE_MAPPING_PASS", "NECESSITY_PASS", "OCR_QUALITY_PASS", "TABLE_SEMANTIC_PASS", "SOURCE_TRACEABILITY_PASS", "NEGATIVE_VALIDATION_PASS", "LEAKAGE_AUDIT_PASS", "REPORT_CONSISTENCY_PASS")), "READINESS_GATE_FALSE")
    require(ready["HUMAN_VALIDATED"] is False, "HUMAN_VALIDATION_MISLABEL")
    require(ready["DATASET_FROZEN"] is True and ready["DEV_CHALLENGE_QA"] > 0, "INVALID_FREEZE")
    require((ROOT / "snapshots" / "pre_v3_2_final_freeze" / "SNAPSHOT_MANIFEST.json").exists(), "PRE_FREEZE_SNAPSHOT_MISSING")

    result = {"status": "PASS" if not errors else "FAIL", "error_count": len(errors), "errors": errors[:100],
              "verified": {"qa": len(all_qa), "negatives": len(minimal) + len(hard), "mapping_rows": len(maps),
                           "dev_challenge": sum(bool(r.get("relation_type")) for r in split_rows["dev"]),
                           "family_leakage": split_meta["document_family_leakage_count"]}}
    (REPORTS / "V3_2_INDEPENDENT_VERIFICATION.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksums = {}
    for path in sorted(list(DATA.rglob("*")) + list(REPORTS.rglob("*"))):
        if path.is_file() and path.name != "V3_2_CHECKSUMS.json":
            checksums[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    (REPORTS / "V3_2_CHECKSUMS.json").write_text(json.dumps(checksums, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors: raise SystemExit(1)


if __name__ == "__main__": main()
