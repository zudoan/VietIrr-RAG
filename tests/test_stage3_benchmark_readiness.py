"""Regression and integration tests for Benchmark Readiness Sprint:
Phase A:
- A1: Exact retrieved evidence metadata preservation (dict-based and P5 Evidence object).
- A2: Enforce source-index provenance for live correction (fail-closed, unregistered ID rejection).
- A3: Independent version constraint enforcement.
Phase B:
- Controlled evaluation protocol: UntargetedCorrectionExecutor matching budget & call audits.
"""

from typing import Any, Optional
import pytest

from viirr_ontology.schema.claim import ClaimPolarity, TechnicalClaim
from viirr_ontology.schema.evidence import (
    EvidenceItem,
    EvidenceRelation,
    EvidenceSet,
)
from viirr_ontology.verifier.models import ClaimVerificationStatus
from viirr_ontology.verifier.ontology_verifier import OntologyConstraintVerifier
from viirr_ontology.correction.planner import EvidenceCorrectionPlanner
from viirr_ontology.correction.retrieval_adapter import (
    MockRetrievalBackend,
    PageRegionRetrievalAdapter,
    RealRetrievalBackend,
)
from viirr_ontology.correction.executor import (
    TargetedCorrectionExecutor,
    UntargetedCorrectionExecutor,
)
from viirr_ontology.correction.provenance import (
    DocumentIdentityRegistry,
    EvidenceProvenanceValidator,
    ProvenanceValidationStatus,
    StructuralRelationVerifier,
    TrustedSourceStructureRegistry,
)


def _item(
    evidence_id: str,
    text: str,
    doc_id: str = "DOC_740",
    page: int = 1,
    metadata: Optional[dict[str, Any]] = None,
    document_number: Optional[str] = None,
    document_version: Optional[str] = None,
    source: str = "test_source",
    page_id: Optional[str] = None,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        doc_id=doc_id,
        page_id=page_id or f"P{page}",
        page_number=page,
        text=text,
        provenance_metadata=metadata or {},
        document_number=document_number,
        document_version=document_version,
        source=source,
    )


# =============================================================================
# PHASE A1: PRESERVE EXACT RETRIEVED EVIDENCE METADATA
# =============================================================================

def test_a1_dict_based_retrieval_preserves_exact_metadata():
    """Independent reproduction case:
    Input contains:
    - page_id = DOC_X_P17
    - source = authoritative_pdf_index
    - evidence_id = REG_123
    Verify adapter preserves exact page_id, source, document identity, citation fields.
    """
    dict_row = {
        "doc_id": "DOC_X",
        "page_id": "DOC_X_P17",
        "evidence_id": "REG_123",
        "text": "Mực nước dâng bình thường hồ chứa là 117.0 m.",
        "page": 17,
        "source": "authoritative_pdf_index",
        "document_number": "740/QĐ-TTg",
        "document_version": "2.1",
        "region_id": "REG_123",
        "bbox": [10.0, 20.0, 30.0, 40.0],
        "publication_date": "2019-06-17",
        "legal_status": "VALID",
        "rank": 1,
        "custom_audit_key": "audit_val_999",
    }

    mock_backend = MockRetrievalBackend()
    adapter = PageRegionRetrievalAdapter(retrieval_backend=mock_backend)

    converted = adapter._convert_p5_evidence([dict_row])
    assert len(converted) == 1
    ev = converted[0]

    assert ev.page_id == "DOC_X_P17", f"Expected DOC_X_P17, got {ev.page_id}"
    assert ev.source == "authoritative_pdf_index", f"Expected authoritative_pdf_index, got {ev.source}"
    assert ev.evidence_id == "REG_123"
    assert ev.doc_id == "DOC_X"
    assert ev.document_number == "740/QĐ-TTg"
    assert ev.document_version == "2.1"
    assert ev.page_number == 17
    assert ev.region_id == "REG_123"
    assert ev.bbox == (10.0, 20.0, 30.0, 40.0)
    assert ev.publication_date == "2019-06-17"
    assert ev.provenance_metadata.get("custom_audit_key") == "audit_val_999"


def test_a1_p5_object_preserves_exact_metadata():
    """Verify that a P5 Evidence-like object retains all metadata attributes."""
    class MockP5Evidence:
        def __init__(self):
            self.evidence_id = "P5_EV_456"
            self.doc_id = "DOC_Y"
            self.page_id = "DOC_Y_P42"
            self.page = 42
            self.text = "Lưu lượng xả đáy tối đa 4000 m3/s."
            self.source = "frozen_p5_v4_index"
            self.document_number = "123/QĐ-BNN"
            self.document_version = "1.0"
            self.region_id = "REG_456"
            self.bbox = [5.0, 10.0, 50.0, 100.0]

    obj = MockP5Evidence()
    adapter = PageRegionRetrievalAdapter(retrieval_backend=MockRetrievalBackend())
    converted = adapter._convert_p5_evidence([obj])

    assert len(converted) == 1
    ev = converted[0]
    assert ev.evidence_id == "P5_EV_456"
    assert ev.doc_id == "DOC_Y"
    assert ev.page_id == "DOC_Y_P42"
    assert ev.page_number == 42
    assert ev.source == "frozen_p5_v4_index"
    assert ev.document_number == "123/QĐ-BNN"
    assert ev.document_version == "1.0"
    assert ev.region_id == "REG_456"
    assert ev.bbox == (5.0, 10.0, 50.0, 100.0)


