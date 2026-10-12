def validate(qa: dict, context: dict) -> dict:
    pages = sorted(set(item.get("page_number") for item in qa.get("gold_evidence", []) if isinstance(item.get("page_number"), int)))
    failures = []
    expected = {
        "gold_pages": pages,
        "gold_page_count": len(pages),
        "page_span": (max(pages) - min(pages)) if pages else 0,
        "same_page": len(pages) == 1,
        "cross_page": len(pages) > 1,
    }
    for key, value in expected.items():
        if qa.get(key) != value:
            failures.append(f"PAGE_METADATA_MISMATCH:{key}")
    return {"status": "FAIL" if failures else "PASS", "failures": failures, "derived": expected}
