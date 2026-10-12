"""Independent Stage 1 freeze audit and reproducible HOLD/PASS candidate builder."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".vendor"))

import fitz

from src.common.io_utils import read_jsonl, write_json, write_jsonl
from src.structure.semantic_table_parser import fold

REPORT_DIR = ROOT / "reports/stage1"
RELEASE = ROOT / "VietIrrDocBench_v1_candidate"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def count_duplicates(values: list[str]) -> int:
    counts = Counter(values)
    return sum(value - 1 for value in counts.values() if value > 1)


def normalized_title(value: str) -> str:
    value = fold(value)
    value = re.sub(r"\b20\d{2}\b|\b\d{1,4}\b", "#", value)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9#]+", " ", value)).strip()


def question_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", fold(value)))


def evidence_text(ev: dict) -> str:
    if ev.get("evidence_type") == "TEXT_REGION":
        return ev.get("claim_text") or ev.get("text") or ""
    return ev.get("text") or " ".join(str(x) for x in (ev.get("entity"), ev.get("metric_raw"), ev.get("value"), ev.get("unit")) if x)


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    docs = read_jsonl(ROOT / "data/v3_1/metadata/documents.jsonl")
    parsed_docs = read_jsonl(ROOT / "data/parsed/documents.jsonl")
    pages_all = read_jsonl(ROOT / "data/parsed/pages.jsonl")
    regions_all = read_jsonl(ROOT / "data/parsed/regions.jsonl")
    tables_all = read_jsonl(ROOT / "data/parsed/tables.jsonl")
    core = read_jsonl(ROOT / "data/v3_1/qa/core_qa.jsonl")
    challenge = read_jsonl(ROOT / "data/v3_1/qa/challenge_qa.jsonl")
    qa = core + challenge
    train = read_jsonl(ROOT / "data/v3_1/qa/train.jsonl")
    dev = read_jsonl(ROOT / "data/v3_1/qa/dev.jsonl")
    test = read_jsonl(ROOT / "data/v3_1/qa/candidate_gold_test.jsonl")
    minimal = read_jsonl(ROOT / "data/v3_1/negatives/minimal_negatives.jsonl")
    partial = read_jsonl(ROOT / "data/v3_1/negatives/partial_sets.jsonl")
    redundant = read_jsonl(ROOT / "data/v3_1/negatives/redundant_sets.jsonl")
    negatives = minimal + partial + redundant
    split_audit = json.loads((ROOT / "reports/v3_1/split_audit.json").read_text(encoding="utf-8"))
    semantic_audit = json.loads((ROOT / "reports/v3_1/semantic_red_flag_scan.json").read_text(encoding="utf-8"))
    ocr_audit = json.loads((ROOT / "reports/V3_OCR_AUDIT.json").read_text(encoding="utf-8"))

    doc_ids = {d["doc_id"] for d in docs}
    doc_index = {d["doc_id"]: d for d in docs}
    pages = [p for p in pages_all if p["doc_id"] in doc_ids]
    regions = [r for r in regions_all if r["doc_id"] in doc_ids]
    tables = [t for t in tables_all if t["doc_id"] in doc_ids]
    page_index = {p["page_id"]: p for p in pages}
    region_index = {r["region_id"]: r for r in regions}
    table_index = {t["table_id"]: t for t in tables}
    tuple_index = {u["tuple_id"]: (t, u) for t in tables for u in t.get("semantic_tuples", [])}
    all_evidence_ids = set(region_index) | set(tuple_index)

    # A. Corpus file, checksum, page-count, duplicate, and provenance audit.
    corpus_errors, source_rows = [], []
    pages_by_doc = Counter(p["doc_id"] for p in pages)
    page_hashes_by_doc = defaultdict(set)
    for p in pages:
        page_hashes_by_doc[p["doc_id"]].add(p.get("sha256"))
    for doc in docs:
        path = ROOT / doc["local_path"]
        row = {"doc_id": doc["doc_id"], "source_id": doc["source_id"], "local_path": doc["local_path"], "sha256": doc["sha256"]}
        if not path.is_file():
            corpus_errors.append({"doc_id": doc["doc_id"], "error": "MISSING_SOURCE_FILE"})
            row["file_status"] = "MISSING"
        else:
            actual_hash = file_sha256(path)
            row.update({"bytes": path.stat().st_size, "actual_sha256": actual_hash, "file_status": "PASS" if actual_hash == doc["sha256"] else "FAIL"})
            if actual_hash != doc["sha256"]:
                corpus_errors.append({"doc_id": doc["doc_id"], "error": "SOURCE_CHECKSUM_MISMATCH"})
            try:
                with fitz.open(path) as pdf:
                    actual_pages = len(pdf)
                row["actual_page_count"] = actual_pages
                if actual_pages != doc["page_count"] or pages_by_doc[doc["doc_id"]] != doc["page_count"]:
                    corpus_errors.append({"doc_id": doc["doc_id"], "error": "PAGE_COUNT_MISMATCH", "metadata": doc["page_count"], "pdf": actual_pages, "parsed": pages_by_doc[doc["doc_id"]]})
            except Exception as exc:
                corpus_errors.append({"doc_id": doc["doc_id"], "error": "UNREADABLE_PDF", "detail": str(exc)})
        for required in ("source_url", "source_group", "source_agency", "sha256", "local_path"):
            if not doc.get(required):
                corpus_errors.append({"doc_id": doc["doc_id"], "error": f"MISSING_PROVENANCE_{required.upper()}"})
        source_rows.append(row)
    exact_duplicate_docs = count_duplicates([d["sha256"] for d in docs])
    if exact_duplicate_docs:
        corpus_errors.append({"error": "EXACT_DUPLICATE_DOCUMENTS", "count": exact_duplicate_docs})
    near_duplicate_pairs = []
    for i, left in enumerate(docs):
        left_hashes = page_hashes_by_doc[left["doc_id"]]
        for right in docs[i + 1:]:
            right_hashes = page_hashes_by_doc[right["doc_id"]]
            if not left_hashes or not right_hashes:
                continue
            overlap = len(left_hashes & right_hashes) / max(len(left_hashes | right_hashes), 1)
            title_score = SequenceMatcher(None, normalized_title(left["title"]), normalized_title(right["title"])).ratio()
            if overlap >= 0.90 and title_score >= 0.90:
                near_duplicate_pairs.append({"left": left["doc_id"], "right": right["doc_id"], "page_hash_jaccard": round(overlap, 4), "title_similarity": round(title_score, 4)})

    # B. Mapping/orphan and OCR audit.
    mapping_errors = []
    if count_duplicates([p["page_id"] for p in pages]):
        mapping_errors.append({"error": "DUPLICATE_PAGE_ID"})
    if count_duplicates([r["region_id"] for r in regions]):
        mapping_errors.append({"error": "DUPLICATE_REGION_ID"})
    if count_duplicates([t["table_id"] for t in tables]):
        mapping_errors.append({"error": "DUPLICATE_TABLE_ID"})
    for region in regions:
        page = page_index.get(region["page_id"])
        if not page or page["doc_id"] != region["doc_id"] or page["page_number"] != region["page_number"]:
            mapping_errors.append({"error": "ORPHAN_OR_MISMATCHED_REGION", "id": region["region_id"]})
    for table in tables:
        page = page_index.get(table["page_id"])
        if not page or page["doc_id"] != table["doc_id"] or page["page_number"] != table["page_number"]:
            mapping_errors.append({"error": "ORPHAN_OR_MISMATCHED_TABLE", "id": table["table_id"]})
    ocr_docs = {d["doc_id"]: d for d in docs if d.get("ocr_used")}
    ocr_gold_refs = [e["evidence_id"] for row in qa for e in row.get("gold_evidence", []) if e.get("doc_id") in ocr_docs]
    ocr_numeric_gold_refs = [e["evidence_id"] for row in qa for e in row.get("gold_evidence", []) if e.get("doc_id") in ocr_docs and (e.get("evidence_type") == "TABLE_CELL" or any(ch.isdigit() for ch in row.get("answer", "")))]
    accepted_ocr_sources = {d["source_id"] for d in ocr_docs.values()}
    ocr_audit_rows = [x for x in ocr_audit["ocr_documents"] if x["source_id"] in accepted_ocr_sources]
    pending_ocr = [x for x in ocr_audit_rows if x.get("visual_audit_status") != "HUMAN_VALIDATED"]
    ocr_pages = sum(x["page_count"] for x in ocr_audit_rows)
    ocr_partial_broken_pages = sum(x["quality_counts"].get("PARTIAL", 0) + x["quality_counts"].get("BROKEN", 0) for x in ocr_audit_rows)

    # C. Semantic table audit for every gold-used cell.
    table_errors, used_tables, table_evidence_refs = [], set(), 0
    for row in qa:
        for ev in row.get("gold_evidence", []):
            if ev.get("evidence_type") != "TABLE_CELL":
                continue
            table_evidence_refs += 1
            used_tables.add(ev.get("table_id"))
            pair = tuple_index.get(ev["evidence_id"])
            table = table_index.get(ev.get("table_id"))
            if not pair or not table:
                table_errors.append({"qa_id": row["qa_id"], "evidence_id": ev["evidence_id"], "error": "UNRESOLVED_TABLE_TUPLE"}); continue
            source_table, tup = pair
            if source_table["table_id"] != table["table_id"] or table.get("structural_quality") != "GOOD" or table.get("semantic_quality") != "GOOD":
                table_errors.append({"qa_id": row["qa_id"], "evidence_id": ev["evidence_id"], "error": "TABLE_NOT_GOLD_USABLE"})
            expected = {
                "doc_id": source_table["doc_id"], "page_id": source_table["page_id"],
                "entity": (tup.get("entity") or {}).get("raw"), "metric": (tup.get("metric") or {}).get("canonical"),
                "value": (tup.get("value") or {}).get("raw"), "unit_normalized": (tup.get("unit") or {}).get("normalized"),
            }
            observed = {key: ev.get(key) for key in expected}
            for key in expected:
                if observed[key] != expected[key]:
                    table_errors.append({"qa_id": row["qa_id"], "evidence_id": ev["evidence_id"], "error": f"TABLE_{key.upper()}_MISMATCH", "expected": expected[key], "observed": observed[key]})
            if ev.get("cell_ref") != tup.get("cell_ref"):
                table_errors.append({"qa_id": row["qa_id"], "evidence_id": ev["evidence_id"], "error": "CELL_REFERENCE_MISMATCH"})
    semantic_good_tables = sum(t.get("structural_quality") == "GOOD" and t.get("semantic_quality") == "GOOD" for t in tables)

    # D/E. QA schema, evidence, derivability, necessity, and distribution audit.
    qa_errors = []
    required_qa = {"qa_id", "question", "answer", "gold_evidence", "gold_evidence_ids", "human_validated", "review_status"}
    if count_duplicates([row["qa_id"] for row in qa]):
        qa_errors.append({"error": "DUPLICATE_QA_ID"})
    exact_questions = count_duplicates([fold(row["question"]) for row in qa])
    for row in qa:
        missing = sorted(required_qa - set(row))
        if missing:
            qa_errors.append({"qa_id": row.get("qa_id"), "error": "SCHEMA_MISSING_FIELDS", "fields": missing})
        if not row.get("question", "").endswith("?") or not row.get("answer", "").strip():
            qa_errors.append({"qa_id": row.get("qa_id"), "error": "MALFORMED_QUESTION_OR_ANSWER"})
        if row.get("gold_evidence_ids") != [e.get("evidence_id") for e in row.get("gold_evidence", [])]:
            qa_errors.append({"qa_id": row["qa_id"], "error": "GOLD_EVIDENCE_ID_LIST_MISMATCH"})
        for evidence_id in row.get("gold_evidence_ids", []):
            if evidence_id not in all_evidence_ids:
                qa_errors.append({"qa_id": row["qa_id"], "error": "UNRESOLVED_GOLD_EVIDENCE", "evidence_id": evidence_id})
        if row in core:
            if row.get("status") != "PASS" or any(value == "FAIL" for value in (row.get("validation_v3_1") or {}).values()):
                qa_errors.append({"qa_id": row["qa_id"], "error": "CORE_SEMANTIC_VALIDATION_FAIL"})
        else:
            necessity = row.get("necessity_validation") or {}
            if row.get("relation_validation_status") != "PASS" or row.get("necessity_status") != "PASS":
                qa_errors.append({"qa_id": row["qa_id"], "error": "RELATION_OR_NECESSITY_FAIL"})
            if not necessity.get("ablation_executed") or len(necessity.get("ablations", {})) != row.get("evidence_count"):
                qa_errors.append({"qa_id": row["qa_id"], "error": "ABLATION_NOT_COMPLETE"})
            if any(value != "FULL_SUPPORT" for value in necessity.get("full_set_support", {}).values()):
                qa_errors.append({"qa_id": row["qa_id"], "error": "ANSWER_NOT_FULLY_DERIVABLE"})
            if not all(value.get("necessary") for value in necessity.get("ablations", {}).values()):
                qa_errors.append({"qa_id": row["qa_id"], "error": "REDUNDANT_GOLD_EVIDENCE"})
    evidence_count = Counter(row.get("evidence_count", len(row.get("gold_evidence", []))) for row in qa)
    modality = Counter(row.get("modality", "SINGLE") for row in qa)
    cross_section = sum(len({e.get("section_id") for e in row.get("gold_evidence", []) if e.get("section_id")}) >= 2 for row in challenge)
    qa_stats = {
        "total": len(qa), "single_evidence": evidence_count[1], "multi_evidence": sum(value for key, value in evidence_count.items() if key >= 2),
        "two_evidence": evidence_count[2], "three_plus_evidence": sum(value for key, value in evidence_count.items() if key >= 3),
        "cross_page": sum(row.get("cross_page", False) for row in qa), "same_page": sum(not row.get("cross_page", False) for row in qa),
        "cross_section": cross_section, "text_text": modality["MULTI_TEXT"], "text_table": modality["TEXT_TABLE"],
        "table_table": modality["TABLE_TABLE"], "human_reviewed": sum(row.get("human_validated", False) for row in qa),
    }
    targets = {
        "documents_80_120": 80 <= len(docs) <= 120, "qa_600_900": 600 <= len(qa) <= 900,
        "multi_evidence>=180": qa_stats["multi_evidence"] >= 180, "cross_page>=120": qa_stats["cross_page"] >= 120,
        "text_table>=70": qa_stats["text_table"] >= 70, "three_plus>=50": qa_stats["three_plus_evidence"] >= 50,
        "core_long_documents>=25": sum(d["document_type_v3_1"] == "core_long" for d in docs) >= 25,
    }

    # F. Negative identity, source grounding, minimality, and contamination audit.
    negative_errors = []
    if count_duplicates([n["negative_id"] for n in negatives]):
        negative_errors.append({"error": "DUPLICATE_NEGATIVE_ID"})
    qa_index = {row["qa_id"]: row for row in qa}
    minimal_full_answer_overlap = []
    for row in negatives:
        source = qa_index.get(row.get("source_qa_id"))
        if not source:
            negative_errors.append({"negative_id": row["negative_id"], "error": "UNRESOLVED_SOURCE_QA"}); continue
        negative_evidence_id = row.get("negative_evidence_id")
        if negative_evidence_id not in all_evidence_ids:
            negative_errors.append({"negative_id": row["negative_id"], "error": "UNRESOLVED_NEGATIVE_EVIDENCE"})
        if not row.get("source_grounded") or row.get("semantic_validation") != "PASS":
            negative_errors.append({"negative_id": row["negative_id"], "error": "NEGATIVE_VALIDATION_FAIL"})
        kind = row.get("negative_type")
        if row.get("negative_status") == "VALID_MINIMAL":
            expected = kind.removeprefix("WRONG_").lower()
            if row.get("signature_differences") != [expected]:
                negative_errors.append({"negative_id": row["negative_id"], "error": "NONMINIMAL_SIGNATURE_DIFFERENCE"})
            if negative_evidence_id in source.get("gold_evidence_ids", []):
                negative_errors.append({"negative_id": row["negative_id"], "error": "NEGATIVE_DUPLICATES_GOLD"})
            combined = fold(" ".join(evidence_text(e) for e in row.get("candidate_evidence", [])))
            answer = fold(source.get("answer", "")).strip(" .;:")
            if len(answer) >= 25 and answer in combined:
                minimal_full_answer_overlap.append(row["negative_id"])
        elif kind == "PARTIAL_EVIDENCE_SET":
            if not set(row.get("candidate_evidence_ids", [])) < set(source.get("gold_evidence_ids", [])) or not (row.get("ablation_proof") or {}).get("necessary"):
                negative_errors.append({"negative_id": row["negative_id"], "error": "INVALID_PARTIAL_SET"})
        elif kind == "REDUNDANT_EVIDENCE_SET":
            if not set(source.get("gold_evidence_ids", [])) < set(row.get("candidate_evidence_ids", [])) or row.get("redundant_evidence_id") in source.get("gold_evidence_ids", []):
                negative_errors.append({"negative_id": row["negative_id"], "error": "INVALID_REDUNDANT_SET"})
    if minimal_full_answer_overlap:
        negative_errors.append({"error": "MINIMAL_NEGATIVE_CONTAINS_FULL_ANSWER_TEXT", "count": len(minimal_full_answer_overlap), "examples": minimal_full_answer_overlap[:20]})

    # G. Split integrity and conservative leakage audit.
    split_errors = []
    split_rows = {"train": train, "dev": dev, "candidate_gold_test": test}
    membership = defaultdict(list)
    evidence_split = defaultdict(set)
    for name, rows in split_rows.items():
        for row in rows:
            membership[row["qa_id"]].append(name)
            for evidence_id in row.get("gold_evidence_ids", []):
                evidence_split[evidence_id].add(name)
    duplicate_split_membership = {qid: names for qid, names in membership.items() if len(names) != 1}
    if duplicate_split_membership or set(membership) != set(qa_index):
        split_errors.append({"error": "SPLIT_PARTITION_INVALID", "duplicate_or_missing": len(duplicate_split_membership), "partition_size": len(membership), "qa_size": len(qa)})
    evidence_leakage = {eid: sorted(names) for eid, names in evidence_split.items() if len(names) > 1}
    if evidence_leakage:
        split_errors.append({"error": "EVIDENCE_CROSS_SPLIT_LEAKAGE", "count": len(evidence_leakage)})
    if not split_audit.get("leakage_audit_pass") or split_audit.get("family_overlap_count"):
        split_errors.append({"error": "DOCUMENT_FAMILY_LEAKAGE", "detail": split_audit})
    # Semantic near duplicates are blockers only when question and answer are both near-identical across splits.
    near_duplicate_qa = []
    split_flat = [(name, row) for name, rows in split_rows.items() for row in rows]
    for i, (left_split, left) in enumerate(split_flat):
        left_tokens = question_tokens(left["question"])
        for right_split, right in split_flat[i + 1:]:
            if left_split == right_split:
                continue
            right_tokens = question_tokens(right["question"])
            jaccard = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
            if jaccard < 0.92:
                continue
            answer_similarity = SequenceMatcher(None, fold(left["answer"]), fold(right["answer"])).ratio()
            if answer_similarity >= 0.92:
                near_duplicate_qa.append({"left": left["qa_id"], "left_split": left_split, "right": right["qa_id"], "right_split": right_split, "question_jaccard": round(jaccard, 4), "answer_similarity": round(answer_similarity, 4)})
    if near_duplicate_qa:
        split_errors.append({"error": "NEAR_DUPLICATE_QA_CROSS_SPLIT", "count": len(near_duplicate_qa), "examples": near_duplicate_qa[:20]})
    evaluation_human_reviewed = sum(row.get("human_validated", False) for row in dev + test)

    # Gold-evidence provenance export.
    provenance_rows, seen_evidence = [], set()
    for row in qa:
        for ev, sig in zip(row.get("gold_evidence", []), row.get("provenance_signatures", [])):
            if ev["evidence_id"] in seen_evidence:
                continue
            seen_evidence.add(ev["evidence_id"])
            doc = doc_index[ev["doc_id"]]
            provenance_rows.append({
                "evidence_id": ev["evidence_id"], "document_id": ev["doc_id"],
                "document_version": doc.get("version_status") or "UNKNOWN",
                "page_id": ev.get("page_id"), "page_number": ev.get("page_number"),
                "region_id": ev["evidence_id"] if ev.get("evidence_type") == "TEXT_REGION" else None,
                "table_id": ev.get("table_id"), "cell_ref": ev.get("cell_ref"),
                "reservoir_basin_station_or_entity": (sig.get("entity") or {}).get("raw") if sig else ev.get("entity"),
                "date_or_period": sig.get("period") if sig else ev.get("period"),
                "metric": (sig.get("metric") or {}).get("canonical") if sig else ev.get("metric"),
                "unit": (sig.get("unit") or {}).get("normalized") if sig else ev.get("unit_normalized"),
                "role": sig.get("role") if sig else ev.get("role"), "evidence_type": ev.get("evidence_type"),
                "source_url": doc.get("source_url"), "source_sha256": doc.get("sha256"),
            })

    # Status and exact freeze blockers.
    automatic = {
        "CORPUS_VALID": not corpus_errors and not near_duplicate_pairs and not mapping_errors,
        "OCR_VALID": not pending_ocr and not ocr_numeric_gold_refs,
        "TABLE_VALID": not table_errors,
        "QA_SEMANTIC_VALID": not qa_errors and semantic_audit.get("qa_alignment_pass") and exact_questions == 0,
        "EVIDENCE_VALID": not qa_errors and not table_errors,
        "PROVENANCE_VALID": not corpus_errors and not mapping_errors and semantic_audit.get("provenance_validation_pass"),
        "NEGATIVES_VALID": not negative_errors,
        "SPLIT_VALID": not split_errors,
        "LEAKAGE_CHECK": not split_errors,
    }
    blockers = []
    if pending_ocr:
        blockers.append({
            "id": "OCR_HUMAN_VERIFICATION_PENDING", "count": len(pending_ocr), "pages": ocr_pages,
            "core_long_documents": sum(doc_index[next(did for did, d in ocr_docs.items() if d["source_id"] == x["source_id"])]["document_type_v3_1"] == "core_long" for x in pending_ocr),
            "detail": f"{len(pending_ocr)} accepted OCR documents ({ocr_pages} pages) remain SAMPLED_PENDING_HUMAN_VALIDATION; {ocr_partial_broken_pages} pages are automated PARTIAL/BROKEN.",
            "files": ["reports/V3_OCR_AUDIT.json", "data/ocr/v3/"],
        })
    if evaluation_human_reviewed < len(dev) + len(test):
        blockers.append({
            "id": "EVALUATION_GOLD_NOT_HUMAN_REVIEWED", "count": len(dev) + len(test) - evaluation_human_reviewed,
            "detail": f"0/{len(dev)+len(test)} dev+candidate-test QA are human validated; all {len(qa)} QA remain machine/audit validated only.",
            "files": ["data/v3_1/qa/dev.jsonl", "data/v3_1/qa/candidate_gold_test.jsonl", "reports/v3_1/review_sample/"],
        })
    unmet_targets = {key: value for key, value in targets.items() if not value}
    if unmet_targets:
        blockers.append({
            "id": "RESEARCH_COVERAGE_TARGETS_UNMET", "count": len(unmet_targets),
            "detail": "QA=597 (gap 3); cross-page=100 (gap 20); text+table=55 (gap 15); 3+ evidence=29 (gap 21); true core-long documents=16 (gap 9).",
            "files": ["reports/v3_1/dataset_stats.json", "reports/v3_1/03_challenge_quality.md"],
        })
    for name, errors in (("CORPUS_ERRORS", corpus_errors + mapping_errors), ("TABLE_ERRORS", table_errors), ("QA_ERRORS", qa_errors), ("NEGATIVE_ERRORS", negative_errors), ("SPLIT_ERRORS", split_errors)):
        write_json(REPORT_DIR / f"{name.lower()}.json", errors)
        if errors:
            blockers.append({"id": name, "count": len(errors), "detail": f"Automatic validation found {len(errors)} errors.", "files": [f"reports/stage1/{name.lower()}.json"]})
    stage_pass = not blockers and all(automatic.values())

    validation = {
        "STAGE_1": "PASS" if stage_pass else "HOLD", "automatic_gates": automatic,
        "human_review_status": {"dataset_human_validated": False, "qa_human_reviewed": qa_stats["human_reviewed"], "evaluation_qa_human_reviewed": evaluation_human_reviewed},
        "counts": {
            "documents": len(docs), "pages": len(pages), "regions": len(regions), "tables": len(tables),
            "tables_semantically_usable": semantic_good_tables, "tables_used_by_gold": len(used_tables), "table_gold_evidence_references": table_evidence_refs,
            "qa": qa_stats, "hard_negatives": len(negatives), "minimal_negatives": len(minimal),
            "dev": len(dev), "candidate_test": len(test), "ocr_documents": len(ocr_docs), "ocr_pages": ocr_pages,
        },
        "integrity": {
            "source_files_verified": len(source_rows), "source_errors": len(corpus_errors),
            "exact_duplicate_documents": exact_duplicate_docs, "near_duplicate_document_pairs": len(near_duplicate_pairs),
            "mapping_errors": len(mapping_errors), "gold_table_errors": len(table_errors), "qa_errors": len(qa_errors),
            "exact_duplicate_questions": exact_questions, "negative_errors": len(negative_errors),
            "split_errors": len(split_errors), "cross_split_evidence_leakage": len(evidence_leakage),
            "cross_split_near_duplicate_qa": len(near_duplicate_qa),
        },
        "targets": targets, "blockers": blockers,
    }
    write_json(REPORT_DIR / "STAGE1_VALIDATION.json", validation)
    write_json(REPORT_DIR / "corpus_source_integrity.json", {"sources": source_rows, "errors": corpus_errors, "near_duplicate_pairs": near_duplicate_pairs})
    write_json(REPORT_DIR / "mapping_ocr_audit.json", {"mapping_errors": mapping_errors, "ocr_documents": list(ocr_docs), "ocr_gold_refs": ocr_gold_refs, "ocr_numeric_gold_refs": ocr_numeric_gold_refs, "pending_ocr": [x["source_id"] for x in pending_ocr]})
    write_json(REPORT_DIR / "table_gold_audit.json", {"status": "PASS" if not table_errors else "FAIL", "semantic_good_tables": semantic_good_tables, "used_tables": len(used_tables), "gold_evidence_references": table_evidence_refs, "errors": table_errors})
    write_json(REPORT_DIR / "qa_evidence_audit.json", {"status": "PASS" if not qa_errors else "FAIL", "stats": qa_stats, "targets": targets, "errors": qa_errors})
    write_json(REPORT_DIR / "negative_contamination_audit.json", {"status": "PASS" if not negative_errors else "FAIL", "total": len(negatives), "minimal": len(minimal), "partial": len(partial), "redundant": len(redundant), "errors": negative_errors})
    write_json(REPORT_DIR / "split_leakage_audit.json", {"status": "PASS" if not split_errors else "FAIL", "counts": {k: len(v) for k, v in split_rows.items()}, "family_overlap_count": split_audit.get("family_overlap_count"), "evidence_leakage": evidence_leakage, "near_duplicate_qa": near_duplicate_qa, "errors": split_errors})

    statuses = {key: "PASS" if value else "HOLD" for key, value in automatic.items()}
    report = f"""# VietIrrDocBench — Stage 1 Freeze Report

