"""Create leakage-safe document-family V3 splits and candidate gold test."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def family_key(doc: dict) -> str:
    text = unicodedata.normalize("NFKD", doc.get("title", ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower().replace("đ", "d")
    text = re.sub(r"\b(?:20\d{2}|\d{1,2})\b", "#", text)
    text = re.sub(r"\b(?:ngay|tuan|thang|ky|dot)\s*#", "SERIES", text)
    text = re.sub(r"[^a-z#]+", " ", text)
    tokens = [t for t in text.split() if t not in {"bao", "cao", "ban", "tin", "nam"}]
    base = " ".join(tokens[:12])
    return f"{doc.get('source_group')}::{base}"


def main() -> None:
    docs = {d["doc_id"]: d for d in read_jsonl(ROOT / "data" / "parsed" / "documents.jsonl")}
    qa = read_jsonl(ROOT / "data" / "qa" / "core_qa.jsonl") + read_jsonl(ROOT / "data" / "qa" / "challenge_qa.jsonl")
    by_family = defaultdict(list)
    for row in qa:
        by_family[family_key(docs[row["doc_id"]])].append(row)
    # Deterministic family assignment targets roughly 67/15/18 percent by QA.
    buckets = {"train": [], "dev": [], "candidate_gold_test": []}
    targets = {"train": 0.67 * len(qa), "dev": 0.15 * len(qa), "candidate_gold_test": 0.18 * len(qa)}
    families = sorted(by_family, key=lambda f: (-len(by_family[f]), hashlib.sha256(f.encode()).hexdigest()))
    assignments = []
    for family in families:
        choices = sorted(buckets, key=lambda s: (len(buckets[s]) / max(targets[s], 1), s))
        split = choices[0]
        buckets[split].extend(by_family[family])
        assignments.append({"family_id": hashlib.sha256(family.encode()).hexdigest()[:16], "family_key": family, "split": split, "doc_ids": sorted({q["doc_id"] for q in by_family[family]}), "qa_count": len(by_family[family])})
    # Candidate gold is bounded for future human adjudication without ever
    # splitting a document family between candidate-test and dev.
    candidate_assignments = sorted(
        # Rebalance the held-out evaluation families between dev and candidate
        # test; training families remain frozen and isolated.
        (row for row in assignments if row["split"] in {"dev", "candidate_gold_test"}),
        # Prefer several smaller families so the human-review package is not
        # dominated by one long document series.
        key=lambda row: (row["qa_count"], row["family_id"]),
    )
    kept_families: set[str] = set()
    kept_count = 0
    for row in candidate_assignments:
        proposed = kept_count + row["qa_count"]
        if (kept_count < 100 and proposed <= 150) or (kept_count >= 100 and proposed <= 120):
            kept_families.add(row["family_key"])
            kept_count = proposed
    candidate = []
    buckets["dev"] = []
    for row in candidate_assignments:
        family_rows = by_family[row["family_key"]]
        if row["family_key"] in kept_families:
            candidate.extend(family_rows)
            row["split"] = "candidate_gold_test"
        else:
            buckets["dev"].extend(family_rows)
            row["split"] = "dev"
    candidate = sorted(candidate, key=lambda q: hashlib.sha256(q["qa_id"].encode()).hexdigest())
    if not 100 <= len(candidate) <= 150:
        raise RuntimeError(f"whole-family candidate test outside 100-150 range: {len(candidate)}")
    write_jsonl(ROOT / "data" / "qa" / "train.jsonl", buckets["train"])
    write_jsonl(ROOT / "data" / "qa" / "dev.jsonl", buckets["dev"])
    write_jsonl(ROOT / "data" / "qa" / "candidate_gold_test.jsonl", candidate)
    write_jsonl(ROOT / "data" / "metadata" / "splits" / "family_assignments.jsonl", assignments)
    metadata = {
        "strategy": "document_family_and_series_grouped",
        "human_validated": False,
        "candidate_gold_test_status": "CANDIDATE_ONLY_PENDING_HUMAN_REVIEW",
        "counts": {"train": len(buckets["train"]), "dev": len(buckets["dev"]), "candidate_gold_test": len(candidate)},
        "leakage_controls": ["same document", "same normalized series", "same reupload family", "same source-period family"],
    }
    (ROOT / "data" / "metadata" / "splits.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
