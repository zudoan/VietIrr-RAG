def validate(qa: dict, context: dict) -> dict:
    failures = []
    question, answer = qa.get("question", "").strip(), qa.get("answer", "").strip()
    if not question or not answer:
        failures.append("EMPTY_QUESTION_OR_ANSWER")
    components = qa.get("answer_components", [])
    if not components:
        failures.append("NO_ANSWER_COMPONENTS")
    for component in components:
        content = str(component.get("answer_content", "")).strip()
        requirement = str(component.get("requirement", "")).strip()
        if not content or content not in answer:
            failures.append(f"ANSWER_COMPONENT_MISSING:{component.get('component_id')}")
        if not requirement:
            failures.append(f"EMPTY_REQUIREMENT:{component.get('component_id')}")
    if not question.endswith("?"):
        failures.append("QUESTION_NOT_INTERROGATIVE")
    return {"status": "FAIL" if failures else "PASS", "failures": failures}
