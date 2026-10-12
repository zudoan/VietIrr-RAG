"""Correct historical active V3 labels while preserving snapshots/v3_0."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "data/qa/core_qa.jsonl", ROOT / "data/qa/challenge_qa.jsonl",
    ROOT / "data/qa/train.jsonl", ROOT / "data/qa/dev.jsonl",
    ROOT / "data/qa/candidate_gold_test.jsonl",
    ROOT / "reports/v3_review_sample/core_100.jsonl",
    ROOT / "reports/v3_review_sample/challenge_100.jsonl",
    ROOT / "reports/v3_review_sample/negatives_100.jsonl",
    ROOT / "reports/V3_LLM_REVIEW_AUDIT.json",
    ROOT / "reports/V3_FINAL_DATASET_AUDIT.json",
]

for path in TARGETS:
    if path.exists():
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace('"LLM_REVIEWED"', '"AUTO_VALIDATED"'), encoding="utf-8", newline="\n")
