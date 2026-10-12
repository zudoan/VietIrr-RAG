"""Build and validate real-evidence V3.1 negative sets."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.io_utils import read_jsonl, write_json, write_jsonl
from src.negatives.source_grounded_v3_1 import build_minimal, build_partial, build_redundant, build_table_pool
from src.validation.source_grounded_negative_validator import validate


def main() -> None:
    docs = read_jsonl(ROOT / "data/v3_1/metadata/documents.jsonl")
    tables = read_jsonl(ROOT / "data/parsed/tables.jsonl")
    core = read_jsonl(ROOT / "data/v3_1/qa/core_qa.jsonl")
    challenge = read_jsonl(ROOT / "data/v3_1/qa/challenge_qa.jsonl")
    qa = core + challenge
    pool = build_table_pool(docs, tables)
    evidence = {ev["evidence_id"]: ev for ev in pool}
    for row in qa:
        for ev in row.get("gold_evidence", []):
            evidence[ev["evidence_id"]] = ev
    qa_index = {row["qa_id"]: row for row in qa}

    minimal, rejected_min = validate(build_minimal(qa, pool, docs), evidence, qa_index)
    partial, rejected_partial = validate(build_partial(challenge), evidence, qa_index)
    redundant, rejected_redundant = validate(build_redundant(challenge, pool, docs), evidence, qa_index)
    rejected = rejected_min + rejected_partial + rejected_redundant
    out = ROOT / "data/v3_1/negatives"
    write_jsonl(out / "minimal_negatives.jsonl", minimal)
    write_jsonl(out / "partial_sets.jsonl", partial)
    write_jsonl(out / "redundant_sets.jsonl", redundant)
    write_jsonl(out / "hard_nonminimal_negatives.jsonl", partial + redundant)
    write_jsonl(out / "rejected_negatives.jsonl", rejected)
    summary = {
        "source_grounded_total": len(minimal) + len(partial) + len(redundant),
        "minimal_source_grounded": len(minimal), "partial": len(partial), "redundant": len(redundant),
        "rejected": len(rejected), "metadata_only_remaining": 0, "query_rewrite_only_remaining": 0,
        "minimal_types": dict(Counter(row["negative_type"] for row in minimal)),
        "all_negative_evidence_resolved": all(
            (not row.get("negative_evidence_id") or row["negative_evidence_id"] in evidence)
            for row in minimal + partial + redundant
        ),
    }
    write_json(ROOT / "reports/v3_1/negative_build_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
