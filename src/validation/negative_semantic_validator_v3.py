"""Independent semantic validation for V3 negative instances."""

from __future__ import annotations

from src.structure.semantic_table_parser import DATE_LIKE, ROMAN, clean, fold


RED_FLAGS = {"tt", "stt", "date", "year", "ngay", "thang", "nam", "index"}


def validate_negative(row: dict) -> tuple[bool, list[str]]:
    errors = []
    if row.get("expected_label") != "NEGATIVE" or not row.get("candidate_evidence"):
        errors.append("INVALID_NEGATIVE_STRUCTURE")
    kind = row.get("negative_type")
    if kind and kind.startswith("WRONG_"):
        original, mutated = row.get("original_signature") or {}, row.get("counterfactual_signature") or {}
        dims = row.get("mutation_dimensions") or []
        if len(dims) != 1 or not row.get("minimal_counterfactual"):
            errors.append("NOT_MINIMAL_ONE_DIMENSION")
        changed = []
        for dim in ("entity", "metric", "period", "unit"):
            if original.get(dim) != mutated.get(dim):
                changed.append(dim)
        if changed != dims:
            errors.append("MUTATION_DIMENSION_MISMATCH")
        entity = mutated.get("entity") or {}; metric = mutated.get("metric") or {}
        eraw = clean(entity.get("raw")); mraw = clean(metric.get("raw"))
        if not eraw or fold(eraw) in RED_FLAGS or DATE_LIKE.fullmatch(eraw) or ROMAN.fullmatch(eraw):
            errors.append("INVALID_COUNTERFACTUAL_ENTITY")
        if not metric.get("canonical") or fold(mraw) in RED_FLAGS:
            errors.append("INVALID_COUNTERFACTUAL_METRIC")
        if kind == "WRONG_PERIOD" and not (mutated.get("period") or {}).get("start"):
            errors.append("INVALID_COUNTERFACTUAL_PERIOD")
        if kind == "WRONG_UNIT" and not (mutated.get("unit") or {}).get("normalized"):
            errors.append("INVALID_COUNTERFACTUAL_UNIT")
    elif kind == "PARTIAL_EVIDENCE_SET":
        if not row.get("removed_evidence_id") or not row.get("unsupported_component_ids"):
            errors.append("PARTIAL_SET_NOT_PROVEN")
    elif kind == "REDUNDANT_EVIDENCE_SET":
        if not row.get("redundant_evidence_id"):
            errors.append("REDUNDANCY_NOT_PROVEN")
    else:
        errors.append("UNKNOWN_NEGATIVE_TYPE")
    return not errors, sorted(set(errors))


def validate_negatives(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    passed, rejected = [], []
    for row in rows:
        ok, errors = validate_negative(row)
        row["semantic_validation"] = "PASS" if ok else "REJECT"
        row["validation_errors"] = errors
        (passed if ok else rejected).append(row)
    return passed, rejected

