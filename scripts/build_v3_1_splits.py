"""Regenerate leakage-safe V3.1 splits by connected document families."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.io_utils import read_jsonl, write_json, write_jsonl
from src.structure.semantic_table_parser import fold


class UnionFind:
    def __init__(self, values):
        self.parent = {v: v for v in values}

    def find(self, value):
        root = value
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[value] != value:
            value, self.parent[value] = self.parent[value], root
        return root

    def union(self, left, right):
        a, b = self.find(left), self.find(right)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def family_key(doc: dict) -> str:
    title = fold(doc.get("title", ""))
    title = re.sub(r"\b(?:ngay\s*)?\d{1,2}[/-]\d{1,2}(?:[/-]20\d{2})?\b", " DATE ", title)
    title = re.sub(r"\b20\d{2}\b", " YEAR ", title)
    title = re.sub(r"\b(?:so|quyet dinh)\s*\d+[a-z0-9/-]*", " DECISION ", title)
    title = re.sub(r"\b\d+\b", " # ", title)
    title = re.sub(r"[^a-z0-9#]+", " ", title)
    tokens = [t for t in title.split() if t not in {"bao", "cao", "ban", "tin", "nam"}]
    return f"{doc.get('source_group','')}::{' '.join(tokens[:18])}"


def is_challenge(row: dict) -> bool:
    return bool(row.get("relation_id") or row.get("relation_type"))


def choose_subset(groups: list[tuple[str, list[dict]]], low: int, high: int, challenge_priority: bool) -> set[str]:
    # Deterministic knapsack: one best feature score for each reachable count.
    states: dict[tuple[int, int, int, int], tuple[float, tuple[str, ...]]] = {(0, 0, 0, 0): (0.0, ())}
    for group_id, rows in sorted(groups, key=lambda x: x[0]):
        size = len(rows)
        features = sum(
            (5 if is_challenge(r) else 0)
            + (3 if r.get("modality") == "TEXT_TABLE" else 0)
            + (2 if r.get("cross_page") else 0)
            + (2 if r.get("document_type") == "core_long" and is_challenge(r) else 0)
            for r in rows
        ) if challenge_priority else sum(1 for r in rows if not is_challenge(r))
        group_challenge = sum(is_challenge(r) for r in rows)
        group_core_long = sum(is_challenge(r) and r.get("document_type") == "core_long" for r in rows)
        group_text_table = sum(r.get("modality") == "TEXT_TABLE" for r in rows)
        for (total, challenge_count, core_long_count, text_table_count), (score, selected) in list(states.items())[::-1]:
            new_total = total + size
            if new_total > high:
                continue
            new_challenge = challenge_count + group_challenge
            new_core_long = core_long_count + group_core_long
            new_text_table = text_table_count + group_text_table
            candidate = (score + features, selected + (group_id,))
            state_key = (new_total, new_challenge, new_core_long, new_text_table)
            if state_key not in states or candidate[0] > states[state_key][0]:
                states[state_key] = candidate
    viable = [(key, value) for key, value in states.items()
              if low <= key[0] <= high and (not challenge_priority or
                  (40 <= key[1] <= 110 and key[0] - key[1] >= 30 and key[2] >= 15 and key[3] >= 10))]
    if not viable:
        viable = [(key, value) for key, value in states.items() if key[0] > 0]
    (_, _, _, _), (_, selected) = max(viable, key=lambda item: (item[1][0], -abs(item[0][0] - low), item[0][0]))
    return set(selected)


def main() -> None:
    docs = read_jsonl(ROOT / "data/v3_1/metadata/documents.jsonl")
    core = read_jsonl(ROOT / "data/v3_1/qa/core_qa.jsonl")
    challenge = read_jsonl(ROOT / "data/v3_1/qa/challenge_qa.jsonl")
    rows = core + challenge
    doc_map = {d["doc_id"]: d for d in docs}
    uf = UnionFind(doc_map)
    family_docs: dict[str, list[str]] = defaultdict(list)
    for doc in docs:
        family_docs[family_key(doc)].append(doc["doc_id"])
    for members in family_docs.values():
        for other in members[1:]:
            uf.union(members[0], other)
    for row in rows:
        members = [x for x in row.get("doc_ids", [row.get("doc_id")]) if x in doc_map]
        for other in members[1:]:
            uf.union(members[0], other)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        members = [x for x in row.get("doc_ids", [row.get("doc_id")]) if x in doc_map]
        if not members:
            raise ValueError(f"QA without resolved document: {row.get('qa_id')}")
        grouped[uf.find(members[0])].append(row)
    groups = list(grouped.items())
    test_groups = choose_subset(groups, 100, 150, True)
    remaining = [item for item in groups if item[0] not in test_groups]
    dev_groups = choose_subset(remaining, 70, 100, False)
    assignments = {gid: ("candidate_gold_test" if gid in test_groups else "dev" if gid in dev_groups else "train") for gid in grouped}

    outputs = {name: [] for name in ("train", "dev", "candidate_gold_test")}
    doc_splits: dict[str, str] = {}
    for gid, group_rows in grouped.items():
        split = assignments[gid]
        for source in group_rows:
            row = dict(source); row["split"] = split; row["leakage_group_id"] = gid
            outputs[split].append(row)
            for doc_id in row.get("doc_ids", [row.get("doc_id")]):
                prior = doc_splits.setdefault(doc_id, split)
                if prior != split:
                    raise ValueError(f"Document leakage: {doc_id}")
    out = ROOT / "data/v3_1/qa"
    for split, split_rows in outputs.items():
        write_jsonl(out / f"{split}.jsonl", sorted(split_rows, key=lambda x: x["qa_id"]))
    write_jsonl(ROOT / "data/v3_1/metadata/splits.jsonl", [
        {"doc_id": doc_id, "family_key": family_key(doc_map[doc_id]), "leakage_group_id": uf.find(doc_id), "split": split}
        for doc_id, split in sorted(doc_splits.items())
    ])
    families_by_split = defaultdict(set)
    for doc_id, split in doc_splits.items():
        families_by_split[split].add(family_key(doc_map[doc_id]))
    overlaps = {}
    split_names = list(outputs)
    for i, left in enumerate(split_names):
        for right in split_names[i + 1:]:
            overlaps[f"{left}__{right}"] = sorted(families_by_split[left] & families_by_split[right])
    summary = {
        "counts": {name: len(value) for name, value in outputs.items()},
        "challenge_counts": {name: sum(is_challenge(r) for r in value) for name, value in outputs.items()},
        "test_coverage": {
            "core": sum(not is_challenge(r) for r in outputs["candidate_gold_test"]),
            "challenge": sum(is_challenge(r) for r in outputs["candidate_gold_test"]),
            "multi_evidence": sum(r.get("evidence_count", 0) >= 2 for r in outputs["candidate_gold_test"]),
            "cross_page": sum(bool(r.get("cross_page")) for r in outputs["candidate_gold_test"]),
            "text_table": sum(r.get("modality") == "TEXT_TABLE" for r in outputs["candidate_gold_test"]),
            "table_table": sum(r.get("modality") == "TABLE_TABLE" for r in outputs["candidate_gold_test"]),
            "core_long_challenge": sum(r.get("document_type") == "core_long" and is_challenge(r) for r in outputs["candidate_gold_test"]),
        },
        "document_overlap_count": 0,
        "family_overlap_count": sum(len(v) for v in overlaps.values()),
        "family_overlaps": overlaps,
        "leakage_audit_pass": not any(overlaps.values()),
        "split_unit": "connected document-family and QA co-occurrence component",
    }
    write_json(ROOT / "reports/v3_1/split_audit.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
