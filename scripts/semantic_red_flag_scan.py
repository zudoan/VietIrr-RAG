"""Scan final V3 accepted data for critical semantic red flags."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.structure.semantic_table_parser import DATE_LIKE, ROMAN, clean, fold
from src.validation.negative_semantic_validator_v3 import validate_negative
from src.validation.v3_semantic_validator import validate_record


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def main() -> None:
    core = read_jsonl(ROOT / "data" / "qa" / "core_qa.jsonl")
    challenge = read_jsonl(ROOT / "data" / "qa" / "challenge_qa.jsonl")
    negatives = []
    for name in ("minimal_negatives", "partial_sets", "redundant_sets"):
        negatives += read_jsonl(ROOT / "data" / "negatives" / f"{name}.jsonl")
    counts = Counter()
    examples: dict[str, list[str]] = {}
    seen = set()
    cell_usage = Counter()
    evidence_ids = {r["region_id"] for r in read_jsonl(ROOT / "data" / "parsed" / "regions.jsonl")}
    for table in read_jsonl(ROOT / "data" / "parsed" / "tables.jsonl"):
        evidence_ids.update(t["tuple_id"] for t in table.get("semantic_tuples", []))
    for qa in core + challenge:
        status, errors = validate_record(qa)
        for error in errors:
            counts[error] += 1; examples.setdefault(error, []).append(qa["qa_id"])
        qkey = fold(qa["question"])
        if qkey in seen:
            counts["EXACT_DUPLICATE_QUESTION"] += 1; examples.setdefault("EXACT_DUPLICATE_QUESTION", []).append(qa["qa_id"])
        seen.add(qkey)
        for ev_id in qa.get("gold_evidence_ids", []):
            if ev_id not in evidence_ids:
                counts["UNRESOLVED_EVIDENCE_REFERENCE"] += 1; examples.setdefault("UNRESOLVED_EVIDENCE_REFERENCE", []).append(qa["qa_id"])
            if "_R" in ev_id and "_C" in ev_id:
                cell_usage[ev_id] += 1
        for sig in qa.get("provenance_signatures", []):
            eraw = clean((sig.get("entity") or {}).get("raw")); mraw = clean((sig.get("metric") or {}).get("raw"))
            if fold(eraw) in {"tt", "stt", "date", "year", "ngay", "thang", "nam"} or DATE_LIKE.fullmatch(eraw) or ROMAN.fullmatch(eraw):
                counts["CRITICAL_ENTITY_RED_FLAG"] += 1; examples.setdefault("CRITICAL_ENTITY_RED_FLAG", []).append(qa["qa_id"])
            if fold(mraw) in {"tt", "stt", "date", "year", "ngay", "thang", "nam"}:
                counts["CRITICAL_METRIC_RED_FLAG"] += 1; examples.setdefault("CRITICAL_METRIC_RED_FLAG", []).append(qa["qa_id"])
    for ev_id, used in cell_usage.items():
        if used > 3:
            counts["SAME_CELL_LIMIT_EXCEEDED"] += 1; examples.setdefault("SAME_CELL_LIMIT_EXCEEDED", []).append(f"{ev_id}:{used}")
    for row in negatives:
        ok, errors = validate_negative(row)
        for error in errors:
            counts[f"NEGATIVE_{error}"] += 1; examples.setdefault(f"NEGATIVE_{error}", []).append(row["negative_id"])
    critical = sum(counts.values())
    output = {
        "scan_status": "PASS" if critical == 0 else "FAIL",
        "critical_semantic_red_flags": critical,
        "counts": dict(sorted(counts.items())),
        "examples": {k: v[:20] for k, v in examples.items()},
        "scanned": {"qa": len(core) + len(challenge), "negatives": len(negatives)},
    }
    path = ROOT / "reports" / "V3_SEMANTIC_RED_FLAG_SCAN.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