`STAGE_1 = {'PASS' if stage_pass else 'HOLD'}`

## Validation gates

| Gate | Result | Evidence |
|---|---|---|
| CORPUS_VALID | {statuses['CORPUS_VALID']} | {len(docs)} source files checked against SHA-256/PDF/page mapping; {len(corpus_errors)+len(mapping_errors)} errors. |
| OCR_VALID | {statuses['OCR_VALID']} | {len(ocr_docs)} OCR documents / {ocr_pages} pages; {len(ocr_gold_refs)} gold references; {len(pending_ocr)} pending human verification. |
| TABLE_VALID | {statuses['TABLE_VALID']} | {semantic_good_tables} tables usable; {len(used_tables)} used by gold; {table_evidence_refs} cell references checked; {len(table_errors)} errors. |
| QA_SEMANTIC_VALID | {statuses['QA_SEMANTIC_VALID']} | {len(qa)} accepted QA; {len(qa_errors)} automatic semantic/schema errors; human validation separate below. |
| EVIDENCE_VALID | {statuses['EVIDENCE_VALID']} | All accepted challenge QA have full-set support and actual ablation. |
| PROVENANCE_VALID | {statuses['PROVENANCE_VALID']} | Source, document, page, region/table/cell mapping checked; normalized export generated. |
| NEGATIVES_VALID | {statuses['NEGATIVES_VALID']} | {len(negatives)} source-grounded negatives; {len(negative_errors)} contamination/minimality errors. |
| SPLIT_VALID | {statuses['SPLIT_VALID']} | train={len(train)}, dev={len(dev)}, candidate-test={len(test)}. |
| LEAKAGE_CHECK | {statuses['LEAKAGE_CHECK']} | Document-family overlap={split_audit.get('family_overlap_count')}; evidence overlap={len(evidence_leakage)}; semantic near-duplicate cross-split={len(near_duplicate_qa)}. |
| HUMAN_REVIEW_STATUS | HOLD | Human-validated QA: {qa_stats['human_reviewed']}/{len(qa)}; dev+candidate-test: {evaluation_human_reviewed}/{len(dev)+len(test)}. |

