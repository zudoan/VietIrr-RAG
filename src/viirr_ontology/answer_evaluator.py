"""Evaluation module separating Factual Claim Support, Citation Validity, and Question Requirement Completeness.

Resolves:
- Issue in previous evaluator: Marking answers as CORRECT_COMPLETE even when containing extra unsupported / hallucinated claims.
- Conflating Claim Support Coverage (SUPPORTED / extracted claims) with Answer Completeness (Satisfied requirements / required components).
- Enforces strict 4-way separation:
  1. Factual Claim Support
  2. Citation Validity
  3. Answer Correctness
  4. Question Requirement Coverage
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from viirr_ontology.schema.claim import TechnicalClaim
from viirr_ontology.shadow_verifier import FourValuedStatus, ShadowClaimVerificationResult
from viirr_ontology.typed_facts import (
    KNOWN_PARAMETERS,
    KNOWN_STRUCTURES,
    extract_iso_date,
    resolve_canonical_entity,
    resolve_canonical_parameter,
    strip_accents_lower,
)


class RequirementStatus(str, Enum):
    SATISFIED = "SATISFIED"
    PARTIALLY_SATISFIED = "PARTIALLY_SATISFIED"
    NOT_SATISFIED = "NOT_SATISFIED"
    UNKNOWN = "UNKNOWN"


class OverallEvaluationStatus(str, Enum):
    CORRECT_COMPLETE = "CORRECT_COMPLETE"
    CORRECT_PARTIAL = "CORRECT_PARTIAL"
    CONTRADICTED = "CONTRADICTED"
    HAS_UNSUPPORTED_EXTRA = "HAS_UNSUPPORTED_EXTRA"
    INSUFFICIENT_SUPPORT = "INSUFFICIENT_SUPPORT"
    ABSTAINED = "ABSTAINED"
    NOT_EVALUABLE = "NOT_EVALUABLE"


@dataclass
class QuestionRequirement:
    req_id: str
    description: str
    req_type: str  # TEMPORAL_VALUE, NUMERIC_VALUE, COMPARISON, EXPLANATION, GENERAL
    target_entity: str | None = None
    target_parameter: str | None = None
    target_date_iso: str | None = None
    target_obs_type: str | None = None  # ACTUAL_OBSERVED, FORECAST_ESTIMATE, DESIGN_SPECIFICATION
    status: RequirementStatus = RequirementStatus.NOT_SATISFIED
    matched_claim_id: str | None = None
    notes: str = ""


@dataclass
class AnswerEvaluationReport:
    qa_id: str
    question: str
    answer: str
    abstained: bool

    # 1. Factual Claim Support
    total_claims: int = 0
    supported_claims: int = 0
    contradicted_claims: int = 0
    insufficient_claims: int = 0
    out_of_scope_claims: int = 0
    claim_support_coverage: float = 0.0

    # 2. Citation Validity
    valid_citations: int = 0
    invalid_citations: int = 0
    missing_citations: int = 0

    # 3. Extra Claims
    extra_unsupported_claims: list[dict[str, Any]] = field(default_factory=list)
    extra_supported_claims: list[dict[str, Any]] = field(default_factory=list)

    # 4. Question Requirement Completeness
    total_requirements: int = 0
    satisfied_requirements: int = 0
    partially_satisfied_requirements: int = 0
    question_requirement_coverage: float = 0.0
    requirements: list[QuestionRequirement] = field(default_factory=list)

    # Overall Verdict
    overall_status: OverallEvaluationStatus = OverallEvaluationStatus.NOT_EVALUABLE
    verdict_explanation: str = ""


def extract_all_entities(text: str) -> list[str]:
    """Extract all distinct canonical entity IDs mentioned in text in order of appearance."""
    norm = strip_accents_lower(text)
    sorted_structures = sorted(
        KNOWN_STRUCTURES.items(),
        key=lambda kv: (kv[0] == "CONG_XA", -max(len(strip_accents_lower(a)) for a in [kv[1]["canonical_name"]] + kv[1]["aliases"])),
    )
    matches: list[tuple[int, int, str]] = []
    for ent_id, meta in sorted_structures:
        if ent_id == "CONG_XA":
            continue  # Generic noun marker, not a specific requirement entity
        candidates = [meta["canonical_name"]] + meta["aliases"]
        for cand in candidates:
            cand_norm = strip_accents_lower(cand)
            if not cand_norm:
                continue
            if len(cand_norm) <= 4:
                pattern = r"\b" + re.escape(cand_norm) + r"\b"
            else:
                pattern = re.escape(cand_norm)
            for m in re.finditer(pattern, norm):
                s, e = m.start(), m.end()
                if not any(max(s, ms) < min(e, me) for ms, me, _ in matches):
                    matches.append((s, e, ent_id))
                    break
    matches.sort(key=lambda x: x[0])
    seen = set()
    result = []
    for _, _, ent_id in matches:
        if ent_id not in seen:
            seen.add(ent_id)
            result.append(ent_id)
    return result


def extract_question_observation_type(question: str) -> str | None:
    q_lower = question.lower()
    if any(k in q_lower for k in ["thực đo", "quan trắc", "đo được", "hiện tại"]):
        return "ACTUAL_OBSERVED"
    if any(k in q_lower for k in ["dự báo", "dự kiến"]):
        return "FORECAST_ESTIMATE"
    if any(k in q_lower for k in ["thiết kế", "quy định", "mndbt", "mnc"]):
        return "DESIGN_SPECIFICATION"
    return None


class QuestionRequirementExtractor:
    """Extracts required semantic components directly from the user's question."""

    @classmethod
    def extract_requirements(cls, question: str) -> list[QuestionRequirement]:
        reqs: list[QuestionRequirement] = []
        q_norm = question.strip()

        # 1. Extract dates
        date_pattern = r'(?:ngày\s+)?(\d{1,2}(?:/\d{1,2}(?:/\d{4})?|\s+tháng\s+\d{1,2}(?:\s+năm\s+\d{4})?))'
        raw_dates = re.findall(date_pattern, q_norm, re.IGNORECASE)
        parsed_dates = []
        for d_str in raw_dates:
            p_iso = extract_iso_date(d_str)
            if p_iso and p_iso not in parsed_dates:
                parsed_dates.append(p_iso)

        # 2. Extract entities
        parsed_entities = extract_all_entities(q_norm)
        canonical_entity = parsed_entities[0] if parsed_entities else None

        # 3. Extract parameter
        param_res = resolve_canonical_parameter(q_norm)
        canonical_param = param_res[0] if param_res else None

        # 4. Extract observation type
        target_obs = extract_question_observation_type(q_norm)
        target_date = parsed_dates[0] if parsed_dates else None

        # 5. Check for comparison / explanation requirements
        has_comparison = any(term in q_norm.lower() for term in ["so sánh", "chênh lệch", "cao hơn", "thấp hơn"])
        has_explanation = any(term in q_norm.lower() for term in ["giải thích", "nguyên nhân", "lý do", "vì sao"])

        if len(parsed_entities) >= 2:
            # Multi-entity requirement (e.g. Hàm Giang and Long Hiệp)
            for idx, ent_id in enumerate(parsed_entities, 1):
                reqs.append(
                    QuestionRequirement(
                        req_id=f"REQ_ENT_{idx:02d}",
                        description=f"Thông số {canonical_param or 'thông số'} của {ent_id}",
                        req_type="NUMERIC_VALUE",
                        target_entity=ent_id,
                        target_parameter=canonical_param,
                        target_date_iso=target_date,
                        target_obs_type=target_obs,
                    )
                )
        elif len(parsed_dates) >= 2:
            # Multi-temporal requirement
            for idx, p_date in enumerate(parsed_dates, 1):
                reqs.append(
                    QuestionRequirement(
                        req_id=f"REQ_TEMP_{idx:02d}",
                        description=f"Giá trị của {canonical_entity or 'đối tượng'} vào ngày {p_date}",
                        req_type="TEMPORAL_VALUE",
                        target_entity=canonical_entity,
                        target_parameter=canonical_param,
                        target_date_iso=p_date,
                        target_obs_type=target_obs,
                    )
                )
        elif canonical_entity or canonical_param:
            reqs.append(
                QuestionRequirement(
                    req_id="REQ_PARAM_01",
                    description=f"Thông số {canonical_param or 'thông số'} của {canonical_entity or 'đối tượng'}",
                    req_type="NUMERIC_VALUE",
                    target_entity=canonical_entity,
                    target_parameter=canonical_param,
                    target_date_iso=target_date,
                    target_obs_type=target_obs,
                )
            )

        if has_comparison:
            reqs.append(
                QuestionRequirement(
                    req_id="REQ_COMP_01",
                    description="Nhận xét so sánh hoặc đánh giá chênh lệch",
                    req_type="COMPARISON",
                )
            )

        if has_explanation:
            reqs.append(
                QuestionRequirement(
                    req_id="REQ_EXPL_01",
                    description="Giải thích nguyên nhân hoặc căn cứ quy định",
                    req_type="EXPLANATION",
                )
            )

        if not reqs:
            # Fallback general requirement
            reqs.append(
                QuestionRequirement(
                    req_id="REQ_GEN_01",
                    description="Trả lời đúng trọng tâm câu hỏi",
                    req_type="GENERAL",
                    target_entity=canonical_entity,
                    target_parameter=canonical_param,
                    target_obs_type=target_obs,
                )
            )

        return reqs


