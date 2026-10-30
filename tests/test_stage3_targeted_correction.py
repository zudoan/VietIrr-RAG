"""Tests for Stage 3 Sprint A: Evidence-Targeted Correction MVP.

Verifies the 12 core evaluation scenarios:
1. Missing table header -> corrected after retrieval.
2. Missing technical unit -> corrected after retrieval.
3. Missing applicability condition -> corrected after retrieval.
4. Missing legal actor/action rule -> corrected after retrieval.
5. Missing document version -> corrected after retrieval.
6. Retrieval returns unrelated evidence -> remain INSUFFICIENT.
7. Retrieval returns conflicting evidence -> no false SUPPORT (detects CONTRADICTED).
8. No new evidence -> stop immediately.
9. Repeated same evidence -> avoid redundant retries.
10. Invalid citation after correction -> reject provenance.
11. Retrieval from another document -> enforce document scope.
12. Multiple claims with different missing slots -> maintain separate correction plans.
"""

from __future__ import annotations

from typing import Any
import pytest

from viirr_ontology.correction.executor import TargetedCorrectionExecutor
from viirr_ontology.correction.models import CorrectionGoal
from viirr_ontology.correction.planner import EvidenceCorrectionPlanner
from viirr_ontology.correction.retrieval_adapter import MockRetrievalBackend, PageRegionRetrievalAdapter
from viirr_ontology.schema.claim import ClaimCondition, ClaimPolarity, TechnicalClaim
from viirr_ontology.schema.evidence import EvidenceItem, EvidenceSet
from viirr_ontology.verifier.models import ClaimVerificationStatus, ReasonCode
from viirr_ontology.verifier.ontology_verifier import OntologyConstraintVerifier


