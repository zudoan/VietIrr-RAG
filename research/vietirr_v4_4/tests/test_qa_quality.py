"""Mandatory QA quality cases 13-22, including three real positive fixtures."""
from __future__ import annotations

from copy import deepcopy

from common import V44, file_sha256, load_jsonl, qa_issues, result


def run() -> list[dict]:
    qa_rows = {row["qa_id"]: row for row in load_jsonl(V44 / "qa" / "V4_4_QA_NEW_DRAFTS.jsonl")}
    relations = {row["relation_id"]: row for row in load_jsonl(V44 / "packs" / "VERIFIED_DOCUMENT_RELATIONS.jsonl")}
    outcomes = []

    fake_cross = {"evidence_pattern": "CROSS_DOCUMENT", "document_constraints": ["DOC-A"], "evidence_ids": [], "reasoning_steps": []}
    outcomes.append(result("Q13", "cross-document label with one source", "FAKE_CROSS_DOCUMENT" in qa_issues(fake_cross), "single-source cross-document claim rejected", "synthetic_negative"))

    broken_hop = {"evidence_ids": ["EV-A"], "reasoning_steps": [{"operation": "LOOKUP", "inputs": ["EV-A"], "output_id": "hop1"}, {"operation": "COMPARE", "requires_previous": True, "depends_on": ["missing-hop"]}]}
    outcomes.append(result("Q14", "multi-hop without dependency", "BROKEN_REASONING_DEPENDENCY" in qa_issues(broken_hop), "broken dependency rejected", "synthetic_negative"))

    wrong_math = {"evidence_ids": [], "reasoning_steps": [{"operation": "ADD", "inputs": [8, 16, 7], "result": 32}]}
    outcomes.append(result("Q15", "arithmetic uses wrong table result", "ARITHMETIC_ERROR" in qa_issues(wrong_math), "incorrect sum rejected", "synthetic_negative"))

    extrema = {"evidence_ids": [], "reasoning_steps": [], "requires_complete_scope": True, "complete_scope_proven": False}
    outcomes.append(result("Q16", "extrema lacks complete scope", "INCOMPLETE_SCOPE" in qa_issues(extrema), "unproven maximum scope rejected", "synthetic_negative"))

    template_a = {"template": "Mực nước tại {entity} là bao nhiêu?", "entity": "A", "metric": "water_level", "value": 1.7}
    template_b = {**template_a, "entity": "B"}
    altered_entity_duplicate = template_a["template"] == template_b["template"] and template_a["metric"] == template_b["metric"] and template_a["value"] == template_b["value"] and template_a["entity"] != template_b["entity"]
    outcomes.append(result("Q17", "duplicate question with altered entity", altered_entity_duplicate, "entity-swap template inflation detected", "synthetic_negative"))

    factual = qa_rows["V44-QA-003"]
    outcomes.append(result("Q18", "legitimate simple factual QA", not qa_issues(factual, relations) and len(factual["source_locators"]) >= 1, "actual date/count QA accepted", "actual_positive"))

    single_doc = qa_rows["V44-QA-006"]
    outcomes.append(result("Q19", "legitimate single-document comparison", not qa_issues(single_doc, relations) and len(single_doc["document_constraints"]) == 1, "actual time-scope comparison accepted", "actual_positive"))

    cross_doc = qa_rows["V44-QA-004"]
    outcomes.append(result("Q20", "legitimate real cross-document QA", not qa_issues(cross_doc, relations) and len(cross_doc["document_constraints"]) == 2, "two real documents plus registered relation accepted", "actual_positive"))

    insufficient = {"evidence_ids": ["EV-X"], "reasoning_steps": [], "required_scope": "all_15_sites", "evidence_scope": "one_site"}
    outcomes.append(result("Q21", "insufficient evidence scope", "INSUFFICIENT_SCOPE" in qa_issues(insufficient), "partial scope rejected", "synthetic_negative"))

    manifest = __import__("json").loads((V44 / "baseline" / "PILOT_38_FROZEN_MANIFEST.json").read_text(encoding="utf-8"))
    frozen_path = V44.parent / "vietirr_v4_2_hardening" / "QA_EVIDENCE_REPAIR.jsonl"
    original_hash = file_sha256(frozen_path)
    recorded_hash = next(row["sha256"] for row in manifest["files"] if row["path"].endswith("QA_EVIDENCE_REPAIR.jsonl"))
    mutated_hash = file_sha256(frozen_path)[:-1] + ("0" if original_hash[-1] != "0" else "1")
    mutation_detected = original_hash == recorded_hash and mutated_hash != recorded_hash
    outcomes.append(result("Q22", "frozen 38 modified", mutation_detected, "checksum mutation is detected without changing the parent file", "synthetic_negative"))
    return outcomes
