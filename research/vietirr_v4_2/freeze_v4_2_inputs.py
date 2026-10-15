"""Seal V4.1 and frozen dependencies before V4.2 work.

Candidate Test is handled with stat() only and is never opened or hashed.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / "V4_2_INPUT_FREEZE.json"
CANDIDATE = "data/v3_2_final_semantic/candidate_test.jsonl"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    inputs = []
    roots = [ROOT / "research/vietirr_v4_1", ROOT / "data/v4_corpus"]
    for base in roots:
        for path in sorted(p for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
            inputs.append({"path": path.relative_to(ROOT).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha(path)})
    for rel in ["data/v3_2_final_semantic/train.jsonl", "data/v3_2_final_semantic/dev.jsonl",
                "data/documents.jsonl", "reports/TCB_RR_P2_3/P2_3_FROZEN_CONFIG.json"]:
        p = ROOT / rel; inputs.append({"path": rel, "size_bytes": p.stat().st_size, "sha256": sha(p)})
    cp = ROOT / CANDIDATE; st = cp.stat()
    result = {"schema_version": "1.0", "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "purpose": "V4.2 pre-change seal", "readable_inputs": inputs,
              "candidate_test": {"path": CANDIDATE, "policy": "SEALED_NOT_OPENED_NOT_HASHED",
                                   "size_bytes_from_stat_only": st.st_size, "mtime_ns_from_stat_only": st.st_mtime_ns,
                                   "sha256": "INTENTIONALLY_NOT_COMPUTED"},
              "claims": {"v4_1_mutation_authorized": False, "v3_2_mutation_authorized": False,
                         "candidate_content_accessed": False, "candidate_hashed": False}}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"sealed_files": len(inputs), "candidate_policy": result["candidate_test"]["policy"]}))


if __name__ == "__main__": main()
