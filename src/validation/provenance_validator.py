ALLOWED_VALUE_TYPES = {"OBSERVED", "FORECAST", "PLANNED", "THRESHOLD", "HISTORICAL", "TARGET", "UNKNOWN"}


def validate(qa: dict, context: dict) -> dict:
    failures = []
    doc = context["documents"].get(qa.get("doc_id"))
    if not doc:
        failures.append("MISSING_DOCUMENT")
    for evidence in qa.get("gold_evidence", []):
        sig = evidence.get("provenance_signature") or {}
        if sig.get("value_type") not in ALLOWED_VALUE_TYPES:
            failures.append("INVALID_VALUE_TYPE")
        if doc and sig.get("document_version") != doc.get("version_status"):
            failures.append("VERSION_MISMATCH")
        for period in sig.get("periods", []):
            if not isinstance(period, dict) or not {"raw_period", "normalized_start", "normalized_end", "period_type"}.issubset(period):
                failures.append("INVALID_PERIOD")
    return {"status": "FAIL" if failures else "PASS", "failures": failures}
