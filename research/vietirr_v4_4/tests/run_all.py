"""Run all mandatory V4.4 tests without third-party dependencies."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import test_coverage
import test_document_relations
import test_qa_quality

HERE = Path(__file__).resolve().parent
results = test_coverage.run() + test_document_relations.run() + test_qa_quality.run()
passed = sum(row["passed"] for row in results)
payload = {
    "suite": "VIETIRR_RAG_V4_4_MANDATORY_22",
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "total": len(results),
    "passed": passed,
    "failed": len(results) - passed,
    "all_passed": passed == len(results) == 22,
    "candidate_test_accessed": False,
    "results": results,
}
(HERE / "V4_4_TEST_RESULTS.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
lines = ["# V4.4 mandatory test report", "", f"Result: **{passed}/{len(results)} passed**.", "", "| ID | Case | Fixture | Result |", "|---|---|---|---|"]
for row in results:
    lines.append(f"| {row['case_id']} | {row['name']} | {row['fixture_type']} | {'PASS' if row['passed'] else 'FAIL'} |")
lines.extend(["", "Negative cases are synthetic mutations only. Positive cases Q18-Q20 load actual V4.4 artifacts. Candidate Test was not accessed."])
(HERE / "V4_4_TEST_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(json.dumps({key: payload[key] for key in ("total", "passed", "failed", "all_passed")}))
raise SystemExit(0 if payload["all_passed"] else 1)

