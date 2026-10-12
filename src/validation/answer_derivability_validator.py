import re


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def validate(qa: dict, context: dict) -> dict:
    failures = []
    sources = [evidence.get("source_text", "") for evidence in qa.get("gold_evidence", [])]
    support = {}
    for component in qa.get("answer_components", []):
        cid = component.get("component_id")
        content = str(component.get("answer_content", "")).strip()
        hits = [index for index, source in enumerate(sources) if content and _norm(content) in _norm(source)]
        support[cid] = hits
        if not hits:
            failures.append(f"UNSUPPORTED_COMPONENT:{cid}")
    return {"status": "FAIL" if failures else "PASS", "failures": failures, "component_support": support}
