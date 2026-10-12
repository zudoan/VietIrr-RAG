"""Fail-closed validation for V3.1 source-grounded negatives."""

from __future__ import annotations


EXPECTED_DIFFERENCE = {"WRONG_ENTITY": "entity", "WRONG_PERIOD": "period", "WRONG_METRIC": "metric", "WRONG_UNIT": "unit"}


def validate(rows: list[dict], evidence_index: dict[str, dict], qa_index: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    accepted, rejected = [], []
    seen_ids = set()
    for source in rows:
        row = dict(source)
        errors = []
        if row.get("negative_id") in seen_ids:
            errors.append("DUPLICATE_NEGATIVE_ID")
        seen_ids.add(row.get("negative_id"))
        if row.get("source_qa_id") not in qa_index:
            errors.append("UNRESOLVED_SOURCE_QA")
        for evidence_id in row.get("candidate_evidence_ids", []):
            if evidence_id not in evidence_index:
                errors.append("UNRESOLVED_CANDIDATE_EVIDENCE")
        kind = row.get("negative_type")
        if kind in EXPECTED_DIFFERENCE:
            negative_id = row.get("negative_evidence_id")
            if negative_id not in evidence_index:
                errors.append("UNRESOLVED_NEGATIVE_EVIDENCE")
            differences = row.get("signature_differences") or []
            if differences != [EXPECTED_DIFFERENCE[kind]]:
                errors.append("NOT_SINGLE_INTENDED_SEMANTIC_DIFFERENCE")
            if row.get("gold_target_evidence_id") == negative_id:
                errors.append("NEGATIVE_EQUALS_GOLD")
        elif kind == "PARTIAL_EVIDENCE_SET":
            if row.get("negative_evidence_id") not in evidence_index:
                errors.append("UNRESOLVED_NEGATIVE_EVIDENCE")
            proof = row.get("ablation_proof") or {}
            if not proof.get("necessary") or not row.get("unsupported_component_ids"):
                errors.append("MISSING_NECESSITY_PROOF")
            if row.get("removed_evidence_id") in row.get("candidate_evidence_ids", []):
                errors.append("REMOVED_EVIDENCE_STILL_PRESENT")
        elif kind == "REDUNDANT_EVIDENCE_SET":
            if row.get("redundant_evidence_id") not in evidence_index:
                errors.append("UNRESOLVED_REDUNDANT_EVIDENCE")
            if row.get("redundant_evidence_id") not in row.get("candidate_evidence_ids", []):
                errors.append("REDUNDANT_EVIDENCE_NOT_PRESENT")
        else:
            errors.append("UNKNOWN_NEGATIVE_TYPE")
        if not row.get("source_grounded") or row.get("construction_method") in {"metadata_only", "query_rewrite"}:
            errors.append("NOT_SOURCE_GROUNDED")
        row["semantic_validation"] = "PASS" if not errors else "FAIL"
        if errors:
            row["negative_status"] = "INVALID"
        elif kind in EXPECTED_DIFFERENCE:
            row["negative_status"] = "VALID_MINIMAL"
        else:
            row["negative_status"] = "VALID_HARD_NONMINIMAL"
        row["validation_errors"] = errors
        (accepted if not errors else rejected).append(row)
    return accepted, rejected
