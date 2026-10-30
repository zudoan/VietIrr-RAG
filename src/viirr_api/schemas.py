from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


StageStatus = Literal["completed", "in_progress", "blocked", "planned"]


class HealthResponse(BaseModel):
    status: Literal["ready", "degraded"]
    service: str
    api_version: str
    mode: str
    answer_generation: bool
    retrieval_method: str
    corpus_version: str
    index_cache: str
    evidence_units: int
    database: Literal["ready", "unavailable"]
    public_mode: bool
    uptime_seconds: float
    r6: dict[str, Any] | None = None


class StatsResponse(BaseModel):
    corpus_version: str
    frozen: bool
    human_validated: bool
    documents: int
    pages: int
    regions: int
    tables: int
    evidence_units: int
    qa_total: int
    qa_core: int
    qa_challenge: int
    source_grounded_negatives: int
    retrieval_method: str
    verified_at: datetime | None = None


class StageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_index: int
    name: str
    status: StageStatus
    summary: str
    evidence_source: str
    updated_at: datetime


class StagesResponse(BaseModel):
    items: list[StageResponse]
    source: str
    updated_at: datetime | None


class MilestoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str
    summary: str
    status: StageStatus
    occurred_on: date | None
    source_path: str


class DocumentRegion(BaseModel):
    evidence_id: str
    page_number: int
    unit_type: str
    text: str | None


class DocumentResponse(BaseModel):
    doc_id: str
    title: str
    doc_type: str
    source_agency: str
    source_domain: str | None = None
    source_url: str | None = None
    publication_date: str | None = None
    page_count: int | None = None
    core_or_temporal: str | None = None
    basin: list[str] = Field(default_factory=list)
    province: list[str] = Field(default_factory=list)
    acceptance_status: str | None = None
    redistribution_status: str
    pdf_available: bool
    pdf_url: str | None = None
    document_number: str | None = None
    effective_date: str | None = None
    reporting_period: str | dict[str, Any] | None = None
    landing_page_url: str | None = None
    version_status: str | None = None
    is_scanned: bool | None = None
    ocr_used: bool | None = None
    human_validated: bool | None = None
    evidence_count: int | None = None
    regions: list[DocumentRegion] | None = None
    access_notice: str | None = None


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int
    pages: int
    types: list[str]


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    top_k: int = Field(default=8, ge=1, le=20)


class EvidenceResult(BaseModel):
    rank: int
    evidence_id: str
    doc_id: str
    page_number: int
    unit_type: str
    score: float
    relevance: float
    text: str | None
    title: str
    source_agency: str
    source_url: str | None = None
    doc_type: str
    redistribution_status: str
    pdf_available: bool
    pdf_url: str | None = None
    access_notice: str | None = None


class SearchResponse(BaseModel):
    query: str
    mode: str
    answer: None = None
    answer_notice: str
    retrieval_method: str
    corpus_version: str
    result_count: int
    latency_ms: float
    excerpt_policy: Literal["local_research", "approved_public_only", "metadata_only"]
    results: list[EvidenceResult]


class QARequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    pipeline: Literal["r6"] = "r6"
    verification_mode: Literal["off", "ontology", "shadow"] = "off"
    correction_mode: Literal["off", "targeted"] = "off"


class CitationResponse(BaseModel):
    document_id: str
    page_id: str
    page_number: int = Field(ge=1)
    evidence_id: str
    source_version: str
    snippet: str | None = None
    provenance_status: Literal["VALID", "PDF_UNAVAILABLE"]
    viewer_url: str | None = None
    title: str
    source_agency: str
    unit_type: str


class QAResponse(BaseModel):
    request_id: str
    answer: str
    pipeline: Literal["r6"]
    generation_model: str
    corpus_version: str
    verification: dict[str, Any]
    correction: dict[str, str]
    citations: list[CitationResponse]
    retrieved_references: list[CitationResponse] = Field(default_factory=list)
    timing_ms: dict[str, float | None]
    trace: dict[str, Any]

    # Canonical status & abstention contract
    abstained: bool = False
    abstention_type: Literal[
        "NONE",
        "MODEL_ABSTAINED",
        "GUARD_REJECTED",
        "NO_PERMITTED_EVIDENCE",
        "NO_EVIDENCE",
    ] = "NONE"
    guard_verdict: Literal["PASS", "ABSTAIN", "NOT_RUN"] = "NOT_RUN"
    guard_reason: str = ""
    model_generated_answer: bool = False
    final_status: Literal[
        "FINAL_ANSWER_ACCEPTED",
        "FINAL_ABSTAINED",
    ] = "FINAL_ANSWER_ACCEPTED"


class ReadinessResponse(BaseModel):
    generated_at: datetime | None
    source: str
    candidate_test_accessed: bool
    canonical_corpus: dict[str, Any]
    v3_2_frozen: dict[str, Any]
    v4_candidate_expansion: dict[str, Any]
    validation: dict[str, Any]
    phase_e_demo: dict[str, Any]


class ReportResponse(BaseModel):
    generated_at: datetime | None
    sources: list[str]
    corpus: dict[str, Any]
    datasets: dict[str, Any]
    data_quality: dict[str, Any]
    retrieval: dict[str, Any]
    limitations: list[str]
    milestones: list[MilestoneResponse]
