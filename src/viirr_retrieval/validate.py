from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .io_utils import iter_jsonl, load_config, write_json


def validate_b1(root: Path) -> dict:
    config = load_config(root)
    source = config["source"]
    units = list(iter_jsonl(root / config["processed"]["evidence_units"]))
    unit_ids = {row["evidence_id"] for row in units}
    all_qa = list(iter_jsonl(root / source["benchmark"] / "all_qa.jsonl"))
    train = list(iter_jsonl(root / source["benchmark"] / "train.jsonl"))
    dev = list(iter_jsonl(root / source["benchmark"] / "dev.jsonl"))
    candidate = list(iter_jsonl(root / source["benchmark"] / "candidate_test.jsonl"))
    all_gold = {eid for row in all_qa for eid in row.get("retrieval_evidence_ids", [])}
    missing = sorted(all_gold - unit_ids)
    group_splits: dict[str, set[str]] = defaultdict(set)
    doc_splits: dict[str, set[str]] = defaultdict(set)
    for split, rows in (("train", train), ("dev", dev), ("candidate_test", candidate)):
        for row in rows:
            group_splits[row["leakage_group_id"]].add(split)
            for doc_id in row.get("gold_doc_ids", []):
                doc_splits[doc_id].add(split)
    group_leaks = {key: sorted(value) for key, value in group_splits.items() if len(value) > 1}
    doc_leaks = {key: sorted(value) for key, value in doc_splits.items() if len(value) > 1}
    minimal = sum(1 for _ in iter_jsonl(root / source["benchmark"] / "negatives/minimal_negatives.jsonl"))
    hard = sum(1 for _ in iter_jsonl(root / source["benchmark"] / "negatives/hard_nonminimal_negatives.jsonl"))
    counts = {
        "documents": sum(1 for _ in iter_jsonl(root / source["documents"])),
        "pages": sum(1 for _ in iter_jsonl(root / source["pages"])),
        "source_text_regions": sum(1 for _ in iter_jsonl(root / source["regions"])),
        "source_tables": sum(1 for _ in iter_jsonl(root / source["tables"])),
        "indexable_evidence_units": len(units), "accepted_qa": len(all_qa),
        "core": sum(not row.get("relation_type") for row in all_qa),
        "challenge": sum(bool(row.get("relation_type")) for row in all_qa),
        "source_grounded_negatives": minimal + hard, "dev_qa": len(dev),
        "dev_retrieval_multi": sum(row.get("retrieval_evidence_count", 0) >= 2 for row in dev),
    }
    expected = {"documents": 89, "pages": 2479, "source_text_regions": 30382,
                "source_tables": 406, "indexable_evidence_units": 27045,
                "accepted_qa": 545, "core": 378, "challenge": 167,
                "source_grounded_negatives": 704, "dev_qa": 93, "dev_retrieval_multi": 25}
    checks = {
        "EXPECTED_COUNTS": counts == expected,
        "MISSING_GOLD_RETRIEVAL_UNITS_ZERO": len(missing) == 0,
        "MISSING_INDEXABLE_GOLD_UNITS_ZERO": len(missing) == 0,
        "DOCUMENT_FAMILY_LEAKAGE_ZERO": not group_leaks and not doc_leaks,
        "UNIQUE_INDEXABLE_EVIDENCE_IDS": len(unit_ids) == len(units),
        "INDEX_SCHEMA_NO_QA_GOLD_FIELDS": all(not ({"question", "answer", "gold_evidence", "retrieval_evidence_ids"} & set(row)) for row in units),
    }
    report = {
        "B1_INTEGRITY": "PASS" if all(checks.values()) else "FAIL",
        "counts": counts, "expected_counts": expected, "checks": checks,
        "missing_gold_retrieval_units": missing, "missing_gold_retrieval_unit_count": len(missing),
        "missing_indexable_gold_unit_count": len(missing),
        "document_family_leakage": len(group_leaks) + len(doc_leaks),
        "group_leaks": group_leaks, "document_leaks": doc_leaks,
        "candidate_test_use": "integrity/leakage verification only; no retrieval evaluation or tuning",
    }
    write_json(root / "reports" / "B1_INTEGRITY.json", report)
    return report

