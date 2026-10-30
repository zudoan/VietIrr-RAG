from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import CorpusVersion, DataQualitySummary, Document, MetricSnapshot, Milestone, ProjectStage
from .repository import PhaseERepository, repair_text


READINESS_SOURCE = "READINESS_COUNTS.json"


def _verified_at(snapshot: dict[str, Any]) -> datetime:
    value = snapshot.get("snapshot", {}).get("generated_at_local")
    if value:
        return datetime.fromisoformat(value)
    return datetime.now(timezone.utc)


def _upsert(session: Session, model: type[Any], identity: dict[str, Any], values: dict[str, Any]) -> Any:
    record = session.scalar(select(model).filter_by(**identity))
    if record is None:
        record = model(**identity, **values)
        session.add(record)
    else:
        for key, value in values.items():
            setattr(record, key, value)
    return record


def seed_verified_artifacts(session: Session, repository: PhaseERepository) -> dict[str, int]:
    snapshot = repository.snapshot
    verified_at = _verified_at(snapshot)
    counts = {"documents": 0, "corpus_versions": 0, "stages": 0, "milestones": 0, "metrics": 0, "quality": 0}

    for source in repository.documents:
        _upsert(session, Document, {"id": source["doc_id"]}, {
            "title": repair_text(source.get("title") or source["doc_id"]),
            "doc_type": repair_text(source.get("doc_type") or "Không xác định"),
            "source_agency": repair_text(source.get("source_agency") or "Không xác định"),
            "source_domain": source.get("source_domain"),
            "source_url": source.get("source_url"),
            "landing_page_url": source.get("landing_page_url"),
            "publication_date": source.get("publication_date"),
            "page_count": source.get("page_count"),
            "redistribution_status": source.get("redistribution_status") or "UNCLEAR",
            "acceptance_status": source.get("acceptance_status"),
            "metadata_json": {
                "basin": [repair_text(item) for item in source.get("basin") or []],
                "province": [repair_text(item) for item in source.get("province") or []],
                "core_or_temporal": source.get("core_or_temporal"),
                "document_number": source.get("document_number"),
                "effective_date": source.get("effective_date"),
                "version_status": source.get("version_status"),
                "is_scanned": source.get("is_scanned"),
                "ocr_used": source.get("ocr_used"),
                "human_validated": source.get("human_validated", False),
            },
            "source_sha256": source.get("sha256"),
            "imported_at": verified_at,
        })
        counts["documents"] += 1

    v3_stats = repository.stats()
    v4_corpus = snapshot.get("canonical_corpus", {})
    corpus_rows = [
        ("V3.2_FINAL_SEMANTIC", "FROZEN", v3_stats["documents"], v3_stats["evidence_units"], "reports/v3_2_final_semantic/dataset_stats.json"),
        ("V4.4_CORPUS", "VERIFIED_CORPUS_ONLY", int(v4_corpus.get("pdf_sha256_match", 0)), None, str(v4_corpus.get("manifest_path", "research/vietirr_v4_1/V4_CORPUS_MANIFEST.jsonl"))),
    ]
    for version, status, document_count, evidence_count, source_path in corpus_rows:
        _upsert(session, CorpusVersion, {"version": version}, {
            "status": status,
            "document_count": document_count,
            "evidence_unit_count": evidence_count,
            "manifest_sha256": None,
            "source_path": source_path,
            "verified_at": verified_at,
        })
        counts["corpus_versions"] += 1

    v4 = snapshot.get("v4_candidate_expansion", {})
    validation = snapshot.get("validation", {})
    phase_e = snapshot.get("phase_e_demo", {})
    demo_ready = bool(phase_e.get("all_queries_returned_source_page"))
    stages = [
        ("corpus", 1, "Corpus", "completed" if v4_corpus.get("pdf_sha256_match") == v4_corpus.get("manifest_records") else "blocked", "93 tài liệu V4.4 đã được đối chiếu SHA-256; corpus phục vụ live vẫn là V3.2 frozen."),
        ("qa", 2, "QA & kiểm định dữ liệu", "in_progress" if v4.get("human_gold_true", 0) == 0 else "completed", f"{v4.get('records_total', 0)} QA candidate V4; chưa có human-gold, còn {v4.get('normalized_status_counts', {}).get('REVIEW_REQUIRED', 0)} bản ghi cần review."),
        ("retrieval", 3, "Retrieval", "completed" if demo_ready else "blocked", "BM25 V3.2 đang phục vụ Evidence Search; dense, hybrid và Page→Region mới được xác minh offline."),
        ("evaluation", 4, "Đánh giá", "blocked" if validation.get("evaluation_eligible_v4_candidates", 0) == 0 else "in_progress", "Metric hiện tại chỉ thuộc V3.2 frozen DEV; V4 chưa đủ điều kiện đánh giá."),
        ("training", 5, "Training", "planned", "Không có mô hình sinh câu trả lời trong serving stack; nghiên cứu dense/reranking được giữ tách biệt."),
        ("deployment", 6, "Triển khai", "in_progress", "Production stack đã được cấu hình; trạng thái public chỉ hoàn thành sau khi xác minh URL HTTPS."),
    ]
    for stage_id, order_index, name, status, summary in stages:
        _upsert(session, ProjectStage, {"id": stage_id}, {
            "order_index": order_index,
            "name": name,
            "status": status,
            "summary": summary,
            "evidence_source": READINESS_SOURCE,
            "updated_at": verified_at,
        })
        counts["stages"] += 1

    milestones = [
        ("v3-2-freeze", "Đóng băng Dataset V3.2", "545 QA accepted; DEV gồm 93 QA và Candidate Test vẫn sealed.", "completed", date(2026, 10, 16), "READINESS_DATA_SNAPSHOT.md"),
        ("v4-corpus-verified", "Xác minh corpus V4.4", "93/93 PDF khớp SHA-256 trong manifest kiểm chứng.", "completed", date(2026, 10, 16), READINESS_SOURCE),
        ("phase-e-live", "Evidence Search Phase E", "Ba truy vấn demo đều trả về source và page bằng BM25 live V3.2.", "completed" if demo_ready else "blocked", date(2026, 10, 16), "DEMO_READINESS_2026_10_17.md"),
        ("v4-human-review", "Human review V4", "Candidate expansion chưa được xem là human gold hoặc evaluation set.", "in_progress", None, READINESS_SOURCE),
        ("public-release", "Public HTTPS release", "Chờ kết nối tài khoản hosting, PostgreSQL managed và xác minh URL bên ngoài.", "planned", None, "PRODUCTION_DEPLOYMENT_GUIDE.md"),
    ]
    for slug, title, summary, status, occurred_on, source_path in milestones:
        _upsert(session, Milestone, {"slug": slug}, {
            "title": title,
            "summary": summary,
            "status": status,
            "occurred_on": occurred_on,
            "source_path": source_path,
        })
        counts["milestones"] += 1

    retrieval = snapshot.get("retrieval_smoke", {})
    for method, metrics in retrieval.get("metrics", {}).items():
        _upsert(session, MetricSnapshot, {
            "corpus_version": "V3.2_FINAL_SEMANTIC",
            "evaluation_split": "DEV",
            "method": method,
        }, {
            "sample_count": int(metrics.get("sample_count", 0)),
            "metrics_json": metrics,
            "source_path": "reports/B2/B2_BASELINE_METRICS.json",
            "verified_at": verified_at,
        })
        counts["metrics"] += 1

    normalized = v4.get("normalized_status_counts", {})
    quality_rows = [
        ("V3.2_FINAL_SEMANTIC", int(snapshot.get("v3_2_frozen", {}).get("counts", {}).get("accepted_total", 0)), 0, 0, 0, 0, snapshot.get("v3_2_frozen", {}), "data/v3_2_final_semantic/all_qa.jsonl"),
        ("V4_BATCH_01_09", int(v4.get("records_total", 0)), int(normalized.get("CANDIDATE_MACHINE_SUPPORTED", 0)), int(normalized.get("REVIEW_REQUIRED", 0)), int(normalized.get("QUARANTINED", 0)), int(v4.get("human_gold_true", 0)), {"validation": validation, "after_all_quarantine": v4.get("after_all_quarantine")}, READINESS_SOURCE),
    ]
    for version, qa_total, machine, review, quarantined, human_gold, details, source_path in quality_rows:
        _upsert(session, DataQualitySummary, {"version": version}, {
            "qa_total": qa_total,
            "machine_supported": machine,
            "review_required": review,
            "quarantined": quarantined,
            "human_gold": human_gold,
            "details_json": details,
            "source_path": source_path,
            "verified_at": verified_at,
        })
        counts["quality"] += 1

    session.commit()
    return counts
