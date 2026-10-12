"""Generate and independently validate V3 core/challenge QA."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.qa_generation.v3_generator import generate
from src.validation.v3_semantic_validator import validate_dataset


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    core_candidates, challenge_candidates, generator_rejected, generator_uncertain = generate(ROOT)
    core, core_rejected, core_uncertain = validate_dataset(core_candidates)
    challenge, challenge_rejected, challenge_uncertain = validate_dataset(challenge_candidates)
    qa_dir = ROOT / "data" / "qa"
    write_jsonl(qa_dir / "core_qa.jsonl", core)
    write_jsonl(qa_dir / "challenge_qa.jsonl", challenge)
    write_jsonl(qa_dir / "rejected_qa.jsonl", generator_rejected + core_rejected + challenge_rejected)
    write_jsonl(qa_dir / "uncertain_qa.jsonl", generator_uncertain + core_uncertain + challenge_uncertain)
    write_jsonl(qa_dir / "rejected.jsonl", generator_rejected + core_rejected + challenge_rejected)
    write_jsonl(qa_dir / "uncertain.jsonl", generator_uncertain + core_uncertain + challenge_uncertain)
    all_qa = core + challenge
    localization = [{
        "qa_id": q["qa_id"], "doc_id": q["doc_id"], "gold_pages": q["gold_pages"],
        "gold_page_count": q["gold_page_count"], "page_span": q["page_span"],
        "same_page": q["same_page"], "cross_page": q["cross_page"],
    } for q in all_qa]
    provenance = [{"qa_id": q["qa_id"], "signatures": q["provenance_signatures"]} for q in all_qa]
    write_jsonl(ROOT / "data" / "metadata" / "page_localization_gold.jsonl", localization)
    write_jsonl(ROOT / "data" / "metadata" / "provenance_signatures.jsonl", provenance)
    print(json.dumps({
        "core_candidates": len(core_candidates), "core_pass": len(core), "core_reject": len(core_rejected),
        "challenge_candidates": len(challenge_candidates), "challenge_pass": len(challenge), "challenge_reject": len(challenge_rejected),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
