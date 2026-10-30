"""Offline Evaluation Runner for Stage 2.4.

Runs reproducible offline development checks on two explicitly non-gold suites:
- Category A: synthetic logic regression fixtures.
- Category B: source-backed development fixtures loaded from recorded corpus provenance.

Neither suite is an independently annotated benchmark. Reported rates are fixture
agreement, not scientific accuracy. P5 comparisons are NOT EVALUATED unless an
actual P5 execution result is supplied by a separate paired-run pipeline.

Computes:
- 3-way Precision, Recall, and F1 for SUPPORTED, CONTRADICTED, and INSUFFICIENT.
- 3x3 Confusion Matrix across gold vs predicted labels.
- False Acceptance (predicted SUPPORTED when gold is CONTRADICTED or INSUFFICIENT).
- False Rejection (predicted CONTRADICTED when gold is SUPPORTED).
- Abstention rate (INSUFFICIENT rate).
- Latency per claim, constraint coverage, and provenance trace coverage.
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from viirr_ontology.schema.claim import ClaimCondition, ClaimPolarity, TechnicalClaim
from viirr_ontology.schema.evidence import EvidenceItem, EvidenceRelation, EvidenceSet
from viirr_ontology.verifier.models import ClaimVerificationStatus, ReasonCode
from viirr_ontology.verifier.ontology_verifier import OntologyConstraintVerifier


@dataclass
class EvalCase:
    """Individual test case for offline evaluation."""

    case_id: str
    category: str
    claim: TechnicalClaim
    evidence_set: EvidenceSet
    expected_label: ClaimVerificationStatus
    p5_result: str = "NOT_EVALUATED"
    description: str = ""
    is_provisional: bool = True
    label_origin: str = "DEVELOPER_ASSIGNED_REGRESSION_EXPECTATION"
    source_provenance: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EvalCaseOutput:
    """Per-case evaluation record."""

    case_id: str
    category: str
    claim_id: str
    claim_text: str
    subject: str
    parameter: str
    expected_label: str
    p5_result: str
    s2_4_result: str
    is_correct: bool
    reason_codes: list[str]
    supporting_evidence_ids: list[str]
    conflicting_evidence_ids: list[str]
    missing_slots: list[str]
    checked_constraints: list[str]
    violated_constraints: list[str]
    latency_ms: float
    explanation: str
    label_origin: str
    source_provenance: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvaluationSummary:
    """Aggregate scientific metrics for an evaluation run."""

    suite_name: str
    total_cases: int
    correct_count: int
    agreement_rate: float
    label_status: str

    # Per-class metrics
    supported_metrics: dict[str, float]
    contradicted_metrics: dict[str, float]
    insufficient_metrics: dict[str, float]

    # Error metrics
    false_acceptance_count: int
    false_acceptance_rate: float
    false_rejection_count: int
    false_rejection_rate: float
    abstention_count: int
    abstention_rate: float

    # Confusion matrix: {gold_label: {pred_label: count}}
    confusion_matrix: dict[str, dict[str, int]]

    # System metrics
    mean_latency_ms: float
    constraint_coverage: float
    provenance_coverage: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OfflineEvaluationRunner:
    """Orchestrates offline evaluation runs for S2.4 claim verification."""

    def __init__(self, verifier: Optional[OntologyConstraintVerifier] = None) -> None:
        self.verifier = verifier or OntologyConstraintVerifier()

    # =========================================================================
    # Suite Loaders
    # =========================================================================

    def load_synthetic_suite(self) -> list[EvalCase]:
        """Category A: 22 deterministic synthetic adversarial & failure-mode cases."""
        cases: list[EvalCase] = []

        # 1. P5-KNOWN-01: Multi-word jurisdiction mismatch
        cases.append(
            EvalCase(
                case_id="SYNTH_01_P5_KNOWN_01_JUR_MISMATCH",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.CONTRADICTED,
                p5_result="PASS",  # P5 baseline historically passed this mistakenly
                description="P5-KNOWN-01: Multi-word jurisdiction mismatch (Đồng Nai vs Đồng Tháp)",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_01",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E_SYNTH_DN",
                            doc_id="DOC_GOV_DN",
                            page_id="P1",
                            page_number=1,
                            text="Ủy ban nhân dân tỉnh Đồng Nai có trách nhiệm phê duyệt phương án ứng phó thiên tai.",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_01",
                    claim_text="UBND tỉnh Đồng Tháp có trách nhiệm phê duyệt phương án ứng phó thiên tai",
                    subject="Ủy ban nhân dân tỉnh Đồng Tháp",
                    jurisdiction="tỉnh Đồng Tháp",
                    action="phê duyệt phương án ứng phó thiên tai",
                    evidence_ids=["E_SYNTH_DN"],
                ),
            )
        )

        # 2. P5-KNOWN-02: Negated legal action
        cases.append(
            EvalCase(
                case_id="SYNTH_02_P5_KNOWN_02_LEGAL_NEGATION",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.CONTRADICTED,
                p5_result="PASS",  # P5 baseline historically passed negated strings
                description="P5-KNOWN-02: Legal negation conflict",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_02",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E_SYNTH_AFFIRMED",
                            doc_id="IRR_CP_2019_ee0bca33",
                            page_id="P10",
                            page_number=10,
                            text="Bộ Tài nguyên và Môi trường quyết định phương án vận hành các hồ chứa để giảm lũ.",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_02",
                    claim_text="Bộ Tài nguyên và Môi trường không có thẩm quyền quyết định phương án vận hành các hồ chứa",
                    subject="Bộ Tài nguyên và Môi trường",
                    action="quyết định phương án vận hành",
                    polarity=ClaimPolarity.NEGATED,
                    evidence_ids=["E_SYNTH_AFFIRMED"],
                ),
            )
        )

        # 3. Correct reservoir and water-level
        cases.append(
            EvalCase(
                case_id="SYNTH_03_CORRECT_RESERVOIR_MNDBT",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.SUPPORTED,
                p5_result="PASS",
                description="Scenario 1: Correct reservoir and MNDBT",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_03",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E_HB_117",
                            doc_id="IRR_CP_2019_ee0bca33",
                            page_id="P4",
                            page_number=4,
                            text="Hồ Hòa Bình: mực nước dâng bình thường là 117.0 m.",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_03",
                    claim_text="Mực nước dâng bình thường hồ Hòa Bình là 117.0 m",
                    subject="Hồ Hòa Bình",
                    parameter="Mực nước dâng bình thường",
                    value="117.0",
                    unit="m",
                    evidence_ids=["E_HB_117"],
                ),
            )
        )

        # 4. Wrong reservoir, same numeric value
        cases.append(
            EvalCase(
                case_id="SYNTH_04_WRONG_RESERVOIR_SAME_VALUE",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.CONTRADICTED,
                p5_result="PASS",
                description="Scenario 2: Wrong reservoir with same numeric value (Sơn La vs Hòa Bình)",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_04",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E_HB_117_b",
                            doc_id="IRR_CP_2019_ee0bca33",
                            page_id="P4",
                            page_number=4,
                            text="Hồ Hòa Bình: mực nước dâng bình thường là 117.0 m.",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_04",
                    claim_text="Mực nước dâng bình thường hồ Sơn La là 117.0 m",
                    subject="Hồ Sơn La",
                    parameter="Mực nước dâng bình thường",
                    value="117.0",
                    unit="m",
                    evidence_ids=["E_HB_117_b"],
                ),
            )
        )

        # 5. Normal pool level confused with dead water level
        cases.append(
            EvalCase(
                case_id="SYNTH_05_MNDBT_CONFUSED_WITH_MNC",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.CONTRADICTED,
                p5_result="PASS",
                description="Scenario 3: Normal pool level confused with dead water level",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_05",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E_HB_MNC_80",
                            doc_id="IRR_CP_2019_ee0bca33",
                            page_id="P4",
                            page_number=4,
                            text="Hồ Hòa Bình có mực nước chết là 80,0 m.",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_05",
                    claim_text="Mực nước dâng bình thường của hồ Hòa Bình là 80.0 m",
                    subject="Hồ Hòa Bình",
                    parameter="Mực nước dâng bình thường",
                    value="80.0",
                    unit="m",
                    evidence_ids=["E_HB_MNC_80"],
                ),
            )
        )

        # 6. Correct number but wrong unit
        cases.append(
            EvalCase(
                case_id="SYNTH_06_WRONG_UNIT",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.CONTRADICTED,
                p5_result="PASS",
                description="Scenario 4: Correct number but wrong unit (117 m3/s instead of 117 m)",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_06",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E_HB_117_M",
                            doc_id="IRR_CP_2019_ee0bca33",
                            page_id="P4",
                            page_number=4,
                            text="Hồ Hòa Bình có mực nước dâng bình thường là 117.0 m.",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_06",
                    claim_text="Mực nước dâng bình thường của hồ Hòa Bình là 117.0 m3/s",
                    subject="Hồ Hòa Bình",
                    parameter="Mực nước dâng bình thường",
                    value="117.0",
                    unit="m3/s",
                    evidence_ids=["E_HB_117_M"],
                ),
            )
        )

        # 7. Correct unit wrong parameter
        cases.append(
            EvalCase(
                case_id="SYNTH_07_WRONG_PHYSICAL_PARAMETER",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.CONTRADICTED,
                p5_result="PASS",
                description="Scenario 5: Unit m3/s applied to water level concept",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_07",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E_HB_Q",
                            doc_id="IRR_CP_2019_ee0bca33",
                            page_id="P4",
                            page_number=4,
                            text="Lưu lượng xả lớn nhất của hồ Hòa Bình là 3500 m3/s.",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_07",
                    claim_text="Mực nước dâng bình thường của hồ Hòa Bình là 3500 m3/s",
                    subject="Hồ Hòa Bình",
                    parameter="Mực nước dâng bình thường",
                    value="3500",
                    unit="m3/s",
                    evidence_ids=["E_HB_Q"],
                ),
            )
        )

        # 8. Missing design condition
        cases.append(
            EvalCase(
                case_id="SYNTH_08_MISSING_DESIGN_CONDITION",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.INSUFFICIENT,
                p5_result="PASS",
                description="Scenario 6: Missing flood frequency condition",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_08",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E_HB_GENERAL",
                            doc_id="IRR_CP_2019_ee0bca33",
                            page_id="P5",
                            page_number=5,
                            text="Hồ Hòa Bình có mực nước cao nhất là 120.0 m.",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_08",
                    claim_text="Mực nước cao nhất với tần suất lũ thiết kế p=0.01% là 120.0 m",
                    subject="Hồ Hòa Bình",
                    parameter="Mực nước cao nhất",
                    value="120.0",
                    unit="m",
                    conditions=[ClaimCondition(operator="EQ", value="0.01", unit="%", raw_text="p=0.01%")],
                    evidence_ids=["E_HB_GENERAL"],
                ),
            )
        )

        # 9. Different design flood frequency
        cases.append(
            EvalCase(
                case_id="SYNTH_09_DIFFERENT_DESIGN_FREQUENCY",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.INSUFFICIENT,
                p5_result="PASS",
                description="Scenario 7: Different frequency is non-applicable evidence, not contradiction",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_09",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E_HB_FREQ_01",
                            doc_id="IRR_CP_2019_ee0bca33",
                            page_id="P5",
                            page_number=5,
                            text="Mực nước lũ thiết kế của hồ Hòa Bình ứng với tần suất p = 0.1 % là 120.0 m.",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_09",
                    claim_text="Mực nước lũ kiểm tra ứng với p=0.01% là 120.0 m",
                    subject="Hồ Hòa Bình",
                    parameter="Mực nước lũ",
                    value="120.0",
                    unit="m",
                    conditions=[ClaimCondition(operator="EQ", value="0.01", unit="%", raw_text="p=0.01%")],
                    evidence_ids=["E_HB_FREQ_01"],
                ),
            )
        )

        # 10. Table row separated from header
        cases.append(
            EvalCase(
                case_id="SYNTH_10_TABLE_ROW_UNLINKED",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.INSUFFICIENT,
                p5_result="ABSTAIN",
                description="Scenario 8: Table row unlinked from header",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_10",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E_ROW_ISOLATED",
                            doc_id="DOC_TABLE",
                            page_id="P1",
                            page_number=1,
                            content_type="table",
                            text="Hồ Hòa Bình | 117.0 | 80.0",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_10",
                    claim_text="Mực nước dâng bình thường của hồ Hòa Bình là 117.0 m",
                    subject="Hồ Hòa Bình",
                    parameter="Mực nước dâng bình thường",
                    value="117.0",
                    unit="m",
                    evidence_ids=["E_ROW_ISOLATED"],
                ),
            )
        )

        # 11. Multi-region complementary evidence synthesis
        cases.append(
            EvalCase(
                case_id="SYNTH_11_MULTI_REGION_SYNTHESIS",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.SUPPORTED,
                p5_result="PASS",
                description="Scenario 10: Multi-region evidence that collectively supports one claim",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_11",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E_HEADER_11",
                            doc_id="DOC_SPECS",
                            page_id="P2",
                            page_number=2,
                            content_type="table",
                            text="Bảng thông số: Mực nước dâng bình thường (m)",
                        ),
                        EvidenceItem(
                            evidence_id="E_ROW_11",
                            doc_id="DOC_SPECS",
                            page_id="P2",
                            page_number=2,
                            content_type="table",
                            text="Hồ Hòa Bình: 117.0",
                        ),
                    ],
                    evidence_relations=[
                        EvidenceRelation(
                            source_id="E_ROW_11",
                            target_id="E_HEADER_11",
                            relation_type="table_row_to_header",
                            verified=True,
                            provenance_source="layout_link",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_11",
                    claim_text="Mực nước dâng bình thường của hồ Hòa Bình là 117.0 m",
                    subject="Hồ Hòa Bình",
                    parameter="Mực nước dâng bình thường",
                    value="117.0",
                    unit="m",
                    evidence_ids=["E_ROW_11", "E_HEADER_11"],
                ),
            )
        )

        # 12. Cross-document mismatch
        cases.append(
            EvalCase(
                case_id="SYNTH_12_CROSS_DOC_MISMATCH",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.INSUFFICIENT,
                p5_result="ABSTAIN",
                description="Scenario 11: Evidence ID belongs to mismatched document",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_12",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E_DOC_B",
                            doc_id="DOC_B",
                            page_id="P1",
                            page_number=1,
                            text="Hồ Hòa Bình có mực nước dâng bình thường 117.0 m.",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_12",
                    claim_text="Mực nước dâng bình thường của hồ Hòa Bình là 117.0 m",
                    subject="Hồ Hòa Bình",
                    parameter="Mực nước dâng bình thường",
                    value="117.0",
                    unit="m",
                    document_scope="DOC_A",
                    evidence_ids=["E_DOC_B"],
                ),
            )
        )

        # 13. Conflicting document versions
        cases.append(
            EvalCase(
                case_id="SYNTH_13_DOC_VERSION_CONFLICT",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.CONTRADICTED,
                p5_result="PASS",
                description="Scenario 12: Conflicting document versions",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_13",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E_QD_922",
                            doc_id="IRR_CP_2025_2d3e4a1e",
                            page_id="P2",
                            page_number=2,
                            text="QĐ 922 sửa đổi Điều 5: Hồ Hòa Bình mực nước đón lũ là 105.0 m.",
                            document_number="922/QĐ-TTg",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_13",
                    claim_text="Mực nước đón lũ hồ Hòa Bình theo QĐ 922 là 101.0 m",
                    subject="Hồ Hòa Bình",
                    parameter="Mực nước đón lũ",
                    value="101.0",
                    unit="m",
                    document_scope="922/QĐ-TTg",
                    evidence_ids=["E_QD_922"],
                ),
            )
        )

        # 14. Unknown jurisdiction
        cases.append(
            EvalCase(
                case_id="SYNTH_14_UNKNOWN_JURISDICTION",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.INSUFFICIENT,
                p5_result="ABSTAIN",
                description="Scenario 15: Unknown jurisdiction not evidenced",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_14",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E_GEN_14",
                            doc_id="DOC_GEN",
                            page_id="P1",
                            page_number=1,
                            text="Ủy ban nhân dân chỉ đạo công tác cứu hộ cứu nạn.",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_14",
                    claim_text="Ủy ban nhân dân tỉnh X chỉ đạo công tác cứu hộ",
                    subject="Ủy ban nhân dân",
                    jurisdiction="tỉnh X",
                    action="chỉ đạo công tác cứu hộ",
                    evidence_ids=["E_GEN_14"],
                ),
            )
        )

        # 15. Ambiguous parameter phrase
        cases.append(
            EvalCase(
                case_id="SYNTH_15_AMBIGUOUS_PARAMETER",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.INSUFFICIENT,
                p5_result="ABSTAIN",
                description="Scenario 18: Ambiguous compound parameter phrase",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_15",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E_HB_PARAM",
                            doc_id="DOC_HB",
                            page_id="P1",
                            page_number=1,
                            text="Hồ Hòa Bình: mực nước dâng bình thường 117.0 m.",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_15",
                    claim_text="Mực nước dâng bình thường và mực nước chết là 117.0 m",
                    subject="Hồ Hòa Bình",
                    parameter="mực nước dâng bình thường và mực nước chết",
                    value="117.0",
                    unit="m",
                    evidence_ids=["E_HB_PARAM"],
                ),
            )
        )

        # 16. Malformed claim extraction
        cases.append(
            EvalCase(
                case_id="SYNTH_16_MALFORMED_CLAIM",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.INSUFFICIENT,
                p5_result="ABSTAIN",
                description="Scenario 20: Malformed or incomplete claim extraction",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_16",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E_ANY_16",
                            doc_id="DOC_1",
                            page_id="P1",
                            page_number=1,
                            text="Hồ Hòa Bình mực nước 117.0 m.",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_16",
                    claim_text="",
                    subject="",
                    parameter="",
                ),
            )
        )

        # 17-22: Direct physical bound checks & additional adversarial combinations
        cases.append(
            EvalCase(
                case_id="SYNTH_17_NEGATIVE_STORAGE",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.CONTRADICTED,
                p5_result="PASS",
                description="Structural physical constraint violation: negative storage volume",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_17",
                    evidence_items=[EvidenceItem(evidence_id="E17", doc_id="DOC17", page_id="P1", page_number=1, text="Hồ Hòa Bình.")],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_17",
                    claim_text="Dung tích toàn bộ hồ Hòa Bình là -15.0 triệu m3",
                    subject="Hồ Hòa Bình",
                    parameter="Dung tích toàn bộ",
                    value="-15.0",
                    unit="triệu m3",
                ),
            )
        )

        cases.append(
            EvalCase(
                case_id="SYNTH_18_UNIT_CONVERSION_SAFE",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.SUPPORTED,
                p5_result="PASS",
                description="Unit conversion safe check: 11700 cm == 117.0 m",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_18",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E18",
                            doc_id="DOC18",
                            page_id="P1",
                            page_number=1,
                            text="Hồ Hòa Bình có mực nước dâng bình thường là 117.0 m.",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_18",
                    claim_text="Mực nước dâng bình thường hồ Hòa Bình là 11700 cm",
                    subject="Hồ Hòa Bình",
                    parameter="Mực nước dâng bình thường",
                    value="11700",
                    unit="cm",
                    evidence_ids=["E18"],
                ),
            )
        )

        cases.append(
            EvalCase(
                case_id="SYNTH_19_DECIMAL_COMMA_CONVERSION",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.SUPPORTED,
                p5_result="PASS",
                description="Vietnamese decimal comma format: '117,0' matches '117.0'",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_19",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E19",
                            doc_id="DOC19",
                            page_id="P1",
                            page_number=1,
                            text="Hồ Hòa Bình có mực nước dâng bình thường 117,0 m.",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_19",
                    claim_text="Mực nước dâng bình thường hồ Hòa Bình là 117.0 m",
                    subject="Hồ Hòa Bình",
                    parameter="Mực nước dâng bình thường",
                    value="117.0",
                    unit="m",
                    evidence_ids=["E19"],
                ),
            )
        )

        cases.append(
            EvalCase(
                case_id="SYNTH_20_EMPTY_EVIDENCE_PROVENANCE_MISSING",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.INSUFFICIENT,
                p5_result="ABSTAIN",
                description="Absence of evidence produces INSUFFICIENT, not contradiction",
                evidence_set=EvidenceSet(query_id="Q_SYNTH_20", evidence_items=[]),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_20",
                    claim_text="Mực nước hồ Hòa Bình là 117.0 m",
                    subject="Hồ Hòa Bình",
                    parameter="Mực nước",
                    value="117.0",
                    unit="m",
                ),
            )
        )

        cases.append(
            EvalCase(
                case_id="SYNTH_21_DISCHARGE_SAFE_CONVERSION",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.SUPPORTED,
                p5_result="PASS",
                description="Safe discharge conversion: 3500 m3/s matches 3500 m³/s",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_21",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E21",
                            doc_id="DOC21",
                            page_id="P1",
                            page_number=1,
                            text="Hồ Hòa Bình lưu lượng xả lớn nhất là 3500 m³/s.",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_21",
                    claim_text="Lưu lượng xả lớn nhất hồ Hòa Bình là 3500 m3/s",
                    subject="Hồ Hòa Bình",
                    parameter="Lưu lượng xả lớn nhất",
                    value="3500",
                    unit="m3/s",
                    evidence_ids=["E21"],
                ),
            )
        )

        cases.append(
            EvalCase(
                case_id="SYNTH_22_AMENDED_STANDARD_SCOPING",
                category="CATEGORY_A_SYNTHETIC",
                expected_label=ClaimVerificationStatus.SUPPORTED,
                p5_result="PASS",
                description="QĐ 740 baseline provision remains valid where not amended by QĐ 922",
                evidence_set=EvidenceSet(
                    query_id="Q_SYNTH_22",
                    evidence_items=[
                        EvidenceItem(
                            evidence_id="E22",
                            doc_id="IRR_CP_2019_ee0bca33",
                            page_id="P4",
                            page_number=4,
                            text="Hồ Hòa Bình: mực nước dâng bình thường là 117.0 m theo Quyết định 740/QĐ-TTg.",
                            document_number="740/QĐ-TTg",
                        )
                    ],
                ),
                claim=TechnicalClaim(
                    claim_id="C_SYNTH_22",
                    claim_text="Mực nước dâng bình thường hồ Hòa Bình theo QĐ 740 là 117.0 m",
                    subject="Hồ Hòa Bình",
                    parameter="Mực nước dâng bình thường",
                    value="117.0",
                    unit="m",
                    document_scope="740/QĐ-TTg",
                    evidence_ids=["E22"],
                ),
            )
        )

        for case in cases:
            case.p5_result = "NOT_EVALUATED"
            case.label_origin = "DEVELOPER_ASSIGNED_SYNTHETIC_REGRESSION_EXPECTATION"
            case.is_provisional = True
            case.source_provenance = []
        return cases

    def load_source_backed_development_suite(
        self, fixture_path: Optional[Path | str] = None
    ) -> list[EvalCase]:
        """Load corpus-derived development fixtures with explicit, auditable provenance.

        Labels are development expectations derived from the displayed source text. They
        have not been independently adjudicated and therefore are not scientific gold.
        """
        path = Path(fixture_path) if fixture_path else (
            Path(__file__).resolve().parents[3]
            / "reports" / "STAGE2" / "S2_4" / "fixtures" / "source_backed_development.jsonl"
        )
        if not path.exists():
            return []

        cases: list[EvalCase] = []
        with open(path, "r", encoding="utf-8") as fixture_file:
            for line in fixture_file:
                if not line.strip():
                    continue
                record = json.loads(line)
                evidence_id = record["evidence_id"]
                evidence = EvidenceItem(
                    evidence_id=evidence_id,
                    doc_id=record["doc_id"],
                    page_id=record["page_id"],
                    page_number=int(record["page_number"]),
                    text=record["source_text"],
                    source=record["source_path"],
                    document_number=record.get("document_number"),
                    provenance_metadata={
                        "source_record_sha256": record["source_record_sha256"],
                        "excerpt_method": record["excerpt_method"],
                    },
                )
                claim_data = record["claim"]
                claim = TechnicalClaim.from_dict({
                    **claim_data,
                    "evidence_ids": [evidence_id],
                })
                cases.append(EvalCase(
                    case_id=record["case_id"],
                    category="CATEGORY_B_SOURCE_BACKED_DEVELOPMENT",
                    expected_label=ClaimVerificationStatus(record["expected_label"]),
                    description=record["description"],
                    evidence_set=EvidenceSet(
                        query_id=f"Q_{record['case_id']}",
                        evidence_items=[evidence],
                    ),
                    claim=claim,
                    p5_result="NOT_EVALUATED",
                    is_provisional=True,
                    label_origin=record["label_origin"],
                    source_provenance=[{
                        "doc_id": record["doc_id"],
                        "page_number": int(record["page_number"]),
                        "evidence_id": evidence_id,
                        "source_path": record["source_path"],
                        "source_record_sha256": record["source_record_sha256"],
                        "source_text": record["source_text"],
                    }],
                ))
        return cases

    def load_real_pilot_suite(self) -> list[EvalCase]:
        """Deprecated name retained only as a truthful source-backed loader."""
        return self.load_source_backed_development_suite()

    # =========================================================================
    # Evaluation Execution & Metrics
    # =========================================================================

    def run_suite(self, cases: list[EvalCase], suite_name: str = "Evaluation") -> tuple[list[EvalCaseOutput], EvaluationSummary]:
        """Execute verification across a suite of cases and compute scientific metrics."""
        case_outputs: list[EvalCaseOutput] = []
        latencies: list[float] = []
        constraint_evaluated_count = 0
        provenance_valid_count = 0

        # Confusion matrix: gold -> pred -> count
        confusion: dict[str, dict[str, int]] = {
            "SUPPORTED": {"SUPPORTED": 0, "CONTRADICTED": 0, "INSUFFICIENT": 0},
            "CONTRADICTED": {"SUPPORTED": 0, "CONTRADICTED": 0, "INSUFFICIENT": 0},
            "INSUFFICIENT": {"SUPPORTED": 0, "CONTRADICTED": 0, "INSUFFICIENT": 0},
        }

        correct_count = 0
        false_acceptance = 0
        false_rejection = 0
        abstention = 0

        for case in cases:
            start_t = time.perf_counter()
            res = self.verifier.verify_single_claim(case.claim, case.evidence_set)
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            latencies.append(elapsed_ms)

            pred_label = res.status.value
            gold_label = case.expected_label.value
            is_correct = (pred_label == gold_label)

            if is_correct:
                correct_count += 1

            confusion[gold_label][pred_label] += 1

            # Check false acceptance / false rejection / abstention
            if pred_label == "SUPPORTED" and gold_label in ("CONTRADICTED", "INSUFFICIENT"):
                false_acceptance += 1
            if pred_label == "CONTRADICTED" and gold_label == "SUPPORTED":
                false_rejection += 1
            if pred_label == "INSUFFICIENT":
                abstention += 1

            if res.checked_constraints or res.violated_constraints:
                constraint_evaluated_count += 1
            if res.provenance_trace or res.supporting_evidence_ids:
                provenance_valid_count += 1

            case_outputs.append(
                EvalCaseOutput(
                    case_id=case.case_id,
                    category=case.category,
                    claim_id=case.claim.claim_id,
                    claim_text=case.claim.claim_text,
                    subject=case.claim.subject,
                    parameter=case.claim.parameter,
                    expected_label=gold_label,
                    p5_result=case.p5_result,
                    s2_4_result=pred_label,
                    is_correct=is_correct,
                    reason_codes=res.reason_codes,
                    supporting_evidence_ids=res.supporting_evidence_ids,
                    conflicting_evidence_ids=res.conflicting_evidence_ids,
                    missing_slots=res.missing_evidence_slots,
                    checked_constraints=res.checked_constraints,
                    violated_constraints=res.violated_constraints,
                    latency_ms=round(elapsed_ms, 3),
                    explanation=res.explanation,
                    label_origin=case.label_origin,
                    source_provenance=case.source_provenance,
                )
            )

        total = len(cases)
        agreement_rate = correct_count / total if total > 0 else 0.0

        def calc_prf(label: str) -> dict[str, float]:
            tp = confusion[label][label]
            fp = sum(confusion[g][label] for g in confusion if g != label)
            fn = sum(confusion[label][p] for p in confusion[label] if p != label)
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
            return {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "support": tp + fn,
            }

        summary = EvaluationSummary(
            suite_name=suite_name,
            total_cases=total,
            correct_count=correct_count,
            agreement_rate=round(agreement_rate, 4),
            label_status="NOT_INDEPENDENT_GOLD",
            supported_metrics=calc_prf("SUPPORTED"),
            contradicted_metrics=calc_prf("CONTRADICTED"),
            insufficient_metrics=calc_prf("INSUFFICIENT"),
            false_acceptance_count=false_acceptance,
            false_acceptance_rate=round(false_acceptance / total, 4) if total > 0 else 0.0,
            false_rejection_count=false_rejection,
            false_rejection_rate=round(false_rejection / total, 4) if total > 0 else 0.0,
            abstention_count=abstention,
            abstention_rate=round(abstention / total, 4) if total > 0 else 0.0,
            confusion_matrix=confusion,
            mean_latency_ms=round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
            constraint_coverage=round(constraint_evaluated_count / total, 4) if total > 0 else 0.0,
            provenance_coverage=round(provenance_valid_count / total, 4) if total > 0 else 0.0,
        )

        return case_outputs, summary

    def run_all(self, output_dir: Optional[Path | str] = None) -> dict[str, Any]:
        """Run both Category A and Category B suites and persist JSON and CSV outputs."""
        synth_cases = self.load_synthetic_suite()
        real_cases = self.load_source_backed_development_suite()

        synth_outputs, synth_summary = self.run_suite(synth_cases, suite_name="Category_A_Synthetic_Logic")
        real_outputs, real_summary = self.run_suite(
            real_cases, suite_name="Category_B_Source_Backed_Development"
        )

        combined_outputs = synth_outputs + real_outputs
        combined_summary_dict = {
            "category_a_synthetic": synth_summary.to_dict(),
            "category_b_source_backed_development": real_summary.to_dict(),
            "overall_total_cases": len(combined_outputs),
            "overall_fixture_agreement_count": synth_summary.correct_count + real_summary.correct_count,
            "overall_fixture_agreement_rate": round(
                (synth_summary.correct_count + real_summary.correct_count) / len(combined_outputs), 4
            )
            if combined_outputs
            else 0.0,
            "scientific_accuracy": None,
            "scientific_evaluation_status": "NOT_EVALUATED_NO_INDEPENDENT_GOLD_LABELS",
            "p5_paired_comparison_status": "NOT_EVALUATED_NO_ACTUAL_P5_EXECUTION",
            "methodological_note": (
                "Rates are agreement with developer-assigned regression expectations, not benchmark accuracy. "
                "Source-backed cases are development fixtures and have not been independently adjudicated."
            ),
        }

        if output_dir:
            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)

            # 1. Write Summary JSON
            with open(out_path / "evaluation_summary.json", "w", encoding="utf-8") as f:
                json.dump(combined_summary_dict, f, ensure_ascii=False, indent=2)

            # 2. Write Detailed Results CSV
            csv_path = out_path / "case_evaluation_results.csv"
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "case_id",
                        "category",
                        "claim_id",
                        "subject",
                        "parameter",
                        "expected_label",
                        "label_origin",
                        "p5_result",
                        "s2_4_result",
                        "is_correct",
                        "reason_codes",
                        "latency_ms",
                        "explanation",
                        "doc_id",
                        "page_number",
                        "evidence_id",
                        "source_text",
                        "source_provenance_json",
                    ],
                )
                writer.writeheader()
                for co in combined_outputs:
                    writer.writerow({
                        "case_id": co.case_id,
                        "category": co.category,
                        "claim_id": co.claim_id,
                        "subject": co.subject,
                        "parameter": co.parameter,
                        "expected_label": co.expected_label,
                        "label_origin": co.label_origin,
                        "p5_result": co.p5_result,
                        "s2_4_result": co.s2_4_result,
                        "is_correct": co.is_correct,
                        "reason_codes": ";".join(co.reason_codes),
                        "latency_ms": co.latency_ms,
                        "explanation": co.explanation,
                        "doc_id": co.source_provenance[0].get("doc_id", "") if co.source_provenance else "",
                        "page_number": co.source_provenance[0].get("page_number", "") if co.source_provenance else "",
                        "evidence_id": co.source_provenance[0].get("evidence_id", "") if co.source_provenance else "",
                        "source_text": co.source_provenance[0].get("source_text", "") if co.source_provenance else "",
                        "source_provenance_json": json.dumps(co.source_provenance, ensure_ascii=False),
                    })

        return {
            "summary": combined_summary_dict,
            "case_outputs": [co.to_dict() for co in combined_outputs],
        }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="VietIRR-RAG S2.4 Offline Evaluation Runner")
    parser.add_argument("--out-dir", type=str, default="reports/STAGE2/S2_4/eval_results", help="Output directory")
    args = parser.parse_args()

    runner = OfflineEvaluationRunner()
    results = runner.run_all(output_dir=args.out_dir)

    print("=" * 70)
    print("VIETIRR-RAG S2.4 OFFLINE EVALUATION RESULTS")
    print("=" * 70)
    summary = results["summary"]
    print("Scientific accuracy: NOT EVALUATED (no independent gold labels)")
    print(
        f"Overall fixture agreement: {summary['overall_fixture_agreement_rate'] * 100:.2f}% "
        f"({summary['overall_fixture_agreement_count']}/{summary['overall_total_cases']})"
    )
    print("\n--- CATEGORY A: SYNTHETIC LOGIC REGRESSION ---")
    cat_a = summary["category_a_synthetic"]
    print(f"Fixture agreement: {cat_a['agreement_rate'] * 100:.2f}% ({cat_a['correct_count']}/{cat_a['total_cases']})")
    print(f"Supported F1: {cat_a['supported_metrics']['f1']:.4f} | Contradicted F1: {cat_a['contradicted_metrics']['f1']:.4f} | Insufficient F1: {cat_a['insufficient_metrics']['f1']:.4f}")
    print(f"Mean Latency: {cat_a['mean_latency_ms']:.2f} ms")
    print("\n--- CATEGORY B: SOURCE-BACKED DEVELOPMENT (NOT INDEPENDENT GOLD) ---")
    cat_b = summary["category_b_source_backed_development"]
    print(f"Fixture agreement: {cat_b['agreement_rate'] * 100:.2f}% ({cat_b['correct_count']}/{cat_b['total_cases']})")
    print(f"Supported F1: {cat_b['supported_metrics']['f1']:.4f} | Contradicted F1: {cat_b['contradicted_metrics']['f1']:.4f} | Insufficient F1: {cat_b['insufficient_metrics']['f1']:.4f}")
    print(f"Mean Latency: {cat_b['mean_latency_ms']:.2f} ms")
    print("=" * 70)
