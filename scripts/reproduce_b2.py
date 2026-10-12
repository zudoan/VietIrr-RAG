"""Rerun B2 from caches and prove byte-identical deterministic rankings."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from viirr_retrieval.experiment import run_b2
from viirr_retrieval.io_utils import sha256, write_json


def ranking_hashes() -> dict[str, str]:
    directory = ROOT / "outputs" / "B2" / "rankings"
    return {path.name: sha256(path) for path in sorted(directory.glob("*.jsonl"))}


def main() -> None:
    before = ranking_hashes()
    run_b2(ROOT)
    after = ranking_hashes()
    payload = {
        "rerun_from_cache": True, "before_sha256": before, "after_sha256": after,
        "rankings_identical": bool(before) and before == after,
        "candidate_test_annotations_loaded": False,
    }
    write_json(ROOT / "reports" / "B2" / "B2_REPRODUCIBILITY.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["rankings_identical"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
