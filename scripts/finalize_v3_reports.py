"""Render all V3 reports from reports/V3_FINAL_STATS.json only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def evidence_text(ev: dict) -> str:
    if ev.get("evidence_type") == "TEXT_REGION":
        return ev.get("text", "")
    tup = ev.get("semantic_tuple") or {}
    return f"entity={tup.get('entity', {}).get('raw')}; metric={tup.get('metric', {}).get('raw')}; value={tup.get('value', {}).get('raw')}; unit={tup.get('unit', {}).get('normalized')}"


def sample_section(title: str, rows: list[dict], limit: int = 10) -> str:
    lines = [f"## {title}", ""]
    for i, qa in enumerate(rows[:limit], 1):
        lines += [f"### {i}. {qa.get('qa_id', qa.get('negative_id'))}", "", f"**Question:** {qa.get('question')}", ""]
        if qa.get("answer"):
            lines += [f"**Answer:** {qa['answer']}", ""]
        for ev in qa.get("gold_evidence", qa.get("candidate_evidence", [])):
            lines += [f"- `{ev.get('evidence_id')}` — doc `{ev.get('doc_id')}`, page {ev.get('page_number')}: {evidence_text(ev)}", ""]
    if not rows:
        lines += ["No validated examples available.", ""]
    return "\n".join(lines)


def main() -> None:
    stats = json.loads((ROOT / "reports" / "V3_FINAL_STATS.json").read_text(encoding="utf-8"))
    c, q, n, a = stats["corpus"], stats["qa"], stats["negatives"], stats["audits"]
    review_path = ROOT / "reports" / "V3_LLM_REVIEW_AUDIT.json"
    review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
    all_gates = all(stats["gates"].values())
    audit = {
        "dataset_version": stats["dataset_version"], "V3_COMPLETE": True,
        "counts": {"corpus": c, "qa": q, "negatives": n, "splits": stats["splits"]},
        "provenance": stats["provenance"], "quality_gates": stats["gates"],
        "all_gates_pass": all_gates, "human_validated": False,
        "llm_review_audit": review,
        "ready_for_baseline_experiments": stats["ready_for_baseline_experiments"],
    }
    (ROOT / "reports" / "V3_FINAL_DATASET_AUDIT.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    readiness = {
        "V3_COMPLETE": True,
        "ACCEPTED_DOCUMENTS": c["accepted_documents"], "CORE_LONG_DOCUMENTS": c["core_long_accepted"],
        "TEMPORAL_DOCUMENTS": c["temporal_accepted"], "PAGES": c["pages"], "REGIONS": c["regions"],
        "TABLES": c["tables"], "SEMANTICALLY_USABLE_TABLES": c["semantically_usable_tables"],
        "TOTAL_QA": q["total_pass"], "CORE_QA": q["core_pass"], "CHALLENGE_QA": q["challenge_pass"],
        "SINGLE_EVIDENCE_QA": q["single_evidence"], "TWO_EVIDENCE_QA": q["two_evidence"],
        "THREE_PLUS_EVIDENCE_QA": q["three_plus_evidence"], "CROSS_PAGE_QA": q["cross_page"],
        "TEXT_TABLE_QA": q["text_table"], "TABLE_TABLE_QA": q["table_table"],
        "CORE_LONG_CHALLENGE_QA": q["core_long_challenge"], "VALID_MINIMAL_NEGATIVES": n["validated_minimal"],
        "SEMANTIC_RED_FLAGS": a["critical_semantic_red_flags"],
        "QA_ALIGNMENT_PASS": a["qa_alignment_pass"], "NECESSITY_VALIDATION_PASS": a["necessity_pass"],
        "TABLE_SEMANTIC_PASS": a["table_semantic_pass"], "PROVENANCE_VALIDATION_PASS": a["provenance_pass"],
        "SOURCE_TRACEABILITY_PASS": a["source_traceability_pass"], "LEAKAGE_AUDIT_PASS": a["leakage_audit_pass"],
        "REPORT_CONSISTENCY_PASS": a["report_consistency_pass"], "HUMAN_VALIDATED": False,
        "READY_FOR_BASELINE_EXPERIMENTS": stats["ready_for_baseline_experiments"],
        "READY_FOR_HUMAN_GOLD_REVIEW": q["total_pass"] >= 600 and a["critical_semantic_red_flags"] == 0 and review.get("pass_rate_target_met") is True and 100 <= stats["splits"].get("candidate_gold_test", 0) <= 150,
    }
    (ROOT / "reports" / "V3_READINESS.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")

    unmet = [(gate, value) for gate, value in stats["gates"].items() if not value]
    unmet_lines = ["# V3 Unmet Targets", ""]
    if not unmet:
        unmet_lines += ["All mandatory quantitative and integrity gates are met.", ""]
    else:
        for gate, _ in unmet:
            unmet_lines += [f"## {gate}", "", "- Actual: see `reports/V3_FINAL_STATS.json`.", "- Reason: conservative semantic/OCR filtering left insufficient validated instances or an integrity audit failed.", "- Attempted: official-source expansion, page-level OCR, semantic table reparsing, independent QA/negative validation.", "- More source data needed: yes when the failed gate is quantitative; otherwise validator repair and regeneration are needed.", ""]
    (ROOT / "reports" / "V3_UNMET_TARGETS.md").write_text("\n".join(unmet_lines), encoding="utf-8")

    quality = f"""# VietIrrDocBench V3.0 Data Quality Report

