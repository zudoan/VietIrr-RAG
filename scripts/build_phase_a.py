from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.io_utils import write_json, write_jsonl
from src.negatives.build_negatives import build_minimal_negatives, build_nonminimal_negatives
from src.parsing.canonical_parser import build_corpus, corpus_summary
from src.qa_generation.evidence_first_generator import generate_candidates
from src.validation.run_validators import build_context, validate_qa


def main() -> None:
    documents, pages, regions, tables, migrations = build_corpus()
    write_jsonl("data/documents.jsonl", documents)
    write_jsonl("data/pages.jsonl", pages)
    write_jsonl("data/regions.jsonl", regions)
    write_jsonl("data/tables.jsonl", tables)
    write_json("data/metadata/doc_id_migration.json", {"migrations": migrations})

    core_candidates, challenge_candidates = generate_candidates(documents, tables, regions)
    context = build_context(documents, regions, tables)
    core, core_rejected, core_uncertain = validate_qa(core_candidates, context, challenge=False)
    challenge, challenge_rejected, challenge_uncertain = validate_qa(challenge_candidates, context, challenge=True)
    write_jsonl("data/qa/core_qa.jsonl", core)
    write_jsonl("data/qa/challenge_qa.jsonl", challenge)
    write_jsonl("data/qa/rejected_qa.jsonl", core_rejected + challenge_rejected)
    write_jsonl("data/qa/uncertain_qa.jsonl", core_uncertain + challenge_uncertain)

    localization = []
    for qa in core + challenge:
        localization.append({
            "qa_id": qa["qa_id"], "doc_id": qa["doc_id"], "gold_pages": qa["gold_pages"],
            "gold_page_count": qa["gold_page_count"], "page_span": qa["page_span"],
            "same_page": qa["same_page"], "cross_page": qa["cross_page"],
        })
    write_jsonl("data/metadata/page_localization_gold.jsonl", localization)
    write_json("data/metadata/splits.json", {"strategy": "pilot_only_no_final_split", "pilot_doc_ids": sorted({qa["doc_id"] for qa in core + challenge})})

    minimal, rejected_negatives = build_minimal_negatives(core)
    nonminimal = build_nonminimal_negatives(challenge)
    write_jsonl("data/negatives/minimal_negatives.jsonl", minimal)
    write_jsonl("data/negatives/nonminimal_negatives.jsonl", nonminimal)
    write_jsonl("data/negatives/rejected_negatives.jsonl", rejected_negatives)
    print(corpus_summary(documents, pages, regions, tables))
    print({"core_candidates": len(core_candidates), "core_pass": len(core), "challenge_candidates": len(challenge_candidates), "challenge_pass": len(challenge), "minimal_negatives": len(minimal)})


if __name__ == "__main__":
    main()
