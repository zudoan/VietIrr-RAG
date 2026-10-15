"""Mandatory corpus-coverage adversarial cases 01-05."""
from __future__ import annotations

from copy import deepcopy

from common import V44, corpus_issues, load_csv, result


def run() -> list[dict]:
    actual = load_csv(V44 / "corpus" / "CORPUS_93_CANONICAL_AUDIT.csv")
    base = actual[0]
    outcomes = []

    missing = deepcopy(base)
    missing["local_path"] = "data/raw/__synthetic_missing__.pdf"
    outcomes.append(result("C01", "corpus document missing", "MISSING_PDF" in corpus_issues([missing], True), "missing file rejected", "synthetic_negative"))

    mismatch = deepcopy(base)
    mismatch["actual_sha256"] = "0" * 64
    outcomes.append(result("C02", "canonical hash mismatch", "HASH_MISMATCH" in corpus_issues([mismatch], True), "wrong digest rejected", "synthetic_negative"))

    duplicate = [deepcopy(base), deepcopy(base)]
    duplicate[1]["doc_id"] = "SYNTHETIC_DUPLICATE_DOC"
    outcomes.append(result("C03", "duplicate physical PDF", "DUPLICATE_PHYSICAL_PDF" in corpus_issues(duplicate), "same digest under two IDs rejected", "synthetic_negative"))

    domain = deepcopy(base)
    domain["allowed_domains"] = "D01"
    domain["domains"] = "D06"
    outcomes.append(result("C04", "incorrect domain assignment", "INCORRECT_DOMAIN" in corpus_issues([domain]), "out-of-vocabulary assignment rejected", "synthetic_negative"))

    title_claim = {"title": "Báo cáo chất lượng nước", "extracted_content": "", "claimed_fact": "BOD5 đạt chuẩn"}
    supported = bool(title_claim["extracted_content"].strip()) and title_claim["claimed_fact"] in title_claim["extracted_content"]
    outcomes.append(result("C05", "title suggests content but PDF does not", not supported, "title metadata is not accepted as evidence", "synthetic_negative"))
    return outcomes

