"""Targeted Correction Executor for Stage 3 Sprint A Correctness Gate.

Coordinates the bounded iterative evidence-targeted correction loop:
1. Validates retrieval budget (respects budget=0, rejects negative budgets).
2. Identifies missing slots and generates an interpretable CorrectionPlan.
3. Retrieves targeted Page/Region evidence units via PageRegionRetrievalAdapter.
4. Validates provenance and exact canonical document identity (never fuzzy/substring).
5. Only creates verified EvidenceRelation records when supported by authentic structural
   metadata (table_id, block_id, parent_id, or layout parser structure). Candidate links
   without structural verification remain verified=False and cannot be consumed by the verifier.
6. Enforces strict retry boundaries (budget, no-new-evidence, contradiction stops).
7. Emits a transparent before/after audit trace.
"""

from __future__ import annotations

import copy
from pathlib import Path
import time
from typing import Optional, Union

from viirr_ontology.schema.claim import EvidenceCitation, TechnicalClaim
from viirr_ontology.schema.evidence import EvidenceItem, EvidenceRelation, EvidenceSet
from viirr_ontology.verifier.models import ClaimVerificationStatus, VerificationResult
from viirr_ontology.verifier.ontology_verifier import OntologyConstraintVerifier

from .models import CorrectionAttempt, CorrectionPlan, CorrectionResult
from .planner import EvidenceCorrectionPlanner
from .provenance import (
    DocumentIdentityRegistry,
    EvidenceProvenanceValidator,
    ProvenanceValidationStatus,
    StructuralRelationVerifier,
    TrustedSourceStructureRegistry,
)
from .retrieval_adapter import PageRegionRetrievalAdapter


