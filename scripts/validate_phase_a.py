from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.io_utils import read_jsonl, sha256_file, write_json
from src.validation.negative_minimality_validator import validate as validate_negative
from src.validation.run_validators import VALIDATORS, build_context


def main() -> None:
    documents = read_jsonl("data/documents.jsonl")
    pages = read_jsonl("data/pages.jsonl")
    regions = read_jsonl("data/regions.jsonl")
    tables = read_jsonl("data/tables.jsonl")
    core = read_jsonl("data/qa/core_qa.jsonl")
    challenge = read_jsonl("data/qa/challenge_qa.jsonl")
    negatives = read_jsonl("data/negatives/minimal_negatives.jsonl")
    stats = json.loads(Path("reports/dataset_stats.json").read_text(encoding="utf-8"))
    recorded_checksums = json.loads(Path("checksums/phaseA_checksums.json").read_text(encoding="utf-8"))
    context = build_context(documents, regions, tables)
    failures = []

    expected_counts = {
        "documents": len(documents), "pages": len(pages), "regions": len(regions), "tables": len(tables),
        "core_qa": len(core), "challenge_qa": len(challenge), "valid_minimal": len(negatives),
    }
    actual_counts = {
        "documents": stats["corpus"]["documents"], "pages": stats["corpus"]["pages"],
        "regions": stats["corpus"]["regions"], "tables": stats["corpus"]["tables"],
        "core_qa": stats["qa_dataset"]["core_qa"], "challenge_qa": stats["qa_dataset"]["challenge_qa"],
        "valid_minimal": stats["hard_negatives"]["valid_minimal"],
    }
    if expected_counts != actual_counts:
        failures.append({"check": "CANONICAL_COUNTS", "expected": expected_counts, "actual": actual_counts})

    for qa in core + challenge:
        if qa.get("validation_status") != "PASS":
            failures.append({"check": "ACCEPTED_QA_NOT_PASS", "id": qa.get("qa_id")})
        for name, validator in VALIDATORS.items():
            result = validator(qa, context)
            if name == "evidence_necessity" and len(qa.get("gold_evidence", [])) < 2:
                if result["status"] != "SKIP_NOT_APPLICABLE":
                    failures.append({"check": name, "id": qa["qa_id"], "result": result})
            elif result["status"] != "PASS":
                failures.append({"check": name, "id": qa["qa_id"], "result": result})

    for negative in negatives:
        result = validate_negative(negative, {})
        if result["status"] != "PASS" or negative.get("validation_status") != "VALID_MINIMAL":
            failures.append({"check": "NEGATIVE_MINIMALITY", "id": negative.get("negative_id"), "result": result})

    for path, expected in recorded_checksums.items():
        actual = sha256_file(path)
        if actual != expected:
            failures.append({"check": "FILE_CHECKSUM", "path": path, "expected": expected, "actual": actual})

    builder_text = Path("scripts/build_phase_a.py").read_text(encoding="utf-8")
    if "v2_" in builder_text.lower() or "pilot_qa" in builder_text.lower():
        failures.append({"check": "OLD_QA_DEPENDENCY", "detail": "canonical builder references a V2/legacy QA artifact"})

    readme = Path("README.md").read_text(encoding="utf-8")
    for count in (len(core), len(challenge), len(negatives)):
        if str(count) not in readme:
            failures.append({"check": "README_COUNT_CONSISTENCY", "missing_count": count})

    required = [
        "reports/source_audit.md", "reports/parsing_audit.md", "reports/table_quality.md", "reports/qa_quality.md",
        "reports/multi_evidence_audit.md", "reports/negative_quality.md", "reports/distribution.md",
        "reports/dataset_stats.json", "reports/phaseA_readiness.json", "reports/final_dataset_audit.json",
        "DATASET_CARD.md", "CROSS_DOMAIN_COMPATIBILITY.md",
    ]
    for path in required:
        if not Path(path).exists():
            failures.append({"check": "MISSING_OUTPUT", "path": path})

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "status": "PASS" if not failures else "FAIL",
        "qa_revalidated": len(core) + len(challenge), "negatives_revalidated": len(negatives),
        "checksums_revalidated": len(recorded_checksums), "failures": failures,
    }
    write_json("reports/validation_run.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
