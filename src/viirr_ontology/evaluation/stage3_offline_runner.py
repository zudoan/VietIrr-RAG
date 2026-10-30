"""Offline Evaluation Runner for Stage 3 Sprint A: Evidence-Targeted Correction MVP.

Compares:
1. Same-case Baseline (S2.4 Ontology Verifier without correction).
2. Evidence-Targeted Correction (Planner + Narrow Adapter + Reassembly + Reverification).
3. Fair Matched-Case Untargeted Retrieval (Generic claim-based query over the EXACT SAME candidate pool).

Strictly separates:
- Engineering correctness (unit tests passing).
- Synthetic fixture agreement (expected developer fixture outcomes).
- Source-backed development observations (recorded corpus provenance pilot).
- Scientific evaluation (independent blind gold benchmark — explicitly pending).
"""

from __future__ import annotations

import copy
import csv
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from viirr_ontology.correction.executor import TargetedCorrectionExecutor, UntargetedCorrectionExecutor
from viirr_ontology.correction.models import CorrectionResult
from viirr_ontology.correction.planner import EvidenceCorrectionPlanner
from viirr_ontology.correction.provenance import DocumentIdentityRegistry, StructuralRelationVerifier
from viirr_ontology.correction.retrieval_adapter import MockRetrievalBackend, PageRegionRetrievalAdapter
from viirr_ontology.schema.claim import ClaimCondition, ClaimPolarity, TechnicalClaim
from viirr_ontology.schema.evidence import EvidenceItem, EvidenceRelation, EvidenceSet
from viirr_ontology.verifier.models import ClaimVerificationStatus
from viirr_ontology.verifier.ontology_verifier import OntologyConstraintVerifier


@dataclass
class Stage3EvalCase:
    """Evaluation test case for Stage 3."""

    case_id: str
    scenario_name: str
    category: str  # "SYNTHETIC" or "SOURCE_BACKED"
    claim: TechnicalClaim
    initial_evidence_set: EvidenceSet
    shared_candidate_pool: list[EvidenceItem]
    expected_baseline_verdict: str
    expected_targeted_verdict: str
    expected_stop_reason: str
    description: str
    source_document: Optional[str] = None
    provenance_status: str = "SYNTHETIC_REGRESSION_FIXTURE"
    trusted_table_units: list[tuple[str, int, str, str]] = field(default_factory=list)


@dataclass
class Stage3CaseResult:
    """Individual evaluated case trace."""

    case_id: str
    scenario_name: str
    category: str
    description: str
    baseline_verdict: str
    targeted_verdict: str
    untargeted_verdict: str
    expected_targeted_verdict: str
    fixture_agreement: bool
    stop_reason: str
    attempts_count: int
    newly_retrieved_evidence_ids: list[str]
    missing_slots_initial: list[str]
    missing_slots_remaining: list[str]
    corrected_slots: list[str]
    provenance_valid: bool
    latency_baseline_ms: float
    latency_correction_ms: float
    total_latency_ms: float = 0.0
    retrieval_calls: int = 0
    verifier_calls: int = 0
    provenance_status: str = "SYNTHETIC_REGRESSION_FIXTURE"
    targeted_candidates_inspected: int = 0
    targeted_candidates_admitted: int = 0
    untargeted_retrieval_calls: int = 0
    untargeted_candidates_inspected: int = 0
    untargeted_candidates_admitted: int = 0
    untargeted_verifier_calls: int = 0
    untargeted_stop_reason: str = ""


def _item(
    evidence_id: str,
    text: str,
    doc_id: str = "DOC_740",
    page: int = 1,
    metadata: Optional[dict[str, Any]] = None,
    document_number: Optional[str] = None,
    document_version: Optional[str] = None,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        doc_id=doc_id,
        page_id=f"P{page}",
        page_number=page,
        text=text,
        provenance_metadata=metadata or {},
        document_number=document_number,
        document_version=document_version,
    )


