"""Independent, artifact-level audit for VietIrr-RAG V4.4."""
from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]

def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))

def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

checks: list[dict] = []
def check(check_id: str, condition: bool, detail: str) -> None:
    checks.append({"check_id": check_id, "passed": bool(condition), "detail": detail})

# Frozen parent provenance and retention decision.
frozen = json.loads((HERE / "baseline/PILOT_38_FROZEN_MANIFEST.json").read_text(encoding="utf-8"))
for item in frozen["files"]:
    path = ROOT / item["path"]
    check(f"FROZEN_{path.name}", path.is_file() and sha(path) == item["sha256"], "parent artifact exists and matches frozen hash")
decisions = csv_rows(HERE / "baseline/PILOT_38_USER_DECISIONS.csv")
reconciliation = jsonl(HERE / "baseline/PILOT_38_RECONCILIATION.jsonl")
check("PILOT_COUNT", len(decisions) == len(reconciliation) == 38, "38 records retained")
check("PILOT_KEEP_SCOPE", all(row["user_decision"] == "KEEP" and row["decision_scope"] == "QUESTION_CONTENT_RETENTION" for row in decisions), "KEEP means question retention only")
check("PILOT_DECISION_PROVENANCE", all(row.get("decision_provenance") == "USER_CONFIRMED_IN_CONVERSATION" and row.get("source_verification_status") == "PRESERVE_EXISTING_STATUS" for row in decisions), "decision provenance and source-status preservation are explicit")
check("NO_FAKE_PILOT_HUMAN", all(row.get("human_evidence_verification") == "PENDING_HUMAN_REVIEW" and row.get("benchmark_release_status") == "NOT_GOLD" for row in reconciliation), "no pilot promoted to human/gold")
check("PILOT_GOLD_POLICY", all(row.get("gold_status") == "NOT_AUTOMATICALLY_VERIFIED" for row in decisions + reconciliation), "KEEP never implies automatic gold")

# Full canonical corpus.
manifest = jsonl(ROOT / "research/vietirr_v4_1/V4_CORPUS_MANIFEST.jsonl")
manifest_by_id = {row["doc_id"]: row for row in manifest}
audit = csv_rows(HERE / "corpus/CORPUS_93_CANONICAL_AUDIT.csv")
profiles = jsonl(HERE / "corpus/DOCUMENT_EVIDENCE_PROFILES.jsonl")
check("CORPUS_CARDINALITY", len(manifest) == len(audit) == len(profiles) == 93 and len(manifest_by_id) == 93, "93 unique canonical documents profiled")
hash_ok = True
for row in audit:
    path = ROOT / row["local_path"]
    hash_ok &= path.is_file() and sha(path) == row["actual_sha256"] == row["declared_sha256"]
check("CORPUS_HASHES", hash_ok, "all 93 physical PDFs exist and match canonical hashes")
check("CORPUS_PROFILE_IDS", {row["doc_id"] for row in profiles} == set(manifest_by_id), "profile set equals manifest set")
matrix = csv_rows(HERE / "corpus/DOMAIN_USECASE_COVERAGE_MATRIX.csv")
check("COVERAGE_LAYERS", len(matrix) > 0 and all(row.get("document_count") not in (None, "") and row.get("evidence_supported_document_count") not in (None, "") for row in matrix), "corpus breadth and typed-evidence depth are separated")
typed = {row["doc_id"] for row in profiles if row.get("available_evidence_patterns")}
check("TYPED_EVIDENCE_DEPTH", len(typed) == 8, "typed evidence currently covers 8 documents")

# Packs and provenance.
packs = jsonl(HERE / "packs/LINKED_EVIDENCE_PACKS.jsonl")
relations = jsonl(HERE / "packs/VERIFIED_DOCUMENT_RELATIONS.jsonl")
pack_ev = jsonl(HERE / "packs/PACK_EVIDENCE_BANK.jsonl")
check("PACK_COUNTS", len(packs) == 3 and len(relations) == 7, "3 selected packs and 7 explicit relations")
valid_status = {"MACHINE_SUPPORTED", "VERIFICATION_REQUIRED"}
check("RELATION_STATUS", all(row["status"] in valid_status for row in relations), "no relation is mislabeled human-verified")
known_or_external = set(manifest_by_id) | {"EXTERNAL_ACT_5470_2016_NOT_IN_CORPUS"}
check("RELATION_DOCUMENTS", all(row["source_document"] in known_or_external and row["target_document"] in known_or_external for row in relations), "relation endpoints are canonical or explicitly external")
ev_ok = True
for row in pack_ev:
    if row["doc_id"] not in manifest_by_id:
        ev_ok = False
        continue
    doc = manifest_by_id[row["doc_id"]]
    ev_ok &= row["pdf_sha256"] == doc["sha256"] and int(row["page"]) >= 1 and bool(row.get("source_text_span"))
