"""Discover and independently validate V3.1 evidence relations."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evidence.relation_discovery import discover_relations
from src.validation.evidence_relation_validator import validate_relation


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    docs = read_jsonl(ROOT / "data" / "v3_1" / "metadata" / "documents.jsonl")
    regions = read_jsonl(ROOT / "data" / "parsed" / "regions.jsonl")
    tables = read_jsonl(ROOT / "data" / "parsed" / "tables.jsonl")
    candidates = discover_relations(docs, regions, tables)
    passed, rejected, uncertain = [], [], []
    for relation in candidates:
        status, errors = validate_relation(relation)
        relation["validation_status"] = status
        relation["validation_errors"] = errors
        relation["review_status"] = "DETERMINISTIC_REVIEWED"
        if status == "PASS":
            passed.append(relation)
        elif status == "UNCERTAIN":
            uncertain.append(relation)
        else:
            rejected.append(relation)
    out = ROOT / "data" / "v3_1" / "relations"
    write_jsonl(out / "evidence_relations.jsonl", passed)
    write_jsonl(out / "rejected_relations.jsonl", rejected)
    write_jsonl(out / "uncertain_relations.jsonl", uncertain)
    summary = {
        "candidates": len(candidates), "pass": len(passed), "fail": len(rejected), "uncertain": len(uncertain),
        "pass_types": dict(Counter(row["relation_type"] for row in passed)),
        "document_types": dict(Counter(ev["document_type"] for row in passed for ev in row["evidence"])),
    }
    (ROOT / "reports" / "v3_1" / "relation_discovery_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
