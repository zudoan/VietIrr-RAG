"""Create deterministic, stratified V3.1 external-review samples."""

from __future__ import annotations

import hashlib
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.io_utils import read_jsonl, write_jsonl


def stable_key(row: dict) -> str:
    value = row.get("qa_id") or row.get("negative_id") or ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stratified(rows: list[dict], key_fn, target: int = 100) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[key_fn(row)].append(row)
    for values in groups.values():
        values.sort(key=stable_key)
    chosen = []
    while len(chosen) < min(target, len(rows)):
        progressed = False
        for key in sorted(groups, key=str):
            if groups[key]:
                chosen.append(groups[key].pop(0)); progressed = True
                if len(chosen) >= min(target, len(rows)):
                    break
        if not progressed:
            break
    return chosen


def qa_review(row: dict) -> dict:
    return {
        "review_status": "AUTO_AUDIT_SAMPLE", "human_validated": False,
        "qa_id": row["qa_id"], "qa_type": row.get("qa_type"),
        "question": row["question"], "answer": row["answer"],
        "exact_evidence": row.get("gold_evidence", []),
        "document_titles": sorted({e.get("document_title") for e in row.get("gold_evidence", []) if e.get("document_title")}),
        "pages": row.get("gold_pages"),
        "evidence_relation": {
            "relation_id": row.get("relation_id"), "relation_type": row.get("relation_type"),
            "relation_metadata": row.get("relation_metadata"),
        } if row.get("relation_id") else None,
        "provenance_signatures": row.get("provenance_signatures", []),
        "answer_components": row.get("answer_components", []),
        "support_matrix": row.get("evidence_support_matrix", {}),
        "ablation_results": (row.get("necessity_validation") or {}).get("ablations") or {},
        "necessity_status": row.get("necessity_status"),
    }


def main() -> None:
    core = read_jsonl(ROOT / "data/v3_1/qa/core_qa.jsonl")
    challenge = read_jsonl(ROOT / "data/v3_1/qa/challenge_qa.jsonl")
    qa_index = {row["qa_id"]: row for row in core + challenge}
    minimal = read_jsonl(ROOT / "data/v3_1/negatives/minimal_negatives.jsonl")
    nonminimal = read_jsonl(ROOT / "data/v3_1/negatives/hard_nonminimal_negatives.jsonl")
    evidence = {e["evidence_id"]: e for row in core + challenge for e in row.get("gold_evidence", [])}
    for row in minimal + nonminimal:
        for ev in row.get("candidate_evidence", []):
            evidence[ev["evidence_id"]] = ev

    core_sample = [qa_review(x) for x in stratified(core, lambda r: (r.get("qa_type"), r.get("document_type")))]
    challenge_sample = [qa_review(x) for x in stratified(challenge, lambda r: (r.get("relation_type"), r.get("modality"), r.get("document_type")))]
    negative_source = minimal + nonminimal
    negative_sample = []
    for row in stratified(negative_source, lambda r: (r.get("negative_status"), r.get("negative_type"))):
        qa = qa_index[row["source_qa_id"]]
        gold_id = row.get("gold_target_evidence_id") or row.get("removed_evidence_id")
        negative_id = row.get("negative_evidence_id") or row.get("redundant_evidence_id")
        negative_sample.append({
            "review_status": "AUTO_AUDIT_SAMPLE", "human_validated": False,
            "negative_id": row["negative_id"], "source_qa_id": row["source_qa_id"],
            "negative_type": row["negative_type"], "negative_status": row.get("negative_status"),
            "question": row["question"], "reference_answer": qa.get("answer"),
            "gold_evidence": evidence.get(gold_id) if gold_id else qa.get("gold_evidence"),
            "negative_evidence": evidence.get(negative_id),
            "target_signature": row.get("gold_signature"),
            "negative_signature": row.get("negative_signature"),
            "differing_factors": row.get("signature_differences") or row.get("unsupported_component_ids") or ["redundant_related_evidence"],
            "candidate_evidence_ids": row.get("candidate_evidence_ids"),
            "source_grounded": row.get("source_grounded"),
        })
    out = ROOT / "reports/v3_1/review_sample"
    write_jsonl(out / "core_100.jsonl", core_sample)
    write_jsonl(out / "challenge_100.jsonl", challenge_sample)
    write_jsonl(out / "negatives_100.jsonl", negative_sample)
    print({"core": len(core_sample), "challenge": len(challenge_sample), "negatives": len(negative_sample)})


if __name__ == "__main__":
    main()
