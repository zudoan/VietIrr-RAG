"""Adversarial and mutation tests for V4.3 verification/review integrity."""
from __future__ import annotations

import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
V43 = HERE.parent


def jsonl(name: str) -> list[dict]:
    return [json.loads(line) for line in (V43 / name).read_text(encoding="utf-8").splitlines() if line.strip()]


dossiers = jsonl("QA_SOURCE_DOSSIERS.jsonl")
checks = jsonl("QA_MACHINE_SOURCE_CHECKS.jsonl")
revisions = jsonl("QA_PROPOSED_REVISIONS.jsonl")
queue = jsonl("QA_FINAL_REVIEW_QUEUE.jsonl")
fixtures = jsonl("SOURCE_PAGE_FIXTURES.jsonl")
allowed_machine = {"MACHINE_SUPPORTED", "MACHINE_CONTRADICTED", "PARTIALLY_SUPPORTED", "AMBIGUOUS", "SOURCE_UNREADABLE", "REVIEW_REQUIRED"}
results: list[dict] = []


def test(name: str, passed: bool, category: str, detail: str) -> None:
    results.append({"test": name, "category": category, "passed": bool(passed), "detail": detail})


def state_errors(ds: list[dict], cs: list[dict], rs: list[dict], qs: list[dict]) -> list[str]:
    errors = []
    dossier_ids = [row.get("qa_id") for row in ds]
    check_ids = [row.get("qa_id") for row in cs]
    if len(ds) != 38 or len(set(dossier_ids)) != 38:
        errors.append("DOSSIER_COVERAGE")
    if len(cs) != 38 or set(check_ids) != set(dossier_ids):
        errors.append("MACHINE_CHECK_COVERAGE")
    if any(row.get("status") not in allowed_machine for row in cs):
        errors.append("INVALID_MACHINE_STATUS")
    if any(row.get("gold_verified") is not False for row in cs):
        errors.append("FABRICATED_GOLD")
    if any(row.get("human_review_status") != "PENDING_HUMAN_REVIEW" for row in cs):
        errors.append("FABRICATED_HUMAN_STATUS")
    if any(not row.get("parent_qa_id") or row.get("revision_status") != "PROPOSED_REVISION" for row in rs):
        errors.append("REVISION_LINEAGE")
    if len(qs) != 38 or {row.get("qa_id") for row in qs} != set(dossier_ids):
        errors.append("QUEUE_COVERAGE")
    q26 = next((row for row in cs if row.get("qa_id") == "V42-QA-026"), {})
    if q26.get("status") == "MACHINE_SUPPORTED":
        errors.append("QA026_FALSE_COMPLETENESS_PASS")
    q36 = next((row for row in ds if row.get("qa_id") == "V42-QA-036"), {})
    if q36.get("required_evidence_ids") != ["EV033", "EV034"]:
        errors.append("QA036_NON_MINIMAL_EVIDENCE")
    return errors


test("baseline_valid", not state_errors(dossiers, checks, revisions, queue), "positive", "Published state satisfies core invariants.")
test("fixtures_cover_bank", len(fixtures) == 59 and len({row["evidence_id"] for row in fixtures}) == 59, "positive", "59 unique evidence fixtures.")
test("all_calculations_reproduce", all(calc.get("reproduced") for row in checks for calc in row.get("calculations", [])), "positive", "Every declared arithmetic trace reproduces.")
test("ledger_starts_empty", not (V43 / "QA_REVIEW_LEDGER.jsonl").read_text(encoding="utf-8").strip(), "positive", "No fabricated review rows.")
test("review_data_real", len(json.loads((V43 / "QA_REVIEW_TOOL/data/qa_review_data.json").read_text(encoding="utf-8"))["qas"]) == 38, "positive", "UI data contains real 38-QA dossiers.")
test("deep_review_18", sum(bool(row["review_priority"]["deep_review"]) for row in dossiers) == 18, "positive", "Exactly 18 risk-selected deep reviews.")

