import re


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def validate(qa: dict, context: dict) -> dict:
    evidence = qa.get("gold_evidence", [])
    if len(evidence) < 2:
        return {"status": "SKIP_NOT_APPLICABLE", "failures": [], "support_matrix": []}
    components = qa.get("answer_components", [])
    matrix = []
    for ev_index, item in enumerate(evidence):
        source = item.get("source_text", "")
        row = {"evidence_index": ev_index, "region_id": item.get("region_id")}
        row["supports"] = [component.get("component_id") for component in components if _norm(str(component.get("answer_content", ""))) in _norm(source)]
        matrix.append(row)
    failures = []
    for ev_index in range(len(evidence)):
        remaining = [row for index, row in enumerate(matrix) if index != ev_index]
        all_still_supported = all(any(component.get("component_id") in row["supports"] for row in remaining) for component in components)
        if all_still_supported:
            failures.append(f"REDUNDANT_EVIDENCE:{ev_index}")
    for component in components:
        if not any(component.get("component_id") in row["supports"] for row in matrix):
            failures.append(f"UNSUPPORTED_COMPONENT:{component.get('component_id')}")
    return {"status": "FAIL" if failures else "PASS", "failures": failures, "support_matrix": matrix}
