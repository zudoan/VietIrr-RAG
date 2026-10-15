"""Independent, deterministic audit of V4.1 artifacts and frozen inputs."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / "V4_1_INDEPENDENT_AUDIT.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()


def main() -> int:
    checks = []
    def check(cid, ok, detail, severity="FAIL"):
        checks.append({"check_id": cid, "pass": bool(ok), "failure_severity": severity, "detail": detail})

    freeze = json.loads((HERE / "V4_1_INPUT_FREEZE.json").read_text(encoding="utf-8"))
    for rel, expected in freeze["readable_inputs"].items():
        p = ROOT / rel; actual = sha(p) if p.is_file() else None
        check(f"FROZEN::{rel}", actual == expected["sha256"], {"expected": expected["sha256"], "actual": actual})
    seal = freeze["candidate_test_seal"]; cp = ROOT / seal["path"]; st = cp.stat()
    check("CANDIDATE_STAT_ONLY_UNCHANGED", st.st_size == seal["size_bytes_from_stat_only"] and st.st_mtime_ns == seal["mtime_ns_from_stat_only"],
          {"policy": seal["policy"], "hash_computed": False, "size": st.st_size, "mtime_ns": st.st_mtime_ns})
    check("CANDIDATE_NOT_HASHED_CLAIM", seal["sha256"] == "INTENTIONALLY_NOT_COMPUTED", seal["sha256"])

    frozen_cfg = json.loads((ROOT / "reports/TCB_RR_P2_3/P2_3_FROZEN_CONFIG.json").read_text(encoding="utf-8"))
    mismatches = [rel for rel, expected in frozen_cfg["code_file_sha256"].items() if not (ROOT / rel).is_file() or sha(ROOT / rel) != expected]
    check("TCB_RR_CODE_FROZEN", not mismatches, mismatches)

    manifest = [json.loads(x) for x in (HERE / "V4_CORPUS_MANIFEST.jsonl").read_text(encoding="utf-8").splitlines() if x]
    legacy = [x for x in manifest if x["corpus_layer"] == "LEGACY_V3_2_REFERENCE"]
    new = [x for x in manifest if x["corpus_layer"] == "V4_1_NEW_SOURCE"]
    check("MANIFEST_COUNTS", len(manifest) == 93 and len(legacy) == 89 and len(new) == 4, {"all": len(manifest), "legacy": len(legacy), "new": len(new)})
    check("MANIFEST_UNIQUE_IDS", len({x["doc_id"] for x in manifest}) == len(manifest), "unique doc IDs")
    legacy_mismatches = [x["doc_id"] for x in legacy if not (ROOT / x["local_path"]).is_file() or sha(ROOT / x["local_path"]) != x["sha256"]]
    check("LEGACY_REFERENCE_HASHES", not legacy_mismatches, {"checked": len(legacy), "mismatches": legacy_mismatches})
    new_hashes = []
    for row in new:
        p = ROOT / row["local_path"]; actual = sha(p) if p.is_file() else None; new_hashes.append(actual)
        check(f"NEW_SOURCE::{row['doc_id']}", p.is_file() and p.read_bytes()[:5] == b"%PDF-" and actual == row["sha256"] and (ROOT / row["parsed_path"]).is_file(),
              {"path": row["local_path"], "sha256": actual, "parsed": row["parsed_path"]})
    check("NO_NEW_SOURCE_DUPLICATE", len(set(new_hashes)) == len(new_hashes), new_hashes)

    with (HERE / "NEW_SOURCE_SCREENING.csv").open(encoding="utf-8-sig", newline="") as f: screening = list(csv.DictReader(f))
    statuses = {s: sum(r["status"] == s for r in screening) for s in ("ACCEPT", "REJECT", "REVIEW", "BLOCKED")}
    check("SCREENING_REAL", len(screening) == 20 and statuses == {"ACCEPT": 4, "REJECT": 5, "REVIEW": 10, "BLOCKED": 1}, statuses)
    accepts = [r for r in screening if r["status"] == "ACCEPT"]
    accept_complete = all(r["url"] and r["publisher"] and r["sha256"] and r["gap"] and r["duplicate_status"] == "UNIQUE_SHA256" for r in accepts)
    check("ACCEPT_METADATA_COMPLETE", accept_complete, {"accepted": len(accepts)})

    packs = json.loads((HERE / "LINKED_DOCUMENT_PACKS.json").read_text(encoding="utf-8"))
    verified_relations = sum(r["status"] == "VERIFIED" for p in packs["packs"] for r in p["relations"])
    check("RELATIONS_NOT_OVERCLAIMED", len(packs["packs"]) == 2 and verified_relations == 0, {"packs": len(packs["packs"]), "verified_for_gold": verified_relations})

    qa = [json.loads(x) for x in (HERE / "QA_GROUND_UP_PILOT.jsonl").read_text(encoding="utf-8").splitlines() if x]
    check("GROUND_UP_LINEAGE", len(qa) == 10 and all(q["origin_type"] == "GROUND_UP" and q["lineage"]["legacy_qa_used"] is False for q in qa), len(qa))
    serialized_qa = json.dumps(qa, ensure_ascii=False).lower()
    check("NO_CANDIDATE_REFERENCE", "candidate_test" not in serialized_qa and "candidate gold" not in serialized_qa, "content strings absent")
    validation = json.loads((HERE / "QA_PILOT_VALIDATION.json").read_text(encoding="utf-8"))["records"]
    check("VALIDATOR_NO_AUTO_SEMANTIC_PASS", all(not r["semantic_pass"] for r in validation), {"semantic_pass": sum(r["semantic_pass"] for r in validation)})
    check("PILOT_AUTO_CHECKS", sum(r["layers"]["layer2"] == "PASS" for r in validation) == 9 and sum(r["layers"]["layer2"] == "REVIEW" for r in validation) == 1,
          {"l2_pass": sum(r["layers"]["layer2"] == "PASS" for r in validation), "l2_review": sum(r["layers"]["layer2"] == "REVIEW" for r in validation)})
    check("NO_FAKE_HUMAN_REVIEW", all(q["review"]["status"] == "PENDING_HUMAN_REVIEW" and q["review"]["reviewer_id"] is None for q in qa), "10 pending; 0 accepted")
    tests = json.loads((HERE / "QA_ADVERSARIAL_TESTS/TEST_RESULTS.json").read_text(encoding="utf-8"))
    check("ADVERSARIAL_TESTS", tests["total"] == 16 and tests["caught"] == 16 and tests["non_default"] == 16 and tests["all_pass"],
          {k: tests[k] for k in ("total", "caught", "non_default", "synthetic", "real_pilot_mutations")})

    required = ["DOMAIN_USE_CASE_MATRIX.csv", "CORPUS_GAP_PRIORITY.csv", "QA_RULEBOOK_V2.md", "QA_SCHEMA_V2.json",
                "QA_COVERAGE_MATRIX.csv", "QA_GENERATION_PIPELINE.py", "QA_VALIDATOR_V2.py", "QA_PILOT_AUDIT.csv",
                "BENCHMARK_SPLIT_PROTOCOL.md", "V4_1_READINESS.json", "V4_CORPUS_INGESTION_REPORT.md"]
    missing = [x for x in required if not (HERE / x).is_file()]
    check("REQUIRED_ARTIFACTS", not missing, missing)
    bundle_exists = (HERE / "V4_1_REVIEW_BUNDLE.zip").is_file()
    check("REVIEW_BUNDLE_PRESENT", bundle_exists, "Bundle is built after the first audit pass", "WARN")

    failures = [x for x in checks if not x["pass"] and x["failure_severity"] == "FAIL"]
    warnings = [x for x in checks if not x["pass"] and x["failure_severity"] == "WARN"]
    result = {"audit_version": "1.0", "independent_from_generator": True, "checks": checks,
              "summary": {"checks": len(checks), "passed": sum(x["pass"] for x in checks), "failures": len(failures), "warnings": len(warnings)},
              "technical_integrity": "PASS" if not failures else "FAIL",
              "release_conclusion": "NOT_BENCHMARK_READY: human QA and relation review remain mandatory."}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"])); return 1 if failures else 0


if __name__ == "__main__": raise SystemExit(main())
