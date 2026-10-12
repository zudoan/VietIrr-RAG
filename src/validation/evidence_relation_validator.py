"""Independent fail-closed validator for V3.1 evidence relations."""

from __future__ import annotations

from src.structure.semantic_table_parser import fold


FORBIDDEN_BASIS = {"same pdf only", "nearby page only", "hash selected", "same generic keyword only"}


def validate_relation(relation: dict) -> tuple[str, list[str]]:
    errors: list[str] = []
    evidence = relation.get("evidence") or []
    ids = relation.get("evidence_ids") or []
    rel_type = relation.get("relation_type")
    basis = {fold(item) for item in relation.get("relation_basis", [])}
    if len(ids) < 2 or len(ids) != len(set(ids)) or len(evidence) != len(ids):
        errors.append("INVALID_EVIDENCE_SET")
    if any(item in FORBIDDEN_BASIS for item in basis):
        errors.append("FORBIDDEN_RELATION_BASIS")
    if relation.get("relation_confidence", 0) < 0.88:
        errors.append("LOW_RELATION_CONFIDENCE")
    if any(ev.get("evidence_id") not in ids for ev in evidence):
        errors.append("EVIDENCE_ID_MISMATCH")

    if rel_type == "SAME_ENTITY_DIFFERENT_TIME":
        if not relation.get("shared_entity") or not relation.get("shared_metric"):
            errors.append("MISSING_SHARED_ENTITY_OR_METRIC")
        periods = {(ev.get("period") or {}).get("start") for ev in evidence}
        if None in periods or len(periods) != len(evidence):
            errors.append("PERIODS_NOT_DISTINCT_OR_EXPLICIT")
        if len({ev.get("entity_canonical") for ev in evidence}) != 1 or len({ev.get("metric") for ev in evidence}) != 1:
            errors.append("TIME_SERIES_SIGNATURE_MISMATCH")
    elif rel_type == "TABLE_TO_TABLE_COMPARISON":
        if any(ev.get("evidence_type") != "TABLE_CELL" for ev in evidence):
            errors.append("TABLE_COMPARISON_NON_TABLE_EVIDENCE")
        if len({ev.get("table_id") for ev in evidence}) != 1:
            errors.append("TABLE_CONTEXT_NOT_SHARED")
        if len({ev.get("metric") for ev in evidence}) != 1 or len({ev.get("unit_normalized") for ev in evidence}) != 1:
            errors.append("INCOMPARABLE_TABLE_SIGNATURE")
        if len({ev.get("entity_canonical") for ev in evidence}) < 2:
            errors.append("COMPARISON_ENTITY_NOT_DISTINCT")
    elif rel_type in {"TABLE_TO_TEXT_EXPLANATION", "TABLE_TO_TEXT_FORECAST"}:
        table = next((ev for ev in evidence if ev.get("evidence_type") == "TABLE_CELL"), None)
        text = next((ev for ev in evidence if ev.get("evidence_type") == "TEXT_REGION"), None)
        if not table or not text:
            errors.append("MISSING_TABLE_OR_TEXT_EVIDENCE")
        else:
            anchors = {a.get("canonical") for a in text.get("anchors", [])}
            if table.get("entity_canonical") not in anchors or table.get("metric") != text.get("metric"):
                errors.append("NO_EXPLICIT_TABLE_TEXT_BRIDGE")
            required = "FORECAST" if rel_type.endswith("FORECAST") else None
            if required and required not in text.get("roles", []):
                errors.append("MISSING_FORECAST_ROLE")
            if not required and not set(text.get("roles", [])) & {"EXPLANATION", "INTERPRETATION", "ACTION"}:
                errors.append("MISSING_EXPLANATION_ROLE")
    elif rel_type in {"STATUS_TO_EXPLANATION", "STATUS_TO_FORECAST", "CONDITION_TO_ACTION", "RULE_TO_EXCEPTION", "RULE_TO_CONDITION", "STATE_TO_RECOMMENDATION"}:
        if any(ev.get("evidence_type") != "TEXT_REGION" for ev in evidence):
            errors.append("TEXT_RELATION_NON_TEXT_EVIDENCE")
        common = None
        for ev in evidence:
            anchors = {a.get("canonical") for a in ev.get("anchors", [])}
            common = anchors if common is None else common & anchors
        if not common:
            errors.append("NO_SHARED_CONCRETE_ENTITY")
    else:
        errors.append("UNSUPPORTED_RELATION_TYPE")

    return ("PASS" if not errors else "FAIL"), errors
