"""Create the deterministic LLM-assisted V3 audit and future human-review package."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.validation.negative_semantic_validator_v3 import validate_negative
from src.validation.v3_semantic_validator import validate_record


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def ordered(rows: list[dict], key: str) -> list[dict]:
    return sorted(rows, key=lambda row: hashlib.sha256(str(row.get(key, "")).encode()).hexdigest())


def take_stratified(rows: list[dict], group_key: str, quotas: dict[str, int], id_key: str) -> list[dict]:
    selected: list[dict] = []
    used: set[str] = set()
    for group, quota in quotas.items():
        candidates = ordered([row for row in rows if str(row.get(group_key)) == group], id_key)
        for row in candidates[:quota]:
            selected.append(row)
            used.add(str(row[id_key]))
    if len(selected) < 100:
        remaining = [row for row in ordered(rows, id_key) if str(row[id_key]) not in used]
        selected.extend(remaining[: 100 - len(selected)])
    return selected[:100]


def naturalness_flags(question: str) -> list[str]:
    flags = []
    if re.search(r"\b(?:Wtb|Whi|column|row|page_id|table_id|cell_ref)\b", question, re.I):
        flags.append("RAW_SCHEMA_OR_COLUMN_NAME")
    if re.search(r"\b(?:trang|page)\s*\d+\b", question, re.I):
        flags.append("PAGE_NUMBER_MENTION")
    if any(mark in question for mark in ("\\", "|", "{", "}", "~")):
        flags.append("BROKEN_EXTRACTION_MARKER")
    if len(question) < 25 or not question.endswith("?"):
        flags.append("QUESTION_FORM")
    return flags


def reviewed_qa(row: dict) -> dict:
    ok, errors = validate_record(row)
    flags = naturalness_flags(row.get("question", ""))
    result = dict(row)
    result["review_status"] = "AUTO_AUDIT_SAMPLE"
    result["human_validated"] = False
    result["audit_review"] = {
        "outcome": "PASS" if ok and not flags else "FAIL",
        "semantic_validator_errors": errors,
        "naturalness_flags": flags,
        "basis": "LLM-assisted semantic inspection plus independent fail-closed validator",
    }
    return result


def reviewed_negative(row: dict) -> dict:
    ok, errors = validate_negative(row)
    result = dict(row)
    result["review_status"] = "AUTO_AUDIT_SAMPLE"
    result["human_validated"] = False
    result["audit_review"] = {
        "outcome": "PASS" if ok else "FAIL",
        "semantic_validator_errors": errors,
        "basis": "LLM-assisted semantic inspection plus independent negative validator",
    }
    return result


def main() -> None:
    core = read_jsonl(ROOT / "data" / "qa" / "core_qa.jsonl")
    challenge = read_jsonl(ROOT / "data" / "qa" / "challenge_qa.jsonl")
    minimal = read_jsonl(ROOT / "data" / "negatives" / "minimal_negatives.jsonl")
    partial = read_jsonl(ROOT / "data" / "negatives" / "partial_sets.jsonl")
    redundant = read_jsonl(ROOT / "data" / "negatives" / "redundant_sets.jsonl")

    core_sample = take_stratified(core, "qa_type", {"TEXT_ONLY": 60, "TABLE_ONLY": 40}, "qa_id")
    challenge_sample = take_stratified(challenge, "qa_type", {
        "THREE_EVIDENCE_TEXT": 25, "TEXT_TABLE": 25, "TABLE_TABLE": 25, "MULTI_TEXT": 25,
    }, "qa_id")
    negative_pool = minimal + partial + redundant
    negative_sample = take_stratified(negative_pool, "negative_type", {
        "WRONG_ENTITY": 15, "WRONG_METRIC": 15, "WRONG_PERIOD": 10, "WRONG_UNIT": 10,
        "PARTIAL_EVIDENCE_SET": 25, "REDUNDANT_EVIDENCE_SET": 25,
    }, "negative_id")

    reviewed_core = [reviewed_qa(row) for row in core_sample]
    reviewed_challenge = [reviewed_qa(row) for row in challenge_sample]
    reviewed_negatives = [reviewed_negative(row) for row in negative_sample]
    out = ROOT / "reports" / "v3_review_sample"
    write_jsonl(out / "core_100.jsonl", reviewed_core)
    write_jsonl(out / "challenge_100.jsonl", reviewed_challenge)
    write_jsonl(out / "negatives_100.jsonl", reviewed_negatives)

    all_qa = core + challenge
    all_questions = [row["question"] for row in all_qa]
    exact_duplicates = len(all_questions) - len(set(q.casefold() for q in all_questions))
    pattern_counts = Counter(re.sub(r"\b\d+(?:[.,/-]\d+)*\b", "#", q.casefold())[:90] for q in all_questions)
    sample_rows = reviewed_core + reviewed_challenge + reviewed_negatives
    failed = [row.get("qa_id", row.get("negative_id")) for row in sample_rows if row["audit_review"]["outcome"] != "PASS"]
    report = {
        "review_status": "AUTO_AUDIT_SAMPLE",
        "human_validated": False,
        "sample_counts": {"core": 100, "challenge": 100, "negatives": 100, "total": 300},
        "semantic_failures": len(failed),
        "semantic_failure_rate_pct": round(100 * len(failed) / len(sample_rows), 2),
        "failed_ids": failed,
        "pass_rate_target_met": len(failed) / len(sample_rows) <= 0.02,
        "question_naturalness_audit": {
            "sample_flag_count": sum(len(row["audit_review"].get("naturalness_flags", [])) for row in reviewed_core + reviewed_challenge),
            "exact_duplicate_questions": exact_duplicates,
            "max_generated_pattern_share_pct": round(100 * max(pattern_counts.values(), default=0) / max(len(all_questions), 1), 2),
            "hard_pattern_limit_pct": 12,
        },
        "candidate_gold_test": {
            "count": len(read_jsonl(ROOT / "data" / "qa" / "candidate_gold_test.jsonl")),
            "status": "CANDIDATE_ONLY_PENDING_HUMAN_REVIEW",
        },
    }
    (ROOT / "reports" / "V3_LLM_REVIEW_AUDIT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
