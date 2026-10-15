"""Build pilot audit, coverage matrix, readiness and narrative reports."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)


def main() -> None:
    qa = load_jsonl(HERE / "QA_GROUND_UP_PILOT.jsonl")
    validation = json.loads((HERE / "QA_PILOT_VALIDATION.json").read_text(encoding="utf-8"))
    vr = {x["qa_id"]: x for x in validation["records"]}
    audit = []
    for q in qa:
        v = vr[q["qa_id"]]
        audit.append({"qa_id": q["qa_id"], "origin_type": q["origin_type"], "use_case": q["use_case"],
                      "domains": ";".join(q["domain"]), "competency": q["competency"], "difficulty": q["difficulty"],
                      "evidence_pattern": q["evidence_pattern"], "evidence_count": len(q["evidence"]),
                      "document_count": len({x["doc_id"] for x in q["evidence"]}),
                      "source_documents": ";".join(sorted({x["doc_id"] for x in q["evidence"]})),
                      "layer1": v["layers"]["layer1"], "layer2": v["layers"]["layer2"], "layer3": v["layers"]["layer3"],
                      "release_state": v["release_state"], "review_status": q["review"]["status"],
                      "human_verified": q["review"]["status"] == "HUMAN_ACCEPTED", "issue_codes": ";".join(x["code"] for x in v["issues"]),
                      "unresolved_conditions": ";".join(q["unsupported_conditions"])})
    fields = list(audit[0]); write_csv(HERE / "QA_PILOT_AUDIT.csv", fields, audit)

    cells = [
        ("D01", "UC01", "FACTUAL_LOOKUP/VERIFIABLE_COMPUTATION", "SAME_PAGE", "Hà Nam-Nam Định; Mekong delta", "EASY/MEDIUM", ["V41-QA-001", "V41-QA-004"], "PENDING_HUMAN_REVIEW"),
        ("D02", "UC14", "CONFLICT_VERSION_RESOLUTION", "SAME_PAGE/CROSS_DOCUMENT", "Bắc Nam Hà", "MEDIUM/HARD", ["V41-QA-007", "V41-QA-008"], "RELATION_REVIEW_REQUIRED"),
        ("D03+D04+D06", "UC08", "VERIFIABLE_COMPUTATION", "SAME_PAGE", "Hà Nam; Nam Định", "MEDIUM", ["V41-QA-003"], "PENDING_HUMAN_REVIEW"),
        ("D04", "UC07", "FACTUAL_LOOKUP", "SAME_PAGE", "Sông Châu/Bắc Nam Hà", "EASY", ["V41-QA-002"], "PENDING_HUMAN_REVIEW"),
        ("D05", "UC09", "FACTUAL_LOOKUP/CROSS_SOURCE_SYNTHESIS", "SAME_PAGE/CROSS_PAGE", "Cái Lớn–Cái Bé", "EASY/MEDIUM", ["V41-QA-009", "V41-QA-010"], "PENDING_HUMAN_REVIEW"),
        ("D06", "UC11", "FACTUAL_LOOKUP", "SAME_PAGE", "National", "EASY", ["V41-QA-005"], "PENDING_HUMAN_REVIEW"),
        ("D06", "UC13", "INSUFFICIENT_EVIDENCE_DETECTION", "SAME_PAGE", "National/facility-specific gap", "MEDIUM", ["V41-QA-006"], "PENDING_HUMAN_REVIEW"),
        ("D02", "UC02", "RULE_CONDITION_INTERPRETATION", "NONE", "All", "UNSET", [], "COVERAGE_GAP: clause-level legal review missing"),
        ("D02+D03", "UC03", "RULE_OBSERVATION_ALIGNMENT", "NONE", "All", "UNSET", [], "COVERAGE_GAP: applicable aligned rule+observation missing"),
        ("D03", "UC06", "TEMPORAL_COMPARISON", "NONE", "All", "UNSET", [], "COVERAGE_GAP: comparable reviewed series missing"),
        ("D05", "UC10", "RULE_OBSERVATION_ALIGNMENT", "NONE", "All", "UNSET", [], "COVERAGE_GAP: applicable standard relation unreviewed"),
        ("D06", "UC12", "RULE_CONDITION_INTERPRETATION", "NONE", "Named facility", "UNSET", [], "COVERAGE_GAP: current facility inspection missing"),
    ]
    cf = ["domain", "use_case", "competency", "evidence_pattern", "geography", "difficulty", "qa_count", "qa_ids", "status"]
    cov = [dict(zip(cf, [a,b,c,d,e,f,len(g),";".join(g),h])) for a,b,c,d,e,f,g,h in cells]
    write_csv(HERE / "QA_COVERAGE_MATRIX.csv", cf, cov)

    tests = json.loads((HERE / "QA_ADVERSARIAL_TESTS/TEST_RESULTS.json").read_text(encoding="utf-8"))
    readiness = {
        "schema_version": "1.0", "technical_acceptance_gate": "PASS_WITH_RELEASE_BLOCKERS",
        "CORPUS_EXPANSION_READY": True, "QA_PIPELINE_READY": True, "QA_HUMAN_VERIFIED": False,
        "BENCHMARK_READY": False, "METHOD_EVALUATION_READY": False,
        "counts": {"legacy_references": 89, "new_sources_screened": 20, "new_sources_accepted": 4,
                   "corpus_manifest_records": 93, "linked_packs": 2, "verified_gold_relations": 0,
                   "ground_up_pilot": len(qa), "auto_rejected_pilot": 0, "pending_human_review": len(qa),
                   "human_accepted_qa": 0, "adversarial_tests": tests["total"], "adversarial_caught": tests["caught"]},
        "release_blockers": ["No V4.1 QA has human/domain acceptance.", "No cross-document relation is VERIFIED_FOR_GOLD.",
                             "Five high-value QA coverage cells remain empty.", "Four new sources have technical screening but no named human source review."],
        "decision": "Do not build or release a large official V4 benchmark yet; conduct source/evidence/relation/QA human review first."
    }
    (HERE / "V4_1_READINESS.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    screening = list(csv.DictReader((HERE / "NEW_SOURCE_SCREENING.csv").open(encoding="utf-8-sig")))
    status = Counter(x["status"] for x in screening)
    ingestion = f"""# V4.1 Corpus Ingestion Report

