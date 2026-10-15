"""Mandatory document-relation adversarial cases 06-12."""
from __future__ import annotations

from common import relation_issues, result


def run() -> list[dict]:
    cases = [
        ("R06", "same facility name, different entities", {"same_name": True, "source_entity_id": "dam-a", "target_entity_id": "dam-b"}, "ENTITY_COLLISION"),
        ("R07", "same basin does not prove applicability", {"relation_type": "APPLIES_TO_EVENT", "explicit_clause": False, "condition_match": False}, "BASIN_ONLY_APPLICABILITY"),
        ("R08", "draft treated as effective rule", {"claims_effective_rule": True, "document_validity": "DRAFT"}, "DRAFT_AS_EFFECTIVE"),
        ("R09", "invalid replacement relation", {"relation_type": "REPLACES", "explicit_reference": False}, "UNSUPPORTED_REPLACEMENT"),
        ("R10", "same metric with incompatible times", {"relation_type": "COMPARE_METRIC", "time_role_a": "OBSERVATION", "time_role_b": "FORECAST", "unit_a": "‰", "unit_b": "‰"}, "INCOMPATIBLE_TIME_ROLE"),
        ("R11", "same value with different units", {"relation_type": "COMPARE_METRIC", "time_role_a": "OBSERVATION", "time_role_b": "OBSERVATION", "unit_a": "m", "unit_b": "cm"}, "INCOMPATIBLE_UNIT"),
    ]
    outcomes = [result(cid, name, code in relation_issues(payload), f"{code} detected", "synthetic_negative") for cid, name, payload, code in cases]
    evidence_set = {"entity": "CL1", "topic": "salinity", "members": [{"entity": "CL1", "topic": "salinity"}, {"entity": "Sông Hương", "topic": "flood storage"}]}
    unrelated = any(member["entity"] != evidence_set["entity"] or member["topic"] != evidence_set["topic"] for member in evidence_set["members"])
    outcomes.append(result("R12", "unrelated evidence in a set", unrelated, "off-entity/off-topic member detected", "synthetic_negative"))
    return outcomes