class TargetedCorrectionExecutor:
    """Executes bounded, evidence-targeted corrective retrieval and reverification."""

    def __init__(
        self,
        verifier: Optional[OntologyConstraintVerifier] = None,
        retrieval_adapter: Optional[PageRegionRetrievalAdapter] = None,
        retrieval_backend: Optional[Any] = None,
        planner: Optional[EvidenceCorrectionPlanner] = None,
        identity_registry: Optional[DocumentIdentityRegistry] = None,
        structural_verifier: Optional[StructuralRelationVerifier] = None,
        provenance_validator: Optional[EvidenceProvenanceValidator] = None,
        trusted_structure_registry: Optional[TrustedSourceStructureRegistry] = None,
        require_index_verification: Optional[bool] = None,
        require_content_verification: Optional[bool] = None,
        synthetic_mode: bool = False,
        corpus_index_path: Optional[Union[str, Path]] = None,
        max_attempts: int = 2,
    ):
        self.verifier = verifier or OntologyConstraintVerifier()
        if retrieval_adapter is not None:
            self.adapter = retrieval_adapter
        elif retrieval_backend is not None:
            self.adapter = PageRegionRetrievalAdapter(backend=retrieval_backend)
        else:
            self.adapter = PageRegionRetrievalAdapter()
        self.planner = planner or EvidenceCorrectionPlanner()
        self.identity_registry = identity_registry or DocumentIdentityRegistry()
        self.synthetic_mode = synthetic_mode
        self.max_attempts = max_attempts

        # Determine index & content verification policy:
        # 1. If explicitly passed, honor user specification.
        # 2. If synthetic_mode, default to False.
        # 3. For RealRetrievalBackend, default to True (Phase A2 & Phase B).
        # 4. Otherwise (mock backend), default to False.
        if require_index_verification is not None:
            self.require_index_verification = bool(require_index_verification)
        elif synthetic_mode:
            self.require_index_verification = False
        elif self.adapter.backend is not None and not self.adapter.backend.is_mock:
            self.require_index_verification = True
        else:
            self.require_index_verification = False

        if require_content_verification is not None:
            self.require_content_verification = bool(require_content_verification)
        elif synthetic_mode:
            self.require_content_verification = False
        elif self.adapter.backend is not None and not self.adapter.backend.is_mock:
            self.require_content_verification = True
        else:
            self.require_content_verification = False

        self.trusted_structure_registry = (
            trusted_structure_registry
            or (structural_verifier.trusted_registry if structural_verifier else TrustedSourceStructureRegistry())
        )
        self.structural_verifier = structural_verifier or StructuralRelationVerifier(
            trusted_structure_registry=self.trusted_structure_registry,
            identity_registry=self.identity_registry,
        )
        self.provenance_validator = provenance_validator or EvidenceProvenanceValidator(
            identity_registry=self.identity_registry
        )

        # In live mode with index verification required, load source index if not already populated
        if self.require_index_verification and not self.provenance_validator.trusted_index:
            candidate_paths = [
                Path(corpus_index_path) if corpus_index_path else None,
                Path("outputs/V4_EXPERIMENT/index/evidence_units_v4.jsonl"),
                Path("data/pages.jsonl"),
            ]
            for p in candidate_paths:
                if p and p.exists():
                    self.provenance_validator.load_trusted_index_from_file(p)
                    self.trusted_structure_registry.load_from_evidence_units(p)
                    break

    def register_trusted_table_unit(self, doc_id: str, page_number: int, evidence_id: str, table_id: str) -> None:
        """Register an authoritative table structure record into the executor's trusted registry."""
        self.structural_verifier.trusted_registry.register_table_unit(doc_id, page_number, evidence_id, table_id)

    def register_trusted_block_unit(self, doc_id: str, page_number: int, evidence_id: str, block_id: str) -> None:
        """Register an authoritative block structure record into the executor's trusted registry."""
        self.structural_verifier.trusted_registry.register_block_unit(doc_id, page_number, evidence_id, block_id)

    def register_trusted_relation(self, source_id: str, target_id: str, relation_type: str) -> None:
        """Register an explicit authoritative parser relation into the executor's trusted registry."""
        self.structural_verifier.trusted_registry.register_relation(source_id, target_id, relation_type)

    def _create_plan(
        self,
        claim: TechnicalClaim,
        verification_result: VerificationResult,
        original_query: str,
        evidence_set: EvidenceSet,
        retrieval_budget: int,
    ) -> CorrectionPlan:
        return self.planner.create_plan(
            claim=claim,
            verification_result=verification_result,
            original_query=original_query,
            evidence_set=evidence_set,
            retrieval_budget=retrieval_budget,
        )

    def _get_query_for_attempt(self, claim: TechnicalClaim, plan: CorrectionPlan, attempt_idx: int) -> str:
        """Formulate targeted query directed at missing information slots."""
        query_idx = min(attempt_idx - 1, len(plan.search_queries) - 1)
        return plan.search_queries[query_idx]

    def execute_correction(
        self,
        claim: TechnicalClaim,
        evidence_set: EvidenceSet,
        initial_result: Optional[VerificationResult] = None,
        original_query: str = "",
        budget: int = 2,
    ) -> CorrectionResult:
        """Alias for correct_claim."""
        return self.correct_claim(
            claim=claim,
            evidence_set=evidence_set,
            initial_result=initial_result,
            original_query=original_query,
            budget=budget,
        )

    def correct_claim(
        self,
        claim: TechnicalClaim,
        evidence_set: EvidenceSet,
        initial_result: Optional[VerificationResult] = None,
        original_query: str = "",
        budget: int = 2,
    ) -> CorrectionResult:
        """Run bounded corrective retrieval on an unverified or insufficient claim."""
        start_time = time.perf_counter()

        # Validation Rule: Budget must be non-negative
        if budget < 0:
            raise ValueError(f"retrieval_budget must be non-negative, got {budget}")

        # Step 0: Initial verification if not provided
        if initial_result is None:
            initial_result = self.verifier.verify_single_claim(claim, evidence_set)

        initial_status_str = initial_result.status.value
        initial_reason_codes = list(initial_result.reason_codes)

        # Rule: If budget is 0, perform exactly zero retrieval attempts and return immediately
        if budget == 0:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return CorrectionResult(
                target_claim_id=claim.claim_id,
                initial_status=initial_status_str,
                final_status=initial_status_str,
                initial_reason_codes=initial_reason_codes,
                final_reason_codes=initial_reason_codes,
                attempts_made=0,
                max_attempts=0,
                stop_reason="BUDGET_EXHAUSTED",
                attempts=[],
                final_evidence_set=evidence_set,
                final_verification_result=initial_result,
                newly_retrieved_evidence_ids=[],
                corrected_missing_slots=[],
                retrieval_calls=0,
                total_candidates_inspected=0,
                total_candidates_admitted=0,
                verifier_calls=1,
                total_latency_ms=elapsed_ms,
            )

        # If not INSUFFICIENT, no targeted correction needed
        if initial_result.status != ClaimVerificationStatus.INSUFFICIENT:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return CorrectionResult(
                target_claim_id=claim.claim_id,
                initial_status=initial_status_str,
                final_status=initial_status_str,
                initial_reason_codes=initial_reason_codes,
                final_reason_codes=initial_reason_codes,
                attempts_made=0,
                max_attempts=budget,
                stop_reason="NO_CORRECTION_NEEDED",
                attempts=[],
                final_evidence_set=evidence_set,
                final_verification_result=initial_result,
                newly_retrieved_evidence_ids=[],
                corrected_missing_slots=[],
                retrieval_calls=0,
                total_candidates_inspected=0,
                total_candidates_admitted=0,
                verifier_calls=1,
                total_latency_ms=elapsed_ms,
            )

        # Phase A2: Fail-closed if index verification is required but trusted index is unavailable
        if self.require_index_verification and not self.provenance_validator.trusted_index:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return CorrectionResult(
                target_claim_id=claim.claim_id,
                initial_status=initial_status_str,
                final_status=initial_status_str,
                initial_reason_codes=initial_reason_codes,
                final_reason_codes=list(set(initial_reason_codes + ["TRUSTED_SOURCE_INDEX_UNAVAILABLE"])),
                attempts_made=0,
                max_attempts=budget,
                stop_reason="TRUSTED_SOURCE_INDEX_UNAVAILABLE",
                attempts=[],
                final_evidence_set=evidence_set,
                final_verification_result=initial_result,
                newly_retrieved_evidence_ids=[],
                corrected_missing_slots=[],
                retrieval_calls=0,
                total_candidates_inspected=0,
                total_candidates_admitted=0,
                verifier_calls=1,
                total_latency_ms=elapsed_ms,
            )

        # Fail-closed if backend is a real retriever but not operational
        if self.adapter.backend is not None and not self.adapter.backend.is_mock and not self.adapter.backend.is_available:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            backend_status = getattr(self.adapter.backend, "status", "UNAVAILABLE")
            return CorrectionResult(
                target_claim_id=claim.claim_id,
                initial_status=initial_status_str,
                final_status=initial_status_str,
                initial_reason_codes=initial_reason_codes,
                final_reason_codes=list(set(initial_reason_codes + [f"RETRIEVAL_BACKEND_UNAVAILABLE:{backend_status}"])),
                attempts_made=0,
                max_attempts=budget,
                stop_reason=f"RETRIEVAL_BACKEND_UNAVAILABLE:{backend_status}",
                attempts=[],
                final_evidence_set=evidence_set,
                final_verification_result=initial_result,
                newly_retrieved_evidence_ids=[],
                corrected_missing_slots=[],
                retrieval_calls=0,
                total_candidates_inspected=0,
                total_candidates_admitted=0,
                verifier_calls=1,
                total_latency_ms=elapsed_ms,
            )

        # Step 1: Formulate correction plan
        plan = self._create_plan(
            claim=claim,
            verification_result=initial_result,
            original_query=original_query,
            evidence_set=evidence_set,
            retrieval_budget=budget,
        )

        current_evidence_set = copy.deepcopy(evidence_set)
        current_claim = copy.deepcopy(claim)
        current_result = initial_result

        attempts: list[CorrectionAttempt] = []
        newly_retrieved_ids: list[str] = []
        stop_reason = "BUDGET_EXHAUSTED"

        # Step 2: Bounded retrieval loop (strictly respects plan.max_attempts)
        for attempt_idx in range(1, plan.max_attempts + 1):
            attempt_start = time.perf_counter()
            query = self._get_query_for_attempt(claim, plan, attempt_idx)

            # Retrieval call
            retrieved_items = self.adapter.search_regions(
                query=query,
                top_k=3,
                filter_doc_id=plan.document_scope,
            )

            # Filter already existing evidence items (deduplication)
            existing_ids = {it.evidence_id for it in current_evidence_set.evidence_items}
            new_items = [it for it in retrieved_items if it.evidence_id not in existing_ids]

            if not new_items:
                attempt_elapsed = (time.perf_counter() - attempt_start) * 1000.0
                attempts.append(CorrectionAttempt(
                    attempt_number=attempt_idx,
                    query_used=query,
                    retrieved_evidence_ids=[],
                    provenance_valid=True,
                    verification_verdict=current_result.status.value,
                    reason_codes=list(current_result.reason_codes),
                    missing_slots_remaining=list(current_result.missing_evidence_slots),
                    candidates_inspected=len(retrieved_items),
                    candidates_admitted=0,
                    latency_ms=attempt_elapsed,
                ))
                stop_reason = "NO_NEW_EVIDENCE"
                break

            # Exact Provenance Validation per candidate (exact document scope, no substring matching)
            admitted_items: list[EvidenceItem] = []
            rejected_candidate_details: list[tuple[str, str]] = []
            req_version = getattr(claim, "document_version", None) or getattr(plan, "document_version", None)

            for it in new_items:
                status, reason = self.provenance_validator.validate_provenance(
                    item=it,
                    required_document_scope=plan.document_scope,
                    required_version=req_version,
                    require_index_verification=self.require_index_verification,
                    require_content_verification=self.require_content_verification,
                )
                if status != ProvenanceValidationStatus.UNVERIFIED:
                    admitted_items.append(it)
                else:
                    rejected_candidate_details.append((it.evidence_id, reason))

            if not admitted_items:
                attempt_elapsed = (time.perf_counter() - attempt_start) * 1000.0
                attempts.append(CorrectionAttempt(
                    attempt_number=attempt_idx,
                    query_used=query,
                    retrieved_evidence_ids=[it.evidence_id for it in new_items],
                    provenance_valid=False,
                    verification_verdict=current_result.status.value,
                    reason_codes=list(current_result.reason_codes) + ["PROVENANCE_INVALID"],
                    missing_slots_remaining=list(current_result.missing_evidence_slots),
                    candidates_inspected=len(retrieved_items),
                    candidates_admitted=0,
                    latency_ms=attempt_elapsed,
                ))
                stop_reason = "UNRESOLVED_DOCUMENT_SCOPE_CONFLICT"
                continue

            # Reassemble evidence set: append admitted items and only create verified relations if structurally proven
            for it in admitted_items:
                current_evidence_set.evidence_items.append(it)
                newly_retrieved_ids.append(it.evidence_id)

                # Connect with existing candidate items
                for ex in list(current_evidence_set.evidence_items):
                    if ex.evidence_id == it.evidence_id:
                        continue
                    if ex.doc_id != it.doc_id:
                        continue

                    # Check if an authoritative relation type is registered between these items
                    registered_type = self.trusted_structure_registry.get_relation_type(
                        ex.evidence_id, it.evidence_id
                    )
                    if registered_type is not None:
                        rel_type = registered_type
                        source_id = ex.evidence_id
                        target_id = it.evidence_id
                    elif (
                        "table_header" in plan.missing_slots
                        or "parameter" in plan.missing_slots
                        or "header" in it.evidence_id.lower()
                    ):
                        rel_type = "table_row_to_header"
                        target_id = it.evidence_id
                        source_id = ex.evidence_id
                    elif (
                        "unit" in plan.missing_slots
                        or "table_note" in plan.missing_slots
                        or "unit" in it.evidence_id.lower()
                    ):
                        rel_type = "table_to_note"
                        target_id = it.evidence_id
                        source_id = ex.evidence_id
                    elif (
                        "conditions" in plan.missing_slots
                        or "applicability_condition" in plan.missing_slots
                        or "cond" in it.evidence_id.lower()
                    ):
                        rel_type = "clause_to_condition"
                        target_id = it.evidence_id
                        source_id = ex.evidence_id
                    elif "version" in plan.missing_slots or "ver" in it.evidence_id.lower():
                        rel_type = "evidence_to_version"
                        target_id = it.evidence_id
                        source_id = ex.evidence_id
                    else:
                        rel_type = "parent_to_child"
                        target_id = it.evidence_id
                        source_id = ex.evidence_id


                    if rel_type:
                        # CRITICAL: Verify with StructuralRelationVerifier!
                        is_verified, prov_source = self.structural_verifier.verify_relation(
                            source_item=ex,
                            target_item=it,
                            candidate_relation_type=rel_type,
                        )

                        if is_verified:
                            # Genuine structural linkage established from source metadata / parser
                            rel = EvidenceRelation(
                                source_id=source_id,
                                target_id=target_id,
                                relation_type=rel_type,
                                verified=True,
                                provenance_source=prov_source,
                            )
                            current_evidence_set.evidence_relations.append(rel)
                        else:
                            # Retain as unverified candidate link; NEVER mark verified=True
                            # Multi-region synthesis strictly ignores unverified relations!
                            rel = EvidenceRelation(
                                source_id=source_id,
                                target_id=target_id,
                                relation_type=rel_type,
                                verified=False,
                                confidence=0.5,
                                provenance_source="unverified_heuristic_candidate",
                            )
                            current_evidence_set.evidence_relations.append(rel)

            # Update reverification claim citations/IDs so newly admitted items are evaluated
            updated_ids = list(current_claim.evidence_ids)
            for it in admitted_items:
                if it.evidence_id not in updated_ids:
                    updated_ids.append(it.evidence_id)
            current_claim.evidence_ids = updated_ids

            if current_claim.evidence_citations:
                updated_citations = list(current_claim.evidence_citations)
                for it in admitted_items:
                    cit = EvidenceCitation(
                        doc_id=it.doc_id,
                        page_number=it.page_number,
                        evidence_id=it.evidence_id,
                    )
                    if cit not in updated_citations:
                        updated_citations.append(cit)
                current_claim.evidence_citations = updated_citations

            # Reverify with S2.4 Verifier
            current_result = self.verifier.verify_single_claim(current_claim, current_evidence_set)

            attempt_elapsed = (time.perf_counter() - attempt_start) * 1000.0
            attempts.append(CorrectionAttempt(
                attempt_number=attempt_idx,
                query_used=query,
                retrieved_evidence_ids=[it.evidence_id for it in admitted_items],
                provenance_valid=True,
                verification_verdict=current_result.status.value,
                reason_codes=list(current_result.reason_codes),
                missing_slots_remaining=list(current_result.missing_evidence_slots),
                candidates_inspected=len(retrieved_items),
                candidates_admitted=len(admitted_items),
                latency_ms=attempt_elapsed,
            ))

            # Stop conditions based on verifier outcome
            if current_result.status == ClaimVerificationStatus.SUPPORTED:
                stop_reason = "SUPPORTED_REACHED"
                break
            elif current_result.status == ClaimVerificationStatus.CONTRADICTED:
                # Contradiction discovered: do not conceal or force support
                stop_reason = "CONTRADICTION_DISCOVERED"
                break

        # Compute corrected slots
        initial_missing_set = set(initial_result.missing_evidence_slots)
        if current_result.status == ClaimVerificationStatus.SUPPORTED:
            corrected_slots = sorted(list(initial_missing_set))
        else:
            final_missing_set = set(current_result.missing_evidence_slots)
            corrected_slots = sorted(list(initial_missing_set - final_missing_set))

        total_elapsed = (time.perf_counter() - start_time) * 1000.0

        return CorrectionResult(
            target_claim_id=claim.claim_id,
            initial_status=initial_status_str,
            final_status=current_result.status.value,
            initial_reason_codes=initial_reason_codes,
            final_reason_codes=list(current_result.reason_codes),
            attempts_made=len(attempts),
            max_attempts=plan.max_attempts,
            stop_reason=stop_reason,
            attempts=attempts,
            final_evidence_set=current_evidence_set,
            final_verification_result=current_result,
            newly_retrieved_evidence_ids=newly_retrieved_ids,
            corrected_missing_slots=corrected_slots,
            retrieval_calls=len(attempts),
            total_candidates_inspected=sum(a.candidates_inspected for a in attempts),
            total_candidates_admitted=sum(a.candidates_admitted for a in attempts),
            verifier_calls=1 + len(attempts),
            total_latency_ms=total_elapsed,
        )


