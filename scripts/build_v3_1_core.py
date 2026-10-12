"""Re-audit V3 core QA under V3.1 domain, source, and semantic rules."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evidence.relation_discovery import METRIC_LABELS
from src.structure.semantic_table_parser import clean, fold
from src.validation.answer_component_extractor_v3_1 import extract_answer_components
from src.validation.necessity_validator_v3_1 import judge_support


DOMAIN_TERMS = (
    "thuy loi", "tai nguyen nuoc", "ho chua", "van hanh", "thuy van", "cap nuoc",
    "han han", "thieu nuoc", "do man", "xam nhap man", "chat luong nuoc", "lu lut",
    "luu luong", "muc nuoc", "luong mua", "cong", "kenh", "de dieu", "dap",
    "nguon nuoc", "tuoi", "nong nghiep", "phong chong thien tai",
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def enrich_evidence(ev: dict) -> dict:
    result = dict(ev)
    if ev.get("evidence_type") == "TABLE_CELL":
        tup = ev.get("semantic_tuple") or {}
        result.update({
            "entity": (tup.get("entity") or {}).get("raw"),
            "entity_canonical": (tup.get("entity") or {}).get("canonical"),
            "metric": (tup.get("metric") or {}).get("canonical"),
            "metric_label": METRIC_LABELS.get((tup.get("metric") or {}).get("canonical"), ((tup.get("metric") or {}).get("raw"), ()))[0],
            "value": (tup.get("value") or {}).get("raw"),
            "unit": (tup.get("unit") or {}).get("raw") or (tup.get("unit") or {}).get("normalized"),
            "unit_normalized": (tup.get("unit") or {}).get("normalized"),
        })
    return result


def validate_core(row: dict, docs: dict[str, dict], evidence_ids: set[str]) -> tuple[bool, list[str], dict]:
    errors = []
    doc = docs.get(row.get("doc_id"))
    if not doc:
        errors.append("UNRESOLVED_DOCUMENT")
    elif doc.get("document_type_v3_1") == "supporting_reference":
        errors.append("SUPPORTING_REFERENCE_EXCLUDED")
    if not row.get("question", "").endswith("?") or len(row.get("question", "")) < 25:
        errors.append("UNNATURAL_QUESTION_FORM")
    if re.search(r"\b(?:Wtb|Whi|column|row|page_id|table_id|cell_ref)\b", row.get("question", ""), re.I):
        errors.append("SCHEMA_LIKE_QUESTION")
    domain_text = fold(f"{row.get('question', '')} {row.get('answer', '')} {doc.get('title', '') if doc else ''}")
    if not any(term in domain_text for term in DOMAIN_TERMS):
        errors.append("DOMAIN_RELEVANCE_FAIL")
    evidence = [enrich_evidence(ev) for ev in row.get("gold_evidence", [])]
    if len(evidence) != 1 or evidence[0].get("evidence_id") not in evidence_ids:
        errors.append("UNRESOLVED_OR_NON_SINGLE_EVIDENCE")
    components = extract_answer_components(row.get("question", ""), row.get("answer", ""))
    support_matrix = {}
    if evidence:
        support_matrix = {comp["component_id"]: {evidence[0]["evidence_id"]: judge_support(comp, evidence[0])} for comp in components}
        if any(next(iter(values.values())) != "FULL_SUPPORT" for values in support_matrix.values()):
            errors.append("ANSWER_NOT_FULLY_DERIVABLE")
    if evidence and evidence[0].get("evidence_type") == "TEXT_REGION":
        if evidence[0].get("text_extraction") != "NATIVE_TEXT":
            errors.append("OCR_CORE_QA_EXCLUDED")
        if fold(row.get("answer", "")).strip(" .;:") not in fold(evidence[0].get("text", "")).strip(" .;:"):
            errors.append("TEXT_ANSWER_NOT_EXTRACTIVE")
    if doc and not (doc.get("source_url") and doc.get("sha256") and doc.get("local_path")):
        errors.append("SOURCE_TRACEABILITY_FAIL")
    reviewed = dict(row)
    reviewed["review_status"] = "AUTO_VALIDATED"
    reviewed["human_validated"] = False
    reviewed["document_type"] = doc.get("document_type_v3_1") if doc else None
    reviewed["gold_evidence"] = evidence
    reviewed["answer_components"] = components
    reviewed["evidence_support_matrix"] = support_matrix
    reviewed["necessity_status"] = "NOT_APPLICABLE_SINGLE_EVIDENCE"
    reviewed.pop("necessity_ablation", None)
    reviewed["validation_v3_1"] = {
        "source_traceability": "PASS" if "SOURCE_TRACEABILITY_FAIL" not in errors else "FAIL",
        "domain_relevance": "PASS" if "DOMAIN_RELEVANCE_FAIL" not in errors else "FAIL",
        "question_naturalness": "PASS" if not {"UNNATURAL_QUESTION_FORM", "SCHEMA_LIKE_QUESTION"} & set(errors) else "FAIL",
        "answer_derivability": "PASS" if "ANSWER_NOT_FULLY_DERIVABLE" not in errors and "TEXT_ANSWER_NOT_EXTRACTIVE" not in errors else "FAIL",
        "table_semantics": "PASS" if evidence and evidence[0].get("evidence_type") == "TABLE_CELL" else "NOT_APPLICABLE",
    }
    reviewed["validation_errors_v3_1"] = errors
    reviewed["status"] = "PASS" if not errors else "REJECT"
    return not errors, errors, reviewed


def main() -> None:
    docs = {row["doc_id"]: row for row in read_jsonl(ROOT / "data" / "v3_1" / "metadata" / "documents.jsonl")}
    regions = read_jsonl(ROOT / "data" / "parsed" / "regions.jsonl")
    tables = read_jsonl(ROOT / "data" / "parsed" / "tables.jsonl")
    evidence_ids = {row["region_id"] for row in regions}
    evidence_ids.update(tup["tuple_id"] for table in tables for tup in table.get("semantic_tuples", []))
    source = read_jsonl(ROOT / "data" / "qa" / "core_qa.jsonl")
    accepted, rejected, audit = [], [], []
    for row in source:
        ok, errors, reviewed = validate_core(row, docs, evidence_ids)
        audit.append({"qa_id": row["qa_id"], "decision": "KEEP" if ok else "REJECT", "reasons": errors})
        (accepted if ok else rejected).append(reviewed)
    out = ROOT / "data" / "v3_1" / "qa"
    write_jsonl(out / "core_qa.jsonl", accepted)
    write_jsonl(out / "rejected_core.jsonl", rejected)
    write_jsonl(ROOT / "data" / "v3_1" / "metadata" / "core_qa_audit.jsonl", audit)
    summary = {"v3_core": len(source), "pass": len(accepted), "rejected": len(rejected), "rejection_reasons": dict(Counter(reason for item in audit for reason in item["reasons"]))}
    (ROOT / "reports" / "v3_1" / "core_qa_audit.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
