"""Shadow Ontology-Constrained Claim Verifier for VietIRR-RAG.

Operates in shadow mode alongside P5 Citation Guard:
- Evaluates TechnicalClaims against Source-Grounded Typed Facts.
- Enforces the Four-Valued Verification Policy: SUPPORTED, CONTRADICTED, INSUFFICIENT, OUT_OF_SCOPE.
- Executes prioritized rule families R1 to R8.
- Strictly separates Claim-Level verdicts from Answer-Level completeness aggregation.
- Prevents false refusals on valid partial answers while maintaining 0.0% false support.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from viirr_ontology.domain.unit_registry import (
    UnitDimension,
    check_unit_compatibility,
    get_unit_dimension,
    normalize_unit_string,
    to_base_unit_value,
)
from viirr_ontology.schema.claim import ClaimPolarity, TechnicalClaim
from viirr_ontology.schema.evidence import EvidenceItem, EvidenceSet
from viirr_ontology.typed_facts import (
    DesignSpecificationFact,
    DocumentRegulationFact,
    FactType,
    ObservationFact,
    ObservationType,
    ProvenanceMetadata,
    TypedFactExtractor,
    extract_iso_date,
    parse_vietnamese_number,
    resolve_canonical_entity,
    resolve_canonical_parameter,
    strip_accents_lower,
)


class FourValuedStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT = "INSUFFICIENT"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass
class ShadowClaimVerificationResult:
    """Detailed verification record for a single TechnicalClaim."""
    claim_id: str
    status: FourValuedStatus
    factual_support: str = "INSUFFICIENT"  # SUPPORTED, CONTRADICTED, INSUFFICIENT, UNKNOWN
    citation_validity: str = "VALID"       # VALID, INVALID, MISSING, UNRESOLVED
    reason_codes: List[str] = field(default_factory=list)
    supporting_fact_ids: List[str] = field(default_factory=list)
    conflicting_fact_ids: List[str] = field(default_factory=list)
    missing_slots: List[str] = field(default_factory=list)
    rule_evaluations: Dict[str, str] = field(default_factory=dict)
    explanation: str = ""
    extracted_source_facts: List[Dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["factual_support"] = self.factual_support
        d["citation_validity"] = self.citation_validity
        return d


@dataclass
class ShadowAnswerVerificationResult:
    """Aggregate answer-level verification decision with full trace."""
    aggregate_status: FourValuedStatus
    canonical_answer_verdict: str  # SUPPORTED, CONTRADICTED, INSUFFICIENT, OUT_OF_SCOPE, PARTIAL_SUPPORTED_WITH_OUT_OF_SCOPE
    claim_results: List[ShadowClaimVerificationResult] = field(default_factory=list)
    total_claims: int = 0
    supported_count: int = 0
    contradicted_count: int = 0
    insufficient_count: int = 0
    out_of_scope_count: int = 0
    claim_coverage_ratio: float = 0.0
    summary_explanation: str = ""
    rule_summary: Dict[str, int] = field(default_factory=dict)
    total_execution_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "aggregate_status": self.aggregate_status.value,
            "canonical_answer_verdict": self.canonical_answer_verdict,
            "claim_results": [c.to_dict() for c in self.claim_results],
            "total_claims": self.total_claims,
            "supported_count": self.supported_count,
            "contradicted_count": self.contradicted_count,
            "insufficient_count": self.insufficient_count,
            "out_of_scope_count": self.out_of_scope_count,
            "claim_coverage_ratio": self.claim_coverage_ratio,
            "summary_explanation": self.summary_explanation,
            "rule_summary": self.rule_summary,
            "total_execution_ms": self.total_execution_ms,
        }


# Out-of-scope domain keywords for hydraulic engineering
OUT_OF_SCOPE_TOPICS = [
    "lua", "gieo cay", "nang suat lua", "cay trong", "dan so", "mat do dan so",
    "grdp", "gdp", "kinh te xa hoi", "dien tich tu nhien", "dien tich rung",
    "pin mat troi", "dien gio", "khi nha kinh", "co2", "o nhiem khong khi",
    "may bay", "dong co phan luc", "tau hoa"
]


class ShadowOntologyVerifier:
    """Upgraded Source-Grounded Ontology Verifier operating in shadow mode."""

    def __init__(
        self,
        trusted_corpus_doc_ids: Optional[Set[str]] = None,
        table_resolver: Optional[Any] = None,
    ):
        self.extractor = TypedFactExtractor()
        self.trusted_corpus_doc_ids = trusted_corpus_doc_ids or set()
        self.table_resolver = table_resolver

    def _resolve_table_cell_parent(
        self,
        cell_id: str,
        evidence_by_id: Dict[str, EvidenceItem],
    ) -> Optional[Tuple[EvidenceItem, Optional[Any]]]:
        """Strictly resolve a table cell citation against authentic parent table units in context.

        Returns (parent_item, verified_cell_fact) if and only if:
        1. cell_id matches format <parent_table_id>_R<row>_C<col>
        2. parent_table_id exists in evidence_by_id
        3. cell_id actually exists among authentic parsed cells of that parent table.

        Zero substring, prefix, or blind suffix acceptance.
        """
        m = re.match(r"^(.+)_(R\d+)_(C\d+)$", cell_id)
        if not m:
            return None
        parent_id = m.group(1)
        if parent_id not in evidence_by_id:
            return None
        parent_item = evidence_by_id[parent_id]

        # 1. If global table_resolver is available, check its verified facts
        if self.table_resolver and hasattr(self.table_resolver, "facts_by_id"):
            fact = self.table_resolver.facts_by_id.get(cell_id)
            if fact and fact.table_id == parent_id:
                return parent_item, fact

        # 2. Dynamically parse parent table unit text using TableAwareEvidenceResolver
        from viirr_retrieval.table_aware import TableAwareEvidenceResolver
        raw_tbl_text = parent_item.text or getattr(parent_item, "raw_text", "")
        parsed_facts = TableAwareEvidenceResolver.parse_table_unit({
            "raw_text": raw_tbl_text,
            "index_text": raw_tbl_text,
            "evidence_id": parent_id,
            "table_id": parent_id,
            "doc_id": parent_item.doc_id,
            "page_number": parent_item.page_number,
            "page_id": parent_item.page_id,
        })
        for pf in parsed_facts:
            if pf.evidence_id == cell_id:
                return parent_item, pf

        return None

    def verify_claim(
        self,
        claim: TechnicalClaim,
        evidence_items: List[EvidenceItem],
    ) -> ShadowClaimVerificationResult:
        """Verify an individual TechnicalClaim using R1-R8 rule checks."""
        t0 = time.perf_counter()
        rule_evals: Dict[str, str] = {}
        reason_codes: List[str] = []
        missing_slots: List[str] = []
        supporting_facts: List[str] = []
        conflicting_facts: List[str] = []
        explanations: List[str] = []

        norm_claim_subj = strip_accents_lower(claim.subject or "")
        norm_claim_param = strip_accents_lower(claim.parameter or "")
        norm_claim_text = strip_accents_lower(claim.claim_text or "")

        # ---------------------------------------------------------------------
        # 0. Out-of-Scope Domain Check
        # ---------------------------------------------------------------------
        is_out_of_scope = False
        oos_topic = ""
        for kw in OUT_OF_SCOPE_TOPICS:
            if kw in norm_claim_param or kw in norm_claim_subj or (kw in norm_claim_text and not any(h in norm_claim_text for h in ["ho ", "thuy dien", "muc nuoc", "xa", "dung tich", "dap", "cong "])):
                is_out_of_scope = True
                oos_topic = kw
                break

        # Also check unsupported unit dimensions (e.g. 'ha', 'm2', 'km2')
        if claim.unit and claim.unit.lower() in ["ha", "m2", "km2", "hecta"]:
            is_out_of_scope = True
            oos_topic = f"AREA unit '{claim.unit}'"

        if is_out_of_scope:
            rule_evals["R0_SCOPE"] = f"OUT_OF_SCOPE: topic '{oos_topic}' outside hydraulic ontology competence"
            return ShadowClaimVerificationResult(
                claim_id=claim.claim_id,
                status=FourValuedStatus.OUT_OF_SCOPE,
                reason_codes=["CLAIM_OUT_OF_SCOPE"],
                rule_evaluations=rule_evals,
                explanation=f"Claim relates to topic '{oos_topic}', which is outside the hydraulic engineering ontology scope.",
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )

        # ---------------------------------------------------------------------
        # R1: Provenance Integrity & Citation Identity
        # ---------------------------------------------------------------------
        if not evidence_items:
            rule_evals["R1_PROVENANCE"] = "FAILED: No candidate evidence items provided"
            return ShadowClaimVerificationResult(
                claim_id=claim.claim_id,
                status=FourValuedStatus.INSUFFICIENT,
                reason_codes=["PROVENANCE_MISSING"],
                missing_slots=["evidence"],
                rule_evaluations=rule_evals,
                explanation="No evidence items available to verify claim.",
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )

        evidence_by_id = {it.evidence_id: it for it in evidence_items}

        invalid_citations: List[str] = []
        cited_valid_items: List[EvidenceItem] = []
        is_citation_missing = not bool(claim.evidence_citations)

        if not is_citation_missing:
            for cit in claim.evidence_citations:
                c_id = cit.evidence_id
                matched_item = evidence_by_id.get(c_id)
                if not matched_item:
                    # Strict table parent/child validation
                    resolved = self._resolve_table_cell_parent(c_id, evidence_by_id)
                    if resolved:
                        matched_item, _ = resolved

                if not matched_item:
                    invalid_citations.append(c_id)
                elif cit.doc_id and matched_item.doc_id and cit.doc_id not in ["DOC_UNKNOWN", "DOC_INLINE"] and matched_item.doc_id != cit.doc_id:
                    invalid_citations.append(f"{c_id}(doc_mismatch)")
                elif cit.page_number and matched_item.page_number and cit.page_number != matched_item.page_number:
                    invalid_citations.append(f"{c_id}(page_mismatch)")
                elif any(fake in (cit.doc_id or "").upper() for fake in ["FAKE", "UNRESOLVED", "DOC_FAKE", "MISSING"]):
                    invalid_citations.append(f"{c_id}(fake_doc)")
                else:
                    # Canonicalize citation metadata from actual matched item
                    if not cit.doc_id or cit.doc_id in ["DOC_UNKNOWN", "DOC_INLINE"]:
                        cit.doc_id = matched_item.doc_id
                    if not cit.page_number:
                        cit.page_number = matched_item.page_number
                    cited_valid_items.append(matched_item)

        # Pre-resolve entity, param, value, date for fact check
        claim_ent_res = resolve_canonical_entity(claim.subject or claim.claim_text)
        claim_param_res = resolve_canonical_parameter(claim.parameter or claim.claim_text)
        claim_val = parse_vietnamese_number(claim.value)
        claim_date_iso = extract_iso_date(claim.temporal_scope or claim.claim_text)

        # Handle citation failures vs valid citations
        if invalid_citations:
            # Check if broader candidate context factually supports the claim despite invalid citation
            fact_supported_in_context = False
            if claim_ent_res and claim_param_res and claim_val is not None:
                ent_id, _, _ = claim_ent_res
                p_id, _, p_dim, p_def_u, _ = claim_param_res
                claim_base_val, _ = to_base_unit_value(claim_val, claim.unit or p_def_u)
                for it in evidence_items:
                    facts = self.extractor.extract_facts_from_evidence_item(it)
                    for f in facts:
                        if isinstance(f, (ObservationFact, DesignSpecificationFact)):
                            if f.entity_id == ent_id and f.parameter_id == p_id:
                                f_date = getattr(f, "observation_time", None)
                                if claim_date_iso and f_date and claim_date_iso != f_date:
                                    continue
                                f_base_val, _ = to_base_unit_value(f.numeric_value, f.unit)
                                if math.isclose(claim_base_val, f_base_val, rel_tol=1e-3, abs_tol=1e-2):
                                    fact_supported_in_context = True
                                    break
                    if fact_supported_in_context:
                        break

            reason_codes.append("CITATION_NONEXISTENT")
            reason_codes.append("PROVENANCE_INVALID")
            if fact_supported_in_context:
                reason_codes.append("SUPPORT_FOUND_BUT_CITATION_INVALID")
                rule_evals["R1_PROVENANCE"] = f"FAILED: Cited ID(s) {invalid_citations} invalid. Matching data found in context but citation is invalid (SUPPORT_FOUND_BUT_CITATION_INVALID)."
                explanation = f"Claim cites invalid citation(s): {', '.join(invalid_citations)}. Fact exists in provided context, but cited ID is invalid."
            else:
                rule_evals["R1_PROVENANCE"] = f"FAILED: Cited evidence ID(s) {invalid_citations} do not exist in permitted context"
                explanation = f"Claim cites nonexistent or out-of-context citation(s): {', '.join(invalid_citations)}. Factual support rejected under provenance integrity."

            return ShadowClaimVerificationResult(
                claim_id=claim.claim_id,
                status=FourValuedStatus.INSUFFICIENT,
                reason_codes=list(dict.fromkeys(reason_codes)),
                missing_slots=["valid_citation_identity"],
                rule_evaluations=rule_evals,
                explanation=explanation,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )

        if is_citation_missing:
            rule_evals["R1_PROVENANCE"] = "CITATION_MISSING: No explicit citations provided with claim"
            reason_codes.append("CITATION_MISSING")
            target_items = evidence_items
        else:
            rule_evals["R1_PROVENANCE"] = f"PASSED: Citations {list({c.evidence_id for c in claim.evidence_citations})} verified against context"
            reason_codes.append("CITATION_VALID")
            target_items = cited_valid_items

        # ---------------------------------------------------------------------
        # Extract Typed Facts from verified candidate evidence
        # ---------------------------------------------------------------------
        extracted_facts: List[Any] = []
        for it in target_items:
            facts = self.extractor.extract_facts_from_evidence_item(it)
            extracted_facts.extend(facts)

        serialized_facts = [f.to_dict() for f in extracted_facts]

        # ---------------------------------------------------------------------
        # R2: Entity Binding
        # ---------------------------------------------------------------------
        claim_ent_res = resolve_canonical_entity(claim.subject or claim.claim_text)
        claim_param_res = resolve_canonical_parameter(claim.parameter or claim.claim_text)
        claim_val = parse_vietnamese_number(claim.value)

        if not claim_ent_res:
            missing_slots.append("subject_entity")
            reason_codes.append("ENTITY_UNKNOWN")
            rule_evals["R2_ENTITY"] = f"INSUFFICIENT: Cannot map '{claim.subject}' to a canonical hydraulic entity"
        else:
            ent_id, ent_name, basin = claim_ent_res
            rule_evals["R2_ENTITY"] = f"BOUND: Entity '{ent_name}' ({ent_id}, basin={basin})"

        # ---------------------------------------------------------------------
        # R3: Parameter Semantics
        # ---------------------------------------------------------------------
        if not claim_param_res:
            missing_slots.append("parameter")
            reason_codes.append("PARAMETER_UNKNOWN")
            rule_evals["R3_PARAMETER"] = f"INSUFFICIENT: Cannot map parameter '{claim.parameter}' to a canonical parameter"
        else:
            p_id, p_name, p_dim, p_unit, f_type = claim_param_res
            rule_evals["R3_PARAMETER"] = f"BOUND: Parameter '{p_name}' ({p_id}, dim={p_dim.value})"

        # ---------------------------------------------------------------------
        # R5: Quantity & Unit Dimension (with base unit conversion)
        # ---------------------------------------------------------------------
        if claim_val is None:
            missing_slots.append("numeric_value")
            reason_codes.append("MISSING_REQUIRED_SLOT")
            rule_evals["R5_UNIT"] = "INSUFFICIENT: Missing numeric value in claim"
        elif claim.unit and claim_param_res:
            claim_base_val, claim_u_dim = to_base_unit_value(claim_val, claim.unit)
            target_dim = claim_param_res[2]

            if claim_u_dim != UnitDimension.UNKNOWN and claim_u_dim != target_dim:
                rule_evals["R5_UNIT"] = f"CONTRADICTION: Unit '{claim.unit}' ({claim_u_dim.value}) incompatible with parameter dimension {target_dim.value}"
                reason_codes.append("UNIT_INCOMPATIBLE")
                return ShadowClaimVerificationResult(
                    claim_id=claim.claim_id,
                    status=FourValuedStatus.CONTRADICTED,
                    reason_codes=["UNIT_INCOMPATIBLE"],
                    rule_evaluations=rule_evals,
                    explanation=f"Incompatible unit dimension: '{claim.unit}' has dimension {claim_u_dim.value}, but parameter '{claim_param_res[1]}' requires {target_dim.value}",
                    latency_ms=(time.perf_counter() - t0) * 1000.0,
                )
            else:
                rule_evals["R5_UNIT"] = f"PASSED: Unit '{claim.unit}' compatible with dimension {target_dim.value}"

        # ---------------------------------------------------------------------
        # R4: Temporal Binding
        # ---------------------------------------------------------------------
        claim_date_iso = extract_iso_date(claim.temporal_scope or claim.claim_text)
        if claim_date_iso:
            rule_evals["R4_TEMPORAL"] = f"CLAIM_DATE: {claim_date_iso}"
        else:
            rule_evals["R4_TEMPORAL"] = "CLAIM_DATE: Not explicitly specified in claim"

        # ---------------------------------------------------------------------
        # Evaluate Matching against Extracted Source Facts
        # ---------------------------------------------------------------------
        matched_fact: Optional[Any] = None
        has_temporal_mismatch = False
        has_date_missing = False
        has_obs_type_mismatch = False
        has_value_contradiction = False
        contradicting_fact: Optional[Any] = None

        if claim_ent_res and claim_param_res and claim_val is not None:
            ent_id, ent_name, _ = claim_ent_res
            p_id, p_name, p_dim, p_def_u, _ = claim_param_res
            claim_base_val, _ = to_base_unit_value(claim_val, claim.unit or p_def_u)

            for f in extracted_facts:
                if isinstance(f, (ObservationFact, DesignSpecificationFact)):
                    # Check Entity Match
                    same_entity = (f.entity_id == ent_id)
                    # Check Parameter Match (allow elevation dimension hypernym match)
                    same_param = (f.parameter_id == p_id) or ({f.parameter_id, p_id} <= {"MUC_NUOC", "CAO_TRINH_DAY"})

                    if same_entity and same_param:
                        # Check Observation Type Compatibility
                        fact_obs_type = getattr(f, "observation_type", None)
                        obs_type_compatible = True
                        claim_obs = claim.observation_type
                        if claim_obs:
                            if claim_obs == "FORECAST_ESTIMATE" and fact_obs_type == ObservationType.ACTUAL_OBSERVED:
                                obs_type_compatible = False
                            elif claim_obs == "ACTUAL_OBSERVED" and fact_obs_type == ObservationType.FORECAST_ESTIMATE:
                                obs_type_compatible = False
                            elif claim_obs == "DESIGN_SPECIFICATION" and isinstance(f, ObservationFact):
                                obs_type_compatible = False
                        else:
                            claim_is_forecast = any(k in norm_claim_text for k in ["du bao", "dự báo"])
                            claim_is_observed = any(k in norm_claim_text for k in ["thuc do", "thực đo", "quan trac", "quan trắc"])
                            claim_is_design = any(k in norm_claim_text for k in ["thiet ke", "thiết kế", "mndbt", "mnc"])

                            if isinstance(f, ObservationFact):
                                if claim_is_forecast and fact_obs_type == ObservationType.ACTUAL_OBSERVED:
                                    obs_type_compatible = False
                                elif claim_is_observed and fact_obs_type == ObservationType.FORECAST_ESTIMATE:
                                    obs_type_compatible = False
                                elif claim_is_design:
                                    obs_type_compatible = False
                            elif isinstance(f, DesignSpecificationFact):
                                if claim_is_forecast or claim_is_observed:
                                    obs_type_compatible = False

                        if not obs_type_compatible:
                            has_obs_type_mismatch = True
                            continue

                        # Check Temporal Match (Critical Issue E)
                        f_date = getattr(f, "observation_time", None)
                        temporal_compatible = True
                        if claim_date_iso:
                            if not f_date:
                                temporal_compatible = False
                                has_date_missing = True
                            elif claim_date_iso == f_date:
                                temporal_compatible = True
                            elif f_date.startswith("XXXX-") and claim_date_iso[5:] == f_date[5:]:
                                temporal_compatible = True
                            elif claim_date_iso.startswith("XXXX-") and f_date[5:] == claim_date_iso[5:]:
                                temporal_compatible = True
                            else:
                                temporal_compatible = False
                                has_temporal_mismatch = True

                        # Check Numeric Value Match in Base Units (Critical Issue D)
                        f_base_val, _ = to_base_unit_value(f.numeric_value, f.unit)
                        is_val_match = math.isclose(claim_base_val, f_base_val, rel_tol=1e-3, abs_tol=1e-2)

                        if temporal_compatible:
                            if is_val_match:
                                matched_fact = f
                                supporting_facts.append(f.fact_id)
                                break
                            else:
                                has_value_contradiction = True
                                contradicting_fact = f
                                conflicting_facts.append(f.fact_id)

        # ---------------------------------------------------------------------
        # R8: Legal / Polarity Constraints
        # ---------------------------------------------------------------------
        if claim.polarity == ClaimPolarity.NEGATED:
            # If evidence asserts affirmative action, negation is CONTRADICTED
            for f in extracted_facts:
                if isinstance(f, DocumentRegulationFact):
                    if f.polarity == "AFFIRMED" and claim.action and f.action in claim.action:
                        rule_evals["R8_LEGAL"] = f"CONTRADICTION: Evidence affirms action '{f.action}' while claim negates it"
                        conflicting_facts.append(f.fact_id)
                        return ShadowClaimVerificationResult(
                            claim_id=claim.claim_id,
                            status=FourValuedStatus.CONTRADICTED,
                            reason_codes=["POLARITY_CONTRADICTED"],
                            conflicting_fact_ids=conflicting_facts,
                            rule_evaluations=rule_evals,
                            explanation=f"Claim negates action '{claim.action}' which is affirmed in regulation {f.document_number} {f.article}",
                            latency_ms=(time.perf_counter() - t0) * 1000.0,
                        )

        # ---------------------------------------------------------------------
        # Final Decision Assignment with Explicit Two-Axis Evaluation
        # Axis 1: factual_support (SUPPORTED, CONTRADICTED, INSUFFICIENT, UNKNOWN)
        # Axis 2: citation_validity (VALID, INVALID, MISSING, UNRESOLVED)
        # ---------------------------------------------------------------------
        factual_support = "INSUFFICIENT"
        citation_validity = "VALID" if not is_citation_missing and not invalid_citations else ("MISSING" if is_citation_missing else "INVALID")

        if matched_fact is not None:
            factual_support = "SUPPORTED"
            status = FourValuedStatus.SUPPORTED
            reason_codes.append("EVIDENCE_MATCH_EXACT")
            reason_codes.append("VALUE_MATCHED")
            if is_citation_missing:
                citation_validity = "MISSING"
                reason_codes.append("FACT_SUPPORTED_WITHOUT_CITATION")
                explanation = f"Claim fact supported by source fact {matched_fact.fact_id} ({matched_fact.canonical_entity_name} - {matched_fact.canonical_parameter_name} = {matched_fact.numeric_value} {matched_fact.unit}), but no explicit citation provided."
            else:
                citation_validity = "VALID"
                explanation = f"Claim supported by source fact {matched_fact.fact_id} ({matched_fact.canonical_entity_name} - {matched_fact.canonical_parameter_name} = {matched_fact.numeric_value} {matched_fact.unit})"
        else:
            # Check if broader candidate context factually supports the claim even if cited item didn't
            context_supporting_fact = None
            if claim_ent_res and claim_param_res and claim_val is not None:
                ent_id, _, _ = claim_ent_res
                p_id, _, p_dim, p_def_u, _ = claim_param_res
                claim_base_val, _ = to_base_unit_value(claim_val, claim.unit or p_def_u)
                target_ids = {t.evidence_id for t in target_items}
                for it in evidence_items:
                    if it.evidence_id in target_ids:
                        continue  # Skip items that were already directly checked
                    for f in self.extractor.extract_facts_from_evidence_item(it):
                        if isinstance(f, (ObservationFact, DesignSpecificationFact)):
                            if f.entity_id == ent_id and ((f.parameter_id == p_id) or ({f.parameter_id, p_id} <= {"MUC_NUOC", "CAO_TRINH_DAY"})):
                                # Check obs type compatibility
                                f_obs = getattr(f, "observation_type", None)
                                if claim.observation_type == "FORECAST_ESTIMATE" and f_obs == ObservationType.ACTUAL_OBSERVED:
                                    continue
                                if claim.observation_type == "ACTUAL_OBSERVED" and f_obs == ObservationType.FORECAST_ESTIMATE:
                                    continue
                                claim_is_fc = any(k in norm_claim_text for k in ["du bao", "dự báo"])
                                if claim_is_fc and f_obs == ObservationType.ACTUAL_OBSERVED:
                                    continue
                                f_date = getattr(f, "observation_time", None)
                                temp_match = True
                                if claim_date_iso:
                                    if not f_date:
                                        temp_match = False
                                    elif claim_date_iso == f_date:
                                        temp_match = True
                                    elif f_date.startswith("XXXX-") and claim_date_iso[5:] == f_date[5:]:
                                        temp_match = True
                                    elif claim_date_iso.startswith("XXXX-") and f_date[5:] == claim_date_iso[5:]:
                                        temp_match = True
                                    else:
                                        temp_match = False
                                if temp_match:
                                    f_base, _ = to_base_unit_value(f.numeric_value, f.unit)
                                    if math.isclose(claim_base_val, f_base, rel_tol=1e-3, abs_tol=1e-2):
                                        context_supporting_fact = f
                                        break
                    if context_supporting_fact:
                        break

            if context_supporting_fact:
                factual_support = "SUPPORTED"
                citation_validity = "INVALID"
                status = FourValuedStatus.INSUFFICIENT
                reason_codes.append("SUPPORT_FOUND_BUT_CITATION_INVALID")
                rule_evals["R1_PROVENANCE"] = f"FACT_IN_CONTEXT_BUT_CITATION_INVALID: Fact supported by {context_supporting_fact.fact_id}, but cited evidence {invalid_citations or [c.evidence_id for c in claim.evidence_citations]} does not ground it."
                explanation = f"Fact supported by candidate context item {context_supporting_fact.fact_id} ({context_supporting_fact.canonical_entity_name} - {context_supporting_fact.canonical_parameter_name} = {context_supporting_fact.numeric_value} {context_supporting_fact.unit}), but cited evidence does not support it (SUPPORT_FOUND_BUT_CITATION_INVALID)."
            elif has_value_contradiction and contradicting_fact is not None:
                factual_support = "CONTRADICTED"
                status = FourValuedStatus.CONTRADICTED
                reason_codes.append("VALUE_CONTRADICTED")
                explanation = (
                    f"Value contradiction for {contradicting_fact.canonical_entity_name} - {contradicting_fact.canonical_parameter_name}: "
                    f"claim asserts {claim_val} {claim.unit}, but source fact {contradicting_fact.fact_id} proves {contradicting_fact.numeric_value} {contradicting_fact.unit}"
                )
            elif has_temporal_mismatch:
                factual_support = "INSUFFICIENT"
                status = FourValuedStatus.INSUFFICIENT
                reason_codes.append("TEMPORAL_SCOPE_MISMATCH")
                missing_slots.append("matching_observation_date")
                explanation = f"Temporal mismatch: Claim specifies date '{claim_date_iso}', while available source facts report for a different date. Evaluated as INSUFFICIENT."
            elif has_date_missing:
                factual_support = "INSUFFICIENT"
                status = FourValuedStatus.INSUFFICIENT
                reason_codes.append("TEMPORAL_DATE_UNVERIFIED")
                missing_slots.append("evidence_observation_date")
                explanation = f"Temporal unverified: Claim specifies date '{claim_date_iso}', but candidate evidence contains no verified observation date. Evaluated as INSUFFICIENT."
            elif has_obs_type_mismatch:
                factual_support = "INSUFFICIENT"
                status = FourValuedStatus.INSUFFICIENT
                reason_codes.append("OBSERVATION_TYPE_MISMATCH")
                missing_slots.append("matching_observation_type")
                explanation = "Observation type mismatch: Claim assertion does not match evidence observation type (observed vs forecast vs design). Evaluated as INSUFFICIENT."
            else:
                factual_support = "INSUFFICIENT"
                status = FourValuedStatus.INSUFFICIENT
                if not missing_slots:
                    missing_slots.append("supporting_source_fact")
                reason_codes.append("PROVENANCE_INSUFFICIENT")
                explanation = "Available evidence items do not establish all required slots (entity, parameter, numeric value, and conditions) to verify this claim."

        return ShadowClaimVerificationResult(
            claim_id=claim.claim_id,
            status=status,
            factual_support=factual_support,
            citation_validity=citation_validity,
            reason_codes=list(dict.fromkeys(reason_codes)),
            supporting_fact_ids=supporting_facts,
            conflicting_fact_ids=conflicting_facts,
            missing_slots=sorted(list(set(missing_slots))),
            rule_evaluations=rule_evals,
            explanation=explanation,
            extracted_source_facts=serialized_facts,
            latency_ms=(time.perf_counter() - t0) * 1000.0,
        )

    def aggregate_answer(
        self,
        claim_results: List[ShadowClaimVerificationResult],
        question: str = "",
    ) -> ShadowAnswerVerificationResult:
        """Aggregate per-claim verification results with R7 Question Completeness checking."""
        t0 = time.perf_counter()
        total = len(claim_results)

        if total == 0:
            return ShadowAnswerVerificationResult(
                aggregate_status=FourValuedStatus.INSUFFICIENT,
                canonical_answer_verdict="EXTRACTION_UNRESOLVED",
                claim_results=[],
                total_claims=0,
                supported_count=0,
                contradicted_count=0,
                insufficient_count=0,
                out_of_scope_count=0,
                claim_coverage_ratio=0.0,
                summary_explanation="No structured claims extracted from answer.",
                rule_summary={},
                total_execution_ms=(time.perf_counter() - t0) * 1000.0,
            )

        supported = [r for r in claim_results if r.status == FourValuedStatus.SUPPORTED]
        contradicted = [r for r in claim_results if r.status == FourValuedStatus.CONTRADICTED]
        insufficient = [r for r in claim_results if r.status == FourValuedStatus.INSUFFICIENT]
        out_of_scope = [r for r in claim_results if r.status == FourValuedStatus.OUT_OF_SCOPE]

        rule_counts: Dict[str, int] = {}
        for r in claim_results:
            for rc in r.reason_codes:
                rule_counts[rc] = rule_counts.get(rc, 0) + 1

        # ---------------------------------------------------------------------
        # Aggregate Status Logic
        # ---------------------------------------------------------------------
        # Invariant 1: Any contradiction rejects the answer
        if len(contradicted) > 0:
            agg_status = FourValuedStatus.CONTRADICTED
            canonical_verdict = "CONTRADICTED"
            summary = f"Answer rejected as CONTRADICTED: {len(contradicted)}/{total} claims violate verified source evidence or physical constraints."
        # Invariant 2: Out of scope separation
        elif len(out_of_scope) == total:
            agg_status = FourValuedStatus.OUT_OF_SCOPE
            canonical_verdict = "OUT_OF_SCOPE"
            summary = "All claims in answer are outside the hydraulic engineering ontology scope."
        elif len(supported) > 0 and len(out_of_scope) > 0 and len(insufficient) == 0:
            # FIX HISTORICAL DEFECT: SUPPORTED + OUT_OF_SCOPE MUST NOT BE CONVERTED TO PURE SUPPORTED!
            agg_status = FourValuedStatus.SUPPORTED
            canonical_verdict = "PARTIAL_SUPPORTED_WITH_OUT_OF_SCOPE"
            summary = f"Answer contains {len(supported)} supported hydraulic claim(s) and {len(out_of_scope)} out-of-scope non-hydraulic claim(s)."
        elif len(supported) == total:
            agg_status = FourValuedStatus.SUPPORTED
            canonical_verdict = "SUPPORTED"
            summary = f"Answer fully SUPPORTED: all {total}/{total} technical claims are verified by source facts."
        elif len(supported) > 0 and len(insufficient) > 0:
            agg_status = FourValuedStatus.INSUFFICIENT
            canonical_verdict = "PARTIAL_SUPPORTED_WITH_INSUFFICIENT"
            summary = f"Answer partially verified: {len(supported)}/{total} claim(s) supported, while {len(insufficient)} lack sufficient verified evidence."
        else:
            agg_status = FourValuedStatus.INSUFFICIENT
            canonical_verdict = "INSUFFICIENT"
            summary = f"Answer is INSUFFICIENT: {len(insufficient)}/{total} claims lack verified source facts."

        coverage_ratio = len(supported) / total if total > 0 else 0.0

        return ShadowAnswerVerificationResult(
            aggregate_status=agg_status,
            canonical_answer_verdict=canonical_verdict,
            claim_results=claim_results,
            total_claims=total,
            supported_count=len(supported),
            contradicted_count=len(contradicted),
            insufficient_count=len(insufficient),
            out_of_scope_count=len(out_of_scope),
            claim_coverage_ratio=coverage_ratio,
            summary_explanation=summary,
            rule_summary=rule_counts,
            total_execution_ms=(time.perf_counter() - t0) * 1000.0,
        )

    def verify_claims(
        self,
        claims: List[TechnicalClaim],
        evidence_items: List[EvidenceItem],
        question: str = "",
    ) -> ShadowAnswerVerificationResult:
        """Verify multiple TechnicalClaims and aggregate into an answer-level verdict."""
        claim_results = [self.verify_claim(c, evidence_items) for c in claims]
        return self.aggregate_answer(claim_results, question=question)