class UntargetedCorrectionExecutor(TargetedCorrectionExecutor):
    """Fair matched-budget untargeted retrieval executor for Phase B comparative evaluation.

    Uses identical candidate pool, scoring method, provenance validation, structural checks,
    budget (number of attempts and top_k), and stop policies.
    Crucial difference: queries use generic claim text rather than missing-slot-targeted formulation.
    """

    def _create_plan(
        self,
        claim: TechnicalClaim,
        verification_result: VerificationResult,
        original_query: str,
        evidence_set: EvidenceSet,
        retrieval_budget: int,
    ) -> CorrectionPlan:
        generic_queries = [claim.claim_text]
        parts = [p for p in [claim.subject, claim.parameter] if p]
        if parts:
            generic_queries.append(" ".join(parts))
        return CorrectionPlan(
            correction_goal="UNTARGETED_GENERIC_RETRIEVAL",
            target_claim_id=claim.claim_id,
            missing_slots=[],
            search_queries=generic_queries,
            document_scope=claim.document_scope,
            max_attempts=retrieval_budget,
            reason_for_correction="Untargeted generic retrieval without missing-slot planning",
        )

    def _get_query_for_attempt(self, claim: TechnicalClaim, plan: CorrectionPlan, attempt_idx: int) -> str:
        if attempt_idx == 1:
            return claim.claim_text
        # Fallback generic query using subject/parameter without targeting missing slot
        parts = [p for p in [claim.subject, claim.parameter] if p]
        return " ".join(parts) if parts else claim.claim_text
