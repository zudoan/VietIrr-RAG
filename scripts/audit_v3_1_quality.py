"""Run fail-closed V3.1 semantic, alignment, traceability, and label audits."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.io_utils import read_jsonl, write_json
from src.structure.semantic_table_parser import fold


DATE_LIKE = re.compile(r"(?:\d{1,2}[/-]){1,2}\d{2,4}|20\d{2}", re.I)
ROMAN = re.compile(r"[IVXLCDM]+", re.I)
NUMERIC_SEQUENCE = re.compile(r"[\d\s,.;/-]+")
BLOCKED = {"tt", "stt", "date", "year", "ngay", "thang", "nam", "index", "row", "column"}


def template(question: str) -> str:
    value = fold(question)
    value = re.sub(r"\b\d+(?:[.,/-]\d+)*\b", "#", value)
    value = re.sub(r"\b20\d{2}\b", "YEAR", value)
    value = re.sub(r"\s+", " ", value)
    return value


def table_red_flag(raw: str | None, is_entity: bool) -> str | None:
    raw = (raw or "").strip()
    normalized = fold(raw)
    if normalized in BLOCKED:
        return "TECHNICAL_COLUMN_AS_SEMANTIC_FIELD"
    if DATE_LIKE.fullmatch(raw):
        return "DATE_OR_YEAR_AS_SEMANTIC_FIELD"
    if is_entity and ROMAN.fullmatch(raw):
        return "ROMAN_NUMERAL_ENTITY"
    if is_entity and NUMERIC_SEQUENCE.fullmatch(raw):
        return "NUMERIC_SEQUENCE_ENTITY"
    return None


def main() -> None:
    docs = read_jsonl(ROOT / "data/v3_1/metadata/documents.jsonl")
    core = read_jsonl(ROOT / "data/v3_1/qa/core_qa.jsonl")
    challenge = read_jsonl(ROOT / "data/v3_1/qa/challenge_qa.jsonl")
    qa = core + challenge
    minimal = read_jsonl(ROOT / "data/v3_1/negatives/minimal_negatives.jsonl")
    partial = read_jsonl(ROOT / "data/v3_1/negatives/partial_sets.jsonl")
    redundant = read_jsonl(ROOT / "data/v3_1/negatives/redundant_sets.jsonl")
    negatives = minimal + partial + redundant
    tables = read_jsonl(ROOT / "data/parsed/tables.jsonl")
    regions = read_jsonl(ROOT / "data/parsed/regions.jsonl")
    doc_index = {d["doc_id"]: d for d in docs}
    table_index = {t["table_id"]: t for t in tables}
    evidence_ids = {r["region_id"] for r in regions}
    evidence_ids.update(tup["tuple_id"] for table in tables for tup in table.get("semantic_tuples", []))

    critical, examples, warnings = Counter(), {}, Counter()
    alignment_errors, table_errors, trace_errors, provenance_errors = [], [], [], []
    question_seen = set()
    label_counts = Counter()
    for row in qa + negatives:
        label_counts[row.get("review_status", "GENERATED")] += 1
    for row in qa:
        qid = row["qa_id"]
        if not row.get("question", "").endswith("?") or not row.get("answer"):
            alignment_errors.append(f"{qid}:MALFORMED_QA")
        qnorm = fold(row.get("question"))
        if qnorm in question_seen:
            critical["EXACT_DUPLICATE_QUESTION"] += 1; examples.setdefault("EXACT_DUPLICATE_QUESTION", []).append(qid)
        question_seen.add(qnorm)
        if row in core:
            checks = row.get("validation_v3_1") or {}
            if row.get("status") != "PASS" or any(v == "FAIL" for v in checks.values()):
                alignment_errors.append(f"{qid}:CORE_VALIDATION")
        else:
            if row.get("relation_validation_status") != "PASS" or not row.get("question_generated_after_relation_pass"):
                alignment_errors.append(f"{qid}:RELATION_ORDER")
            necessity = row.get("necessity_validation") or {}
            if row.get("necessity_status") != "PASS" or not necessity.get("ablation_executed"):
                alignment_errors.append(f"{qid}:NECESSITY")
            if any(v != "FULL_SUPPORT" for v in necessity.get("full_set_support", {}).values()):
                alignment_errors.append(f"{qid}:INCOMPLETE_FULL_SET_SUPPORT")
        for ev in row.get("gold_evidence", []):
            eid = ev.get("evidence_id")
            if eid not in evidence_ids:
                provenance_errors.append(f"{qid}:{eid}:UNRESOLVED")
            doc = doc_index.get(ev.get("doc_id"))
            if not doc or not doc.get("source_url") or not doc.get("sha256") or not doc.get("local_path"):
                trace_errors.append(f"{qid}:{ev.get('doc_id')}")
            if not ev.get("page_id") or ev.get("page_number") is None:
                provenance_errors.append(f"{qid}:{eid}:PAGE")
            if ev.get("evidence_type") == "TABLE_CELL":
                table = table_index.get(ev.get("table_id"))
                if not table or table.get("structural_quality") != "GOOD" or table.get("semantic_quality") != "GOOD":
                    table_errors.append(f"{qid}:{eid}:AMBIGUOUS_OR_UNRESOLVED_TABLE")
                tup = ev.get("semantic_tuple") or {}
                for raw, is_entity in (((tup.get("entity") or {}).get("raw"), True), ((tup.get("metric") or {}).get("raw"), False)):
                    flag = table_red_flag(raw, is_entity)
                    if flag:
                        critical[flag] += 1; examples.setdefault(flag, []).append(f"{qid}:{eid}")
    for row in negatives:
        nid = row["negative_id"]
        if row.get("semantic_validation") != "PASS" or row.get("negative_status") not in {"VALID_MINIMAL", "VALID_HARD_NONMINIMAL"}:
            alignment_errors.append(f"{nid}:NEGATIVE_VALIDATION")
        if row.get("negative_evidence_id") not in evidence_ids:
            provenance_errors.append(f"{nid}:NEGATIVE_EVIDENCE")
        if row.get("construction_method") in {"metadata_only", "query_rewrite"} or not row.get("source_grounded"):
            critical["ARTIFICIAL_NEGATIVE"] += 1; examples.setdefault("ARTIFICIAL_NEGATIVE", []).append(nid)

    templates = Counter(template(row["question"]) for row in challenge)
    top_template, top_count = templates.most_common(1)[0] if templates else (None, 0)
    relation_counts = Counter(row["relation_type"] for row in challenge)
    top_relation, top_relation_count = relation_counts.most_common(1)[0] if relation_counts else (None, 0)
    if top_relation_count / max(len(challenge), 1) > 0.25:
        warnings["RELATION_CONCENTRATION_OVER_25_PERCENT"] = 1
    if top_relation_count / max(len(challenge), 1) > 0.35:
        critical["RELATION_CONCENTRATION_OVER_35_PERCENT"] = 1
    result = {
        "critical_semantic_red_flags": sum(critical.values()), "critical_counts": dict(critical),
        "critical_examples": {k: v[:20] for k, v in examples.items()},
        "warnings": dict(warnings),
        "qa_alignment_pass": not alignment_errors,
        "table_semantic_pass": not table_errors and not any(k in critical for k in (
            "TECHNICAL_COLUMN_AS_SEMANTIC_FIELD", "DATE_OR_YEAR_AS_SEMANTIC_FIELD", "ROMAN_NUMERAL_ENTITY", "NUMERIC_SEQUENCE_ENTITY")),
        "provenance_validation_pass": not provenance_errors,
        "source_traceability_pass": not trace_errors,
        "real_relation_validation_pass": all(r.get("relation_validation_status") == "PASS" for r in challenge),
        "negative_source_grounding_pass": all(r.get("semantic_validation") == "PASS" and r.get("negative_evidence_id") in evidence_ids for r in negatives),
        "errors": {"alignment": alignment_errors[:50], "table": table_errors[:50], "provenance": provenance_errors[:50], "traceability": trace_errors[:50]},
        "review_provenance": {
            "GENERATED": label_counts.get("GENERATED", 0), "AUTO_VALIDATED": label_counts.get("AUTO_VALIDATED", 0),
            "DETERMINISTIC_REVIEWED": label_counts.get("DETERMINISTIC_REVIEWED", 0),
            "LLM_REVIEWED": label_counts.get("LLM_REVIEWED", 0), "HUMAN_REVIEWED": label_counts.get("HUMAN_REVIEWED", 0),
        },
        "challenge_distribution": {
            "relations": dict(relation_counts), "top_relation": top_relation,
            "top_relation_share": round(top_relation_count / max(len(challenge), 1), 4),
            "unique_normalized_templates": len(templates), "top_template": top_template,
            "top_template_count": top_count, "top_template_share": round(top_count / max(len(challenge), 1), 4),
        },
        "scanned": {"qa": len(qa), "challenge": len(challenge), "negatives": len(negatives)},
    }
    result["scan_status"] = "PASS" if result["critical_semantic_red_flags"] == 0 and all(result[k] for k in (
        "qa_alignment_pass", "table_semantic_pass", "provenance_validation_pass", "source_traceability_pass",
        "real_relation_validation_pass", "negative_source_grounding_pass")) else "FAIL"
    write_json(ROOT / "reports/v3_1/semantic_red_flag_scan.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