def build_evaluation_cases() -> list[Stage3EvalCase]:
    """Build the 13 evaluation cases with an identical shared candidate pool for fair comparison."""
    cases: list[Stage3EvalCase] = []

    # Case 1: Missing table header -> corrected after retrieval via verified structural table_id
    c1_claim = TechnicalClaim(
        claim_id="C1_HEADER",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_ROW"],
    )
    c1_init_ev = EvidenceSet("Q1", [_item("E_ROW", "Hồ Hòa Bình | 117 m", page=12, metadata={"table_id": "TAB_SPECS"})])
    c1_header = _item(
        "E_HEADER",
        "Bảng thông số kỹ thuật tiêu đề cột: Mực nước dâng bình thường (m)",
        page=12,
        metadata={"table_id": "TAB_SPECS"},
    )
    c1_distractor = _item("E_DISTRACT_1", "Hồ Hòa Bình là công trình thủy điện lớn trên sông Đà.")
    cases.append(Stage3EvalCase(
        case_id="SYN_01",
        scenario_name="Missing table header (verified table structure)",
        category="SYNTHETIC",
        claim=c1_claim,
        initial_evidence_set=c1_init_ev,
        shared_candidate_pool=[c1_header, c1_distractor],
        expected_baseline_verdict="INSUFFICIENT",
        expected_targeted_verdict="SUPPORTED",
        expected_stop_reason="SUPPORTED_REACHED",
        description="Fragment row lacks parameter name; targeted retrieval finds header sharing verified table_id TAB_SPECS.",
        trusted_table_units=[("DOC_740", 12, "E_ROW", "TAB_SPECS"), ("DOC_740", 12, "E_HEADER", "TAB_SPECS")],
    ))

    # Case 2: Missing technical unit -> corrected after retrieval
    c2_claim = TechnicalClaim(
        claim_id="C2_UNIT",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_NO_UNIT"],
    )
    c2_init_ev = EvidenceSet("Q2", [_item("E_NO_UNIT", "Hồ Hòa Bình mực nước dâng bình thường: 117")])
    c2_unit = _item("E_UNIT", "Ghi chú đơn vị đo: Mực nước dâng bình thường hồ Hòa Bình tính bằng mét (m), cụ thể hồ Hòa Bình mực nước dâng bình thường: 117 m.")
    c2_distractor = _item("E_DISTRACT_2", "Các hồ chứa lớn tại miền Bắc gồm Hòa Bình, Thác Bà, Tuyên Quang.")
    cases.append(Stage3EvalCase(
        case_id="SYN_02",
        scenario_name="Missing technical unit",
        category="SYNTHETIC",
        claim=c2_claim,
        initial_evidence_set=c2_init_ev,
        shared_candidate_pool=[c2_unit, c2_distractor],
        expected_baseline_verdict="INSUFFICIENT",
        expected_targeted_verdict="SUPPORTED",
        expected_stop_reason="SUPPORTED_REACHED",
        description="Evidence has numeric value but unit is absent; targeted retrieval supplies unit.",
    ))

    # Case 3: Missing applicability condition -> corrected after retrieval
    c3_claim = TechnicalClaim(
        claim_id="C3_COND",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m khi ngưỡng >= 85 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="GE", value="85", unit="m")],
        evidence_ids=["E_VAL_ONLY"],
    )
    c3_init_ev = EvidenceSet("Q3", [_item("E_VAL_ONLY", "Hồ Hòa Bình có mực nước dâng bình thường 117 m.")])
    c3_cond = _item("E_COND", "Hồ Hòa Bình có mực nước dâng bình thường 117 m khi mực nước hồ từ 85 m trở lên.")
    c3_distractor = _item("E_DISTRACT_3", "Quy trình vận hành liên hồ chứa trên lưu vực sông Hồng.")
    cases.append(Stage3EvalCase(
        case_id="SYN_03",
        scenario_name="Missing applicability condition",
        category="SYNTHETIC",
        claim=c3_claim,
        initial_evidence_set=c3_init_ev,
        shared_candidate_pool=[c3_cond, c3_distractor],
        expected_baseline_verdict="INSUFFICIENT",
        expected_targeted_verdict="SUPPORTED",
        expected_stop_reason="SUPPORTED_REACHED",
        description="Claim asserts operational threshold GE 85 m; retrieval adds qualifying condition paragraph.",
    ))

    # Case 4: Missing legal actor/action rule -> corrected after retrieval
    c4_claim = TechnicalClaim(
        claim_id="C4_LEGAL",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai có thẩm quyền quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E_MEETING"],
    )
    c4_init_ev = EvidenceSet("Q4", [_item("E_MEETING", "Chủ tịch UBND tỉnh Đồng Nai đã chủ trì cuộc họp ứng phó thiên tai.")])
    c4_auth = _item("E_AUTH", "Chủ tịch UBND tỉnh Đồng Nai có thẩm quyền quyết định xả lũ khẩn cấp trong trường hợp đặc biệt.")
    c4_distractor = _item("E_DISTRACT_4", "Quy định chung về chế độ trực ban mùa lũ của Ban chỉ huy.")
    cases.append(Stage3EvalCase(
        case_id="SYN_04",
        scenario_name="Missing legal authority rule",
        category="SYNTHETIC",
        claim=c4_claim,
        initial_evidence_set=c4_init_ev,
        shared_candidate_pool=[c4_auth, c4_distractor],
        expected_baseline_verdict="INSUFFICIENT",
        expected_targeted_verdict="SUPPORTED",
        expected_stop_reason="SUPPORTED_REACHED",
        description="Meeting mention does not confer legal authority; targeted retrieval supplies explicit authority article.",
    ))

    # Case 5: Missing document version -> corrected after retrieval
    c5_claim = TechnicalClaim(
        claim_id="C5_VER",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        document_scope="740/QĐ-TTg",
        evidence_ids=["E_AMEND"],
    )
    c5_init_ev = EvidenceSet("Q5", [_item("E_AMEND", "Theo Quyết định số 922/QĐ-TTg, quy trình vận hành hồ Hòa Bình được sửa đổi bổ sung năm 2024.", doc_id="922/QĐ-TTg")])
    c5_ver = _item("E_VER", "Quyết định 740/QĐ-TTg ban hành quy trình vận hành liên hồ sông Hồng, hồ Hòa Bình có mực nước dâng bình thường 117 m.", doc_id="740/QĐ-TTg", document_number="740/QĐ-TTg")
    c5_distractor = _item("E_DISTRACT_5", "Các văn bản pháp luật về tài nguyên nước hiện hành.", doc_id="DOC_OTHER")
    cases.append(Stage3EvalCase(
        case_id="SYN_05",
        scenario_name="Missing document version",
        category="SYNTHETIC",
        claim=c5_claim,
        initial_evidence_set=c5_init_ev,
        shared_candidate_pool=[c5_ver, c5_distractor],
        expected_baseline_verdict="INSUFFICIENT",
        expected_targeted_verdict="SUPPORTED",
        expected_stop_reason="SUPPORTED_REACHED",
        description="Initial item belongs to another decision; retrieval supplies authoritative version 740/QĐ-TTg.",
    ))

    # Case 6: Retrieval returns unrelated evidence -> remain INSUFFICIENT
    c6_claim = TechnicalClaim(
        claim_id="C6_UNREL",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_EMPTY"],
    )
    c6_init_ev = EvidenceSet("Q6", [_item("E_EMPTY", "Báo cáo khí tượng thủy văn khu vực Bắc Bộ.")])
    c6_unrel = _item("E_UNREL", "Dự báo thời tiết ngày mai trời có mưa rào rải rác.")
    cases.append(Stage3EvalCase(
        case_id="SYN_06",
        scenario_name="Retrieval returns unrelated evidence",
        category="SYNTHETIC",
        claim=c6_claim,
        initial_evidence_set=c6_init_ev,
        shared_candidate_pool=[c6_unrel],
        expected_baseline_verdict="INSUFFICIENT",
        expected_targeted_verdict="INSUFFICIENT",
        expected_stop_reason="NO_NEW_EVIDENCE",
        description="Retrieved evidence is irrelevant weather news; claim safely remains INSUFFICIENT.",
    ))

    # Case 7: Retrieval returns conflicting evidence -> CONTRADICTED (no false SUPPORT)
    c7_claim = TechnicalClaim(
        claim_id="C7_CONFLICT",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_INIT"],
    )
    c7_init_ev = EvidenceSet("Q7", [_item("E_INIT", "Tài liệu giới thiệu chung về hệ thống bậc thang sông Đà.")])
    c7_conflict = _item("E_CONFLICT", "Hồ Hòa Bình có mực nước dâng bình thường 120 m theo hồ sơ thiết kế ban đầu.")
    cases.append(Stage3EvalCase(
        case_id="SYN_07",
        scenario_name="Retrieval returns conflicting evidence",
        category="SYNTHETIC",
        claim=c7_claim,
        initial_evidence_set=c7_init_ev,
        shared_candidate_pool=[c7_conflict],
        expected_baseline_verdict="INSUFFICIENT",
        expected_targeted_verdict="CONTRADICTED",
        expected_stop_reason="CONTRADICTION_DISCOVERED",
        description="Retrieved evidence establishes 120 m contradicting 117 m; halts and returns CONTRADICTED.",
    ))

    # Case 8: No new evidence -> stop immediately
    c8_claim = TechnicalClaim(
        claim_id="C8_NONEW",
        claim_text="Hồ Thác Bà có dung tích toàn bộ 2.49 tỷ m3",
        subject="Hồ Thác Bà",
        parameter="Dung tích toàn bộ",
        value="2.49",
        unit="tỷ m3",
        evidence_ids=["E_DOC8"],
    )
    c8_init_ev = EvidenceSet("Q8", [_item("E_DOC8", "Hồ Thác Bà nằm trên sông Chảy.")])
    cases.append(Stage3EvalCase(
        case_id="SYN_08",
        scenario_name="No new evidence returned",
        category="SYNTHETIC",
        claim=c8_claim,
        initial_evidence_set=c8_init_ev,
        shared_candidate_pool=[],
        expected_baseline_verdict="INSUFFICIENT",
        expected_targeted_verdict="INSUFFICIENT",
        expected_stop_reason="NO_NEW_EVIDENCE",
        description="Retrieval index returns zero hits; loop stops without burning budget.",
    ))

    # Case 9: Repeated same evidence -> avoid redundant retries
    c9_claim = TechnicalClaim(
        claim_id="C9_REPEAT",
        claim_text="Hồ Hòa Bình có mực nước chết 80 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước chết",
        value="80",
        unit="m",
        evidence_ids=["E_ALREADY"],
    )
    c9_item = _item("E_ALREADY", "Hồ Hòa Bình có mực nước chết.")
    c9_init_ev = EvidenceSet("Q9", [c9_item])
    cases.append(Stage3EvalCase(
        case_id="SYN_09",
        scenario_name="Repeated same evidence deduplicated",
        category="SYNTHETIC",
        claim=c9_claim,
        initial_evidence_set=c9_init_ev,
        shared_candidate_pool=[c9_item],
        expected_baseline_verdict="INSUFFICIENT",
        expected_targeted_verdict="INSUFFICIENT",
        expected_stop_reason="NO_NEW_EVIDENCE",
        description="Retriever returns already seen item; executor filters it out and halts loop.",
    ))

    # Case 10: Invalid citation after correction -> reject provenance
    c10_claim = TechnicalClaim(
        claim_id="C10_INVCIT",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_CORRUPT"],
    )
    c10_init_ev = EvidenceSet("Q10", [_item("E_CORRUPT", "Dữ liệu ban đầu.")])
    c10_corrupt = EvidenceItem("E_BAD", "", "P1", 1, text="117 m")
    cases.append(Stage3EvalCase(
        case_id="SYN_10",
        scenario_name="Invalid citation / corrupt provenance rejected",
        category="SYNTHETIC",
        claim=c10_claim,
        initial_evidence_set=c10_init_ev,
        shared_candidate_pool=[c10_corrupt],
        expected_baseline_verdict="INSUFFICIENT",
        expected_targeted_verdict="INSUFFICIENT",
        expected_stop_reason="UNRESOLVED_DOCUMENT_SCOPE_CONFLICT",
        description="Retrieved item lacks doc_id; fails provenance check and is rejected without citation addition.",
    ))

    # Case 11: Retrieval result from another document -> enforce exact scope
    c11_claim = TechnicalClaim(
        claim_id="C11_SCOPE",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        document_scope="DOC_A",
        evidence_ids=["E_DOC_A"],
    )
    c11_init_ev = EvidenceSet("Q11", [_item("E_DOC_A", "DOC_A nói về quy hoạch chung.", doc_id="DOC_A")])
    c11_item_b = _item("E_DOC_B", "Hồ Hòa Bình có mực nước dâng bình thường 117 m.", doc_id="DOC_A_EVIL")
    cases.append(Stage3EvalCase(
        case_id="SYN_11",
        scenario_name="Cross-document retrieval rejected (exact scope)",
        category="SYNTHETIC",
        claim=c11_claim,
        initial_evidence_set=c11_init_ev,
        shared_candidate_pool=[c11_item_b],
        expected_baseline_verdict="INSUFFICIENT",
        expected_targeted_verdict="INSUFFICIENT",
        expected_stop_reason="UNRESOLVED_DOCUMENT_SCOPE_CONFLICT",
        description="Scope is locked to DOC_A; candidate from DOC_A_EVIL is rejected under exact scope enforcement.",
    ))

    # Case 12: Multiple claims with different missing slots
    c12_claim = TechnicalClaim(
        claim_id="C12_MULTI",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m khi mực nước >= 85 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="GE", value="85", unit="m")],
        evidence_ids=["E_VAL_NO_COND"],
    )
    c12_init_ev = EvidenceSet("Q12", [_item("E_VAL_NO_COND", "Hồ Hòa Bình có mực nước dâng bình thường 117 m.")])
    c12_cond = _item("E_COND12", "Hồ Hòa Bình có mực nước dâng bình thường 117 m khi mực nước từ 85 m trở lên.")
    cases.append(Stage3EvalCase(
        case_id="SYN_12",
        scenario_name="Multiple claims maintaining separate plans",
        category="SYNTHETIC",
        claim=c12_claim,
        initial_evidence_set=c12_init_ev,
        shared_candidate_pool=[c12_cond],
        expected_baseline_verdict="INSUFFICIENT",
        expected_targeted_verdict="SUPPORTED",
        expected_stop_reason="SUPPORTED_REACHED",
        description="Multi-claim pipeline maintains independent missing-slot plan per claim.",
    ))

    # Case 13: Source-backed development pilot case (Quy trình 740/QĐ-TTg liên hồ sông Hồng)
    src_claim = TechnicalClaim(
        claim_id="SRC_01_HOABINH_MNC",
        claim_text="Hồ Hòa Bình có mực nước chết 80 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước chết",
        value="80",
        unit="m",
        document_scope="740/QĐ-TTg",
        evidence_ids=["E_SRC_INTRO"],
    )
    src_init_ev = EvidenceSet(
        "Q_SRC_01",
        [
            EvidenceItem(
                evidence_id="E_SRC_INTRO",
                doc_id="740/QĐ-TTg",
                page_id="P1",
                page_number=1,
                text="Quy trình vận hành liên hồ chứa trên lưu vực sông Hồng ban hành kèm Quyết định 740/QĐ-TTg.",
                document_number="740/QĐ-TTg",
            )
        ],
    )
    src_param_item = EvidenceItem(
        evidence_id="E_SRC_PARAM_TABLE",
        doc_id="740/QĐ-TTg",
        page_id="P4",
        page_number=4,
        text="Bảng thông số kỹ thuật chính: Hồ Hòa Bình có mực nước chết là 80 m, mực nước dâng bình thường là 117 m.",
        document_number="740/QĐ-TTg",
    )
    cases.append(Stage3EvalCase(
        case_id="SRC_01",
        scenario_name="Source-backed development pilot (740/QĐ-TTg)",
        category="SOURCE_BACKED",
        claim=src_claim,
        initial_evidence_set=src_init_ev,
        shared_candidate_pool=[src_param_item],
        expected_baseline_verdict="INSUFFICIENT",
        expected_targeted_verdict="SUPPORTED",
        expected_stop_reason="SUPPORTED_REACHED",
        description="Recorded provenance from Decision 740/QĐ-TTg; intro lacks dead water level, table retrieval completes support.",
        source_document="740/QĐ-TTg",
        provenance_status="SOURCE_RECORD_VERIFIED_STANDALONE",
    ))

    return cases