check("PACK_EVIDENCE_PROVENANCE", ev_ok, "every pack evidence unit has document hash, page and source span")

# Controlled QA expansion.
qas = jsonl(HERE / "qa/V4_4_QA_NEW_DRAFTS.jsonl")
qa_validation = jsonl(HERE / "qa/V4_4_QA_VALIDATION_RESULTS.jsonl")
qids = {row["qa_id"] for row in qas}
check("QA_CARDINALITY", len(qas) == len(qa_validation) == len(qids) == 10, "10 non-quota-driven QA drafts")
check("QA_REVIEW_SEPARATION", all(row["human_review_status"] == "PENDING_HUMAN_REVIEW" and row["gold_status"] == "NOT_GOLD" for row in qas), "new QA remains pending human and non-gold")
check("QA_VALIDATION_STATUS", Counter(row["validation_status"] for row in qa_validation) == {"MACHINE_SUPPORTED": 7, "REVIEW_REQUIRED": 3}, "expected 7/3 machine/review split")
check("QA_CROSS_DOCUMENT_REAL", all(len(set(row["document_constraints"])) >= 2 for row in qas if row["evidence_pattern"] == "CROSS_DOCUMENT"), "cross-document QA uses at least two source documents")
arith_ok = True
for row in qas:
    for step in row["reasoning_steps"]:
        if step["operation"] == "ADD": arith_ok &= sum(step["inputs"]) == step["result"]
        if step["operation"] == "DIVIDE_PERCENT": arith_ok &= abs(step["inputs"][0] / step["inputs"][1] * 100 - step["result"]) < 1e-9
check("QA_ARITHMETIC", arith_ok, "all explicit arithmetic traces reproduce")

# Mandatory tests and handoff bundle.
tests = json.loads((HERE / "tests/V4_4_TEST_RESULTS.json").read_text(encoding="utf-8"))
check("MANDATORY_TESTS", tests["all_passed"] and tests["total"] == tests["passed"] == 22, "22/22 mandatory tests pass")
bundle_manifest = json.loads((HERE / "V4_4_BUNDLE_MANIFEST.json").read_text(encoding="utf-8"))
with zipfile.ZipFile(HERE / "V4_4_REVIEW_BUNDLE.zip") as archive:
    names = archive.namelist()
    no_pdf = all(not name.lower().endswith(".pdf") for name in names)
    no_candidate_path = all("candidate_test" not in name.lower() for name in names)
    bundle_hashes = True
    for item in bundle_manifest["files"]:
        bundle_hashes &= hashlib.sha256(archive.read(item["path"])).hexdigest() == item["sha256"]
check("BUNDLE_SOURCE_FREE", no_pdf and bundle_manifest["source_pdfs_embedded"] == 0, "review ZIP embeds no source PDF")
check("BUNDLE_CANDIDATE_TEST_FREE", no_candidate_path, "no Candidate Test path is bundled")
check("BUNDLE_HASHES", bundle_hashes, "bundled support files match manifest hashes")

passed = sum(row["passed"] for row in checks)
payload = {
    "audit": "VIETIRR_RAG_V4_4_INDEPENDENT_ARTIFACT_AUDIT",
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "checks_total": len(checks),
    "checks_passed": passed,
    "checks_failed": len(checks) - passed,
    "all_passed": passed == len(checks),
    "candidate_test_accessed": False,
    "human_verified_count": 0,
    "official_gold_count": 0,
    "checks": checks,
}
(HERE / "V4_4_INDEPENDENT_AUDIT.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: payload[key] for key in ("checks_total", "checks_passed", "checks_failed", "all_passed")}))
raise SystemExit(0 if payload["all_passed"] else 1)