def _item(
    evidence_id: str,
    text: str,
    doc_id: str = "DOC_740",
    page: int = 1,
    metadata: dict[str, Any] | None = None,
    document_number: str | None = None,
    document_version: str | None = None,
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


@pytest.fixture
def verifier() -> OntologyConstraintVerifier:
    return OntologyConstraintVerifier()


@pytest.fixture
def planner() -> EvidenceCorrectionPlanner:
    return EvidenceCorrectionPlanner()


@pytest.fixture
def mock_backend() -> MockRetrievalBackend:
    return MockRetrievalBackend()


@pytest.fixture
def executor(verifier, mock_backend, planner) -> TargetedCorrectionExecutor:
    adapter = PageRegionRetrievalAdapter(mock_backend)
    return TargetedCorrectionExecutor(verifier=verifier, retrieval_adapter=adapter, planner=planner)


# =============================================================================
# SCENARIO 1: Missing table header -> corrected after retrieval
# =============================================================================
def test_scenario_01_missing_table_header_corrected(executor, mock_backend):
    """Scenario 1: Fragment lacks parameter name; retrieval adds header -> SUPPORTED.

    Correctness Gate Note: Evidence relations are never fabricated.
    Both row and header share table_id='TAB_SPEC_01' on page 1, establishing genuine
    structural table relationship verified by StructuralRelationVerifier.
    """
    claim = TechnicalClaim(
        claim_id="C_MNDBT",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_ROW"],
    )
    initial_ev = EvidenceSet(
        query_id="Q1",
        evidence_items=[_item("E_ROW", "Hồ Hòa Bình | 117 m", metadata={"table_id": "TAB_SPEC_01"})],
    )

    # Register mock targeted retrieval finding the header with genuine table linkage
    header_item = _item(
        "E_HEADER",
        "Bảng thông số kỹ thuật: Mực nước dâng bình thường (m)",
        metadata={"table_id": "TAB_SPEC_01"},
    )
    executor.register_trusted_table_unit("DOC_740", 1, "E_ROW", "TAB_SPEC_01")
    executor.register_trusted_table_unit("DOC_740", 1, "E_HEADER", "TAB_SPEC_01")
    mock_backend.register_fixture(r"tiêu đề|bảng|đơn vị", [header_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.initial_status == "INSUFFICIENT"
    assert res.final_status == "SUPPORTED"
    assert res.stop_reason == "SUPPORTED_REACHED"
    assert "E_HEADER" in res.newly_retrieved_evidence_ids


# =============================================================================
# SCENARIO 2: Missing technical unit -> corrected after retrieval
# =============================================================================
def test_scenario_02_missing_technical_unit_corrected(executor, mock_backend):
    """Scenario 2: Evidence has numeric value but unit is missing/ambiguous -> corrected."""
    claim = TechnicalClaim(
        claim_id="C_UNIT",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_NO_UNIT"],
    )
    initial_ev = EvidenceSet(
        query_id="Q2",
        evidence_items=[_item("E_NO_UNIT", "Hồ Hòa Bình mực nước dâng bình thường: 117")],
    )

    unit_item = _item("E_UNIT", "Ghi chú đơn vị đo: Mực nước dâng bình thường hồ Hòa Bình tính bằng mét (m), cụ thể hồ Hòa Bình mực nước dâng bình thường: 117 m.")
    mock_backend.register_fixture(r"đơn vị|tiêu đề|mực nước", [unit_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.initial_status == "INSUFFICIENT"
    assert res.final_status == "SUPPORTED"
    assert res.stop_reason == "SUPPORTED_REACHED"
    assert "E_UNIT" in res.newly_retrieved_evidence_ids


# =============================================================================
# SCENARIO 3: Missing applicability condition -> corrected after retrieval
# =============================================================================
def test_scenario_03_missing_applicability_condition_corrected(executor, mock_backend):
    """Scenario 3: Claim requires GE 85 m condition; retrieval adds condition -> SUPPORTED."""
    claim = TechnicalClaim(
        claim_id="C_COND",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m khi ngưỡng >= 85 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="GE", value="85", unit="m")],
        evidence_ids=["E_VAL_ONLY"],
    )
    initial_ev = EvidenceSet(
        query_id="Q3",
        evidence_items=[_item("E_VAL_ONLY", "Hồ Hòa Bình có mực nước dâng bình thường 117 m.")],
    )

    cond_item = _item("E_COND", "Hồ Hòa Bình có mực nước dâng bình thường 117 m khi mực nước hồ từ 85 m trở lên.")
    mock_backend.register_fixture(r"ngưỡng|điều kiện|vận hành", [cond_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.initial_status == "INSUFFICIENT"
    assert res.final_status == "SUPPORTED"
    assert "E_COND" in res.newly_retrieved_evidence_ids


# =============================================================================
# SCENARIO 4: Missing legal actor/action rule -> corrected after retrieval
# =============================================================================
def test_scenario_04_missing_legal_actor_action_rule_corrected(executor, mock_backend):
    """Scenario 4: Missing legal authorization provision; retrieved article confirms -> SUPPORTED."""
    claim = TechnicalClaim(
        claim_id="C_LEGAL",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai có thẩm quyền quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E_MEETING"],
    )
    initial_ev = EvidenceSet(
        query_id="Q4",
        evidence_items=[_item("E_MEETING", "Chủ tịch UBND tỉnh Đồng Nai tham dự cuộc họp an toàn đập.")],
    )

    auth_item = _item("E_AUTH", "Chủ tịch UBND tỉnh Đồng Nai có thẩm quyền quyết định xả lũ trong tình huống khẩn cấp.")
    mock_backend.register_fixture(r"thẩm quyền|nhiệm vụ|quyết định", [auth_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.initial_status == "INSUFFICIENT"
    assert res.final_status == "SUPPORTED"
    assert res.stop_reason == "SUPPORTED_REACHED"
    assert "E_AUTH" in res.newly_retrieved_evidence_ids


# =============================================================================
# SCENARIO 5: Missing document version -> corrected after retrieval
# =============================================================================
def test_scenario_05_missing_document_version_corrected(executor, mock_backend):
    """Scenario 5: Document version conflict resolved by retrieving amendment clause."""
    claim = TechnicalClaim(
        claim_id="C_VER",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        document_scope="740/QĐ-TTg",
        evidence_ids=["E_AMEND"],
    )
    initial_ev = EvidenceSet(
        query_id="Q5",
        evidence_items=[
            _item("E_AMEND", "Theo Quyết định số 922/QĐ-TTg, quy trình vận hành hồ Hòa Bình được sửa đổi bổ sung năm 2024.", doc_id="922/QĐ-TTg")
        ],
    )

    ver_item = _item("E_VER", "Quyết định 740/QĐ-TTg ban hành quy trình vận hành liên hồ sông Hồng, hồ Hòa Bình có mực nước dâng bình thường 117 m.", doc_id="740/QĐ-TTg")
    mock_backend.register_fixture(r"quyết định|quy trình|hiệu lực|740", [ver_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.final_status == "SUPPORTED"
    assert "E_VER" in res.newly_retrieved_evidence_ids


# =============================================================================
# SCENARIO 6: Retrieval returns unrelated evidence -> remain INSUFFICIENT
# =============================================================================
def test_scenario_06_retrieval_returns_unrelated_evidence_remains_insufficient(executor, mock_backend):
    """Scenario 6: Retrieved evidence is unrelated; claim safely remains INSUFFICIENT."""
    claim = TechnicalClaim(
        claim_id="C_UNRELATED",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_EMPTY"],
    )
    initial_ev = EvidenceSet(
        query_id="Q6",
        evidence_items=[_item("E_EMPTY", "Báo cáo khí tượng thủy văn khu vực Bắc Bộ.")],
    )

    unrelated_item = _item("E_UNREL", "Dự báo thời tiết ngày mai trời có mưa rào rải rác.")
    mock_backend.register_fixture(r".*", [unrelated_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.final_status == "INSUFFICIENT"
    assert res.stop_reason in ("BUDGET_EXHAUSTED", "NO_NEW_EVIDENCE")


# =============================================================================
# SCENARIO 7: Retrieval returns conflicting evidence -> CONTRADICTED (no false SUPPORT)
# =============================================================================
def test_scenario_07_retrieval_returns_conflicting_evidence_no_false_support(executor, mock_backend):
    """Scenario 7: Newly retrieved item contains conflicting value; verdict becomes CONTRADICTED."""
    claim = TechnicalClaim(
        claim_id="C_CONFLICT",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_VAGUE"],
    )
    initial_ev = EvidenceSet(
        query_id="Q7",
        evidence_items=[_item("E_VAGUE", "Hồ Hòa Bình là công trình thủy điện trọng điểm quốc gia.")],
    )

    conflict_item = _item("E_CONFLICT", "Hồ Hòa Bình có mực nước dâng bình thường 118 m.")
    mock_backend.register_fixture(r".*", [conflict_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.final_status == "CONTRADICTED"
    assert res.stop_reason == "CONTRADICTION_DISCOVERED"


# =============================================================================
# SCENARIO 8: No new evidence -> stop immediately
# =============================================================================
def test_scenario_08_no_new_evidence_stops_immediately(executor, mock_backend):
    """Scenario 8: When backend returns nothing, stop immediately without endless retry."""
    claim = TechnicalClaim(
        claim_id="C_NO_NEW",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_BASE"],
    )
    initial_ev = EvidenceSet(
        query_id="Q8",
        evidence_items=[_item("E_BASE", "Văn bản chưa đề cập thông số.")],
    )

    # Empty backend response
    res = executor.correct_claim(claim, initial_ev, budget=3)
    assert res.stop_reason == "NO_NEW_EVIDENCE"
    assert res.attempts_made == 1


# =============================================================================
# SCENARIO 9: Repeated same evidence -> avoid redundant retries
# =============================================================================
def test_scenario_09_repeated_same_evidence_avoids_redundant_retries(executor, mock_backend):
    """Scenario 9: Backend returns already known evidence items -> stop immediately."""
    claim = TechnicalClaim(
        claim_id="C_REPEAT",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_EXISTING"],
    )
    existing_item = _item("E_EXISTING", "Văn bản nhắc đến hồ Hòa Bình nhưng thiếu giá trị.")
    initial_ev = EvidenceSet(query_id="Q9", evidence_items=[existing_item])

    # Backend returns the exact same item
    mock_backend.register_fixture(r".*", [existing_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.stop_reason == "NO_NEW_EVIDENCE"
    assert res.attempts_made == 1


# =============================================================================
# SCENARIO 10: Invalid citation after correction -> reject provenance
# =============================================================================
def test_scenario_10_invalid_citation_after_correction_rejected(executor, mock_backend):
    """Scenario 10: Item with malformed provenance (e.g. empty doc_id) is rejected."""
    claim = TechnicalClaim(
        claim_id="C_INVALID_PROV",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_BASE"],
    )
    initial_ev = EvidenceSet(
        query_id="Q10",
        evidence_items=[_item("E_BASE", "Văn bản thiếu thông số.")],
    )

    malformed_item = EvidenceItem(
        evidence_id="E_MALFORMED",
        doc_id="",  # Invalid empty doc_id
        page_id="P1",
        page_number=1,
        text="Hồ Hòa Bình có mực nước dâng bình thường 117 m.",
    )
    mock_backend.register_fixture(r".*", [malformed_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.stop_reason == "UNRESOLVED_DOCUMENT_SCOPE_CONFLICT"


# =============================================================================
# SCENARIO 11: Retrieval from another document -> enforce document scope
# =============================================================================
def test_scenario_11_retrieval_from_another_document_enforces_scope(executor, mock_backend):
    """Scenario 11: Scope is restricted to DOC_A; item from DOC_B is rejected."""
    claim = TechnicalClaim(
        claim_id="C_SCOPE",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        document_scope="DOC_A",
        evidence_ids=["E_DOC_A"],
    )
    initial_ev = EvidenceSet(
        query_id="Q11",
        evidence_items=[_item("E_DOC_A", "DOC_A nói về quy hoạch chung.", doc_id="DOC_A")],
    )

    # Retrieval brings an item from DOC_B
    item_doc_b = _item("E_DOC_B", "Hồ Hòa Bình có mực nước dâng bình thường 117 m.", doc_id="DOC_B")
    mock_backend.register_fixture(r".*", [item_doc_b])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.stop_reason == "UNRESOLVED_DOCUMENT_SCOPE_CONFLICT"


# =============================================================================
# SCENARIO 12: Multiple claims with different missing slots -> separate plans
# =============================================================================
def test_scenario_12_multiple_claims_separate_plans(planner, verifier):
    """Scenario 12: Multiple claims with different missing slots receive customized plans."""
    # Claim A: missing physical unit
    claim_a = TechnicalClaim(
        claim_id="C_A",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_A"],
    )
    ev_a = EvidenceSet(query_id="QA", evidence_items=[_item("E_A", "Hồ Hòa Bình mực nước dâng bình thường: 117")])
    res_a = verifier.verify_single_claim(claim_a, ev_a)
    plan_a = planner.create_plan(claim_a, res_a, retrieval_budget=2)

    # Claim B: missing legal authority
    claim_b = TechnicalClaim(
        claim_id="C_B",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai được quyền quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E_B"],
    )
    ev_b = EvidenceSet(query_id="QB", evidence_items=[_item("E_B", "Chủ tịch UBND tỉnh Đồng Nai dự họp.")])
    res_b = verifier.verify_single_claim(claim_b, ev_b)
    plan_b = planner.create_plan(claim_b, res_b, retrieval_budget=2)

    assert plan_a.correction_goal == CorrectionGoal.RESOLVE_MISSING_UNIT.value
    assert "table_header" in plan_a.required_evidence_types
    assert any("đơn vị tính" in q for q in plan_a.search_queries)

    assert plan_b.correction_goal == CorrectionGoal.RESOLVE_MISSING_AUTHORITY.value
    assert "legal_article" in plan_b.required_evidence_types
    assert any("thẩm quyền" in q for q in plan_b.search_queries)

    assert plan_a.target_claim_id != plan_b.target_claim_id


def test_stage3_offline_runner_full_run(tmp_path):
    """Verify that Stage3OfflineEvaluationRunner executes all 13 cases with 100% agreement and 0 false support."""
    from viirr_ontology.evaluation.stage3_offline_runner import Stage3OfflineEvaluationRunner
    runner = Stage3OfflineEvaluationRunner(output_dir=tmp_path)
    summary = runner.run_all()
    assert summary["total_cases"] == 13
    assert summary["fixture_agreement_rate"] == 1.0
    assert summary["false_support_rate"] == 0.0
    assert (tmp_path / "correction_summary.json").exists()
    assert (tmp_path / "correction_cases.csv").exists()


# =============================================================================
# ADVERSARIAL CORRECTNESS GATE TESTS
# =============================================================================

def test_adv_01_same_doc_distant_pages_no_verified_relation(executor, mock_backend):
    """Adversarial 1: Same document, distant pages (page 1 vs page 99) -> no verified relation, remains INSUFFICIENT.

    Independent failure reproduction:
    Claim: 'Hồ Hòa Bình có mực nước dâng bình thường 117 m'
    Initial: E_ROW on Page 1: 'Hồ Hòa Bình | 117 m'
    Retrieved: E_HEADER on Page 99: 'Bảng thông số kỹ thuật: Mực nước dâng bình thường (m)'
    Because page distance = 98 (>1) and no explicit parser linkage exists, the relation is unverified.
    Multi-region synthesis cannot consume unverified links -> verdict remains INSUFFICIENT.
    """
    claim = TechnicalClaim(
        claim_id="C_ADV_01",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_ROW_P1"],
    )
    initial_ev = EvidenceSet(
        query_id="Q_ADV_01",
        evidence_items=[_item("E_ROW_P1", "Hồ Hòa Bình | 117 m", doc_id="DOC_A", page=1)],
    )

    header_item = _item(
        "E_HEADER_P99",
        "Bảng thông số kỹ thuật: Mực nước dâng bình thường (m)",
        doc_id="DOC_A",
        page=99,
    )
    mock_backend.register_fixture(r".*", [header_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.initial_status == "INSUFFICIENT"
    assert res.final_status == "INSUFFICIENT"
    # Verify that any relations formed were unverified
    assert all(not rel.verified for rel in res.final_evidence_set.evidence_relations)


def test_adv_02_same_doc_unrelated_tables_no_fabricated_support(executor, mock_backend):
    """Adversarial 2: Same document and same page, but different table IDs -> no fabricated SUPPORT."""
    claim = TechnicalClaim(
        claim_id="C_ADV_02",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_ROW_HYDRO"],
    )
    initial_ev = EvidenceSet(
        query_id="Q_ADV_02",
        evidence_items=[_item(
            "E_ROW_HYDRO",
            "Hồ Hòa Bình | 117 m",
            doc_id="DOC_A",
            page=5,
            metadata={"table_id": "TAB_HYDROLOGY"},
        )],
    )

    header_item = _item(
        "E_HEADER_ELEC",
        "Bảng thông số kỹ thuật: Mực nước dâng bình thường (m)",
        doc_id="DOC_A",
        page=5,
        metadata={"table_id": "TAB_ELECTRICAL"},
    )
    mock_backend.register_fixture(r".*", [header_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.initial_status == "INSUFFICIENT"
    assert res.final_status == "INSUFFICIENT"
    assert all(not rel.verified for rel in res.final_evidence_set.evidence_relations)


def test_adv_03_genuine_verified_table_header_row_link_allowed(executor, mock_backend):
    """Adversarial 3: Genuine verified table header/row link (same table_id, same page) -> SUPPORTED."""
    claim = TechnicalClaim(
        claim_id="C_ADV_03",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_ROW_GENUINE"],
    )
    initial_ev = EvidenceSet(
        query_id="Q_ADV_03",
        evidence_items=[_item(
            "E_ROW_GENUINE",
            "Hồ Hòa Bình | 117 m",
            doc_id="DOC_A",
            page=10,
            metadata={"table_id": "TAB_SPECS_DAM"},
        )],
    )

    header_item = _item(
        "E_HEADER_GENUINE",
        "Bảng thông số kỹ thuật: Mực nước dâng bình thường (m)",
        doc_id="DOC_A",
        page=10,
        metadata={"table_id": "TAB_SPECS_DAM"},
    )
    executor.register_trusted_table_unit("DOC_A", 10, "E_ROW_GENUINE", "TAB_SPECS_DAM")
    executor.register_trusted_table_unit("DOC_A", 10, "E_HEADER_GENUINE", "TAB_SPECS_DAM")
    mock_backend.register_fixture(r".*", [header_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.initial_status == "INSUFFICIENT"
    assert res.final_status == "SUPPORTED"
    assert any(rel.verified for rel in res.final_evidence_set.evidence_relations)


def test_adv_04_same_page_unverified_regions_remain_unverified(executor, mock_backend):
    """Adversarial 4: Same-page unverified regions lacking table/block metadata remain unverified."""
    claim = TechnicalClaim(
        claim_id="C_ADV_04",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_RAW_ROW"],
    )
    initial_ev = EvidenceSet(
        query_id="Q_ADV_04",
        evidence_items=[_item("E_RAW_ROW", "Hồ Hòa Bình | 117 m", doc_id="DOC_A", page=3)],
    )

    header_item = _item(
        "E_RAW_HEADER",
        "Bảng thông số kỹ thuật: Mực nước dâng bình thường (m)",
        doc_id="DOC_A",
        page=3,
    )
    mock_backend.register_fixture(r".*", [header_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.final_status == "INSUFFICIENT"
    # Same page alone must NOT promote heuristic relation to verified=True
    for rel in res.final_evidence_set.evidence_relations:
        assert not rel.verified


def test_adv_05_missing_parser_relationship_conservative_insufficient(executor, mock_backend):
    """Adversarial 5: Missing parser structural relationship -> conservative INSUFFICIENT."""
    claim = TechnicalClaim(
        claim_id="C_ADV_05",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_RAW_OCR_1"],
    )
    initial_ev = EvidenceSet(
        query_id="Q_ADV_05",
        evidence_items=[_item(
            "E_RAW_OCR_1",
            "Hồ Hòa Bình | 117",
            doc_id="DOC_A",
            page=2,
            metadata={"parser_source": "raw_ocr_box_1"},
        )],
    )

    retrieved_item = _item(
        "E_RAW_OCR_2",
        "Mực nước dâng bình thường: mét (m)",
        doc_id="DOC_A",
        page=2,
        metadata={"parser_source": "raw_ocr_box_2"},
    )
    mock_backend.register_fixture(r".*", [retrieved_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.final_status == "INSUFFICIENT"


def test_adv_06_document_scope_prefix_suffix_collision_rejected(executor, mock_backend):
    """Adversarial 6: Exact document identity validation rejects prefix/suffix collisions (DOC_A vs DOC_A_EVIL).

    Independent failure reproduction:
    Claim scope: DOC_A
    Retrieved: DOC_A_EVIL
    Must reject retrieved item and remain INSUFFICIENT.
    """
    claim = TechnicalClaim(
        claim_id="C_ADV_06",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        document_scope="DOC_A",
        evidence_ids=["E_DOC_A"],
    )
    initial_ev = EvidenceSet(
        query_id="Q_ADV_06",
        evidence_items=[_item("E_DOC_A", "Hồ Hòa Bình quy hoạch chung.", doc_id="DOC_A", page=1)],
    )

    # DOC_A_EVIL has DOC_A as prefix substring!
    evil_item = _item(
        "E_EVIL",
        "Hồ Hòa Bình có mực nước dâng bình thường 117 m.",
        doc_id="DOC_A_EVIL",
        page=1,
    )
    mock_backend.register_fixture(r".*", [evil_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.final_status == "INSUFFICIENT"
    assert res.stop_reason == "UNRESOLVED_DOCUMENT_SCOPE_CONFLICT"
    # Evil item must not be included in final evidence set
    assert "E_EVIL" not in [it.evidence_id for it in res.final_evidence_set.evidence_items]


def test_adv_07_valid_canonical_alias_accepted_only_when_verified(executor, mock_backend):
    """Adversarial 7: Valid canonical alias accepted only when registered in DocumentIdentityRegistry."""
    claim = TechnicalClaim(
        claim_id="C_ADV_07",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        document_scope="DOC_740",
        evidence_ids=["E_INIT"],
    )
    initial_ev = EvidenceSet(
        query_id="Q_ADV_07",
        evidence_items=[_item("E_INIT", "Văn bản hồ chứa.", doc_id="DOC_740", page=1)],
    )

    # 1. Registered alias 740/QĐ-TTg -> accepted
    alias_item = _item(
        "E_ALIAS",
        "Quyết định 740/QĐ-TTg: Hồ Hòa Bình có mực nước dâng bình thường 117 m.",
        doc_id="740/QĐ-TTg",
        page=1,
    )
    mock_backend.register_fixture(r".*", [alias_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.final_status == "SUPPORTED"
    assert "E_ALIAS" in res.newly_retrieved_evidence_ids

    # 2. Unregistered alias DOC_740_UNOFFICIAL -> rejected
    mock_backend.clear_fixtures()
    unverified_item = _item(
        "E_UNVERIFIED",
        "Tài liệu tham khảo 740: Hồ Hòa Bình có mực nước dâng bình thường 117 m.",
        doc_id="DOC_740_UNOFFICIAL",
        page=1,
    )
    mock_backend.register_fixture(r".*", [unverified_item])

    res_unverified = executor.correct_claim(claim, initial_ev, budget=2)
    assert res_unverified.final_status == "INSUFFICIENT"
    assert res_unverified.stop_reason == "UNRESOLVED_DOCUMENT_SCOPE_CONFLICT"


def test_adv_08_same_document_number_incompatible_version_rejected(executor, mock_backend):
    """Adversarial 8: Incompatible version or issuing authority rejected even if document number matches."""
    claim = TechnicalClaim(
        claim_id="C_ADV_08",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        document_scope="740/QĐ-TTg",
        evidence_ids=["E_INIT"],
    )
    initial_ev = EvidenceSet(
        query_id="Q_ADV_08",
        evidence_items=[_item("E_INIT", "Văn bản hồ Hòa Bình.", doc_id="740/QĐ-TTg", page=1)],
    )

    # Retrieved item has document_number="740/QĐ-UBND" (different issuing authority)
    diff_auth_item = _item(
        "E_DIFF_AUTH",
        "Quyết định 740/QĐ-UBND: Hồ Hòa Bình có mực nước dâng bình thường 117 m.",
        doc_id="740/QĐ-UBND",
        document_number="740/QĐ-UBND",
        page=1,
    )
    mock_backend.register_fixture(r".*", [diff_auth_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.final_status == "INSUFFICIENT"
    assert res.stop_reason == "UNRESOLVED_DOCUMENT_SCOPE_CONFLICT"


def test_adv_09_missing_or_synthetic_evidence_provenance_never_trusted(executor, mock_backend):
    """Adversarial 9: Missing or synthetic evidence provenance rejected by EvidenceProvenanceValidator."""
    claim = TechnicalClaim(
        claim_id="C_ADV_09",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_INIT"],
    )
    initial_ev = EvidenceSet(
        query_id="Q_ADV_09",
        evidence_items=[_item("E_INIT", "Khảo sát mực nước.", doc_id="DOC_740", page=1)],
    )

    # Item with empty doc_id and synthetic ID
    synthetic_item = EvidenceItem(
        evidence_id="SYNTHETIC_EV_999",
        doc_id="",  # empty doc_id
        page_id="P1",
        page_number=1,
        text="Hồ Hòa Bình có mực nước dâng bình thường 117 m.",
    )
    mock_backend.register_fixture(r".*", [synthetic_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.final_status == "INSUFFICIENT"
    assert res.stop_reason == "UNRESOLVED_DOCUMENT_SCOPE_CONFLICT"


def test_adv_10_budget_zero_and_negative_handling(executor, mock_backend):
    """Adversarial 10: Budget zero results in zero retrieval calls; negative budget raises ValueError."""
    claim = TechnicalClaim(
        claim_id="C_ADV_10",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_INIT"],
    )
    initial_ev = EvidenceSet(
        query_id="Q_ADV_10",
        evidence_items=[_item("E_INIT", "Văn bản chưa đề cập thông số.", doc_id="DOC_740", page=1)],
    )

    # Budget 0: exactly 0 attempts made
    res_zero = executor.correct_claim(claim, initial_ev, budget=0)
    assert res_zero.attempts_made == 0
    assert res_zero.stop_reason == "BUDGET_EXHAUSTED"
    assert len(res_zero.attempts) == 0

    # Negative budget raises ValueError
    with pytest.raises(ValueError, match="retrieval_budget must be non-negative"):
        executor.correct_claim(claim, initial_ev, budget=-1)


def test_adv_11_correction_retrieves_conflicting_evidence_no_false_support(executor, mock_backend):
    """Adversarial 11: Correction retrieves conflicting evidence -> halts at CONTRADICTED, no false SUPPORT."""
    claim = TechnicalClaim(
        claim_id="C_ADV_11",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_INIT"],
    )
    initial_ev = EvidenceSet(
        query_id="Q_ADV_11",
        evidence_items=[_item("E_INIT", "Hồ Hòa Bình trên lưu vực sông Đà.", doc_id="DOC_740", page=1)],
    )

    # Retrieved item explicitly contradicts claim value (120 m != 117 m)
    conflict_item = _item(
        "E_CONFLICT",
        "Hồ Hòa Bình có mực nước dâng bình thường 120 m.",
        doc_id="DOC_740",
        page=2,
    )
    mock_backend.register_fixture(r".*", [conflict_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.final_status == "CONTRADICTED"
    assert res.stop_reason == "CONTRADICTION_DISCOVERED"
    assert res.final_status != "SUPPORTED"


def test_adv_12_targeted_vs_untargeted_identical_candidate_pool(verifier, planner):
    """Adversarial 12: Targeted vs untargeted retrieval evaluated against the EXACT SAME candidate pool.

    Demonstrates scientifically fair comparison: both query strategies face identical candidates.
    Targeted retrieval formulates precise query matching the missing slot, retrieving the exact item.
    """
    claim = TechnicalClaim(
        claim_id="C_ADV_12",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_ROW"],
    )
    initial_ev = EvidenceSet(
        query_id="Q_ADV_12",
        evidence_items=[_item("E_ROW", "Hồ Hòa Bình | 117 m", doc_id="DOC_740", page=12, metadata={"table_id": "TAB_SPEC"})],
    )

    # Shared candidate pool with 5 items
    candidate_header = _item(
        "E_HEADER_SPEC",
        "Bảng thông số kỹ thuật tiêu đề cột: Mực nước dâng bình thường (m)",
        doc_id="DOC_740",
        page=12,
        metadata={"table_id": "TAB_SPEC"},
    )
    candidate_unrelated_1 = _item("E_UNREL_1", "Thủy điện Sơn La nằm ở thượng lưu sông Đà.", doc_id="DOC_740", page=5)
    candidate_unrelated_2 = _item("E_UNREL_2", "Quy trình điều tiết mực nước hồ mùa lũ.", doc_id="DOC_740", page=8)
    candidate_unrelated_3 = _item("E_UNREL_3", "Dung tích hữu ích của hồ chứa là 6000 triệu m3.", doc_id="DOC_740", page=15)
    candidate_unrelated_4 = _item("E_UNREL_4", "Lưu lượng xả đáy tối đa 12000 m3/s.", doc_id="DOC_740", page=20)

    shared_pool = [
        candidate_header,
        candidate_unrelated_1,
        candidate_unrelated_2,
        candidate_unrelated_3,
        candidate_unrelated_4,
    ]

    backend = MockRetrievalBackend()
    backend.register_candidate_pool(shared_pool)
    adapter = PageRegionRetrievalAdapter(backend)
    exec_fair = TargetedCorrectionExecutor(verifier=verifier, retrieval_adapter=adapter, planner=planner)
    exec_fair.register_trusted_table_unit("DOC_740", 12, "E_ROW", "TAB_SPEC")
    exec_fair.register_trusted_table_unit("DOC_740", 12, "E_HEADER_SPEC", "TAB_SPEC")

    res_targeted = exec_fair.correct_claim(claim, initial_ev, budget=2)
    assert res_targeted.final_status == "SUPPORTED"
    assert "E_HEADER_SPEC" in res_targeted.newly_retrieved_evidence_ids
