REQUIRED = {
    "qa_id": str, "question": str, "answer": str, "gold_evidence": list, "gold_pages": list,
    "answer_components": list, "question_types": list, "reasoning_types": list,
    "research_tags": list, "application_tags": list, "validation_status": str, "human_status": str,
}


def validate(qa: dict, context: dict) -> dict:
    failures = []
    for key, expected in REQUIRED.items():
        if key not in qa:
            failures.append(f"MISSING_FIELD:{key}")
        elif not isinstance(qa[key], expected):
            failures.append(f"INVALID_TYPE:{key}")
    if qa.get("human_status") not in {"NOT_REVIEWED", "LLM_REVIEWED", "HUMAN_REVIEWED"}:
        failures.append("INVALID_HUMAN_STATUS")
    for evidence in qa.get("gold_evidence", []):
        for key in ("region_id", "page_id", "page_number", "region_type", "role", "source_text", "provenance_signature"):
            if key not in evidence:
                failures.append(f"EVIDENCE_MISSING_FIELD:{key}")
    return {"status": "FAIL" if failures else "PASS", "failures": failures}
