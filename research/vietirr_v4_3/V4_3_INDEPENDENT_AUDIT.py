"""Independent audit for V4.3 published artifacts and frozen-parent integrity."""
from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
HARD = ROOT / "research/vietirr_v4_2_hardening"
V42 = ROOT / "research/vietirr_v4_2"
V41 = ROOT / "research/vietirr_v4_1"
results: list[dict] = []


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def check(name: str, condition: bool, detail: object) -> None:
    results.append({"check": name, "passed": bool(condition), "detail": detail})


freeze = json.loads((HERE / "V4_3_INPUT_FREEZE.json").read_text(encoding="utf-8"))
freeze_mismatches = []
for row in freeze["files"]:
    path = ROOT / row["path"]
    if not path.is_file() or path.stat().st_size != row["size_bytes"] or sha256(path) != row["sha256"]:
        freeze_mismatches.append(row["path"])
check("input_freeze_unchanged", not freeze_mismatches, freeze_mismatches)
check("candidate_test_not_accessed_claim", freeze.get("candidate_test_accessed") is False, freeze.get("candidate_test_accessed"))

raw = jsonl(V42 / "V4_2_QA_DRAFTS.jsonl")
repaired = jsonl(HARD / "QA_EVIDENCE_REPAIR.jsonl")
dossiers = jsonl(HERE / "QA_SOURCE_DOSSIERS.jsonl")
machine = jsonl(HERE / "QA_MACHINE_SOURCE_CHECKS.jsonl")
revisions = jsonl(HERE / "QA_PROPOSED_REVISIONS.jsonl")
queue = jsonl(HERE / "QA_FINAL_REVIEW_QUEUE.jsonl")
fixtures = jsonl(HERE / "SOURCE_PAGE_FIXTURES.jsonl")
raw_ids = {row["qa_id"] for row in raw}
check("raw_and_repaired_38_same_ids", len(raw) == len(repaired) == 38 and raw_ids == {row["qa_id"] for row in repaired}, len(raw_ids))
check("dossiers_38_unique", len(dossiers) == 38 and {row["qa_id"] for row in dossiers} == raw_ids, len(dossiers))
check("machine_checks_38_unique", len(machine) == 38 and {row["qa_id"] for row in machine} == raw_ids, len(machine))

allowed = {"MACHINE_SUPPORTED", "MACHINE_CONTRADICTED", "PARTIALLY_SUPPORTED", "AMBIGUOUS", "SOURCE_UNREADABLE", "REVIEW_REQUIRED"}
check("machine_status_vocabulary", all(row["status"] in allowed for row in machine), sorted({row["status"] for row in machine}))
check("machine_not_gold", all(row.get("gold_verified") is False for row in machine), "All false")
check("human_status_pending", all(row.get("human_review_status") == "PENDING_HUMAN_REVIEW" for row in dossiers + machine), "0 fabricated verdicts")
check("human_ledger_empty", not (HERE / "QA_REVIEW_LEDGER.jsonl").read_text(encoding="utf-8").strip(), "0 rows")

source_index = list(csv.DictReader((HERE / "QA_SOURCE_INDEX.csv").open(encoding="utf-8-sig", newline="")))
index_valid = all(row["qa_id"] in raw_ids and int(row["page"]) >= 1 and len(row["pdf_sha256"]) == 64 for row in source_index)
check("source_locators_valid", index_valid and {row["qa_id"] for row in source_index} == raw_ids, len(source_index))
check("evidence_fixtures_59", len(fixtures) == 59 and len({row["evidence_id"] for row in fixtures}) == 59, len(fixtures))
check("source_pdf_hashes_and_pages", all(row["direct_check"]["pdf_hash_match"] and row["direct_check"]["page_valid"] and row["direct_check"]["page_hash_match"] for row in fixtures), "All 59 evidence locators reconcile")

calculations = [calc for row in machine for calc in row.get("calculations", [])]
check("calculations_reproduced", len(calculations) == 13 and all(calc.get("reproduced") for calc in calculations), f"{sum(calc.get('reproduced', False) for calc in calculations)}/{len(calculations)}")
check("qa026_not_false_pass", next(row for row in machine if row["qa_id"] == "V42-QA-026")["status"] == "REVIEW_REQUIRED", "Completeness pending")
check("qa036_minimal", next(row for row in dossiers if row["qa_id"] == "V42-QA-036")["required_evidence_ids"] == ["EV033", "EV034"], "EV033;EV034")