## Outcome

The isolated corpus contains **93 manifest records**: 89 immutable references to the accepted V3.2 sources and 4 newly downloaded PDFs. No legacy PDF was copied or modified. Candidate Test was not opened or hashed.

The initial survey screened **{len(screening)}** candidates: **{status['ACCEPT']} ACCEPT**, **{status['REJECT']} REJECT**, **{status['REVIEW']} REVIEW**, and **{status['BLOCKED']} BLOCKED**. ACCEPT means the PDF was downloaded, passed PDF-magic/checksum/duplicate checks, had an attributable official publisher, and yielded reviewable text. It does not mean its facts or resulting QA are human gold.

## Accepted sources

| ID | Scope | Pages | Use restriction |
|---|---|---:|---|
| V4_CTTL_2025_77c60f84 | Current Bắc Nam Hà operation procedure | 38 | Clause-level human review before legal gold |
| V4_IWRP_2021_3031564c | Sông Châu/Bắc Nam Hà water forecast and use plan | 9 | Historical plan/forecast, not actual delivery |
| V4_CTTL_2024_dda51c21 | Cái Lớn–Cái Bé operation draft | 47 | **Draft only; never an applicable rule** |
| V4_BNNMT_2025_594e7382 | 2025 irrigation/dike safety directive | 5 | General duties; not facility-condition evidence |

All four have SHA-256, URL, publisher, date/version status, gap mapping, page count, local raw path and machine-parsed derivative. Parsed text carries a warning that it is not approved gold evidence.

## Duplicate and access findings

The two indexed Bắc Nam Hà attachment URLs returned byte-identical PDFs; only one canonical copy was retained and the other candidate is `REJECT_DUPLICATE`. The proposed TCVN dam-safety draft could not be downloaded and is `BLOCKED`, not ACCEPT. HTML news summaries are not treated as substitute PDFs.

## Linked packs

Two real packs are recorded: Bắc Nam Hà (current operation procedure + historical seasonal plan) and Cái Lớn–Cái Bé (draft operation context + two accepted 2025 water-quality bulletins). Their relations remain `MANIFEST_RELATION_PENDING_HUMAN`; therefore zero relations are eligible for gold.

## Rights and reproducibility

The files are public downloads from official domains. No open redistribution licence was found, so the manifest records the source URLs and does not claim an open licence. The review bundle excludes PDF binaries; reviewers can verify checksums against locally acquired copies.
"""
    (HERE / "V4_CORPUS_INGESTION_REPORT.md").write_text(ingestion, encoding="utf-8")
    print(json.dumps(readiness["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