def test_a1_missing_mandatory_provenance_rejected():
    """Adapter rejects rows missing mandatory doc_id or text."""
    invalid_row = {
        "page_id": "P1",
        # missing doc_id and text
    }
    adapter = PageRegionRetrievalAdapter(retrieval_backend=MockRetrievalBackend())
    converted = adapter._convert_p5_evidence([invalid_row])
    assert len(converted) == 0


# =============================================================================
# PHASE A2: ENFORCE SOURCE-INDEX PROVENANCE FOR LIVE CORRECTION
# =============================================================================

def test_a2_real_backend_defaults_to_index_verification_and_fails_closed():
    """For RealRetrievalBackend, executor defaults to require_index_verification=True.
    If the trusted source index is unavailable, it fails closed (does not promote claim).
    """
    real_backend = RealRetrievalBackend(retriever=None)
    # Intentionally do not provide corpus_index_path or mock mode
    executor = TargetedCorrectionExecutor(
        retrieval_backend=real_backend,
        corpus_index_path="non_existent_corpus_index_path.jsonl",
    )
    assert executor.require_index_verification is True
    assert executor.synthetic_mode is False

    claim = TechnicalClaim(
        claim_id="claim_test",
        claim_text="Hồ Hòa Bình MNDBT 117.0 m",
        subject="Hồ Hòa Bình",
        parameter="MNDBT",
        value="117.0",
        unit="m",
        polarity=ClaimPolarity.AFFIRMED,
        document_scope="DOC_TEST",
    )
    evidence_set = EvidenceSet(query_id="q_test", evidence_items=[])

    # Should fail closed safely without crashing
    result = executor.execute_correction(claim, evidence_set)
    assert result.success is False
    assert result.final_status != ClaimVerificationStatus.SUPPORTED


def test_a2_unregistered_evidence_id_cannot_promote_claim_in_live_mode():
    """In live mode (require_index_verification=True), a valid-looking but
    unregistered evidence ID must be rejected by provenance validation
    and CANNOT promote an unverified claim to SUPPORTED.
    """
    validator = EvidenceProvenanceValidator()
    # Populate trusted index with only valid_ev_1
    validator.register_verified_index_evidence(doc_id="DOC_REAL", page_number=1, evidence_id="VALID_EV_1")

    # Attempt to validate an unregistered evidence ID
    fake_item = _item(
        evidence_id="UNREGISTERED_EV_999",
        text="Mực nước dâng bình thường 117.0 m.",
        doc_id="DOC_REAL",
        page=1,
    )
    status, reason = validator.validate_provenance(fake_item, require_index_verification=True)
    assert status == ProvenanceValidationStatus.UNVERIFIED
    assert "UNTRUSTED_SOURCE_IDENTITY" in reason

    # Now verify with an executor configured with this validator
    mock_backend = MockRetrievalBackend()
    mock_backend.add_response(
        "MNDBT",
        [_item("UNREGISTERED_EV_999", "Mực nước dâng bình thường 117.0 m.", doc_id="DOC_REAL", page=1)],
    )

    executor = TargetedCorrectionExecutor(
        retrieval_backend=mock_backend,
        provenance_validator=validator,
        require_index_verification=True,
        synthetic_mode=False,
    )

    claim = TechnicalClaim(
        claim_id="claim_unregistered",
        claim_text="Hồ Hòa Bình MNDBT 117.0 m",
        subject="Hồ Hòa Bình",
        parameter="MNDBT",
        value="117.0",
        unit="m",
        polarity=ClaimPolarity.AFFIRMED,
        document_scope="DOC_REAL",
    )

    # Initial evidence set has insufficient evidence
    init_ev = _item("INIT_EV", "Thông tin chung về hồ chứa.", doc_id="DOC_REAL", page=1)
    validator.register_verified_index_evidence("DOC_REAL", 1, "INIT_EV")
    evidence_set = EvidenceSet(query_id="q_unreg", evidence_items=[init_ev])

    result = executor.execute_correction(claim, evidence_set)
    # Claim must NOT be promoted to SUPPORTED because candidate was rejected by index check
    assert result.final_status != ClaimVerificationStatus.SUPPORTED


