"""Main Ontology-Constrained Claim Verifier for Stage 2.4.

Provides the standalone `OntologyConstraintVerifier` class.
Operates deterministically without LLM calls or graph databases.
Evaluates structured TechnicalClaims against EvidenceSet and ontology constraints,
supporting independent shadow mode execution alongside P5.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from viirr_ontology.domain.constraint_registry import ConstraintRegistry
from viirr_ontology.domain.ontology_loader import HydraulicOntology
from viirr_ontology.schema.claim import ClaimPolarity, TechnicalClaim
from viirr_ontology.schema.evidence import EvidenceItem, EvidenceSet
from viirr_ontology.verifier.claim_constraints import ClaimConstraintChecker
from viirr_ontology.verifier.evidence_matcher import EvidenceMatcher, strip_accents_lower
from viirr_ontology.verifier.models import (
    AnswerVerificationResult,
    ClaimVerificationStatus,
    ReasonCode,
    VerificationResult,
)
from viirr_ontology.verifier.verdict_aggregation import VerdictAggregator


class OntologyConstraintVerifier:
    """Standalone deterministic ontology-constrained claim verifier.

    Performs 3-way claim verification:
    - SUPPORTED: Genuinely evidenced by matched records under active verified constraints.
    - CONTRADICTED: Demonstrated violation of active verified constraint or explicit incompatible evidence.
    - INSUFFICIENT: Incomplete slots, missing evidence, unverified rules, or ambiguous parameter.
    """

    def __init__(
        self,
        ontology: Optional[HydraulicOntology] = None,
        constraint_registry: Optional[ConstraintRegistry] = None,
    ) -> None:
        self.ontology = ontology or HydraulicOntology.load()
        self.registry = constraint_registry or ConstraintRegistry.load_from_file()
        self.matcher = EvidenceMatcher(ontology=self.ontology)
        self.constraint_checker = ClaimConstraintChecker(constraint_registry=self.registry)
        self.aggregator = VerdictAggregator()

    def verify_single_claim(
        self, claim: TechnicalClaim, evidence_set: Optional[EvidenceSet] = None
    ) -> VerificationResult:
        """Verify an individual TechnicalClaim against available evidence and ontology rules."""
        # 1. Structural Claim Completeness Check
        if not claim.claim_id or (not claim.claim_text.strip() and not claim.subject.strip() and not claim.parameter.strip()):
            return VerificationResult(
                claim_id=claim.claim_id or "MALFORMED_CLAIM",
                status=ClaimVerificationStatus.INSUFFICIENT,
                reason_codes=[ReasonCode.INCOMPLETE_CLAIM_EXTRACTION.value],
                explanation="Claim is malformed or lacks both text and structured fields",
                missing_evidence_slots=["claim_text", "subject", "parameter"],
            )

        # 1.1 Out-of-Scope Domain & Boundary Check
        is_out_of_scope = False
        oos_explanation = ""
        if getattr(claim, "extraction_status", "") == "OUT_OF_SCOPE":
            is_out_of_scope = True
            oos_explanation = "Claim extraction status is OUT_OF_SCOPE."
        elif (claim.parameter or "").upper() in ["OUT_OF_SCOPE", "NON_ONTOLOGY", "NGOAI_PHAM_VI"]:
            is_out_of_scope = True
            oos_explanation = f"Claim parameter '{claim.parameter}' is designated OUT_OF_SCOPE."
        else:
            norm_subj = strip_accents_lower(claim.subject or "")
            norm_param = strip_accents_lower(claim.parameter or "")
            norm_text = strip_accents_lower(claim.claim_text or "")
            out_of_scope_keywords = [
                "co2", "khi quyen", "luc day", "may bay", "dong co", "phan luc", "dan so", "mat do dan so",
                "nang suat lua", "cay trong", "grdp", "gdp", "kinh te xa hoi", "dien tich tu nhien",
                "khi nha kinh", "o nhiem khong khi"
            ]
            for kw in out_of_scope_keywords:
                if kw in norm_param or kw in norm_subj or (kw in norm_text and not any(h in norm_text for h in ["ho ", "thuy dien", "muc nuoc", "xa", "dung tich", "dap", "cong "])):
                    is_out_of_scope = True
                    oos_explanation = f"Claim topic '{kw}' is outside the domain/competency scope of the hydraulic ontology."
                    break

        if is_out_of_scope:
            return VerificationResult(
                claim_id=claim.claim_id,
                status=ClaimVerificationStatus.OUT_OF_SCOPE,
                reason_codes=[ReasonCode.CLAIM_OUT_OF_SCOPE.value],
                explanation=oos_explanation or "Claim is outside the hydraulic engineering ontology scope.",
                applicability_scope={"subject": claim.subject, "parameter": claim.parameter},
                verifier_metadata={"verification_tier": "OUT_OF_SCOPE"},
            )

        # 2. Domain Constraint Evaluation
        (
            checked_constraints,
            violated_constraints,
            unverified_constraints,
            constraint_rcs,
            constraint_exps,
        ) = self.constraint_checker.check_constraints_for_claim(claim)

        # If an active constraint is directly violated, this is an immediate CONTRADICTION
        if violated_constraints:
            return VerificationResult(
                claim_id=claim.claim_id,
                status=ClaimVerificationStatus.CONTRADICTED,
                checked_constraints=checked_constraints,
                violated_constraints=violated_constraints,
                missing_constraints=unverified_constraints,
                reason_codes=[rc.value for rc in constraint_rcs],
                explanation="; ".join(constraint_exps),
                applicability_scope={"subject": claim.subject, "parameter": claim.parameter},
                verifier_metadata={"verification_tier": "DOMAIN_CONSTRAINT_VIOLATION"},
            )

        # 3. Evidence Presence Check
        if evidence_set is None or len(evidence_set.evidence_items) == 0:
            ev_reasons = [rc.value for rc in constraint_rcs]
            if ReasonCode.PROVENANCE_MISSING.value not in ev_reasons:
                ev_reasons.append(ReasonCode.PROVENANCE_MISSING.value)
            ev_exp = "; ".join(constraint_exps) if constraint_exps else "No evidence items provided to verify claim"
            return VerificationResult(
                claim_id=claim.claim_id,
                status=ClaimVerificationStatus.INSUFFICIENT,
                checked_constraints=checked_constraints,
                missing_constraints=unverified_constraints,
                missing_evidence_slots=["evidence"],
                reason_codes=ev_reasons,
                explanation=ev_exp,
                applicability_scope={"subject": claim.subject, "parameter": claim.parameter},
                verifier_metadata={"verification_tier": "NO_EVIDENCE_PROVIDED"},
            )

        # 4. Resolve Candidate Evidence Items
        candidate_items: list[EvidenceItem] = []
        invalid_references: list[dict[str, Any]] = []
        for citation in claim.evidence_citations:
            item = evidence_set.get_item_by_citation(*citation.citation_key())
            if item is None:
                invalid_references.append({
                    "citation_key": list(citation.citation_key()),
                    "reason": "full_citation_identity_not_found",
                })
            else:
                candidate_items.append(item)

        for evidence_id in claim.evidence_ids:
            item = evidence_set.get_item(evidence_id)
            if item is None:
                invalid_references.append({
                    "evidence_id": evidence_id,
                    "reason": "evidence_id_not_found",
                })
            else:
                candidate_items.append(item)

        if not claim.evidence_ids and not claim.evidence_citations:
            candidate_items = list(evidence_set.evidence_items)

        # Preserve original item identity while de-duplicating references.
        candidate_items = list({item.citation_key(): item for item in candidate_items}.values())
        if not candidate_items:
            return VerificationResult(
                claim_id=claim.claim_id,
                status=ClaimVerificationStatus.INSUFFICIENT,
                checked_constraints=checked_constraints,
                missing_constraints=unverified_constraints,
                missing_evidence_slots=["explicit_citation"],
                reason_codes=[
                    ReasonCode.PROVENANCE_INVALID.value,
                    ReasonCode.CITATION_IDENTITY_MISMATCH.value,
                ],
                explanation="No explicitly cited evidence reference resolves to a complete citation identity",
                verifier_metadata={"invalid_references": invalid_references},
            )

        version_tags = {
            (item.document_number or item.document_version or "").strip()
            for item in candidate_items
            if (item.document_number or item.document_version or "").strip()
        }
        # If candidate evidence spans multiple documents but claim subject matches a specific document, scope to it
        if not claim.document_scope and len(version_tags) > 1 and claim.subject:
            subject_matched = [it for it in candidate_items if claim.subject.lower() in it.text.lower()]
            if subject_matched:
                sub_tags = {
                    (it.document_number or it.document_version or "").strip()
                    for it in subject_matched
                    if (it.document_number or it.document_version or "").strip()
                }
                if len(sub_tags) == 1:
                    candidate_items = subject_matched
                    version_tags = sub_tags

        if not claim.document_scope and len(version_tags) > 1:
            return VerificationResult(
                claim_id=claim.claim_id,
                status=ClaimVerificationStatus.INSUFFICIENT,
                checked_constraints=checked_constraints,
                missing_constraints=unverified_constraints,
                missing_evidence_slots=["document_scope"],
                reason_codes=[ReasonCode.DOCUMENT_VERSION_CONFLICT.value],
                explanation=(
                    "Candidate evidence spans multiple document versions/numbers without a claim-specific "
                    f"document scope: {sorted(version_tags)}"
                ),
                provenance_trace=[{
                    "evidence_id": item.evidence_id,
                    "doc_id": item.doc_id,
                    "page_number": item.page_number,
                    "citation_key": list(item.citation_key()),
                    "document_number": item.document_number,
                    "document_version": item.document_version,
                } for item in candidate_items],
                verifier_metadata={"candidate_document_versions": sorted(version_tags)},
            )

        # 5. Evaluate Candidate Items
        supporting_ids: list[str] = []
        conflicting_ids: list[str] = []
        collected_reasons: list[str] = [rc.value for rc in constraint_rcs]
        collected_explanations: list[str] = list(constraint_exps)
        collected_trace: list[dict[str, Any]] = []
        collected_missing_slots: set[str] = set()

        for item in candidate_items:
            assessment = self.matcher.compare_claim_to_evidence_item(claim, item)
            collected_trace.extend(assessment.evidence_trace)

            if assessment.matched:
                supporting_ids.extend(assessment.supporting_evidence_ids)
                collected_reasons.extend(rc.value for rc in assessment.reason_codes)
                collected_explanations.extend(assessment.explanations)
            elif assessment.is_contradiction:
                supporting_ids.extend(assessment.supporting_evidence_ids)
                conflicting_ids.extend(assessment.conflicting_evidence_ids)
                collected_reasons.extend(rc.value for rc in assessment.reason_codes)
                collected_explanations.extend(assessment.explanations)
            else:
                collected_missing_slots.update(assessment.missing_slots)
                collected_reasons.extend(rc.value for rc in assessment.reason_codes)
                collected_explanations.extend(assessment.explanations)

        # 6. Multi-Region Complementary Synthesis Check
        # If not supported by a single item, and we have multiple candidates, try synthesizing
        if not supporting_ids and not conflicting_ids and len(candidate_items) > 1:
            multi_assessment = self.matcher.synthesize_multi_region_evidence(
                claim, candidate_items, list(evidence_set.evidence_relations)
            )
            if multi_assessment.matched:
                supporting_ids.extend(multi_assessment.supporting_evidence_ids)
                collected_reasons.extend(rc.value for rc in multi_assessment.reason_codes)
                collected_explanations.extend(multi_assessment.explanations)
                collected_trace.extend(multi_assessment.evidence_trace)
            elif multi_assessment.is_contradiction:
                conflicting_ids.extend(multi_assessment.conflicting_evidence_ids)
                collected_reasons.extend(rc.value for rc in multi_assessment.reason_codes)
                collected_explanations.extend(multi_assessment.explanations)
            else:
                collected_missing_slots.update(multi_assessment.missing_slots)
                collected_reasons.extend(rc.value for rc in multi_assessment.reason_codes)
                collected_explanations.extend(multi_assessment.explanations)

        # Always record citation/provenance error reason codes and missing slots
        # whenever any explicit reference is invalid, so valid evidence never silently hides invalid references.
        if invalid_references:
            collected_missing_slots.add("explicit_citation")
            if ReasonCode.PROVENANCE_INVALID.value not in collected_reasons:
                collected_reasons.append(ReasonCode.PROVENANCE_INVALID.value)
            if ReasonCode.CITATION_IDENTITY_MISMATCH.value not in collected_reasons:
                collected_reasons.append(ReasonCode.CITATION_IDENTITY_MISMATCH.value)
            collected_explanations.append(
                f"One or more explicit citations could not be resolved: {invalid_references}"
            )

        # 7. Final 3-Way Status Assignment
        # Explicit Conservative Verdict Policy:
        # - When a factual contradiction is demonstrated by valid evidence (conflicting_ids),
        #   verdict is CONTRADICTED for factual safety, while invalid citations are strictly preserved
        #   in reason_codes, missing_evidence_slots, and explanation.
        # - When there is no factual contradiction but invalid citations exist, verdict is INSUFFICIENT
        #   (support cannot be claimed when explicit citations are unresolvable).
        # - When supporting evidence exists without conflicts or invalid citations, verdict is SUPPORTED.
        # - Otherwise, verdict is INSUFFICIENT.
        if conflicting_ids:
            status = ClaimVerificationStatus.CONTRADICTED
            explanation = "; ".join(dict.fromkeys(collected_explanations))
        elif invalid_references:
            status = ClaimVerificationStatus.INSUFFICIENT
            explanation = "; ".join(dict.fromkeys(collected_explanations))
        elif supporting_ids:
            status = ClaimVerificationStatus.SUPPORTED
            explanation = "; ".join(dict.fromkeys(collected_explanations))
        else:
            status = ClaimVerificationStatus.INSUFFICIENT
            missing_list = sorted(list(collected_missing_slots)) or ["supporting_evidence"]
            collected_missing_slots = set(missing_list)
            explanation = "; ".join(dict.fromkeys(collected_explanations)) or "Insufficient evidence to support or contradict claim"

        return VerificationResult(
            claim_id=claim.claim_id,
            status=status,
            supporting_evidence_ids=list(dict.fromkeys(supporting_ids)),
            conflicting_evidence_ids=list(dict.fromkeys(conflicting_ids)),
            checked_constraints=checked_constraints,
            violated_constraints=violated_constraints,
            missing_constraints=unverified_constraints,
            missing_evidence_slots=sorted(list(collected_missing_slots)),
            applicability_scope={"subject": claim.subject, "parameter": claim.parameter},
            reason_codes=list(dict.fromkeys(collected_reasons)),
            explanation=explanation,
            provenance_trace=collected_trace,
            verifier_metadata={
                "candidate_evidence_count": len(candidate_items),
                "total_evidence_set_count": len(evidence_set.evidence_items),
                "invalid_references": invalid_references,
            },
        )

    def verify_answer(
        self,
        claims: list[TechnicalClaim],
        evidence_set: Optional[EvidenceSet] = None,
        p5_output: Optional[dict[str, Any]] = None,
    ) -> AnswerVerificationResult:
        """Verify all structured claims of an answer and produce an aggregated decision.

        Operates in independent shadow mode: records p5_comparison if p5_output is provided,
        without requiring P5 PASS to execute.
        """
        start_time = time.perf_counter()

        claim_results: list[VerificationResult] = []
        for claim in claims:
            res = self.verify_single_claim(claim, evidence_set)
            claim_results.append(res)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        p5_comp: Optional[dict[str, Any]] = None
        if p5_output is not None:
            p5_verdict = p5_output.get("verdict", "UNKNOWN")
            p5_comp = {
                "p5_verdict": p5_verdict,
                "p5_reason": p5_output.get("reason", ""),
                "p5_citations": p5_output.get("citations", []),
            }

        return self.aggregator.aggregate_answer_decision(
            claim_results=claim_results,
            p5_comparison=p5_comp,
            execution_time_ms=elapsed_ms,
        )
