"""Small dependency-free validators used by the V4.4 adversarial tests."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
V44 = ROOT / "research" / "vietirr_v4_4"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def result(case_id: str, name: str, passed: bool, detail: str, fixture_type: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "name": name,
        "expected": "DETECT_INVALID" if fixture_type == "synthetic_negative" else "ACCEPT_VALID",
        "passed": bool(passed),
        "detail": detail,
        "fixture_type": fixture_type,
    }


def corpus_issues(rows: list[dict[str, Any]], verify_files: bool = False) -> set[str]:
    issues: set[str] = set()
    seen_hash: dict[str, str] = {}
    for row in rows:
        path = ROOT / str(row.get("local_path", ""))
        if verify_files and not path.is_file():
            issues.add("MISSING_PDF")
        elif verify_files and row.get("actual_sha256") and file_sha256(path) != row["actual_sha256"]:
            issues.add("HASH_MISMATCH")
        digest = str(row.get("actual_sha256") or row.get("sha256") or "")
        if digest and digest in seen_hash and seen_hash[digest] != row.get("doc_id"):
            issues.add("DUPLICATE_PHYSICAL_PDF")
        seen_hash[digest] = str(row.get("doc_id"))
        allowed = set(filter(None, str(row.get("allowed_domains", "")).split(";")))
        assigned = set(filter(None, str(row.get("domains", row.get("assigned_domains", ""))).split(";")))
        if allowed and not assigned.issubset(allowed):
            issues.add("INCORRECT_DOMAIN")
    return issues


def relation_issues(relation: dict[str, Any]) -> set[str]:
    issues: set[str] = set()
    rtype = relation.get("relation_type")
    if relation.get("same_name") and relation.get("source_entity_id") != relation.get("target_entity_id"):
        issues.add("ENTITY_COLLISION")
    if rtype == "APPLIES_TO_EVENT" and not (relation.get("explicit_clause") and relation.get("condition_match")):
        issues.add("BASIN_ONLY_APPLICABILITY")
    if relation.get("claims_effective_rule") and relation.get("document_validity") == "DRAFT":
        issues.add("DRAFT_AS_EFFECTIVE")
    if rtype == "REPLACES" and not relation.get("explicit_reference"):
        issues.add("UNSUPPORTED_REPLACEMENT")
    if rtype == "COMPARE_METRIC" and relation.get("time_role_a") != relation.get("time_role_b"):
        issues.add("INCOMPATIBLE_TIME_ROLE")
    if rtype == "COMPARE_METRIC" and relation.get("unit_a") != relation.get("unit_b"):
        issues.add("INCOMPATIBLE_UNIT")
    return issues


def qa_issues(qa: dict[str, Any], relations: dict[str, dict[str, Any]] | None = None) -> set[str]:
    issues: set[str] = set()
    documents = set(qa.get("document_constraints", []))
    if qa.get("evidence_pattern") == "CROSS_DOCUMENT" and len(documents) < 2:
        issues.add("FAKE_CROSS_DOCUMENT")
    if qa.get("requires_complete_scope") and not qa.get("complete_scope_proven"):
        issues.add("INCOMPLETE_SCOPE")
    if qa.get("evidence_scope") and qa.get("required_scope") and qa["evidence_scope"] != qa["required_scope"]:
        issues.add("INSUFFICIENT_SCOPE")
    available = set(qa.get("evidence_ids", []))
    produced: set[str] = set()
    for index, step in enumerate(qa.get("reasoning_steps", [])):
        op = step.get("operation")
        inputs = step.get("inputs", [])
        if op == "ADD" and isinstance(inputs, list) and all(isinstance(x, (int, float)) for x in inputs):
            if sum(inputs) != step.get("result"):
                issues.add("ARITHMETIC_ERROR")
        if step.get("requires_previous") and not set(step.get("depends_on", [])).issubset(produced):
            issues.add("BROKEN_REASONING_DEPENDENCY")
        if step.get("output_id"):
            produced.add(step["output_id"])
        relation_id = step.get("relation_id")
        if relation_id and relations is not None and relation_id not in relations:
            issues.add("MISSING_DOCUMENT_RELATION")
        for value in inputs:
            if isinstance(value, str) and value.startswith(("EV", "PKE-")) and value not in available:
                issues.add("UNDECLARED_EVIDENCE")
    return issues