with (HARD / "QA_38_FULL_AUDIT.csv").open(encoding="utf-8-sig", newline="") as stream:
    rejected = {row["qa_id"] for row in csv.DictReader(stream) if row["status"] == "REJECT"}
check("rejected_qas_retained", rejected <= {row["qa_id"] for row in dossiers} and rejected <= {row["qa_id"] for row in queue}, sorted(rejected))
parent_sha = sha256(HARD / "QA_EVIDENCE_REPAIR.jsonl")
lineage_ok = all(row["parent_qa_id"] in raw_ids and row["parent_sha256"] == parent_sha and row["revision_status"] == "PROPOSED_REVISION" and row["human_review_status"] == "PENDING_HUMAN_REVIEW" for row in revisions)
check("revision_lineage", lineage_ok, len(revisions))

pilot8 = next(row for row in jsonl(V41 / "QA_GROUND_UP_PILOT.jsonl") if row["qa_id"] == "V41-QA-008")
check("v41_qa008_no_retrospective_claim", bool(pilot8.get("unsupported_conditions")) and pilot8["review"]["status"] == "PENDING_HUMAN_REVIEW", pilot8["unsupported_conditions"])

tool_files = [HERE / "QA_REVIEW_TOOL/index.html", HERE / "QA_REVIEW_TOOL/app.js", HERE / "QA_REVIEW_TOOL/styles.css", HERE / "QA_REVIEW_TOOL/serve.py", HERE / "QA_REVIEW_TOOL/data/qa_review_data.json"]
tool_data = json.loads(tool_files[-1].read_text(encoding="utf-8"))
check("review_tool_real_data", all(path.is_file() for path in tool_files) and len(tool_data["qas"]) == 38 and tool_data["human_results_prefilled"] is False, len(tool_data["qas"]))

readiness = json.loads((HERE / "V4_3_BENCHMARK_READINESS.json").read_text(encoding="utf-8"))
check("coverage_layers_separated", readiness["counts"]["qa"] == 38 and readiness["counts"]["human_reviews"] == 0 and readiness["human_gold_ready"] is False, readiness["counts"])
check("expansion_no_go", readiness["benchmark_expansion_ready"] is False and readiness["official_benchmark_ready"] is False, readiness["decision"])

test_result = json.loads((HERE / "V4_3_TEST_RESULTS.json").read_text(encoding="utf-8"))
check("adversarial_tests_pass", test_result["all_pass"] is True, f"{test_result['passed']}/{test_result['total']}")

bundle = HERE / "V4_3_REVIEW_BUNDLE.zip"
bundle_manifest_path = HERE / "V4_3_BUNDLE_MANIFEST.json"
bundle_ok = bundle.is_file() and bundle_manifest_path.is_file()
bundle_detail: object = "missing"
if bundle_ok:
    bundle_manifest = json.loads(bundle_manifest_path.read_text(encoding="utf-8"))
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        bundle_ok = (
            bundle_manifest["candidate_test_included"] is False
            and bundle_manifest["source_pdfs_included"] is False
            and bundle_manifest["human_review_rows_included"] == 0
            and "research/vietirr_v4_3/QA_SOURCE_DOSSIERS.jsonl" in names
            and "research/vietirr_v4_3/V4_3_INDEPENDENT_AUDIT.py" in names
            and not any(name.lower().endswith(".pdf") for name in names)
            and not any("candidate_test" in name.lower() or "candidate-gold" in name.lower() for name in names)
        )
        bundle_detail = {"entries": len(names), "external_pdf_dependencies": bundle_manifest["external_pdf_dependencies"]}
check("review_bundle_reproducible_scope", bundle_ok, bundle_detail)

forbidden_names = [path.relative_to(HERE).as_posix() for path in HERE.rglob("*") if "candidate_test" in path.name.lower() or "candidate-gold" in path.name.lower()]
check("candidate_test_not_packaged", not forbidden_names, forbidden_names)
check("frozen_integrity_flags", readiness["scientific_integrity"]["raw_v4_2_mutated"] is False and readiness["scientific_integrity"]["frozen_v3_2_mutated"] is False and readiness["scientific_integrity"]["retrieval_baselines_mutated"] is False, readiness["scientific_integrity"])

passed = sum(row["passed"] for row in results)
output = {"total": len(results), "passed": passed, "failed": len(results) - passed, "all_pass": passed == len(results), "checks": results}
(HERE / "V4_3_INDEPENDENT_AUDIT.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: output[key] for key in ("total", "passed", "failed", "all_pass")}, ensure_ascii=False))
raise SystemExit(0 if output["all_pass"] else 1)
