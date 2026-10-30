"""Evidence-Targeted Correction Planner for Stage 3 Sprint A.

Formulates an interpretable CorrectionPlan driven strictly by missing evidence slots
and unresolved constraints identified during S2.4 verification.
"""

from __future__ import annotations

import re
from typing import Optional

from viirr_ontology.schema.claim import TechnicalClaim
from viirr_ontology.schema.evidence import EvidenceSet
from viirr_ontology.verifier.models import ClaimVerificationStatus, VerificationResult
from .models import CorrectionGoal, CorrectionPlan


class EvidenceCorrectionPlanner:
    """Generates an interpretable CorrectionPlan targeting missing evidence slots."""

    def create_plan(
        self,
        claim: TechnicalClaim,
        verification_result: VerificationResult,
        original_query: str = "",
        evidence_set: Optional[EvidenceSet] = None,
        retrieval_budget: int = 2,
    ) -> CorrectionPlan:
        """Create a targeted plan driven by verification gaps, without inventing new facts."""
        missing_slots = list(verification_result.missing_evidence_slots)
        missing_constraints = list(verification_result.missing_constraints)
        reason_codes = list(verification_result.reason_codes)

        subject = (claim.subject or "").strip()
        parameter = (claim.parameter or "").strip()
        action = (claim.action or "").strip()
        jurisdiction = (claim.jurisdiction or "").strip()
        doc_scope = claim.document_scope
        temporal_scope = claim.temporal_scope

        # Determine primary correction goal and queries based on gaps
        search_queries: list[str] = []
        required_evidence_types: list[str] = []
        correction_goal = CorrectionGoal.GENERIC_MISSING_SLOTS.value
        reason_for_correction = "Address missing evidence slots identified by verifier"

        # 1. Document version conflict / mismatch / missing scope
        if (
            "DOCUMENT_VERSION_CONFLICT" in reason_codes
            or "DOCUMENT_MISMATCH" in reason_codes
            or any("version" in s or "document_scope" in s for s in missing_slots)
        ):
            correction_goal = CorrectionGoal.RESOLVE_MISSING_VERSION.value
            required_evidence_types = ["document_metadata", "decision_header", "amendment_clause"]
            reason_for_correction = "Document version conflict, mismatch, or missing authoritative version metadata"
            target_doc = doc_scope or subject
            search_queries.append(f"{target_doc} quyết định quy trình vận hành ngày ban hành hiệu lực")
            search_queries.append(f"{target_doc} văn bản sửa đổi bổ sung")

        # 2. Missing legal authority, action rule, or mandate
        elif any(s in missing_slots for s in ("action", "polarity", "jurisdiction")) or "ACTION_MISMATCH" in reason_codes:
            correction_goal = CorrectionGoal.RESOLVE_MISSING_AUTHORITY.value
            required_evidence_types = ["legal_article", "authority_clause", "powers_and_duties"]
            reason_for_correction = f"Missing explicit legal authorization provision for '{subject}' - action '{action}'"
            if subject and action:
                jur_str = f" {jurisdiction}" if jurisdiction else ""
                search_queries.append(f"{subject}{jur_str} thẩm quyền {action}")
                search_queries.append(f"{subject} trách nhiệm nhiệm vụ quyền hạn ban hành lệnh")
            elif subject:
                search_queries.append(f"{subject} thẩm quyền trách nhiệm quyết định")

        # 3. Missing applicability condition, seasonal qualification, or threshold
        elif any(s in missing_slots for s in ("conditions", "claim_conditions")):
            correction_goal = CorrectionGoal.RESOLVE_MISSING_CONDITION.value
            required_evidence_types = ["table_note", "applicability_paragraph", "operating_threshold_rule"]
            cond_desc = ""
            if claim.conditions:
                c0 = claim.conditions[0]
                cond_desc = c0.raw_text or f"{c0.operator} {c0.value} {c0.unit}".strip()
            reason_for_correction = f"Missing applicability condition or operating threshold: '{cond_desc}'"
            if subject and cond_desc:
                search_queries.append(f"{subject} quy định ngưỡng vận hành {cond_desc}")
                search_queries.append(f"{subject} ghi chú điều kiện áp dụng {parameter}")
            elif subject and parameter:
                search_queries.append(f"{subject} {parameter} điều kiện áp dụng thời kỳ mùa lũ mùa cạn")

        # 4. Missing unit or parameter-value binding in tables
        elif any(s in missing_slots for s in ("unit", "parameter_value_binding", "parameter")):
            correction_goal = CorrectionGoal.RESOLVE_MISSING_UNIT.value
            required_evidence_types = ["table_header", "unit_column", "table_metadata"]
            reason_for_correction = f"Missing physical unit or column header binding for parameter '{parameter}'"
            if subject and parameter:
                search_queries.append(f"{subject} {parameter} đơn vị tính tiêu đề bảng")
                search_queries.append(f"{subject} bảng thông số kỹ thuật tiêu đề cột")
            elif subject:
                search_queries.append(f"{subject} thông số kỹ thuật đơn vị tính")

        # 5. Missing verified relation between multi-region table parts
        elif any(s in missing_slots for s in ("verified_evidence_relation", "table_continuation")):
            correction_goal = CorrectionGoal.RESOLVE_MISSING_RELATION.value
            required_evidence_types = ["table_body", "table_caption", "continuation_paragraph"]
            reason_for_correction = "Disjoint table row without verified header relation"
            search_queries.append(f"{subject} {parameter} bảng biểu toàn văn số liệu")

        # 5. Missing verified relation between multi-region table parts
        elif any(s in missing_slots for s in ("verified_evidence_relation", "table_continuation")):
            correction_goal = CorrectionGoal.RESOLVE_MISSING_RELATION.value
            required_evidence_types = ["table_body", "table_caption", "continuation_paragraph"]
            reason_for_correction = "Disjoint table row without verified header relation"
            search_queries.append(f"{subject} {parameter} bảng biểu toàn văn số liệu")

        # Fallback query generation
        if not search_queries:
            q_terms = [t for t in [subject, parameter, action, original_query] if t]
            fallback_q = " ".join(q_terms[:3]) if q_terms else "quy trình vận hành hồ chứa thủy lợi"
            search_queries.append(fallback_q)

        # Subject and parameter scope constraints
        subject_constraints = [subject] if subject else []
        param_constraints = [parameter] if parameter else []

        return CorrectionPlan(
            correction_goal=correction_goal,
            target_claim_id=claim.claim_id,
            missing_slots=missing_slots,
            required_evidence_types=required_evidence_types,
            search_queries=search_queries,
            subject_constraints=subject_constraints,
            parameter_constraints=param_constraints,
            document_scope=doc_scope,
            temporal_scope=temporal_scope,
            allowed_retrieval_strategy="targeted_focused_slot_retrieval",
            max_attempts=max(0, min(retrieval_budget, 3)),
            reason_for_correction=reason_for_correction,
        )