class AnswerEvaluator:
    """Rigorous evaluation of factual claim support and question requirement completeness."""

    @classmethod
    def evaluate(
        cls,
        question: str,
        answer: str,
        claims: list[TechnicalClaim],
        verification_results: list[ShadowClaimVerificationResult],
        abstained: bool = False,
        qa_id: str = "QA_UNKNOWN",
    ) -> AnswerEvaluationReport:
        requirements = QuestionRequirementExtractor.extract_requirements(question)
        total_reqs = len(requirements)

        total_claims = len(claims)
        res_by_id = {cr.claim_id: cr for cr in verification_results}

        # 1. Tách rõ Factual Claim Support
        supported_count = 0
        contradicted_count = 0
        insufficient_count = 0
        out_of_scope_count = 0

        # 2. Tách rõ Citation Validity
        valid_citations = 0
        invalid_citations = 0
        missing_citations = 0

        for claim in claims:
            cr = res_by_id.get(claim.claim_id)
            if cr is None:
                insufficient_count += 1
                continue

            if cr.status == FourValuedStatus.SUPPORTED:
                supported_count += 1
            elif cr.status == FourValuedStatus.CONTRADICTED:
                contradicted_count += 1
            elif cr.status == FourValuedStatus.INSUFFICIENT:
                insufficient_count += 1
            elif cr.status == FourValuedStatus.OUT_OF_SCOPE:
                out_of_scope_count += 1

            # Citation validity check
            if cr.citation_validity == "VALID":
                valid_citations += 1
            elif cr.citation_validity == "INVALID":
                invalid_citations += 1
            elif cr.citation_validity == "MISSING":
                missing_citations += 1

        claim_support_cov = (supported_count / total_claims) if total_claims > 0 else (1.0 if abstained else 0.0)

        # 3. Extra Claims Analysis
        extra_unsupported: list[dict[str, Any]] = []
        extra_supported: list[dict[str, Any]] = []

        # Map claims to requirements (strictly 1-to-1)
        req_matched_claims: set[str] = set()

        ans_lower = answer.lower()
        for req in requirements:
            if req.req_type == "COMPARISON":
                if any(term in ans_lower for term in ["cao hơn", "thấp hơn", "chênh lệch", "tăng", "giảm", "biến thiên", "lớn hơn", "nhỏ hơn"]):
                    req.status = RequirementStatus.SATISFIED
                else:
                    req.status = RequirementStatus.NOT_SATISFIED
                continue

            if req.req_type == "EXPLANATION":
                if any(term in ans_lower for term in ["do ", "bởi vì", "nguyên nhân", "căn cứ", "quy định", "theo đó", "lý do"]):
                    req.status = RequirementStatus.SATISFIED
                else:
                    req.status = RequirementStatus.NOT_SATISFIED
                continue

            # Candidate matching among claims
            matched = False
            for claim in claims:
                # Enforce strict 1-to-1 claim matching: a single claim cannot satisfy two distinct requirements
                if claim.claim_id in req_matched_claims:
                    continue

                cr = res_by_id.get(claim.claim_id)
                status = cr.status if cr else FourValuedStatus.INSUFFICIENT

                # Resolve claim entity & parameter
                ent_res = resolve_canonical_entity(claim.subject or claim.claim_text)
                claim_ent = ent_res[0] if ent_res else (claim.subject if claim.subject else None)

                param_res = resolve_canonical_parameter(claim.parameter or claim.claim_text)
                claim_param = param_res[0] if param_res else (claim.parameter if claim.parameter else None)

                claim_date = extract_iso_date(claim.temporal_scope or claim.claim_text)

                # Strict Entity match: If requirement specifies entity, claim MUST specify that exact entity
                if req.target_entity:
                    if not claim_ent or req.target_entity != claim_ent:
                        continue

                # Strict Date match: If requirement specifies date, claim MUST specify that matching date
                if req.target_date_iso:
                    if not claim_date:
                        continue
                    req_has_year = not req.target_date_iso.startswith("XXXX")
                    claim_has_year = not claim_date.startswith("XXXX")
                    if req_has_year and claim_has_year:
                        # Full date (including year) MUST match exactly!
                        if req.target_date_iso != claim_date:
                            continue
                    else:
                        # Year was not specified in at least one date: compare month and day
                        if req.target_date_iso[5:] != claim_date[5:]:
                            continue

                # Strict Parameter match: If requirement specifies parameter, claim MUST specify that exact parameter
                # NO WILDCARDS OR FALSE EQUIVALENCES (e.g. MUC_NUOC != CAO_TRINH_DAY)
                if req.target_parameter:
                    if not claim_param or req.target_parameter != claim_param:
                        continue

                # Strict Observation Type match: If requirement specifies obs type (e.g. ACTUAL vs FORECAST)
                if req.target_obs_type:
                    claim_obs = claim.observation_type
                    if not claim_obs or claim_obs == "UNKNOWN":
                        c_text_lower = claim.claim_text.lower()
                        if any(k in c_text_lower for k in ["dự báo", "dự kiến"]):
                            claim_obs = "FORECAST_ESTIMATE"
                        elif any(k in c_text_lower for k in ["thực đo", "quan trắc", "đo được"]):
                            claim_obs = "ACTUAL_OBSERVED"
                        elif any(k in c_text_lower for k in ["thiết kế", "quy định", "mndbt", "mnc"]):
                            claim_obs = "DESIGN_SPECIFICATION"
                    # Neither None, nor UNKNOWN, nor mismatched types are allowed to match
                    if not claim_obs or claim_obs == "UNKNOWN" or claim_obs != req.target_obs_type:
                        continue

                # Must have a value
                if not claim.value:
                    continue

                # Found matching claim!
                matched = True
                req.matched_claim_id = claim.claim_id
                req_matched_claims.add(claim.claim_id)

                if status == FourValuedStatus.SUPPORTED:
                    req.status = RequirementStatus.SATISFIED
                elif status == FourValuedStatus.CONTRADICTED:
                    req.status = RequirementStatus.NOT_SATISFIED
                    req.notes = "Claim mâu thuẫn với tài liệu nguồn"
                else:
                    req.status = RequirementStatus.PARTIALLY_SATISFIED
                    req.notes = "Claim thiếu bằng chứng xác thực"
                break

            if not matched:
                if req.req_type == "GENERAL" and not req.target_entity and not req.target_parameter:
                    req.status = RequirementStatus.UNKNOWN
                    req.notes = "Yêu cầu không đủ thông tin từ câu hỏi"
                else:
                    req.status = RequirementStatus.NOT_SATISFIED
                    req.notes = "Không tìm thấy claim phù hợp trong câu trả lời"

        # Identify extra claims
        for claim in claims:
            if claim.claim_id not in req_matched_claims:
                cr = res_by_id.get(claim.claim_id)
                claim_stat = cr.status if cr else FourValuedStatus.INSUFFICIENT
                info = {
                    "claim_id": claim.claim_id,
                    "text": claim.claim_text,
                    "entity": claim.subject,
                    "parameter": claim.parameter,
                    "value": claim.value,
                    "status": claim_stat.value,
                }
                if claim_stat == FourValuedStatus.SUPPORTED:
                    extra_supported.append(info)
                else:
                    extra_unsupported.append(info)

        satisfied_reqs = sum(1 for r in requirements if r.status == RequirementStatus.SATISFIED)
        partial_reqs = sum(1 for r in requirements if r.status == RequirementStatus.PARTIALLY_SATISFIED)
        req_cov = (satisfied_reqs / total_reqs) if total_reqs > 0 else 0.0

        # Synthesize Overall Verdict
        if abstained:
            overall_status = OverallEvaluationStatus.ABSTAINED
            verdict_exp = "Mô hình từ chối trả lời (Abstained)"
        elif contradicted_count > 0:
            overall_status = OverallEvaluationStatus.CONTRADICTED
            verdict_exp = f"Có {contradicted_count} claim mâu thuẫn trực tiếp với nguồn tài liệu."
        elif extra_unsupported:
            overall_status = OverallEvaluationStatus.HAS_UNSUPPORTED_EXTRA
            verdict_exp = (
                f"Câu trả lời chứa {len(extra_unsupported)} claim nằm ngoài yêu cầu câu hỏi "
                "và KHÔNG được tài liệu nguồn hỗ trợ (chặn đánh giá COMPLETE)."
            )
        elif satisfied_reqs == total_reqs and total_reqs > 0:
            if supported_count == total_claims:
                overall_status = OverallEvaluationStatus.CORRECT_COMPLETE
                verdict_exp = "Đầy đủ các yêu cầu câu hỏi và 100% claims được nguồn tài liệu hỗ trợ."
            else:
                overall_status = OverallEvaluationStatus.CORRECT_PARTIAL
                verdict_exp = "Đạt các yêu cầu câu hỏi nhưng một số claim chưa đủ bằng chứng nguồn."
        elif satisfied_reqs > 0:
            overall_status = OverallEvaluationStatus.CORRECT_PARTIAL
            verdict_exp = f"Chỉ đáp ứng {satisfied_reqs}/{total_reqs} yêu cầu của câu hỏi."
        else:
            overall_status = OverallEvaluationStatus.INSUFFICIENT_SUPPORT
            verdict_exp = "Không đáp ứng được yêu cầu nào của câu hỏi trên bằng chứng đã xác thực."

        return AnswerEvaluationReport(
            qa_id=qa_id,
            question=question,
            answer=answer,
            abstained=abstained,
            total_claims=total_claims,
            supported_claims=supported_count,
            contradicted_claims=contradicted_count,
            insufficient_claims=insufficient_count,
            out_of_scope_claims=out_of_scope_count,
            claim_support_coverage=round(claim_support_cov, 4),
            valid_citations=valid_citations,
            invalid_citations=invalid_citations,
            missing_citations=missing_citations,
            extra_unsupported_claims=extra_unsupported,
            extra_supported_claims=extra_supported,
            total_requirements=total_reqs,
            satisfied_requirements=satisfied_reqs,
            partially_satisfied_requirements=partial_reqs,
            question_requirement_coverage=round(req_cov, 4),
            requirements=requirements,
            overall_status=overall_status,
            verdict_explanation=verdict_exp,
        )
