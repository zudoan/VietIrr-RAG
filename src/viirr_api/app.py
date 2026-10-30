"""Production FastAPI service for verified VietIrr metadata and live BM25 retrieval."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import threading
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .database import Base, create_database_engine, create_session_factory
from .models import Document, Milestone, ProjectStage, SearchAnalytics
from .repository import PhaseERepository, repair_text
from .r6_service import R6Unavailable, RAGInferenceService
from .schemas import (
    DocumentListResponse,
    DocumentResponse,
    HealthResponse,
    ReadinessResponse,
    ReportResponse,
    QARequest,
    QAResponse,
    SearchRequest,
    SearchResponse,
    StagesResponse,
    StatsResponse,
)
from .seed import seed_verified_artifacts
from .settings import Settings


LOGGER = logging.getLogger("viirr_api")
PUBLIC_REDISTRIBUTION_STATUSES = {"PUBLIC", "OPEN", "PERMITTED", "REDISTRIBUTABLE"}


class RateLimiter:
    def __init__(self, requests_per_minute: int) -> None:
        self.limit = requests_per_minute
        self.events: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        cutoff = time.monotonic() - 60
        with self.lock:
            queue = self.events[key]
            while queue and queue[0] < cutoff:
                queue.popleft()
            if len(queue) >= self.limit:
                return False
            queue.append(time.monotonic())
            return True


def _generated_at(snapshot: dict[str, Any]) -> datetime | None:
    value = snapshot.get("snapshot", {}).get("generated_at_local")
    return datetime.fromisoformat(value) if value else None


def _select(source: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: source[key] for key in keys if key in source}


def _public_readiness_projection(snapshot: dict[str, Any]) -> dict[str, Any]:
    canonical = snapshot.get("canonical_corpus", {})
    frozen = snapshot.get("v3_2_frozen", {})
    expansion = snapshot.get("v4_candidate_expansion", {})
    validation = snapshot.get("validation", {})
    demo = snapshot.get("phase_e_demo", {})
    public_queries = [
        _select(query, "query", "modality", "location_type", "result_count", "latency_ms")
        for query in demo.get("queries", [])
    ]
    return {
        "canonical_corpus": _select(
            canonical,
            "manifest_records", "unique_document_ids", "pdf_present", "pdf_sha256_match",
            "pdf_sha256_mismatch", "pdf_missing", "pdf_page_read_errors", "duplicate_document_ids",
        ),
        "v3_2_frozen": _select(frozen, "counts", "candidate_test", "evaluation_scope_used_now"),
        "v4_candidate_expansion": _select(
            expansion,
            "records_total", "unique_candidate_ids", "after_semantic_duplicate_removal",
            "after_all_quarantine", "normalized_status_counts", "human_gold_true",
            "dataset_split_assigned", "unique_source_documents",
        ),
        "validation": _select(
            validation,
            "candidate_schema_issue_count", "candidate_source_issue_count", "candidate_evidence_instances",
            "candidate_evidence_page_locators", "candidate_evidence_without_anchor_claim_or_locator",
            "review_flags_nonempty_records", "evaluation_eligible_v4_candidates", "evaluation_exclusion_reason",
        ),
        "phase_e_demo": {
            **_select(demo, "repository_status", "selection_note", "all_queries_returned_source_page", "answer_generation"),
            "queries": public_queries,
        },
    }


def _public_document_view(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    status_value = str(payload.get("redistribution_status") or "UNCLEAR").upper()
    distributable = status_value in PUBLIC_REDISTRIBUTION_STATUSES
    if settings.public_mode and not distributable:
        payload["pdf_available"] = False
        payload["pdf_url"] = None
        payload["access_notice"] = "Chỉ công bố metadata và liên kết nguồn vì quyền tái phân phối tài liệu chưa rõ."
        for region in payload.get("regions") or []:
            region["text"] = None
    return payload


def _document_from_model(document: Document) -> dict[str, Any]:
    metadata = document.metadata_json or {}
    return {
        "doc_id": document.id,
        "title": document.title,
        "doc_type": document.doc_type,
        "source_agency": document.source_agency,
        "source_domain": document.source_domain,
        "source_url": document.source_url,
        "publication_date": document.publication_date,
        "page_count": document.page_count,
        "core_or_temporal": metadata.get("core_or_temporal"),
        "basin": metadata.get("basin") or [],
        "province": metadata.get("province") or [],
        "acceptance_status": document.acceptance_status,
        "redistribution_status": document.redistribution_status,
        "pdf_available": False,
        "pdf_url": None,
    }


def create_app(
    settings: Settings | None = None,
    repository: PhaseERepository | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    active_settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        active_repository = repository or PhaseERepository(active_settings.root)
        active_engine = engine or create_database_engine(active_settings.database_url)
        if active_settings.auto_create_schema:
            Base.metadata.create_all(active_engine)
        factory = create_session_factory(active_engine)
        if active_settings.auto_seed:
            try:
                with factory() as session:
                    seed_verified_artifacts(session, active_repository)
            except SQLAlchemyError:
                LOGGER.exception("Database seed failed; health endpoint will report degraded state.")
        application.state.settings = active_settings
        application.state.repository = active_repository
        application.state.engine = active_engine
        application.state.session_factory = factory
        application.state.rate_limiter = RateLimiter(active_settings.rate_limit_per_minute)
        application.state.r6_service = RAGInferenceService(
            active_settings.root,
            max_concurrency=active_settings.r6_max_concurrency,
            context_budget_tokens=active_settings.r6_context_budget_tokens,
        ) if active_settings.r6_enabled else None
        yield
        active_engine.dispose()

    application = FastAPI(
        title="VietIrr Evidence API",
        description="Evidence-first retrieval and verified research reporting. No answer generation.",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
        max_age=600,
    )

    @application.middleware("http")
    async def security_boundary(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                request_size = int(content_length)
            except ValueError:
                return JSONResponse({"detail": "Content-Length không hợp lệ."}, status_code=status.HTTP_400_BAD_REQUEST)
            if request_size > active_settings.max_request_bytes:
                return JSONResponse({"detail": "Request body vượt quá giới hạn cho phép."}, status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        client = request.client.host if request.client else "unknown"
        limiter: RateLimiter = getattr(request.app.state, "rate_limiter", RateLimiter(active_settings.rate_limit_per_minute))
        if (request.url.path.endswith("/search") or request.url.path.endswith("/qa")) and not limiter.allow(client):
            return JSONResponse({"detail": "Quá nhiều truy vấn. Vui lòng thử lại sau."}, status_code=status.HTTP_429_TOO_MANY_REQUESTS)
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path in {"/api/docs", "/api/redoc"}:
            response.headers["Content-Security-Policy"] = "default-src 'none'; script-src https://cdn.jsdelivr.net; style-src 'unsafe-inline' https://cdn.jsdelivr.net; img-src data: https://fastapi.tiangolo.com; frame-ancestors 'none'"
        else:
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["X-Response-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.2f}"
        return response

    @application.exception_handler(Exception)
    async def unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception("Unhandled API error", exc_info=exc)
        return JSONResponse({"detail": "Dịch vụ gặp lỗi nội bộ."}, status_code=500)

    def get_repository(request: Request) -> PhaseERepository:
        return request.app.state.repository

    def get_settings(request: Request) -> Settings:
        return request.app.state.settings

    def get_r6_service(request: Request) -> RAGInferenceService:
        service = getattr(request.app.state, "r6_service", None)
        if service is None:
            raise HTTPException(status_code=503, detail="R6 online inference is disabled by configuration.")
        return service

    def get_session(request: Request) -> Generator[Session, None, None]:
        factory: sessionmaker[Session] = request.app.state.session_factory
        with factory() as session:
            yield session

    @application.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
    def health(request: Request, response: Response, repo: PhaseERepository = Depends(get_repository)) -> dict[str, Any]:
        payload = repo.status()
        r6_service = getattr(request.app.state, "r6_service", None)
        r6_status = r6_service.capability_status() if r6_service is not None else {"enabled": False}
        database_status = "ready"
        try:
            with request.app.state.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            database_status = "unavailable"
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            **payload,
            "status": "ready" if database_status == "ready" else "degraded",
            "api_version": "v1",
            "database": database_status,
            "public_mode": request.app.state.settings.public_mode,
            "mode": "R6_QA" if r6_service is not None else payload["mode"],
            "answer_generation": r6_service is not None,
            "retrieval_method": "R6_HYBRID_BGE_M3_RERANKER" if r6_service is not None else payload["retrieval_method"],
            "corpus_version": r6_status.get("corpus_version", payload["corpus_version"]),
            "r6": r6_status,
        }

    @application.get("/api/v1/stats", response_model=StatsResponse, tags=["research"])
    def stats(repo: PhaseERepository = Depends(get_repository)) -> dict[str, Any]:
        return {**repo.stats(), "verified_at": _generated_at(repo.snapshot)}

    @application.get("/api/v1/readiness", response_model=ReadinessResponse, tags=["research"])
    def readiness(
        repo: PhaseERepository = Depends(get_repository),
        settings_value: Settings = Depends(get_settings),
    ) -> dict[str, Any]:
        snapshot = repo.snapshot
        projection = _public_readiness_projection(snapshot) if settings_value.public_mode else {
            "canonical_corpus": snapshot.get("canonical_corpus", {}),
            "v3_2_frozen": snapshot.get("v3_2_frozen", {}),
            "v4_candidate_expansion": snapshot.get("v4_candidate_expansion", {}),
            "validation": snapshot.get("validation", {}),
            "phase_e_demo": snapshot.get("phase_e_demo", {}),
        }
        return {
            "generated_at": _generated_at(snapshot),
            "source": "verified release snapshot" if settings_value.public_mode else "READINESS_COUNTS.json",
            "candidate_test_accessed": bool(snapshot.get("snapshot", {}).get("candidate_test_content_accessed", False)),
            **projection,
        }

    @application.get("/api/v1/stages", response_model=StagesResponse, tags=["research"])
    def stages(session: Session = Depends(get_session)) -> dict[str, Any]:
        items = list(session.scalars(select(ProjectStage).order_by(ProjectStage.order_index)))
        return {
            "items": items,
            "source": "READINESS_COUNTS.json + verified project reports",
            "updated_at": max((item.updated_at for item in items), default=None),
        }

    @application.get("/api/v1/report", response_model=ReportResponse, tags=["research"])
    def report(
        repo: PhaseERepository = Depends(get_repository),
        settings_value: Settings = Depends(get_settings),
        session: Session = Depends(get_session),
    ) -> dict[str, Any]:
        snapshot = repo.snapshot
        projection = _public_readiness_projection(snapshot) if settings_value.public_mode else {
            "canonical_corpus": snapshot.get("canonical_corpus", {}),
            "v3_2_frozen": snapshot.get("v3_2_frozen", {}),
            "v4_candidate_expansion": snapshot.get("v4_candidate_expansion", {}),
            "validation": snapshot.get("validation", {}),
            "phase_e_demo": snapshot.get("phase_e_demo", {}),
        }
        v4 = projection["v4_candidate_expansion"]
        milestones = list(session.scalars(select(Milestone).order_by(Milestone.occurred_on.asc().nulls_last(), Milestone.id)))
        retrieval = snapshot.get("retrieval_smoke", {})
        return {
            "generated_at": _generated_at(snapshot),
            "sources": ["verified release snapshot", "PostgreSQL"] if settings_value.public_mode else ["READINESS_COUNTS.json", "READINESS_DATA_SNAPSHOT.md", "DEMO_READINESS_2026_10_17.md"],
            "corpus": {
                "v3_2": repo.stats(),
                "v4_4": projection["canonical_corpus"],
            },
            "datasets": {
                "v3_2_frozen": projection["v3_2_frozen"],
                "v4_pre_expansion_registry": snapshot.get("v4_pre_expansion_registry", {}),
                "v4_candidate_expansion": v4,
            },
            "data_quality": projection["validation"],
            "retrieval": {
                "scope": retrieval.get("claim_scope"),
                "mode": retrieval.get("mode"),
                "qa_evaluated": retrieval.get("qa_evaluated"),
                "metrics": retrieval.get("metrics", {}),
                "live_method": repo.status()["retrieval_method"],
                "demo_queries": projection["phase_e_demo"].get("queries", []),
            },
            "limitations": [
                "V4 chưa có HUMAN_GOLD_VERIFIED và không đủ điều kiện báo cáo metric retrieval.",
                f"{v4.get('normalized_status_counts', {}).get('REVIEW_REQUIRED', 0)} QA candidate còn cần review; {v4.get('normalized_status_counts', {}).get('QUARANTINED', 0)} bản ghi bị quarantine.",
                "Dense, Hybrid và Page→Region đã được replay offline nhưng chưa phải phương pháp serving live.",
                "Toàn bộ PDF V3.2 có redistribution_status=UNCLEAR; public API chỉ công bố metadata và link nguồn.",
            ],
            "milestones": milestones,
        }

    @application.get("/api/v1/documents", response_model=DocumentListResponse, tags=["documents"])
    def documents(
        q: str = Query(default="", max_length=200),
        type: str = Query(default="", max_length=180),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=24, ge=1, le=100),
        settings_value: Settings = Depends(get_settings),
        repo: PhaseERepository = Depends(get_repository),
        session: Session = Depends(get_session),
    ) -> dict[str, Any]:
        statement = select(Document)
        count_statement = select(func.count()).select_from(Document)
        if q.strip():
            needle = f"%{q.strip()}%"
            predicate = Document.title.ilike(needle) | Document.source_agency.ilike(needle) | Document.id.ilike(needle)
            statement = statement.where(predicate)
            count_statement = count_statement.where(predicate)
        if type.strip():
            statement = statement.where(Document.doc_type == type.strip())
            count_statement = count_statement.where(Document.doc_type == type.strip())
        total = int(session.scalar(count_statement) or 0)
        records = list(session.scalars(statement.order_by(Document.publication_date.desc(), Document.title).offset((page - 1) * page_size).limit(page_size)))
        types = list(session.scalars(select(Document.doc_type).distinct().order_by(Document.doc_type)))
        items = []
        for record in records:
            artifact = repo.document_by_id.get(record.id)
            payload = repo.document_view(artifact) if artifact else _document_from_model(record)
            items.append(_public_document_view(payload, settings_value))
        return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": math.ceil(total / page_size) if total else 0, "types": types}

    @application.get("/api/v1/documents/{doc_id}", response_model=DocumentResponse, tags=["documents"])
    def document_detail(
        doc_id: str,
        request: Request,
        repo: PhaseERepository = Depends(get_repository),
        settings_value: Settings = Depends(get_settings),
        session: Session = Depends(get_session),
    ) -> dict[str, Any]:
        record = session.get(Document, doc_id)
        r6_service = getattr(request.app.state, "r6_service", None)
        if record is None:
            v4_record = r6_service._load_manifest().get(doc_id) if r6_service is not None else None
            if v4_record is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")
            if settings_value.public_mode and not r6_service.is_public_allowed(doc_id):
                raise HTTPException(status_code=403, detail="V4 document is not approved for public redistribution.")
            pdf_path = r6_service.resolve_pdf(doc_id)
            pdf_available = pdf_path is not None and (not settings_value.public_mode or r6_service.is_public_allowed(doc_id))
            payload = {
                "doc_id": doc_id,
                "title": repair_text(v4_record.get("source_title") or doc_id),
                "doc_type": repair_text(v4_record.get("doc_type") or "Tài liệu kỹ thuật"),
                "source_agency": repair_text(v4_record.get("publisher") or "Không xác định"),
                "source_domain": v4_record.get("source_domain"),
                "source_url": v4_record.get("source_url"),
                "publication_date": v4_record.get("publication_date"),
                "page_count": v4_record.get("page_count", 0),
                "core_or_temporal": v4_record.get("core_or_temporal"),
                "basin": [repair_text(item) for item in (v4_record.get("basin") or [])],
                "province": [repair_text(item) for item in (v4_record.get("province") or [])],
                "acceptance_status": v4_record.get("status", "ACCEPT"),
                "redistribution_status": v4_record.get("redistribution") or v4_record.get("redistribution_status") or "UNCLEAR",
                "pdf_available": pdf_available,
                "pdf_url": f"/api/v1/documents/{doc_id}/pdf" if pdf_available else None,
                "regions": [],
            }
            return _public_document_view(payload, settings_value)
        payload = repo.get_document(doc_id) or _document_from_model(record)
        return _public_document_view(payload, settings_value)

    @application.get("/api/v1/documents/{doc_id}/pdf", response_class=FileResponse, tags=["documents"])
    def document_pdf(
        doc_id: str,
        request: Request,
        repo: PhaseERepository = Depends(get_repository),
        settings_value: Settings = Depends(get_settings),
        session: Session = Depends(get_session),
    ) -> FileResponse:
        record = session.get(Document, doc_id)
        r6_service = getattr(request.app.state, "r6_service", None)
        if record is None:
            v4_record = r6_service._load_manifest().get(doc_id) if r6_service is not None else None
            if v4_record is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")
            if settings_value.public_mode and not r6_service.is_public_allowed(doc_id):
                raise HTTPException(status_code=403, detail="V4 document is not approved for public redistribution.")
            path = r6_service.resolve_pdf(doc_id)
            if path is None:
                raise HTTPException(status_code=404, detail="PDF không khả dụng trong workspace.")
            return FileResponse(path, media_type="application/pdf", filename=Path(path).name)
        if settings_value.public_mode and record.redistribution_status.upper() not in PUBLIC_REDISTRIBUTION_STATUSES:
            raise HTTPException(status_code=403, detail="PDF không được phép tái phân phối công khai; hãy dùng liên kết nguồn chính thức.")
        path = repo.pdf_path(doc_id)
        if path is None:
            path = r6_service.resolve_pdf(doc_id) if r6_service is not None else None
        if path is None:
            raise HTTPException(status_code=404, detail="PDF không khả dụng trong workspace.")
        return FileResponse(path, media_type="application/pdf", filename=Path(path).name)

    @application.post("/api/v1/qa", response_model=QAResponse, tags=["qa"])
    async def ask_question(
        payload: QARequest,
        settings_value: Settings = Depends(get_settings),
        r6_service: RAGInferenceService = Depends(get_r6_service),
    ) -> dict[str, Any]:
        if payload.pipeline != "r6":
            raise HTTPException(status_code=422, detail="Only the frozen R6 policy is available.")
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    r6_service.ask, payload.question,
                    verification_mode=payload.verification_mode,
                    correction_mode=payload.correction_mode,
                    public_mode=settings_value.public_mode,
                ),
                timeout=max(settings_value.search_timeout_seconds, 300.0),
            )
            if settings_value.public_mode:
                result["trace"] = {"diagnostic_status": "REDACTED_IN_PUBLIC_MODE"}
            return result
        except NotImplementedError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except R6Unavailable as exc:
            raise HTTPException(status_code=503, detail=f"R6/Qwen runtime unavailable: {exc}") from exc
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail="R6/Qwen inference exceeded the configured timeout.") from exc

    @application.post("/api/v1/search", response_model=SearchResponse, tags=["search"])
    async def search(
        payload: SearchRequest,
        repo: PhaseERepository = Depends(get_repository),
        settings_value: Settings = Depends(get_settings),
        session: Session = Depends(get_session),
    ) -> dict[str, Any]:
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(repo.search, payload.query, payload.top_k),
                timeout=settings_value.search_timeout_seconds,
            )
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail="Truy vấn vượt quá thời gian xử lý cho phép.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if settings_value.public_mode:
            for item in response["results"]:
                item["pdf_available"] = False
                item["pdf_url"] = None
                if not settings_value.public_evidence_excerpts or str(item.get("redistribution_status")).upper() not in PUBLIC_REDISTRIBUTION_STATUSES:
                    item["text"] = None
                    item["access_notice"] = "Excerpt chưa được phê duyệt để công bố; metadata và locator vẫn khả dụng."
            response["excerpt_policy"] = "approved_public_only" if settings_value.public_evidence_excerpts else "metadata_only"
        else:
            response["excerpt_policy"] = "local_research"
        if settings_value.search_analytics_enabled:
            session.add(SearchAnalytics(
                query_hash=hashlib.sha256(payload.query.casefold().strip().encode("utf-8")).hexdigest(),
                result_count=response["result_count"],
                latency_ms=response["latency_ms"],
                retrieval_method=response["retrieval_method"],
                created_at=datetime.now(timezone.utc),
            ))
            session.commit()
        return response

    application.add_api_route("/api/health", health, methods=["GET"], include_in_schema=False)
    application.add_api_route("/api/stats", stats, methods=["GET"], include_in_schema=False)
    application.add_api_route("/api/documents", documents, methods=["GET"], include_in_schema=False)
    application.add_api_route("/api/documents/{doc_id}", document_detail, methods=["GET"], include_in_schema=False)
    application.add_api_route("/api/documents/{doc_id}/pdf", document_pdf, methods=["GET"], include_in_schema=False)
    application.add_api_route("/api/search", search, methods=["POST"], include_in_schema=False)
    application.add_api_route("/api/qa", ask_question, methods=["POST"], include_in_schema=False)

    return application


app = create_app()


def main() -> None:
    import os
    import uvicorn

    port = int(os.getenv("PORT", os.getenv("VIETIRR_API_PORT", "8000")))
    host = os.getenv("VIETIRR_API_HOST", "0.0.0.0")
    uvicorn.run("viirr_api.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()


__all__ = ["app", "create_app", "main", "PhaseERepository", "repair_text"]
