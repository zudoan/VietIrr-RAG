"""Thin online adapter for the frozen R6 retrieval and local Qwen runtime.

This module deliberately owns no retrieval algorithm.  It connects the
existing HighPerformanceRetriever, grounded-context builder, and Ollama Qwen
provider behind a bounded, provenance-validating service boundary.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from viirr_rag.pipeline import (
    Evidence,
    build_context,
    build_grounded_prompt,
    enforce_citation_grounding,
    parse_generation,
)
from viirr_rag.provider import OllamaProvider


class R6Unavailable(RuntimeError):
    """Raised when a required local R6 runtime dependency is unavailable."""


class RAGInferenceService:
    """Lazy, single-GPU R6 E1 inference service with strict provenance checks."""

    CORPUS_VERSION = "V4_R6_FROZEN"
    RETRIEVAL_POLICY = "r6"
    PUBLIC_PERMISSIONS = {"PUBLIC", "OPEN", "PERMITTED", "REDISTRIBUTABLE"}

    def __init__(
        self,
        root: Path,
        *,
        model: str = "qwen2.5:7b",
        max_concurrency: int = 1,
        context_budget_tokens: int = 4000,
    ) -> None:
        self.root = root.resolve()
        self.model = model
        self.context_budget_tokens = context_budget_tokens
        self._retriever: Any | None = None
        self._provider: OllamaProvider | None = None
        self._manifest: dict[str, dict[str, Any]] | None = None
        self._init_lock = threading.Lock()
        self.inference_lock = threading.BoundedSemaphore(max(1, max_concurrency))
        self.started_at = time.time()
        self.last_error: str | None = None

    def _load_manifest(self) -> dict[str, dict[str, Any]]:
        if self._manifest is None:
            path = self.root / "data" / "v4_corpus" / "metadata" / "v4_corpus_manifest.jsonl"
            if not path.is_file():
                raise R6Unavailable(f"V4 corpus manifest is unavailable: {path}")
            self._manifest = {
                str(row["doc_id"]): row
                for row in (json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip())
            }
        return self._manifest

    def _ensure_initialized(self) -> None:
        if self._retriever is not None and self._provider is not None:
            return
        with self._init_lock:
            if self._retriever is not None and self._provider is not None:
                return
            try:
                from viirr_retrieval.high_perf_retriever import HighPerformanceRetriever
                import torch

                device = "cuda" if torch.cuda.is_available() else "cpu"
                self._load_manifest()
                retriever = HighPerformanceRetriever(self.root, device=device, load_reranker=True)
                provider = OllamaProvider(model=self.model)
                provider.model_info()  # fail closed; never simulate a Qwen answer
                self._retriever, self._provider = retriever, provider
                self.last_error = None
            except Exception as exc:  # preserve a clear availability boundary for HTTP mapping
                self.last_error = f"{type(exc).__name__}: {exc}"
                raise R6Unavailable(self.last_error) from exc

    def capability_status(self) -> dict[str, Any]:
        required = [
            self.root / "outputs" / "V4_EXPERIMENT" / "index" / "pages_v4.jsonl",
            self.root / "outputs" / "V4_EXPERIMENT" / "index" / "evidence_units_v4.jsonl",
            self.root / "outputs" / "RETRIEVAL_UPGRADE" / "cache" / "bge_m3_pages.npy",
            self.root / "data" / "v4_corpus" / "metadata" / "v4_corpus_manifest.jsonl",
        ]
        return {
            "pipeline": self.RETRIEVAL_POLICY,
            "corpus_version": self.CORPUS_VERSION,
            "generation_model": self.model,
            "initialized": self._retriever is not None and self._provider is not None,
            "artifacts_available": all(path.is_file() for path in required),
            "last_error": self.last_error,
        }

    def resolve_pdf(self, document_id: str) -> Path | None:
        record = self._load_manifest().get(document_id)
        if not record or not record.get("local_path"):
            return None
        path = (self.root / str(record["local_path"])).resolve()
        return path if self.root in path.parents and path.suffix.lower() == ".pdf" and path.is_file() else None

    def is_public_allowed(self, document_id: str) -> bool:
        record = self._load_manifest().get(document_id)
        if record is None:
            return False
        permission = str(record.get("redistribution") or record.get("redistribution_status") or "").upper()
        return permission in self.PUBLIC_PERMISSIONS

    def _citation(self, item: Evidence, public_mode: bool = False) -> dict[str, Any]:
        record = self._load_manifest().get(item.doc_id, {})
        pdf = self.resolve_pdf(item.doc_id)
        is_allowed = not public_mode or self.is_public_allowed(item.doc_id)
        viewer_url = f"/api/v1/documents/{item.doc_id}/pdf?page={item.page_number}" if (pdf and is_allowed) else None
        return {
            "document_id": item.doc_id,
            "page_id": item.page_id,
            "page_number": item.page_number,
            "evidence_id": item.evidence_id,
            "source_version": self.CORPUS_VERSION,
            "snippet": item.text if is_allowed else None,
            "provenance_status": "VALID" if pdf else "PDF_UNAVAILABLE",
            "viewer_url": viewer_url,
            "title": str(record.get("source_title") or item.doc_id),
            "source_agency": str(record.get("publisher") or "Unknown"),
            "unit_type": item.unit_type,
        }

    def ask(self, question: str, *, verification_mode: str = "off", correction_mode: str = "off", public_mode: bool = False) -> dict[str, Any]:
        if verification_mode not in {"off", "shadow"}:
            raise NotImplementedError("Ontology verification is only supported in 'off' or 'shadow' mode.")
        if correction_mode != "off":
            raise NotImplementedError("Targeted correction is not enabled for the web runtime; use correction_mode='off'.")
        self._ensure_initialized()
        assert self._retriever is not None and self._provider is not None
        request_id = str(uuid.uuid4())
        started = time.perf_counter()
        with self.inference_lock:
            retrieval_started = time.perf_counter()
            candidates = self._retriever.retrieve_candidates(
                question, top_k_candidates=120, use_identifier_boost=True,
                use_dual_variant=True, use_structure_aware=True, use_ontology_guide=True,
            )
            reranked = self._retriever.rerank_candidates(
                question, candidates, top_k_rerank=min(60, len(candidates)), enhanced_mode=True,
                table_aware=True, window_strategy="r6",
            )
            selected = self._retriever.allocate_budget_b_evidence(
                question, reranked, max_units=5, table_aware=True, selection_policy="a0",
            )
            retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
            index_by_id = {str(row["evidence_id"]): row for row in self._retriever.units}
            manifest = self._load_manifest()
            evidence: list[Evidence] = []
            for rank, row in enumerate(selected, 1):
                evidence_id = str(row.get("evidence_id") or "")
                indexed = index_by_id.get(evidence_id)
                if indexed is not None:
                    if str(indexed.get("doc_id")) != str(row.get("doc_id")):
                        continue  # fail closed on an allocator/provenance mismatch
                    doc_id = str(indexed["doc_id"])
                    page_id = str(indexed["page_id"])
                    page_number = int(indexed["page_number"])
                    unit_type = str(indexed.get("unit_type") or "UNKNOWN")
                    if unit_type in {"TABLE_REGION", "TABLE", "TABLE_ROW"} and indexed.get("index_text"):
                        text = str(indexed["index_text"])
                    else:
                        text = str(indexed.get("raw_text") or indexed.get("index_text") or "")
                elif str(row.get("unit_type")) == "TABLE_CELL":
                    # Authenticate fine-grained table cell against parent table across Identity, Location, Content, and Relation
                    parent_table_id = str(row.get("table_id") or "")
                    parent_table = index_by_id.get(parent_table_id)
                    is_valid, validation_status, verified_fact = self._retriever.table_resolver.validate_cell(row, parent_table)
                    if not is_valid or verified_fact is None:
                        continue  # fail closed on any provenance violation
                    doc_id = verified_fact.document_id
                    page_id = verified_fact.page_id
                    page_number = verified_fact.page_number
                    unit_type = "TABLE_CELL"
                    text = verified_fact.evidence_text()
                else:
                    continue  # unknown unit provenance
                doc_title = str(manifest.get(doc_id, {}).get("source_title") or doc_id)
                evidence.append(Evidence(
                    rank=rank, evidence_id=evidence_id, doc_id=doc_id,
                    page_id=page_id, page_number=page_number,
                    unit_type=unit_type, score=float(row.get("score", row.get("rerank_score", 0))),
                    text=text, source="r6_allocator", doc_title=doc_title,
                ))
            if public_mode:
                evidence = [item for item in evidence if self.is_public_allowed(item.doc_id)]
            context = build_context(evidence, budget_tokens=self.context_budget_tokens)
            generation_started = time.perf_counter()
            if not context.evidence:
                from viirr_rag.pipeline import GenerationResult, REFUSAL_TEXT
                generation = GenerationResult(REFUSAL_TEXT, [], True, "NO_PERMITTED_EVIDENCE" if public_mode else "NO_EVIDENCE", False, "", "")
                grounding = {"action": "ABSTAIN", "reason": "NO_PERMITTED_EVIDENCE" if public_mode else "NO_EVIDENCE"}
                raw_response, provider_model = "", self.model
                model_generated_answer = False
                abstention_type = "NO_PERMITTED_EVIDENCE" if public_mode else "NO_EVIDENCE"
                guard_verdict = "ABSTAIN"
                guard_reason = grounding["reason"]
                final_status = "FINAL_ABSTAINED"
            else:
                provider_response = self._provider.generate(build_grounded_prompt(question, context))
                parsed = parse_generation(provider_response.content)
                raw_abstained = parsed.abstained or "không đủ bằng chứng" in provider_response.content.lower()
                generation, grounding = enforce_citation_grounding(parsed, context)
                raw_response, provider_model = provider_response.content, provider_response.model
                model_generated_answer = not raw_abstained and bool(parsed.answer.strip())
                if raw_abstained:
                    abstention_type = "MODEL_ABSTAINED"
                    guard_verdict = grounding.get("action", "ABSTAIN")
                    guard_reason = grounding.get("reason", "MODEL_SELF_ABSTAINED")
                    final_status = "FINAL_ABSTAINED"
                elif generation.abstained:
                    abstention_type = "GUARD_REJECTED"
                    guard_verdict = "ABSTAIN"
                    guard_reason = grounding.get("reason", "P5 grounding guard rejected unverified or contradicted claims")
                    final_status = "FINAL_ABSTAINED"
                else:
                    abstention_type = "NONE"
                    guard_verdict = "PASS"
                    guard_reason = grounding.get("reason", "OK")
                    final_status = "FINAL_ANSWER_ACCEPTED"
            generation_ms = (time.perf_counter() - generation_started) * 1000
        selected_by_key = {}
        for item in context.evidence:
            selected_by_key[item.citation_key()] = item
            if item.unit_type == "TABLE_CELL":
                parts = item.evidence_id.split("_R")
                if len(parts) == 2:
                    parent_id = parts[0]
                    selected_by_key.setdefault((item.doc_id, item.page_number, parent_id), item)
        citations = []
        for citation in generation.citations:
            item = selected_by_key.get((citation["doc_id"], citation["page_number"], citation["evidence_id"]))
            if item is not None:
                citations.append(self._citation(item, public_mode=public_mode))
        retrieved_references = [self._citation(item, public_mode=public_mode) for item in context.evidence]
        total_ms = (time.perf_counter() - started) * 1000
        verification_payload: dict[str, Any] = {"mode": verification_mode, "status": "NOT_RUN"}
        if verification_mode in ["shadow", "ontology"] and context.evidence:
            try:
                from viirr_ontology.schema.claim import EvidenceCitation
                from viirr_ontology.schema.evidence import EvidenceItem
                from viirr_ontology.shadow_verifier import ShadowOntologyVerifier
                from viirr_ontology.typed_facts import extract_atomic_claims

                ev_items = [
                    EvidenceItem(
                        evidence_id=it.evidence_id,
                        doc_id=it.doc_id,
                        page_id=it.page_id,
                        page_number=it.page_number,
                        text=it.text,
                        document_number=it.doc_id,
                    )
                    for it in context.evidence
                ]
                shadow_verifier = ShadowOntologyVerifier()
                claim_cits = [
                    EvidenceCitation(
                        doc_id=c.get("doc_id", ""),
                        page_number=int(c.get("page_number", 1)),
                        evidence_id=c.get("evidence_id", ""),
                    )
                    for c in generation.citations
                ]
                extracted_claims = extract_atomic_claims(
                    generation.answer,
                    citations=claim_cits,
                    qa_id=f"SHADOW_{request_id[:8]}",
                )
                if not extracted_claims:
                    shadow_res = shadow_verifier.aggregate_answer([], question=question)
                else:
                    shadow_res = shadow_verifier.verify_claims(extracted_claims, ev_items, question=question)

                verification_payload = {
                    "mode": "shadow",
                    "status": "RUN_SHADOW",
                    "aggregate_status": shadow_res.aggregate_status.value,
                    "canonical_verdict": shadow_res.canonical_answer_verdict,
                    "total_claims": shadow_res.total_claims,
                    "supported_count": shadow_res.supported_count,
                    "contradicted_count": shadow_res.contradicted_count,
                    "insufficient_count": shadow_res.insufficient_count,
                    "out_of_scope_count": shadow_res.out_of_scope_count,
                    "claim_results": [
                        {
                            "claim_id": cr.claim_id,
                            "status": cr.status.value,
                            "reason_codes": cr.reason_codes,
                            "supporting_facts": cr.supporting_fact_ids,
                            "conflicting_facts": cr.conflicting_fact_ids,
                            "explanation": cr.explanation,
                        }
                        for cr in shadow_res.claim_results
                    ],
                    "explanation": shadow_res.summary_explanation,
                    "latency_ms": shadow_res.total_execution_ms,
                }
            except Exception as e:
                verification_payload = {"mode": "shadow", "status": "ERROR", "error": str(e)}

        return {
            "request_id": request_id,
            "answer": generation.answer,
            "pipeline": self.RETRIEVAL_POLICY,
            "generation_model": provider_model,
            "corpus_version": self.CORPUS_VERSION,
            "verification": verification_payload,
            "correction": {"mode": "off", "status": "NOT_RUN"},
            "citations": citations,
            "retrieved_references": retrieved_references,
            "timing_ms": {"retrieval": round(retrieval_ms, 2), "reranking": None, "generation": round(generation_ms, 2), "total": round(total_ms, 2)},
            "trace": {
                "candidate_page_ids": [str(row["page_id"]) for row in candidates[:100]],
                "top_ranked_page_ids": [str(row["page_id"]) for row in reranked[:5]],
                "selected_evidence_ids": [item.evidence_id for item in context.evidence],
                "context_chars": len(context.text), "grounding": grounding,
                "generation_parse_error": generation.parse_error,
                "raw_generation": raw_response, "context": context.text,
            },
            # Top-level canonical status contract
            "abstained": generation.abstained,
            "abstention_type": abstention_type,
            "guard_verdict": guard_verdict,
            "guard_reason": guard_reason,
            "model_generated_answer": model_generated_answer,
            "final_status": final_status,
        }
