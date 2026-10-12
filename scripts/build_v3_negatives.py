"""Build and validate the final V3 negative sets."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.negatives.v3_negatives import build_minimal, build_partial, build_redundant
from src.validation.negative_semantic_validator_v3 import validate_negatives


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    core = read_jsonl(ROOT / "data" / "qa" / "core_qa.jsonl")
    challenge = read_jsonl(ROOT / "data" / "qa" / "challenge_qa.jsonl")
    minimal, r1 = validate_negatives(build_minimal(core + challenge[:100]))
    partial, r2 = validate_negatives(build_partial(challenge))
    redundant, r3 = validate_negatives(build_redundant(challenge, core + challenge))
    out = ROOT / "data" / "negatives"
    write_jsonl(out / "minimal_negatives.jsonl", minimal)
    write_jsonl(out / "partial_sets.jsonl", partial)
    write_jsonl(out / "redundant_sets.jsonl", redundant)
    write_jsonl(out / "nonminimal_negatives.jsonl", partial + redundant)
    write_jsonl(out / "rejected_negatives.jsonl", r1 + r2 + r3)
    print(json.dumps({"minimal": len(minimal), "partial": len(partial), "redundant": len(redundant), "total": len(minimal)+len(partial)+len(redundant), "rejected": len(r1)+len(r2)+len(r3)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
