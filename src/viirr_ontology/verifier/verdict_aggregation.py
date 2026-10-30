"""Verdict aggregation and decision logic for Stage 2.4.

Enforces:
- 3-way single-claim outcome: SUPPORTED, CONTRADICTED, INSUFFICIENT.
- Strict absence-of-evidence != contradiction principle.
- Answer-level aggregation:
    - ANY CONTRADICTED -> Answer is CONTRADICTED.
    - ELIF ANY INSUFFICIENT -> Answer is INSUFFICIENT.
    - ONLY ALL SUPPORTED -> Answer is SUPPORTED.
- Supported claims never hide contradicted or unsupported claims.
"""

from __future__ import annotations

from typing import Optional

from viirr_ontology.verifier.models import (
    AnswerVerificationResult,
    ClaimVerificationStatus,
    ReasonCode,
    VerificationResult,
)


class VerdictAggregator:
    """Aggregates claim-level verification results into answer-level decisions."""

    @staticmethod
    def aggregate_answer_decision(
        claim_results: list[VerificationResult],
        p5_comparison: Optional[dict] = None,
        execution_time_ms: float = 0.0,
    ) -> AnswerVerificationResult:
        """Aggregate multiple per-claim verification results into an answer-level decision.

        Rules:
        1. If no claims are provided, status is INSUFFICIENT.
        2. If ANY claim is CONTRADICTED, the answer status is CONTRADICTED.
        3. If no claim is CONTRADICTED, but at least ONE claim is INSUFFICIENT, the answer status is INSUFFICIENT.
        4. If and only if ALL claims are SUPPORTED, the answer status is SUPPORTED.
        """
        total = len(claim_results)
        if total == 0:
            return AnswerVerificationResult(
                aggregate_status=ClaimVerificationStatus.INSUFFICIENT,
                claim_results=[],
                summary_explanation="No claims provided for verification.",
                total_claims=0,
                supported_count=0,
                contradicted_count=0,
                insufficient_count=0,
                p5_comparison=p5_comparison,
                execution_time_ms=execution_time_ms,
            )

        supported = [r for r in claim_results if r.status == ClaimVerificationStatus.SUPPORTED]
        contradicted = [r for r in claim_results if r.status == ClaimVerificationStatus.CONTRADICTED]
        insufficient = [r for r in claim_results if r.status == ClaimVerificationStatus.INSUFFICIENT]
        out_of_scope = [r for r in claim_results if r.status == ClaimVerificationStatus.OUT_OF_SCOPE]

        if contradicted:
            aggregate_status = ClaimVerificationStatus.CONTRADICTED
            reasons = "; ".join(f"Claim '{r.claim_id}': {r.explanation}" for r in contradicted)
            summary = (
                f"Answer rejected as CONTRADICTED: {len(contradicted)}/{total} claims violated "
                f"verified evidence or constraints. Details: {reasons}"
            )
        elif insufficient:
            aggregate_status = ClaimVerificationStatus.INSUFFICIENT
            missing_info = "; ".join(
                f"Claim '{r.claim_id}' missing slots: {r.missing_evidence_slots}"
                for r in insufficient
                if r.missing_evidence_slots
            )
            summary = (
                f"Answer is INSUFFICIENT: {len(insufficient)}/{total} claims lack verified supporting evidence. "
                f"{missing_info}"
            )
        elif out_of_scope and not supported:
            aggregate_status = ClaimVerificationStatus.OUT_OF_SCOPE
            summary = (
                f"Answer is OUT_OF_SCOPE: {len(out_of_scope)}/{total} claims are outside the hydraulic "
                f"engineering ontology scope (e.g. meteorology, administrative land area)."
            )
        else:
            aggregate_status = ClaimVerificationStatus.SUPPORTED
            summary = (
                f"Answer fully SUPPORTED: all {total}/{total} technical claims are evidenced "
                f"and conform to domain constraints."
            )

        return AnswerVerificationResult(
            aggregate_status=aggregate_status,
            claim_results=claim_results,
            summary_explanation=summary,
            total_claims=total,
            supported_count=len(supported),
            contradicted_count=len(contradicted),
            insufficient_count=len(insufficient),
            out_of_scope_count=len(out_of_scope),
            p5_comparison=p5_comparison,
            execution_time_ms=execution_time_ms,
        )