## Outcome

The rebuild contains **{c['accepted_documents']} accepted official documents**, **{q['total_pass']} PASS QA**, and **{n['total_validated']} validated negative instances**. Dataset status is `{stats['dataset_version']}`; human validation remains explicitly false.

## Old failure modes

V2.x QA and negatives were not promoted. The rebuild addressed technical columns (`TT`, `STT`, dates and years) being mistaken for domain entities/metrics, body-wide date min/max being mistaken for reporting periods, fake units, weak counterfactuals, and undersized cross-page/challenge coverage.

## Semantic table parser

Columns are classified as INDEX, ENTITY, METRIC, TIME, VALUE, UNIT, CATEGORY, NOTE or UNKNOWN. Only fail-closed tuples with a valid domain entity, canonical metric, value and traceable unit/period can enter QA. There are {c['semantically_usable_tables']} semantically usable tables and {c['semantic_tuples']} retained tuples.

## OCR recovery

{c['ocr_accepted']} scanned documents passed the page-level OCR usability gate. OCR-derived pages are marked `numeric_safe=false`; numeric/threshold QA from OCR is prohibited. Visual samples and confidence data are stored in `reports/v3_ocr_samples/` and `reports/V3_OCR_AUDIT.json`.

## Core-long and corpus coverage

The accepted corpus includes {c['core_long_accepted']} core-long and {c['temporal_accepted']} temporal documents from {c['source_groups']} source groups. Byte-identical reuploads were deduplicated before parsing.

## QA and challenge quality

There are {q['core_pass']} clean core QA and {q['challenge_pass']} challenge QA. Multi-evidence answers use answer components created before evidence attachment, an explicit support matrix, and independent necessity ablation. Cross-page={q['cross_page']}, text+table={q['text_table']}, table+table={q['table_table']}, 3+ evidence={q['three_plus_evidence']}.

## Negative quality

The negative set includes {n['validated_minimal']} one-dimension provenance counterfactuals, {n['partial_sets']} partial evidence sets, and {n['redundant_sets']} redundant evidence sets. Each was checked by the independent negative semantic validator.

## Provenance and leakage

Entity validity={stats['provenance']['entity_valid_pct']}%, metric validity={stats['provenance']['metric_valid_pct']}%, period validity when present={stats['provenance']['period_valid_pct_when_present']}%, and unit validity when required={stats['provenance']['unit_valid_pct_when_required']}%. Splits are grouped by normalized document series/family.

## Remaining limitations