class Stage3OfflineEvaluationRunner:
    """Runs reproducible offline comparative evaluations for Stage 3."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.verifier = OntologyConstraintVerifier()
        self.planner = EvidenceCorrectionPlanner()
        self.output_dir = output_dir or Path("reports/STAGE3/S3_A/eval_results")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run_case(self, case: Stage3EvalCase) -> Stage3CaseResult:
        """Run an individual evaluation case across baseline, targeted correction, and fair untargeted retrieval."""
        # 1. Baseline Run (Verifier only without correction)
        t0 = time.perf_counter()
        initial_vr = self.verifier.verify_single_claim(case.claim, case.initial_evidence_set)
        t_base = (time.perf_counter() - t0) * 1000.0

        baseline_verdict = initial_vr.status.value
        missing_slots_initial = list(initial_vr.missing_evidence_slots)

        # 2. Targeted Correction Run (Queries derived from missing slots over shared candidate pool)
        backend_targeted = MockRetrievalBackend()
        backend_targeted.register_candidate_pool(case.shared_candidate_pool)
        targeted_adapter = PageRegionRetrievalAdapter(backend_targeted)
        targeted_executor = TargetedCorrectionExecutor(
            verifier=self.verifier,
            retrieval_adapter=targeted_adapter,
            planner=self.planner,
        )
        for doc_id, p_num, ev_id, tab_id in case.trusted_table_units:
            targeted_executor.register_trusted_table_unit(doc_id, p_num, ev_id, tab_id)

        t1 = time.perf_counter()
        targeted_res: CorrectionResult = targeted_executor.correct_claim(
            claim=case.claim,
            evidence_set=case.initial_evidence_set,
            budget=2,
        )
        t_corr = (time.perf_counter() - t1) * 1000.0

        targeted_verdict = targeted_res.final_status
        missing_slots_remaining = (
            list(targeted_res.final_verification_result.missing_evidence_slots)
            if targeted_res.final_verification_result
            else []
        )
        corrected_slots = list(targeted_res.corrected_missing_slots)

        # 3. Fair Matched-Budget Untargeted Retrieval (Through UntargetedCorrectionExecutor with matching budget=2, top_k=3)
        backend_untargeted = MockRetrievalBackend()
        backend_untargeted.register_candidate_pool(case.shared_candidate_pool)
        untargeted_adapter = PageRegionRetrievalAdapter(backend_untargeted)
        untargeted_executor = UntargetedCorrectionExecutor(
            verifier=self.verifier,
            retrieval_adapter=untargeted_adapter,
            planner=self.planner,
        )
        for doc_id, p_num, ev_id, tab_id in case.trusted_table_units:
            untargeted_executor.register_trusted_table_unit(doc_id, p_num, ev_id, tab_id)

        untargeted_res = untargeted_executor.correct_claim(
            claim=case.claim,
            evidence_set=case.initial_evidence_set,
            budget=2,
        )
        untargeted_verdict = untargeted_res.final_status

        fixture_agreement = (targeted_verdict == case.expected_targeted_verdict)
        provenance_valid = all(a.provenance_valid for a in targeted_res.attempts) if targeted_res.attempts else True

        return Stage3CaseResult(
            case_id=case.case_id,
            scenario_name=case.scenario_name,
            category=case.category,
            description=case.description,
            baseline_verdict=baseline_verdict,
            targeted_verdict=targeted_verdict,
            untargeted_verdict=untargeted_verdict,
            expected_targeted_verdict=case.expected_targeted_verdict,
            fixture_agreement=fixture_agreement,
            stop_reason=targeted_res.stop_reason,
            attempts_count=len(targeted_res.attempts),
            newly_retrieved_evidence_ids=targeted_res.newly_retrieved_evidence_ids,
            missing_slots_initial=missing_slots_initial,
            missing_slots_remaining=missing_slots_remaining,
            corrected_slots=corrected_slots,
            provenance_valid=provenance_valid,
            latency_baseline_ms=round(t_base, 2),
            latency_correction_ms=round(t_corr, 2),
            total_latency_ms=round(t_base + t_corr, 2),
            retrieval_calls=targeted_res.retrieval_calls,
            verifier_calls=targeted_res.verifier_calls,
            provenance_status=case.provenance_status,
            targeted_candidates_inspected=targeted_res.total_candidates_inspected,
            targeted_candidates_admitted=targeted_res.total_candidates_admitted,
            untargeted_retrieval_calls=untargeted_res.retrieval_calls,
            untargeted_candidates_inspected=untargeted_res.total_candidates_inspected,
            untargeted_candidates_admitted=untargeted_res.total_candidates_admitted,
            untargeted_verifier_calls=untargeted_res.verifier_calls,
            untargeted_stop_reason=untargeted_res.stop_reason,
        )

    def run_all(self) -> dict[str, Any]:
        """Execute all cases, compute metrics, and export artifacts."""
        cases = build_evaluation_cases()
        results: list[Stage3CaseResult] = []

        for c in cases:
            res = self.run_case(c)
            results.append(res)

        # Aggregate Statistics
        total_cases = len(results)
        agreement_count = sum(1 for r in results if r.fixture_agreement)
        agreement_rate = round(agreement_count / total_cases, 4) if total_cases else 0.0

        baseline_dist = {
            "SUPPORTED": sum(1 for r in results if r.baseline_verdict == "SUPPORTED"),
            "INSUFFICIENT": sum(1 for r in results if r.baseline_verdict == "INSUFFICIENT"),
            "CONTRADICTED": sum(1 for r in results if r.baseline_verdict == "CONTRADICTED"),
        }
        targeted_dist = {
            "SUPPORTED": sum(1 for r in results if r.targeted_verdict == "SUPPORTED"),
            "INSUFFICIENT": sum(1 for r in results if r.targeted_verdict == "INSUFFICIENT"),
            "CONTRADICTED": sum(1 for r in results if r.targeted_verdict == "CONTRADICTED"),
        }
        untargeted_dist = {
            "SUPPORTED": sum(1 for r in results if r.untargeted_verdict == "SUPPORTED"),
            "INSUFFICIENT": sum(1 for r in results if r.untargeted_verdict == "INSUFFICIENT"),
            "CONTRADICTED": sum(1 for r in results if r.untargeted_verdict == "CONTRADICTED"),
        }

        # Safety: false support count on non-supportable cases (Cases 6, 7, 8, 9, 10, 11)
        adversarial_cases = [r for r in results if r.expected_targeted_verdict != "SUPPORTED"]
        false_support_count = sum(1 for r in adversarial_cases if r.targeted_verdict == "SUPPORTED")
        false_support_rate = round(false_support_count / len(adversarial_cases), 4) if adversarial_cases else 0.0

        avg_latency_ms = round(sum(r.total_latency_ms for r in results) / total_cases, 2)
        avg_attempts = round(sum(r.attempts_count for r in results) / total_cases, 2)

        summary = {
            "evaluation_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "evaluation_tier": "OFFLINE_DEVELOPMENT_FIXTURE_EVALUATION",
            "evaluation_methodology": "MATCHED_CASE_SHARED_POOL",
            "methodology_note": (
                "Both targeted correction and untargeted retrieval access the EXACT SAME candidate pool, "
                "with identical budget, top-k, verifier constraints, and citation policies. "
                "Reported differences reflect query planning effectiveness, not artifact asymmetry."
            ),
            "scientific_disclaimer": (
                "These rates reflect agreement against labeled development fixtures and synthetic scenarios. "
                "They do NOT constitute independently adjudicated benchmark accuracy or proof of end-to-end "
                "scientific superiority over an uncorrected baseline."
            ),
            "total_cases": total_cases,
            "synthetic_cases_count": sum(1 for r in results if r.category == "SYNTHETIC"),
            "source_backed_cases_count": sum(1 for r in results if r.category == "SOURCE_BACKED"),
            "fixture_agreement_count": agreement_count,
            "fixture_agreement_rate": agreement_rate,
            "false_support_count": false_support_count,
            "false_support_rate": false_support_rate,
            "baseline_distribution": baseline_dist,
            "targeted_correction_distribution": targeted_dist,
            "untargeted_retrieval_distribution": untargeted_dist,
            "avg_latency_ms": avg_latency_ms,
            "avg_attempts": avg_attempts,
            "cases": [asdict(r) for r in results],
        }

        # Write JSON summary
        json_path = self.output_dir / "correction_summary.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        # Write CSV trace
        csv_path = self.output_dir / "correction_cases.csv"
        fieldnames = [
            "case_id", "scenario_name", "category", "baseline_verdict", "targeted_verdict",
            "untargeted_verdict", "expected_targeted_verdict", "fixture_agreement",
            "stop_reason", "attempts_count", "corrected_slots", "provenance_valid",
            "latency_baseline_ms", "latency_correction_ms", "total_latency_ms",
            "retrieval_calls", "verifier_calls", "provenance_status"
        ]
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in results:
                row = asdict(r)
                row["corrected_slots"] = ";".join(r.corrected_slots)
                writer.writerow(row)

        return summary


if __name__ == "__main__":
    runner = Stage3OfflineEvaluationRunner()
    res = runner.run_all()
    print(f"Evaluated {res['total_cases']} cases. Fixture agreement: {res['fixture_agreement_rate']*100}%")
    print(f"False support rate: {res['false_support_rate']*100}%")
    print(f"Targeted vs Untargeted SUPPORTED count: {res['targeted_correction_distribution']['SUPPORTED']} vs {res['untargeted_retrieval_distribution']['SUPPORTED']}")
