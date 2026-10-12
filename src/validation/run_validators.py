from __future__ import annotations

from src.common.io_utils import sha256_record
from src.validation import (
    answer_derivability_validator,
    evidence_necessity_validator,
    page_consistency_validator,
    provenance_validator,
    qa_alignment_validator,
    schema_validator,
    source_traceability_validator,
    table_semantic_validator,
)


VALIDATORS = {
    "schema": schema_validator.validate,
    "source_traceability": source_traceability_validator.validate,
    "qa_alignment": qa_alignment_validator.validate,
    "answer_derivability": answer_derivability_validator.validate,
    "evidence_necessity": evidence_necessity_validator.validate,
    "table_semantic": table_semantic_validator.validate,
    "provenance": provenance_validator.validate,
    "page_consistency": page_consistency_validator.validate,
}


def build_context(documents: list[dict], regions: list[dict], tables: list[dict]) -> dict:
    return {
        "documents": {item["doc_id"]: item for item in documents},
        "regions": {item["region_id"]: item for item in regions},
        "tables": {item["table_id"]: item for item in tables},
    }


def validate_qa(rows: list[dict], context: dict, challenge: bool) -> tuple[list[dict], list[dict], list[dict]]:
    accepted, rejected, uncertain = [], [], []
    for original in rows:
        qa = dict(original)
        qa["validator_results"] = {name: function(qa, context) for name, function in VALIDATORS.items()}
        statuses = {name: result["status"] for name, result in qa["validator_results"].items()}
        required = ["schema", "source_traceability", "qa_alignment", "answer_derivability", "table_semantic", "provenance", "page_consistency"]
        if challenge:
            required.append("evidence_necessity")
        has_uncertain = any(statuses[name] == "UNCERTAIN" for name in required)
        has_failure = any(statuses[name] != "PASS" for name in required)
        if has_uncertain:
            qa["validation_status"] = "UNCERTAIN"
            uncertain.append(qa)
        elif has_failure:
            qa["validation_status"] = "FAIL"
            rejected.append(qa)
        else:
            qa["validation_status"] = "PASS"
            accepted.append(qa)
        qa["record_sha256"] = sha256_record({key: value for key, value in qa.items() if key != "record_sha256"})
    return accepted, rejected, uncertain