def test_a2_fixture_mode_allows_synthetic_evaluation():
    """In synthetic_mode=True or when require_index_verification=False,
    synthetic mock evaluation fixtures are permitted to proceed.
    """
    mock_backend = MockRetrievalBackend()
    ev_candidate = _item(
        "MOCK_EV_1",
        "Hồ Hòa Bình có mực nước dâng bình thường là 117.0 m.",
        doc_id="DOC_FIXTURE",
    )
    mock_backend.add_response(r"Mực nước|Hồ Hòa Bình|MNDBT", [ev_candidate])

    executor = TargetedCorrectionExecutor(
        retrieval_backend=mock_backend,
        synthetic_mode=True,
        require_index_verification=False,
    )

    claim = TechnicalClaim(
        claim_id="claim_fixture",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117.0 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117.0",
        unit="m",
        document_scope="DOC_FIXTURE",
    )
    evidence_set = EvidenceSet(query_id="q_fixture", evidence_items=[_item("INIT", "Văn bản quy định.", doc_id="DOC_FIXTURE")])

    result = executor.execute_correction(claim, evidence_set)
    # Under synthetic mode, evaluation can verify the mock candidate
    assert result.success is True
    assert result.final_status == "SUPPORTED"


# =============================================================================
# PHASE A3: ENFORCE VERSION CONSTRAINTS INDEPENDENTLY
# =============================================================================

def test_a3_enforce_version_constraints_independently():
    """When required_version is supplied without required_document_scope,
    validate_provenance() must enforce the version requirement.
    Missing or mismatched version must NOT count as verified matching version.
    """
    validator = EvidenceProvenanceValidator()

    # Item with no version
    item_no_version = _item(
        evidence_id="EV_1",
        text="Sample text",
        doc_id="DOC_100",
        document_version=None,
    )
    status, reason = validator.validate_provenance(item_no_version, required_version="2.0")
    assert status == ProvenanceValidationStatus.UNVERIFIED
    assert "DOCUMENT_VERSION_MISSING" in reason

    # Item with mismatched version
    item_wrong_version = _item(
        evidence_id="EV_2",
        text="Sample text",
        doc_id="DOC_100",
        document_version="1.0",
    )
    status, reason = validator.validate_provenance(item_wrong_version, required_version="2.0")
    assert status == ProvenanceValidationStatus.UNVERIFIED
    assert "DOCUMENT_VERSION_MISMATCH" in reason

    # Item with matching version
    item_correct_version = _item(
        evidence_id="EV_3",
        text="Sample text",
        doc_id="DOC_100",
        document_version="2.0",
    )
    status, reason = validator.validate_provenance(item_correct_version, required_version="2.0")
    assert status == ProvenanceValidationStatus.SYNTACTIC_VALID


# =============================================================================
# PHASE B: CONTROLLED EVALUATION PROTOCOL (MATCHING BUDGET & CALL AUDITS)
# =============================================================================

def test_b_untargeted_executor_matching_budget_and_call_audits():
    """UntargetedCorrectionExecutor must:
    1. Operate under the same total retrieval call and candidate budget as targeted (budget=2, top_k=3).
    2. Log per-case retrieval calls, candidates inspected, candidates admitted, verifier calls.
    3. Apply equivalent provenance and verifier stop policies.
    """
    mock_backend = MockRetrievalBackend()
    candidate_1 = _item("CAND_1", "Tài liệu thủy văn chung.", doc_id="DOC_TEST")
    candidate_2 = _item("CAND_2", "Hồ Hòa Bình có mực nước dâng bình thường là 117.0 m.", doc_id="DOC_TEST")

    # Untargeted query uses generic claim query
    mock_backend.add_response("Hồ Hòa Bình có mực nước dâng bình thường 117.0 m", [candidate_1, candidate_2])

    untargeted_exec = UntargetedCorrectionExecutor(
        retrieval_backend=mock_backend,
        synthetic_mode=True,
        require_index_verification=False,
        max_attempts=2,
    )

    claim = TechnicalClaim(
        claim_id="claim_budget_test",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117.0 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117.0",
        unit="m",
        document_scope="DOC_TEST",
    )
    evidence_set = EvidenceSet(query_id="q_budget", evidence_items=[_item("INIT", "Giới thiệu chung.", doc_id="DOC_TEST")])

    result = untargeted_exec.execute_correction(claim, evidence_set)

    # Check call and candidate audit logs
    assert result.retrieval_calls == 1
    assert result.total_candidates_inspected == 2
    assert result.total_candidates_admitted == 2
    assert result.verifier_calls >= 1
    assert result.final_status == "SUPPORTED"
    assert result.success is True

    # Check attempt level audit
    attempt = result.attempts[0]
    assert attempt.candidates_inspected == 2
    assert attempt.candidates_admitted == 2
    assert attempt.verification_verdict == "SUPPORTED"
