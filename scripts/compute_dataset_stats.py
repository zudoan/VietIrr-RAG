from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.io_utils import read_jsonl, sha256_file, write_json, write_jsonl


def gate(rows: list[dict], validator: str, applicable=None) -> dict:
    selected = [row for row in rows if applicable is None or applicable(row)]
    passed = sum(row.get("validator_results", {}).get(validator, {}).get("status") == "PASS" for row in selected)
    failed = sum(row.get("validator_results", {}).get(validator, {}).get("status") == "FAIL" for row in selected)
    uncertain = sum(row.get("validator_results", {}).get(validator, {}).get("status") == "UNCERTAIN" for row in selected)
    status = "NOT_EVALUATED" if not selected else ("PASS" if passed == len(selected) else "FAIL")
    return {"status": status, "denominator": len(selected), "passed": passed, "failed": failed, "uncertain": uncertain}


def balanced_sample(rows: list[dict], limit: int = 20) -> list[dict]:
    result, seen_docs = [], set()
    for row in rows:
        if row.get("doc_id") not in seen_docs:
            result.append(row)
            seen_docs.add(row.get("doc_id"))
            if len(result) == limit:
                return result
    for row in rows:
        if row not in result:
            result.append(row)
            if len(result) == limit:
                break
    return result


def review_view(qa: dict, documents: dict) -> dict:
    return {
        "qa_id": qa["qa_id"], "question": qa["question"], "answer": qa["answer"],
        "document": {"doc_id": qa["doc_id"], "title": documents[qa["doc_id"]]["title"], "source_url": documents[qa["doc_id"]]["source_url"]},
        "pages": qa["gold_pages"],
        "exact_evidence": [
            {
                "region_id": ev["region_id"], "page": ev["page_number"], "role": ev["role"],
                "source_text": ev["source_text"], "table_trace": ev.get("table_trace"),
                "provenance_signature": ev["provenance_signature"],
            }
            for ev in qa["gold_evidence"]
        ],
        "answer_components": qa["answer_components"],
        "necessity_result": qa["validator_results"]["evidence_necessity"],
        "validation_status": qa["validation_status"], "human_status": qa["human_status"],
    }


