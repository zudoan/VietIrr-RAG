def validate(qa: dict, context: dict) -> dict:
    regions = context["regions"]
    failures = []
    if not qa.get("gold_evidence"):
        failures.append("NO_GOLD_EVIDENCE")
    for evidence in qa.get("gold_evidence", []):
        region = regions.get(evidence.get("region_id"))
        if not region:
            failures.append(f"MISSING_REGION:{evidence.get('region_id')}")
            continue
        if evidence.get("page_id") != region.get("page_id") or evidence.get("page_number") != region.get("page_number"):
            failures.append(f"PAGE_MISMATCH:{evidence.get('region_id')}")
        if evidence.get("source_text") != region.get("normalized_text"):
            failures.append(f"SOURCE_TEXT_MISMATCH:{evidence.get('region_id')}")
    return {"status": "FAIL" if failures else "PASS", "failures": failures}
