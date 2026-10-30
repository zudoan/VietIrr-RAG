from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    source_agency: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_domain: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(Text)
    landing_page_url: Mapped[str | None] = mapped_column(Text)
    publication_date: Mapped[str | None] = mapped_column(String(40), index=True)
    page_count: Mapped[int | None] = mapped_column(Integer)
    redistribution_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    acceptance_status: Mapped[str | None] = mapped_column(String(40))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    source_sha256: Mapped[str | None] = mapped_column(String(64), unique=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    evidence_references: Mapped[list["EvidenceReference"]] = relationship(back_populates="document")


class EvidenceReference(Base):
    __tablename__ = "evidence_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evidence_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_type: Mapped[str] = mapped_column(String(40), nullable=False)
    public_excerpt: Mapped[str | None] = mapped_column(Text)
    approved_for_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    document: Mapped[Document] = relationship(back_populates="evidence_references")

    __table_args__ = (Index("ix_evidence_document_page", "document_id", "page_number"),)


class CorpusVersion(Base):
    __tablename__ = "corpus_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_unit_count: Mapped[int | None] = mapped_column(Integer)
    manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProjectStage(Base):
    __tablename__ = "project_stages"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_source: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Milestone(Base):
    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    occurred_on: Mapped[date | None] = mapped_column(Date)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    corpus_version: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    evaluation_split: Mapped[str] = mapped_column(String(40), nullable=False)
    method: Mapped[str] = mapped_column(String(80), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("corpus_version", "evaluation_split", "method", name="uq_metric_scope_method"),)


class DataQualitySummary(Base):
    __tablename__ = "data_quality_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    qa_total: Mapped[int] = mapped_column(Integer, nullable=False)
    machine_supported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_required: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quarantined: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    human_gold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SearchAnalytics(Base):
    __tablename__ = "search_analytics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    retrieval_method: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