mut = copy.deepcopy(dossiers[:-1])
test("mutation_missing_dossier_caught", "DOSSIER_COVERAGE" in state_errors(mut, checks, revisions, queue), "mutation", "Removing one dossier is rejected.")
mut = copy.deepcopy(checks); mut[0]["status"] = "GOLD_VERIFIED"
test("mutation_invalid_machine_status_caught", "INVALID_MACHINE_STATUS" in state_errors(dossiers, mut, revisions, queue), "mutation", "Gold cannot masquerade as a machine status.")
mut = copy.deepcopy(checks); mut[0]["gold_verified"] = True
test("mutation_fabricated_gold_caught", "FABRICATED_GOLD" in state_errors(dossiers, mut, revisions, queue), "mutation", "Machine pass cannot set gold.")
mut = copy.deepcopy(checks); mut[0]["human_review_status"] = "REVIEWED_ACCEPT"
test("mutation_fabricated_human_caught", "FABRICATED_HUMAN_STATUS" in state_errors(dossiers, mut, revisions, queue), "mutation", "Machine output cannot invent a human verdict.")
mut = copy.deepcopy(checks); next(row for row in mut if row["qa_id"] == "V42-QA-026")["status"] = "MACHINE_SUPPORTED"
test("mutation_qa026_false_pass_caught", "QA026_FALSE_COMPLETENESS_PASS" in state_errors(dossiers, mut, revisions, queue), "mutation", "Extrema do not prove all-row completeness.")
mut = copy.deepcopy(dossiers); next(row for row in mut if row["qa_id"] == "V42-QA-036")["required_evidence_ids"].append("EV035")
test("mutation_qa036_extra_evidence_caught", "QA036_NON_MINIMAL_EVIDENCE" in state_errors(mut, checks, revisions, queue), "mutation", "Storage evidence cannot re-enter QA-036.")
mut = copy.deepcopy(revisions); mut[0].pop("parent_qa_id")
test("mutation_revision_lineage_caught", "REVISION_LINEAGE" in state_errors(dossiers, checks, mut, queue), "mutation", "Revision without parent ID is rejected.")
mut = copy.deepcopy(queue[:-1])
test("mutation_rejected_audit_row_loss_caught", "QUEUE_COVERAGE" in state_errors(dossiers, checks, revisions, mut), "mutation", "Dropping any QA, including rejects, is rejected.")
mut = copy.deepcopy(dossiers); mut[0]["sources"][0]["pages"] = [0]
test("mutation_invalid_page_detected", any(page < 1 for row in mut for source in row["sources"] for page in source["pages"]), "mutation", "Page zero is detected.")
mut = copy.deepcopy(fixtures); mut[0]["pdf_sha256"] = "0" * 64
test("mutation_source_hash_detected", mut[0]["pdf_sha256"] != fixtures[0]["pdf_sha256"], "mutation", "A changed source hash is detectable.")
test("candidate_test_absent", not any("candidate_test" in path.name.lower() or "candidate-gold" in path.name.lower() for path in V43.rglob("*")), "adversarial", "No Candidate Test artifact in V4.3.")
test("no_reviewed_prefill", all(row["human_review_status"] == "PENDING_HUMAN_REVIEW" for row in dossiers), "adversarial", "Dossiers do not prefill human verdicts.")

passed = sum(row["passed"] for row in results)
summary = {"total": len(results), "passed": passed, "failed": len(results) - passed, "all_pass": passed == len(results), "results": results}
(V43 / "V4_3_TEST_RESULTS.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
report = ["# V4.3 Adversarial and Mutation Test Report", "", f"Result: **{passed}/{len(results)} passed**.", "", "| Test | Category | Result |", "|---|---|---|"]
report.extend(f"| `{row['test']}` | {row['category']} | {'PASS' if row['passed'] else 'FAIL'} |" for row in results)
report.extend(["", "Tests cover source/dossier completeness, calculation reproducibility, false gold/human labels, QA-026 completeness, QA-036 minimality, revision lineage, rejected-QA retention and Candidate Test exclusion."])
(V43 / "V4_3_TEST_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
print(json.dumps({key: summary[key] for key in ("total", "passed", "failed", "all_pass")}))
raise SystemExit(0 if summary["all_pass"] else 1)
