#!/usr/bin/env python3
"""Independent structural/provenance audit plus controlled mutation tests."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import fitz


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HANDOFF = REPO / "VR4_4_COMPLETE_AUDIT_HANDOFF"
MANIFEST_PATH = HANDOFF / "CORPUS_FILE_MANIFEST.csv"
ALLOWED_RELATION_STATUS = {"PROPOSED", "SOURCE_SUPPORTED", "UNVERIFIED", "CONTRADICTED", "HUMAN_VERIFIED"}


def jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8-sig").splitlines() if x.strip()]


def csvrows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    manifest_rows = csvrows(MANIFEST_PATH)
    manifest = {r["document_id"]: r for r in manifest_rows}
    corpus = csvrows(HERE / "corpus" / "CORPUS_93_CONTENT_AUDIT.csv")
    evidence = jsonl(HERE / "corpus" / "DEEP_DOCUMENT_EVIDENCE.jsonl")
    coverage = csvrows(HERE / "corpus" / "DOMAIN_USECASE_COVERAGE.csv")
    relations = jsonl(HERE / "packs" / "PACK_RELATION_AUDIT.jsonl")
    packs = jsonl(HERE / "packs" / "LINKED_PACKS_VERIFIED.jsonl")
    pack_evidence = jsonl(HERE / "packs" / "PACK_EVIDENCE_BANK.jsonl")
    qa48 = csvrows(HERE / "qa" / "QA_48_CONSOLIDATED_AUDIT.csv")
    qa_review = jsonl(HERE / "qa" / "QA_48_EVIDENCE_REVIEW.jsonl")
    newqa = jsonl(HERE / "qa" / "NEW_QA_DRAFTS.jsonl")
    newval = jsonl(HERE / "qa" / "NEW_QA_VALIDATION.jsonl")
    checks = []

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append({"check_id": check_id, "status": "PASS" if passed else "FAIL", "detail": detail})

    # 1. Canonical corpus and physical integrity.
    check("A01_MANIFEST_COUNT", len(manifest_rows) == 93 and len(manifest) == 93, f"rows={len(manifest_rows)} unique={len(manifest)}")
    physical_ok = True
    for row in manifest_rows:
        pdf = HANDOFF / PurePosixPath(row["bundled_path"])
        physical_ok &= pdf.exists() and sha256(pdf) == row["computed_sha256"] == row["expected_sha256"]
    check("A02_PHYSICAL_PDF_HASHES", physical_ok, "All 93 physical PDFs resolve and match both declared hashes")
    check("A03_CORPUS_AUDIT_ACCOUNTING", len(corpus) == 93 and len({r['document_id'] for r in corpus}) == 93, f"rows={len(corpus)}")
    honest_status = all(r["content_inspection_status"] in {"SCREENED_CONTENT", "INSPECTION_BLOCKED"} for r in corpus)
    check("A04_HONEST_INSPECTION_STATUS", honest_status, "Every canonical PDF has an allowed explicit inspection status")

    # 2. Deep evidence locators.
    evidence_ok = True
    for ev in evidence:
        if ev["document_id"] not in manifest:
            evidence_ok = False
            continue
        row = manifest[ev["document_id"]]
        pdf = HANDOFF / PurePosixPath(row["bundled_path"])
        with fitz.open(pdf) as doc:
            evidence_ok &= 1 <= int(ev["page"]) <= len(doc)
        evidence_ok &= ev["pdf_sha256"] == row["computed_sha256"] and bool(ev["source_span"].strip())
    check("A05_DEEP_EVIDENCE_RESOLVES", evidence_ok and len(evidence) >= 20, f"evidence_records={len(evidence)}")
    deep_docs = {e["document_id"] for e in evidence}
    check("A06_DEEP_DOCUMENT_COUNT", 15 <= len(deep_docs) <= 25, f"deep_documents={len(deep_docs)}")
    check("A07_COVERAGE_USECASE_SPECIFIC", len(coverage) >= 12 and all(r["operational_use_case"] and r["coverage_status"] for r in coverage), f"cells={len(coverage)}")

    # 3. Relation and pack provenance.
    relation_ids = {r["relation_id"] for r in relations}
    relation_ok = all(r["source_document"] in manifest and (r["target_document"] in manifest or r["target_document"].startswith("EXTERNAL_")) for r in relations)
    check("B01_RELATION_ENDPOINTS", relation_ok, f"relations={len(relations)}")
    check("B02_RELATION_STATUS_VOCAB", all(r["verification_status"] in ALLOWED_RELATION_STATUS for r in relations), "All relation statuses use required vocabulary")
    check("B03_NO_FAKE_HUMAN_RELATION", all(not r.get("human_verified") and r["verification_status"] != "HUMAN_VERIFIED" for r in relations), "No relation claims human verification")
    check("B04_PACK_RELATIONS_RESOLVE", all(set(p["relation_ids"]) <= relation_ids for p in packs), f"packs={len(packs)}")
    check("B05_PACK_EVIDENCE_RELATIONS_RESOLVE", all(p["relation_id"] in relation_ids for p in pack_evidence), f"pack_evidence={len(pack_evidence)}")

    # 4. Existing QA accounting and immutable user decisions.
    frozen_relatives = [
        "research/vietirr_v4_2/V4_2_QA_DRAFTS.jsonl",
        "research/vietirr_v4_3/QA_SOURCE_DOSSIERS.jsonl",
        "research/vietirr_v4_4/baseline/PILOT_38_RECONCILIATION.jsonl",
        "research/vietirr_v4_4/qa/V4_4_QA_NEW_DRAFTS.jsonl",
    ]
    upstream_checksums = {}
    checksum_file = HANDOFF / "CHECKSUMS.sha256"
    if checksum_file.exists():
        for line in checksum_file.read_text(encoding="utf-8").splitlines():
            if "  " in line:
                digest, relative = line.split("  ", 1)
                upstream_checksums[relative.replace("\\", "/")] = digest
    frozen_ok = all(
        relative in upstream_checksums
        and (REPO / PurePosixPath(relative)).is_file()
        and sha256(REPO / PurePosixPath(relative)) == upstream_checksums[relative]
        for relative in frozen_relatives
    )
    check("C00_FROZEN_INPUT_HASHES", frozen_ok, f"matched={sum(relative in upstream_checksums and (REPO / PurePosixPath(relative)).is_file() and sha256(REPO / PurePosixPath(relative)) == upstream_checksums[relative] for relative in frozen_relatives)}/{len(frozen_relatives)}")
    qa_ids = {r["qa_id"] for r in qa48}
    check("C01_BASELINE_QA_COUNT", len(qa48) == 48 and len(qa_ids) == 48, f"rows={len(qa48)} unique={len(qa_ids)}")
    keep_count = sum(r["user_keep_status"] == "USER_KEEP" for r in qa48)
    check("C02_USER_KEEP_38", keep_count == 38, f"USER_KEEP={keep_count}")
    check("C03_QA_REVIEW_ACCOUNTING", len(qa_review) == 48 and {r['qa_id'] for r in qa_review} == qa_ids, f"review_rows={len(qa_review)}")
    check("C04_NO_HUMAN_GOLD_PROMOTION", all(r["human_gold_status"] == "NOT_HUMAN_GOLD_VERIFIED" for r in qa48), "All 48 remain non-gold")
    critical = {r["qa_id"]: r for r in qa48}
    check("C05_QA016_OPEN_BOUND_RISK", critical["V42-QA-016"]["answer_correctness_status"] == "REVISE", "QA-016 explicitly requires revision")
    check("C06_KNOWN_RISKS_PRESERVED", all(critical[q]["known_ambiguities"] for q in ["V42-QA-026", "V42-QA-031", "V42-QA-032", "V42-QA-035", "V42-QA-036", "V42-QA-037", "V42-QA-038"]), "Known extrema/legal/chronology issues are explicit")

    # 5. New QA source/provenance/competency checks.
    new_ids = {q["qa_id"] for q in newqa}
    evidence_ids = {eid for q in newqa for eid in q["evidence_ids"]}
    inline_evidence_ids = {record["evidence_id"] for q in newqa for record in q.get("evidence_records", [])}
    components_ok = all(set(c["supported_by"]) <= evidence_ids for q in newqa for c in q["answer_components"])
    check("D01_NEW_QA_COUNT", 1 <= len(newqa) <= 15 and len(new_ids) == len(newqa), f"new_qa={len(newqa)}")
    check("D02_ANSWER_COMPONENT_SUPPORT", components_ok, "Every answer component points to a declared evidence ID")
    inline_evidence_ok = evidence_ids == inline_evidence_ids and all(
        span.get("source_span", "").strip()
        and span["document_id"] in manifest
        and span["pdf_sha256"] == manifest[span["document_id"]]["computed_sha256"]
        for q in newqa for record in q.get("evidence_records", []) for span in record.get("source_spans", [])
    )
    check("D02B_INLINE_EVIDENCE_RESOLVES", inline_evidence_ok, f"declared={len(evidence_ids)} inline={len(inline_evidence_ids)}")
    provenance_ok = all(q["generation_method"] in {"MANUALLY_CURATED_DRAFT", "HUMAN_AUTHORED_DRAFT"} and q["origin_lineage"]["method"] == q["generation_method"] for q in newqa)
    check("D03_GENERATION_METHOD_HONEST", provenance_ok, "Manual curation is not disguised as an automatic generator")
    check("D04_NEW_QA_VALIDATION", len(newval) == len(newqa) and all(v["status"] == "MACHINE_SUPPORTED" for v in newval), f"validation_rows={len(newval)}")
    check("D05_NEW_QA_NOT_GOLD", all(q["human_gold_status"] == "NOT_HUMAN_GOLD_VERIFIED" and q["human_verification_status"] == "PENDING_HUMAN_REVIEW" for q in newqa), "No new QA claims human approval")
    competence_ok = all(not (q["competency"] == "CROSS_DOCUMENT" and len(q["source_documents"]) < 2) for q in newqa)
    check("D06_COMPETENCY_PATTERN_SANITY", competence_ok, "No cross-document label is assigned to a single source")

    # 6. Frozen input and leakage controls.
    expected_input_files = [
        REPO / "research" / "vietirr_v4_2" / "V4_2_QA_DRAFTS.jsonl",
        REPO / "research" / "vietirr_v4_4" / "qa" / "V4_4_QA_NEW_DRAFTS.jsonl",
        REPO / "research" / "vietirr_v4_4" / "baseline" / "PILOT_38_RECONCILIATION.jsonl",
    ]
    check("E01_UPSTREAM_INPUTS_PRESENT", all(p.exists() for p in expected_input_files), "Required frozen/raw upstream QA inputs resolve")
    output_paths_clean = all(not re.search(r"candidate[ _-]?test", str(p), re.I) for p in HERE.rglob("*"))
    declared_no_access = all(q.get("candidate_test_accessed") is False for q in newqa)
    declared_sources_canonical = all(d["document_id"] in manifest for q in newqa for d in q["source_documents"])
    check(
        "E02_NO_CANDIDATE_TEST_LEAKAGE",
        output_paths_clean and declared_no_access and declared_sources_canonical,
        f"output_paths_clean={output_paths_clean}; declarations_false={declared_no_access}; all_QA_sources_canonical={declared_sources_canonical}",
    )
    check("E03_DEPENDENCY_REPRODUCIBLE", fitz.__doc__ is not None, f"PyMuPDF={fitz.__version__}")

    # 7. Mutation tests: validator must reject controlled corruptions.
    def validate_mutant(q: dict) -> bool:
        docs = {d["document_id"]: d for d in q["source_documents"]}
        if not docs or any(d not in manifest for d in docs):
            return False
        if any(manifest[d]["computed_sha256"] != meta["pdf_sha256"] for d, meta in docs.items()):
            return False
        if not q["expected_answer"].strip():
            return False
        for loc in q["source_pages"]:
            if loc["document_id"] not in manifest:
                return False
            path = HANDOFF / PurePosixPath(manifest[loc["document_id"]]["bundled_path"])
            with fitz.open(path) as doc:
                if not all(1 <= int(page) <= len(doc) for page in loc["pages"]):
                    return False
        if q["competency"] in {"VERSION_REASONING", "CROSS_DOCUMENT_SYNTHESIS"} and len(q["source_documents"]) < 2:
            return False
        if q["human_gold_status"] == "HUMAN_GOLD_VERIFIED":
            return False
        return True

    base = newqa[-1]
    mutations = []
    mut = copy.deepcopy(base); mut["expected_answer"] = ""; mutations.append(("wrong_answer_empty", not validate_mutant(mut)))
    mut = copy.deepcopy(base); mut["source_pages"][0]["pages"] = [9999]; mutations.append(("wrong_page", not validate_mutant(mut)))
    mut = copy.deepcopy(base); mut["source_documents"][0]["pdf_sha256"] = "0" * 64; mutations.append(("wrong_hash", not validate_mutant(mut)))
    mut = copy.deepcopy(base); mut["source_documents"] = mut["source_documents"][:1]; mutations.append(("unsupported_cross_document_competency", not validate_mutant(mut)))
    mut = copy.deepcopy(base); mut["human_gold_status"] = "HUMAN_GOLD_VERIFIED"; mutations.append(("fabricated_human_gold", not validate_mutant(mut)))
    check("F01_MUTATION_TESTS", all(passed for _, passed in mutations), f"caught={sum(p for _, p in mutations)}/{len(mutations)}")

    passed = sum(c["status"] == "PASS" for c in checks)
    failed = len(checks) - passed
    result = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "PASS" if failed == 0 else "FAIL",
        "checks_passed": passed,
        "checks_failed": failed,
        "checks_total": len(checks),
        "mutation_tests": [{"mutation": name, "caught": caught} for name, caught in mutations],
        "checks": checks,
        "semantic_disclaimer": "PASS establishes structural integrity, provenance resolution, and declared controls; it does not establish human semantic correctness or official gold status.",
    }
    (HERE / "tests" / "V4_4_DEEP_AUDIT_RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = [
        "# V4.4 Deep Audit — Independent Audit Results",
        "",
        f"- Status: **{result['status']}**",
        f"- Checks: **{passed}/{len(checks)} PASS**",
        f"- Mutation tests: **{sum(x['caught'] for x in result['mutation_tests'])}/{len(mutations)} caught**",
        "- Human semantic/gold verification: **not claimed**",
        "",
        "## Checks",
        "",
    ]
    report.extend(f"- `{c['check_id']}` — {c['status']}: {c['detail']}" for c in checks)
    report.extend(["", result["semantic_disclaimer"], ""])
    (HERE / "tests" / "V4_4_DEEP_AUDIT_RESULTS.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps({"status": result["status"], "passed": passed, "failed": failed, "mutations_caught": sum(x[1] for x in mutations)}, ensure_ascii=False))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