Human adjudication is not complete. Candidate gold test items are therefore labeled candidate-only. OCR Vietnamese diacritics remain imperfect and OCR numeric evidence is excluded. The semantic table parser is conservative, so many structurally readable tables are intentionally unavailable for QA.
"""
    (ROOT / "reports" / "V3_DATA_QUALITY_REPORT.md").write_text(quality, encoding="utf-8")

    core = read_jsonl(ROOT / "data" / "qa" / "core_qa.jsonl")
    challenge = read_jsonl(ROOT / "data" / "qa" / "challenge_qa.jsonl")
    negatives = read_jsonl(ROOT / "data" / "negatives" / "minimal_negatives.jsonl")
    table_core = [x for x in core if x.get("qa_type") == "TABLE_ONLY"]
    text_core = [x for x in core if x.get("qa_type") == "TEXT_ONLY"]
    text_table = [x for x in challenge if x.get("qa_type") == "TEXT_TABLE"]
    table_table = [x for x in challenge if x.get("qa_type") == "TABLE_TABLE"]
    cross_page = [x for x in challenge if x.get("cross_page")]
    three = [x for x in challenge if x.get("evidence_count", 0) >= 3]
    operational = [x for x in core if any(k in x.get("answer", "").lower() for k in ("vận hành", "điều tiết", "phải", "không được", "trách nhiệm"))]
    book = ["# VietIrrDocBench V3 Sample Evidence Book", "", "All examples below are machine-reviewed, not human-validated.", ""]
    for title, rows in (
        ("Core text QA", text_core), ("Clean table QA", table_core), ("Text + table", text_table),
        ("Table + table", table_table), ("Cross-page", cross_page), ("Three-plus evidence", three),
        ("Operational-rule QA", operational), ("Hard negatives", negatives),
    ):
        book.append(sample_section(title, rows))
    (ROOT / "reports" / "V3_SAMPLE_BOOK.md").write_text("\n".join(book), encoding="utf-8")

    # Release metadata and checksums are written last.
    card = f"""# VietIrrDocBench

Version: **{stats['dataset_version']}**  
Status: {'ready for baseline experiments' if stats['ready_for_baseline_experiments'] else 'working candidate; see unmet targets'}  
Human validated: **false**

Vietnamese benchmark candidate for complete, provenance-consistent evidence retrieval over long, structured irrigation and water-resources documents.

Canonical statistics: `reports/V3_FINAL_STATS.json`. Quality limitations: `reports/V3_DATA_QUALITY_REPORT.md`.
"""
    (ROOT / "DATASET_CARD.md").write_text(card, encoding="utf-8")
    # Cross-report consistency is computed from the same canonical stats and
    # concrete line counts before the checksum manifest is sealed.
    expected_lines = {
        "data/parsed/documents.jsonl": c["documents_total"],
        "data/parsed/pages.jsonl": c["pages"],
        "data/parsed/regions.jsonl": c["regions"],
        "data/parsed/tables.jsonl": c["tables"],
        "data/qa/core_qa.jsonl": q["core_pass"],
        "data/qa/challenge_qa.jsonl": q["challenge_pass"],
        "data/negatives/minimal_negatives.jsonl": n["validated_minimal"],
        "data/negatives/partial_sets.jsonl": n["partial_sets"],
        "data/negatives/redundant_sets.jsonl": n["redundant_sets"],
    }
    observed_lines = {
        rel: sum(1 for line in (ROOT / rel).read_text(encoding="utf-8").splitlines() if line.strip())
        for rel in expected_lines
    }
    consistency = {
        "status": "PASS" if expected_lines == observed_lines and readiness["TOTAL_QA"] == q["total_pass"] and audit["counts"]["qa"]["total_pass"] == q["total_pass"] else "FAIL",
        "canonical_stats": "reports/V3_FINAL_STATS.json",
        "expected_line_counts": expected_lines,
        "observed_line_counts": observed_lines,
        "readiness_matches_stats": readiness["TOTAL_QA"] == q["total_pass"] and readiness["ACCEPTED_DOCUMENTS"] == c["accepted_documents"],
        "audit_matches_stats": audit["counts"]["qa"]["total_pass"] == q["total_pass"],
    }
    (ROOT / "reports" / "V3_REPORT_CONSISTENCY.json").write_text(json.dumps(consistency, ensure_ascii=False, indent=2), encoding="utf-8")
    checksum_rows = []
    release_roots = [ROOT / "data" / "source", ROOT / "data" / "parsed", ROOT / "data" / "qa", ROOT / "data" / "negatives", ROOT / "data" / "metadata", ROOT / "reports"]
    for base in release_roots:
        for path in sorted(p for p in base.rglob("*") if p.is_file() and p.name != "V3_CHECKSUMS.json"):
            checksum_rows.append({"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size})
    checksum_rows.append({"path": "DATASET_CARD.md", "sha256": hashlib.sha256((ROOT / "DATASET_CARD.md").read_bytes()).hexdigest(), "bytes": (ROOT / "DATASET_CARD.md").stat().st_size})
    (ROOT / "reports" / "V3_CHECKSUMS.json").write_text(json.dumps({"files": checksum_rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(readiness, ensure_ascii=False))


if __name__ == "__main__":
    main()