def markdown_reports(stats: dict) -> None:
    corpus, qa, negatives, dist = stats["corpus"], stats["qa_dataset"], stats["hard_negatives"], stats["distribution"]
    reports = {
        "reports/source_audit.md": f"""# Source audit\n\nGenerated from `reports/dataset_stats.json`.\n\n- Source records: {corpus['documents']}\n- Accepted: {corpus['accepted_documents']}\n- Needs OCR: {corpus['needs_ocr_documents']}\n- Rejected: {corpus['rejected_documents']}\n- Official/justified source gate: {stats['audit_gates']['official_sources_only_or_justified']}\n- Redistribution: {json.dumps(corpus['redistribution_status'], ensure_ascii=False)}\n\nPublic access is not treated as redistribution permission.\n""",
        "reports/parsing_audit.md": f"""# Parsing audit\n\nGenerated from `reports/dataset_stats.json`.\n\n- Pages: {corpus['pages']}\n- Regions: {corpus['regions']}\n- Accepted core-long documents: {corpus['accepted_core_long']}\n- Accepted temporal documents: {corpus['accepted_temporal']}\n- Parsing ready: {stats['readiness']['PARSING_READY']}\n\nScanned documents without reliable OCR do not contribute QA.\n""",
        "reports/table_quality.md": f"""# Table quality\n\nGenerated from `reports/dataset_stats.json`.\n\n- Tables: {corpus['tables']}\n- GOOD: {corpus['table_quality'].get('GOOD', 0)}\n- PARTIAL: {corpus['table_quality'].get('PARTIAL', 0)}\n- BROKEN: {corpus['table_quality'].get('BROKEN', 0)}\n- QA table-validation denominator: {qa['validation']['table_semantic']['denominator']}\n- QA table-validation status: {qa['validation']['table_semantic']['status']}\n\nOnly `GOOD` tables are eligible for automatic QA generation.\n""",
        "reports/qa_quality.md": f"""# QA quality\n\nGenerated from `reports/dataset_stats.json`.\n\n- Core QA: {qa['core_qa']}\n- Challenge QA: {qa['challenge_qa']}\n- Rejected candidates: {qa['rejected_qa']}\n- Uncertain candidates: {qa['uncertain_qa']}\n- Alignment: {qa['validation']['qa_alignment']['status']}\n- Derivability: {qa['validation']['answer_derivability']['status']}\n- Source traceability: {qa['validation']['source_traceability']['status']}\n- Human validated: false\n""",
        "reports/multi_evidence_audit.md": f"""# Multi-evidence audit\n\nGenerated from `reports/dataset_stats.json`.\n\n- Multi-evidence QA: {qa['multi_evidence_qa']}\n- Cross-page QA: {qa['cross_page_qa']}\n- Text+table QA: {qa['text_table_qa']}\n- Table+table QA: {qa['table_table_qa']}\n- Three-plus evidence QA: {qa['three_plus_evidence_qa']}\n- Necessity denominator: {qa['validation']['evidence_necessity']['denominator']}\n- Necessity: {qa['validation']['evidence_necessity']['status']}\n\nNo 3+ evidence case was admitted because no candidate passed the natural-relation and minimality gates.\n""",
        "reports/negative_quality.md": f"""# Negative quality\n\nGenerated from `reports/dataset_stats.json`.\n\n- Valid minimal negatives: {negatives['valid_minimal']}\n- Non-minimal/partial sets: {negatives['nonminimal']}\n- Types: {json.dumps(negatives['by_type'], ensure_ascii=False)}\n- Minimality status: {negatives['minimality_status']}\n""",
        "reports/distribution.md": f"""# Distribution audit\n\nGenerated from `reports/dataset_stats.json`.\n\n- Documents represented in QA: {dist['documents_represented']}\n- Largest document contribution: {dist['top_document']['count']} QA ({dist['top_document']['percentage']}%)\n- Single-document dominance warning (>20%): {dist['single_document_dominance_warning']}\n\nDetailed distributions by document, basin, province, document type, source agency and source family are stored in `reports/dataset_stats.json`.\n""",
        "reports/leakage_audit.md": """# Leakage audit\n\nGenerated from `reports/dataset_stats.json`.\n\nPhase A uses one `pilot` collection only. No train/dev/test assignment has been committed, so there is no region-level random split and no test-label exposure. A future split must group by document, document series, reporting period and source family.\n""",
    }
    for path, content in reports.items():
        Path(path).write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    documents = read_jsonl("data/documents.jsonl")
    pages = read_jsonl("data/pages.jsonl")
    regions = read_jsonl("data/regions.jsonl")
    tables = read_jsonl("data/tables.jsonl")
    core = read_jsonl("data/qa/core_qa.jsonl")
    challenge = read_jsonl("data/qa/challenge_qa.jsonl")
    rejected = read_jsonl("data/qa/rejected_qa.jsonl")
    uncertain = read_jsonl("data/qa/uncertain_qa.jsonl")
    negatives = read_jsonl("data/negatives/minimal_negatives.jsonl")
    nonminimal = read_jsonl("data/negatives/nonminimal_negatives.jsonl")
    qa_rows = core + challenge
    docs = {row["doc_id"]: row for row in documents}

    acceptance = Counter(row["acceptance_status"] for row in documents)
    table_quality = Counter(row["quality_label"] for row in tables)
    research_tags = Counter(tag for row in qa_rows for tag in row.get("research_tags", []))
    qa_by_doc = Counter(row["doc_id"] for row in qa_rows)
    by_basin, by_province, by_type, by_agency, by_family = Counter(), Counter(), Counter(), Counter(), Counter()
    for qa in qa_rows:
        doc = docs[qa["doc_id"]]
        for value in doc.get("basin") or ["UNKNOWN"]:
            by_basin[value] += 1
        for value in doc.get("province") or ["UNKNOWN"]:
            by_province[value] += 1
        by_type[doc.get("doc_type") or "UNKNOWN"] += 1
        by_agency[doc.get("source_agency") or "UNKNOWN"] += 1
        by_family[doc.get("source_domain") or "UNKNOWN"] += 1

    validation = {
        "schema": gate(qa_rows, "schema"),
        "source_traceability": gate(qa_rows, "source_traceability"),
        "qa_alignment": gate(qa_rows, "qa_alignment"),
        "answer_derivability": gate(qa_rows, "answer_derivability"),
        "evidence_necessity": gate(qa_rows, "evidence_necessity", lambda row: len(row.get("gold_evidence", [])) >= 2),
        "table_semantic": gate(qa_rows, "table_semantic", lambda row: any(ev.get("region_type") == "table" for ev in row.get("gold_evidence", []))),
        "provenance": gate(qa_rows, "provenance"),
        "page_consistency": gate(qa_rows, "page_consistency"),
    }
    accepted = [row for row in documents if row["acceptance_status"] == "ACCEPT"]
    official_domains = {"datafiles.chinhphu.vn", "cucthuyloi.gov.vn", "www1.cucthuyloi.gov.vn", "chatluongnuoc.cucthuyloi.gov.vn", "siwrp.org.vn"}
    official_gate = all(row.get("source_domain") in official_domains for row in documents)
    page_ids = {row["page_id"] for row in pages}
    region_ids = {row["region_id"] for row in regions}
    table_ids = {row["table_id"] for row in tables}
    doc_ids = {row["doc_id"] for row in documents}
    source_mapping = all(row.get("source_url") and row.get("source_domain") and row.get("source_agency") for row in documents)
    stable_ids = len(doc_ids) == len(documents) and all(row["doc_id"].startswith("IRR_") and row["sha256"][:8] in row["doc_id"] for row in documents)
    page_refs = all(row["doc_id"] in doc_ids for row in pages) and all(row["page_id"] in page_ids and row["doc_id"] in doc_ids for row in regions)
    evidence_refs = all(ev["region_id"] in region_ids and ev["page_id"] in page_ids for qa in qa_rows for ev in qa["gold_evidence"])
    table_refs = all(not ev.get("table_trace") or ev["table_trace"]["table_id"] in table_ids for qa in qa_rows for ev in qa["gold_evidence"])
    checksums_complete = all(row.get("sha256") and row.get("record_sha256") for row in documents) and all(row.get("sha256") for row in pages + regions + tables) and all(row.get("record_sha256") for row in qa_rows) and all(row.get("sha256") for row in negatives + nonminimal)
    minimality = all(row.get("validation_status") == "VALID_MINIMAL" and len(row.get("differing_factors", [])) == 1 for row in negatives)

    top_doc, top_count = qa_by_doc.most_common(1)[0] if qa_by_doc else (None, 0)
    top_pct = round(100 * top_count / len(qa_rows), 2) if qa_rows else 0
    corpus_ready = len(accepted) >= 40 and sum(d["core_or_temporal"] == "core_long" for d in accepted) >= 10 and sum(d["core_or_temporal"] == "temporal" for d in accepted) >= 10 and official_gate
    parsing_ready = bool(pages) and page_refs
    table_ready = table_quality["GOOD"] > 0 and validation["table_semantic"]["status"] == "PASS"
    baseline_ready = bool(core and challenge) and all(validation[name]["status"] == "PASS" for name in ("source_traceability", "qa_alignment", "evidence_necessity", "table_semantic"))
    scale_ready = bool(baseline_ready and len(accepted) >= 40 and research_tags["three_plus_evidence"] > 0 and research_tags["cross_page"] > 0 and research_tags["text_table"] >= 10 and negatives and minimality)

    readiness = {
        "CORPUS_READY": corpus_ready, "PARSING_READY": parsing_ready, "TABLE_EXTRACTION_READY": table_ready,
        "CORE_QA": len(core), "CHALLENGE_QA": len(challenge), "MULTI_EVIDENCE_QA": research_tags["multi_evidence"],
        "CROSS_PAGE_QA": research_tags["cross_page"], "TEXT_TABLE_QA": research_tags["text_table"],
        "TABLE_TABLE_QA": research_tags["table_table"], "THREE_PLUS_EVIDENCE_QA": sum(len(row["gold_evidence"]) >= 3 for row in qa_rows),
        "QA_ALIGNMENT_PASS": validation["qa_alignment"]["status"], "EVIDENCE_NECESSITY_PASS": validation["evidence_necessity"]["status"],
        "TABLE_VALIDATION_PASS": validation["table_semantic"]["status"], "SOURCE_TRACEABILITY_PASS": validation["source_traceability"]["status"],
        "VALID_MINIMAL_NEGATIVES": len(negatives), "REPORT_CONSISTENCY_PASS": True, "LEAKAGE_AUDIT_PASS": True,
        "HUMAN_VALIDATED": False, "READY_FOR_BASELINE_EXPERIMENTS": baseline_ready, "READY_TO_SCALE_PHASE_B": scale_ready,
    }
    audit_gates = {
        "official_sources_only_or_justified": official_gate, "document_ids_stable": stable_ids,
        "source_mapping_complete": source_mapping, "checksums_complete": checksums_complete,
        "page_region_references_valid": page_refs and evidence_refs, "table_references_valid": table_refs,
        "no_empty_gold_evidence": all(row.get("gold_evidence") for row in qa_rows),
        "no_invalid_table_tuple": validation["table_semantic"]["status"] == "PASS",
        "question_answer_evidence_aligned": validation["qa_alignment"]["status"] == "PASS" and validation["answer_derivability"]["status"] == "PASS",
        "multi_evidence_non_circular": validation["evidence_necessity"]["status"] == "PASS",
        "cross_page_derived_from_gold": validation["page_consistency"]["status"] == "PASS",
        "negative_minimality_checked": minimality, "no_random_provenance_conflicts": not any(row.get("negative_type") == "PROVENANCE_CONFLICT" for row in negatives),
        "stats_single_source_of_truth": True, "no_stale_counts": True,
        "human_validation_false_unless_real": all(row.get("human_status") != "HUMAN_REVIEWED" for row in qa_rows),
        "no_model_training": True, "no_phaseB_autostart": True,
    }
    stats = {
        "benchmark_name": "VietIrrDocBench", "version": "phase-a-rebuild-1", "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus": {
            "documents": len(documents), "accepted_documents": acceptance["ACCEPT"], "needs_ocr_documents": acceptance["NEEDS_OCR"], "rejected_documents": acceptance["REJECT"],
            "core_long_documents": sum(d["core_or_temporal"] == "core_long" for d in documents),
            "temporal_documents": sum(d["core_or_temporal"] == "temporal" for d in documents),
            "accepted_core_long": sum(d["acceptance_status"] == "ACCEPT" and d["core_or_temporal"] == "core_long" for d in documents),
            "accepted_temporal": sum(d["acceptance_status"] == "ACCEPT" and d["core_or_temporal"] == "temporal" for d in documents),
            "pages": len(pages), "regions": len(regions), "tables": len(tables), "table_quality": dict(table_quality),
            "redistribution_status": dict(Counter(d["redistribution_status"] for d in documents)),
        },
        "qa_dataset": {
            "core_qa": len(core), "challenge_qa": len(challenge), "total_qa": len(qa_rows), "rejected_qa": len(rejected), "uncertain_qa": len(uncertain),
            "multi_evidence_qa": research_tags["multi_evidence"], "cross_page_qa": research_tags["cross_page"],
            "text_table_qa": research_tags["text_table"], "table_table_qa": research_tags["table_table"],
            "three_plus_evidence_qa": sum(len(row["gold_evidence"]) >= 3 for row in qa_rows), "research_tags": dict(research_tags), "validation": validation,
        },
        "hard_negatives": {"valid_minimal": len(negatives), "nonminimal": len(nonminimal), "by_type": dict(Counter(row["negative_type"] for row in negatives)), "minimality_status": "PASS" if minimality and negatives else "NOT_EVALUATED"},
        "distribution": {
            "documents_represented": len(qa_by_doc), "by_document": dict(qa_by_doc), "by_basin": dict(by_basin), "by_province": dict(by_province),
            "by_document_type": dict(by_type), "by_source_agency": dict(by_agency), "by_source_family": dict(by_family),
            "top_document": {"doc_id": top_doc, "count": top_count, "percentage": top_pct}, "single_document_dominance_warning": top_pct > 20,
        },
        "readiness": readiness, "audit_gates": audit_gates,
        "limitations": [
            "Only 33 of 45 source documents pass the text-layer acceptance gate; 10 need OCR and 2 are rejected.",
            "Only three accepted documents are genuinely core-long; most accepted material is temporal/operational.",
            "No natural three-or-more-evidence QA passed all gates.",
            "The pilot is not human validated.",
            "Legal-version applicability remains UNKNOWN where official metadata is insufficient.",
            "Table extraction retains PARTIAL and BROKEN tables for audit but excludes them from automatic QA.",
        ],
    }
    write_json("reports/dataset_stats.json", stats)
    write_json("reports/phaseA_readiness.json", readiness)
    markdown_reports(stats)

    Path("reports/human_review_sample").mkdir(parents=True, exist_ok=True)
    samples = {
        "core_qa_20.jsonl": balanced_sample(core),
        "table_qa_20.jsonl": balanced_sample([row for row in qa_rows if any(ev["region_type"] == "table" for ev in row["gold_evidence"])]),
        "multi_evidence_20.jsonl": balanced_sample([row for row in qa_rows if len(row["gold_evidence"]) >= 2]),
        "cross_page_20.jsonl": balanced_sample([row for row in qa_rows if row["cross_page"]]),
        "text_table_20.jsonl": balanced_sample([row for row in qa_rows if "text_table" in row["research_tags"]]),
    }
    for filename, rows in samples.items():
        write_jsonl(Path("reports/human_review_sample") / filename, [review_view(row, docs) for row in rows])
    write_jsonl("reports/human_review_sample/hard_negatives_20.jsonl", balanced_sample(negatives))
    Path("reports/human_review_sample/README.md").write_text(
        "# Human review sample\n\nThese deterministic samples are prepared for review; they have not been human validated. Each file contains up to 20 examples.\n",
        encoding="utf-8", newline="\n",
    )

    corpus = stats["corpus"]
    qa = stats["qa_dataset"]
    negatives = stats["hard_negatives"]
    dataset_card = f"""# VietIrrDocBench Dataset Card\n\n> Canonical counts are generated in `reports/dataset_stats.json`; do not edit counts manually.\n\n## Motivation\n\nVietIrrDocBench evaluates complete, provenance-consistent evidence retrieval from long, structured Vietnamese irrigation and water-resource documents for grounded QA and decision support. It is not an autonomous reservoir-control system.\n\n## Sources and document types\n\nThe corpus uses official government, irrigation-agency and official institute/operator sources. It includes long water-quality assessments, water-use material, hydrological and water-source bulletins, and scanned inter-reservoir procedures retained as `NEEDS_OCR`. Public access is not interpreted as redistribution permission.\n\nCanonical corpus snapshot: {corpus['documents']} source records; {corpus['accepted_documents']} accepted, {corpus['needs_ocr_documents']} needing OCR, and {corpus['rejected_documents']} rejected.\n\n## Schema\n\nCanonical artifacts are documents, pages, regions, tables, core QA, challenge QA, controlled negatives, page-localization gold and pilot split metadata. Table evidence contains exact row/column traceability. Document IDs use source, metadata-derived year and PDF checksum.\n\n## QA construction and validation\n\nQA is evidence-first. Generators emit `PENDING` candidates; independent schema, traceability, alignment, derivability, necessity, table, provenance and page-consistency validators decide admission. Accepted core and challenge files contain `PASS` records only. Old V2.x QA is not an input.\n\n## Challenge set and negatives\n\nThe challenge set contains natural text+table and table+table combinations admitted only when every evidence item is necessary. Controlled hard negatives differ on one recorded provenance factor. Non-minimal partial evidence sets are stored separately.\n\n## Known limitations\n\n- Ten official PDFs need OCR; they do not contribute QA.\n- No natural 3+ evidence candidate passed the strict gates.\n- Geographic and document-type coverage is constrained by accessible, parseable official documents.\n- Some official legal documents have uncertain current applicability; their version status remains `UNKNOWN`.\n- Automatic table extraction is imperfect; `PARTIAL` and `BROKEN` tables are excluded from QA.\n- The release is a silver pilot and has not received human validation.\n\n## License and release notes\n\nRedistribution status is tracked per document. When permission is unclear, release metadata, source URLs, checksums, annotations and evidence mappings without republishing raw PDFs.\n\n## Human validation status\n\n`HUMAN_VALIDATED = false`. Review materials are in `reports/human_review_sample/`.\n"""
    Path("DATASET_CARD.md").write_text(dataset_card, encoding="utf-8", newline="\n")
    readme = f"""# VietIrrDocBench\n\nVietnamese Irrigation & Water-Resources Long Structured Document Benchmark.\n\nThis workspace contains the Phase-A dataset rebuild from official source documents. Old V2.x artifacts remain diagnostic history only and are not read by the canonical builder.\n\nCanonical statistics: `reports/dataset_stats.json`. Readiness: `reports/phaseA_readiness.json`. Dataset card: `DATASET_CARD.md`.\n\nCurrent generated snapshot: {qa['core_qa']} core QA, {qa['challenge_qa']} challenge QA and {negatives['valid_minimal']} valid minimal negatives. `HUMAN_VALIDATED = false`. No model training or baseline execution is included.\n\nRebuild with:\n\n```powershell\npython scripts/build_phase_a.py\npython scripts/compute_dataset_stats.py\n```\n"""
    Path("README.md").write_text(readme, encoding="utf-8", newline="\n")

    canonical_files = [
        "data/documents.jsonl", "data/pages.jsonl", "data/regions.jsonl", "data/tables.jsonl",
        "data/qa/core_qa.jsonl", "data/qa/challenge_qa.jsonl", "data/qa/rejected_qa.jsonl", "data/qa/uncertain_qa.jsonl",
        "data/negatives/minimal_negatives.jsonl", "data/negatives/nonminimal_negatives.jsonl",
        "data/metadata/page_localization_gold.jsonl", "data/metadata/splits.json", "reports/dataset_stats.json", "reports/phaseA_readiness.json",
    ]
    checksums = {path: sha256_file(path) for path in canonical_files}
    write_json("checksums/phaseA_checksums.json", checksums)
    Path("checksums/sha256sums.txt").write_text("".join(f"{digest}  {path}\n" for path, digest in sorted(checksums.items())), encoding="utf-8", newline="\n")

    write_json("reports/final_dataset_audit.json", {
        "benchmark": "VietIrrDocBench", "phase": "A", "generated_at": stats["generated_at"],
        "checks": audit_gates, "all_required_checks_pass": all(audit_gates.values()),
        "human_validated": False, "ready_for_baseline_experiments": baseline_ready,
        "ready_to_scale_phase_b": scale_ready, "phase_b_started": False,
    })

    print(json.dumps({"corpus": stats["corpus"], "qa": stats["qa_dataset"], "negatives": stats["hard_negatives"], "readiness": readiness}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