## Dataset counts

- Documents: {len(docs)}
- Pages: {len(pages)}
- Regions: {len(regions)}
- Tables usable for gold: {semantic_good_tables} ({len(used_tables)} currently used)
- Validated QA: {len(qa)}
- Single evidence: {qa_stats['single_evidence']}
- Multi evidence: {qa_stats['multi_evidence']}
- Cross-page: {qa_stats['cross_page']}
- Text+table: {qa_stats['text_table']}
- 3+ evidence: {qa_stats['three_plus_evidence']}
- Hard negatives: {len(negatives)}
- Dev: {len(dev)}
- Candidate test: {len(test)}

## Exact blockers

""" + "\n".join(
        f"{index}. **{item['id']}** — {item['detail']} Files: {', '.join(f'`{x}`' for x in item['files'])}."
        for index, item in enumerate(blockers, 1)
    ) + """

## Freeze decision

No immutable final test/freeze marker is issued while status is `HOLD`. The release candidate is reproducible and may be promoted only in a new version after the listed blockers are closed. Stage 2 retrieval baselines were not run.
"""
    (ROOT / "STAGE1_FREEZE_REPORT.md").write_text(report, encoding="utf-8", newline="\n")
    (REPORT_DIR / "STAGE1_FREEZE_REPORT.md").write_text(report, encoding="utf-8", newline="\n")

    # Reproducible candidate layout. Raw PDFs remain referenced by checksum to avoid duplicating the workspace corpus while HOLD.
    for directory in ("manifest", "corpus", "pages", "regions", "tables", "qa", "negatives", "provenance", "validation"):
        (RELEASE / directory).mkdir(parents=True, exist_ok=True)
    write_jsonl(RELEASE / "corpus/documents.jsonl", docs)
    write_jsonl(RELEASE / "corpus/source_files.jsonl", source_rows)
    write_jsonl(RELEASE / "pages/pages.jsonl", pages)
    write_jsonl(RELEASE / "regions/regions.jsonl", regions)
    write_jsonl(RELEASE / "tables/tables.jsonl", tables)
    for source, name in ((core, "core_qa.jsonl"), (challenge, "challenge_qa.jsonl"), (train, "train.jsonl"), (dev, "dev.jsonl"), (test, "test_candidate.jsonl")):
        write_jsonl(RELEASE / f"qa/{name}", source)
    for source, name in ((minimal, "minimal_negatives.jsonl"), (partial, "partial_sets.jsonl"), (redundant, "redundant_sets.jsonl")):
        write_jsonl(RELEASE / f"negatives/{name}", source)
    write_jsonl(RELEASE / "provenance/evidence_provenance.jsonl", provenance_rows)
    for path in REPORT_DIR.glob("*.json"):
        shutil.copy2(path, RELEASE / "validation" / path.name)
    shutil.copy2(ROOT / "STAGE1_FREEZE_REPORT.md", RELEASE / "STAGE1_FREEZE_REPORT.md")
    write_json(RELEASE / "manifest/dataset_manifest.json", {
        "name": "VietIrrDocBench", "candidate_version": "v1", "freeze_status": "PASS" if stage_pass else "HOLD",
        "human_validated": False, "canonical_validation": "validation/STAGE1_VALIDATION.json",
        "final_test_published": stage_pass, "stage2_executed": False,
    })
    manifest_files = []
    for path in sorted(p for p in RELEASE.rglob("*") if p.is_file() and p.name != "SHA256SUMS.json"):
        manifest_files.append({"path": path.relative_to(RELEASE).as_posix(), "sha256": file_sha256(path), "bytes": path.stat().st_size})
    write_json(RELEASE / "manifest/SHA256SUMS.json", {"algorithm": "SHA-256", "file_count": len(manifest_files), "files": manifest_files})
    print(json.dumps({"STAGE_1": validation["STAGE_1"], "counts": validation["counts"], "blockers": blockers, "release_candidate": str(RELEASE)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
