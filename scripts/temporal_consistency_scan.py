"""Scan a QA JSONL file with the final evidence-time validator."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.validation.evidence_time_validator_final import validate_qa_time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", default="data/v3_2_final/all_qa.jsonl")
    parser.add_argument("--output", default="reports/v3_2_final_semantic/temporal_semantics_audit.json")
    args = parser.parse_args()
    rows = [json.loads(line) for line in (ROOT / args.input).open(encoding="utf-8") if line.strip()]
    records = [{"qa_id": row["qa_id"], **validate_qa_time(row)} for row in rows]
    payload = {"input": args.input, "total_qa": len(rows),
               "status_counts": dict(Counter(x["status"] for x in records)), "records": records}
    target = ROOT / args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "records"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
