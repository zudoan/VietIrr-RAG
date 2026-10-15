"""Create a reproducible V4.1 input seal without reading Candidate Test.

The candidate artifact is deliberately handled with stat() only.  It is never
opened and never hashed.  All other listed files are inputs that V4.1 is
allowed to inspect.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("V4_1_INPUT_FREEZE.json")

READABLE_INPUTS = [
    "data/documents.jsonl",
    "data/metadata/splits/family_assignments.jsonl",
    "data/v3_2_final_semantic/train.jsonl",
    "data/v3_2_final_semantic/dev.jsonl",
    "data/v3_2_final_semantic/metadata/splits.json",
    "reports/document_inventory/ALL_PDF_DOCUMENT_INVENTORY.csv",
    "research/vietirr_v4/DOMAIN_ONTOLOGY.md",
    "research/vietirr_v4/APPLICATION_USE_CASES.md",
    "research/vietirr_v4/CORPUS_COVERAGE_MATRIX.csv",
    "research/vietirr_v4/CORPUS_GAP_ANALYSIS.md",
    "research/vietirr_v4/human_validation/DOCUMENT_HUMAN_VALIDATION_LEDGER.csv",
    "reports/TCB_RR_P2_3/P2_3_FROZEN_CONFIG.json",
]

CANDIDATE_PATH = "data/v3_2_final_semantic/candidate_test.jsonl"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_snapshot() -> dict:
    readable = {}
    for rel in READABLE_INPUTS:
        path = ROOT / rel
        readable[rel] = {
            "exists": path.is_file(),
            "size_bytes": path.stat().st_size if path.is_file() else None,
            "sha256": sha256(path) if path.is_file() else None,
        }

    candidate = ROOT / CANDIDATE_PATH
    stat = candidate.stat() if candidate.is_file() else None
    frozen = json.loads((ROOT / "reports/TCB_RR_P2_3/P2_3_FROZEN_CONFIG.json").read_text(encoding="utf-8"))
    method_files = {}
    for rel, expected in frozen["code_file_sha256"].items():
        path = ROOT / rel
        actual = sha256(path) if path.is_file() else None
        method_files[rel] = {
            "expected_sha256": expected,
            "actual_sha256": actual,
            "matches": actual == expected,
        }

    return {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "V4.1 pre-change integrity snapshot",
        "readable_inputs": readable,
        "candidate_test_seal": {
            "path": CANDIDATE_PATH,
            "policy": "SEALED_NOT_OPENED_NOT_HASHED",
            "exists": bool(stat),
            "size_bytes_from_stat_only": stat.st_size if stat else None,
            "mtime_ns_from_stat_only": stat.st_mtime_ns if stat else None,
            "sha256": "INTENTIONALLY_NOT_COMPUTED",
        },
        "frozen_method": {
            "freeze_id": frozen.get("freeze_id"),
            "files": method_files,
            "all_match": all(v["matches"] for v in method_files.values()),
        },
        "claims": {
            "candidate_content_accessed": False,
            "candidate_hashed": False,
            "v3_2_mutation_authorized": False,
            "tcb_rr_mutation_authorized": False,
        },
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build_snapshot(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUT)
