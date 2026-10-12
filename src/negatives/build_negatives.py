from __future__ import annotations

from copy import deepcopy

from src.common.io_utils import sha256_record
from src.validation.negative_minimality_validator import validate as validate_minimality


FACTORS = ("entities", "metrics", "periods", "units", "document_version")


def _signature(evidence: dict) -> dict:
    source = evidence.get("provenance_signature") or {}
    return {key: deepcopy(source.get(key)) for key in FACTORS}


def _difference(target: dict, candidate: dict) -> list[str]:
    return [key for key in FACTORS if target.get(key) != candidate.get(key)]


def build_minimal_negatives(core_qa: list[dict], limit: int = 200) -> tuple[list[dict], list[dict]]:
    pool = []
    for qa in core_qa:
        for evidence in qa.get("gold_evidence", []):
            if evidence.get("region_type") == "table":
                pool.append((qa, evidence, _signature(evidence)))
    minimal: list[dict] = []
    rejected: list[dict] = []
    seen_pairs = set()
    type_for_factor = {"entities": "WRONG_ENTITY", "periods": "WRONG_PERIOD", "metrics": "WRONG_METRIC", "units": "WRONG_UNIT", "document_version": "WRONG_DOCUMENT_VERSION"}
    for target_qa, target_ev, target_sig in pool:
        for candidate_qa, candidate_ev, candidate_sig in pool:
            pair = (target_qa["qa_id"], candidate_qa["qa_id"])
            if pair in seen_pairs or target_ev.get("region_id") == candidate_ev.get("region_id"):
                continue
            factors = _difference(target_sig, candidate_sig)
            if len(factors) != 1:
                continue
            factor = factors[0]
            record = {
                "negative_id": f"NEG_{len(minimal)+1:05d}", "qa_id": target_qa["qa_id"],
                "negative_type": type_for_factor[factor], "target_evidence": target_ev,
                "negative_evidence": candidate_ev, "target_signature": target_sig,
                "negative_signature": candidate_sig, "differing_factors": factors,
                "validation_status": "PENDING", "human_status": "NOT_REVIEWED",
            }
            outcome = validate_minimality(record, {})
            record["validation"] = outcome
            record["validation_status"] = "VALID_MINIMAL" if outcome["status"] == "PASS" else "INVALID"
            record["sha256"] = sha256_record(record)
            (minimal if outcome["status"] == "PASS" else rejected).append(record)
            seen_pairs.add(pair)
            break
        if len(minimal) >= limit:
            break
    return minimal, rejected


def build_nonminimal_negatives(challenge_qa: list[dict]) -> list[dict]:
    result = []
    for qa in challenge_qa:
        evidence = qa.get("gold_evidence", [])
        if len(evidence) < 2:
            continue
        record = {
            "negative_id": f"NEG_PARTIAL_{len(result)+1:05d}", "qa_id": qa["qa_id"],
            "negative_type": "PARTIAL_EVIDENCE_SET", "kept_evidence": evidence[:-1],
            "removed_evidence": [evidence[-1]], "validation_status": "NON_MINIMAL",
            "human_status": "NOT_REVIEWED",
        }
        record["sha256"] = sha256_record(record)
        result.append(record)
    return result
