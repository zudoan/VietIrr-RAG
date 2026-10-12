def validate(negative: dict, context: dict) -> dict:
    target = negative.get("target_signature") or {}
    candidate = negative.get("negative_signature") or {}
    factors = [key for key in ("entities", "metrics", "periods", "units", "document_version") if target.get(key) != candidate.get(key)]
    declared = negative.get("differing_factors", [])
    failures = []
    if factors != declared:
        failures.append("DIFFERING_FACTORS_MISMATCH")
    if len(factors) != 1:
        failures.append("NOT_MINIMAL")
    if negative.get("negative_evidence", {}).get("source_text") == negative.get("target_evidence", {}).get("source_text") and target == candidate:
        failures.append("IDENTICAL_NEGATIVE")
    return {"status": "FAIL" if failures else "PASS", "failures": failures, "computed_differing_factors": factors}
