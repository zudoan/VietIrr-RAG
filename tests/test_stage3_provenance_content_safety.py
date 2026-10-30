"""
Tests for Stage 3 Evidence Provenance Content Authenticity & Tamper Resistance.
Phase B Verification:
- Binds verified evidence identities to canonical source content.
- Enforces content consistency against canonical source text.
- Rejects content tampering (numbers, legal negations, units, technical conditions).
- Tracks index identity separately from content verification (INDEX_VERIFIED vs CONTENT_VERIFIED).
- Prevents valid-looking but altered evidence from promoting claims to SUPPORTED in live mode.
- Preserves synthetic fixture isolation.
"""
import pytest

from viirr_ontology.schema.claim import TechnicalClaim
from viirr_ontology.schema.evidence import EvidenceItem, EvidenceSet
from viirr_ontology.correction.models import CorrectionPlan
from viirr_ontology.correction.provenance import (
    DocumentIdentityRegistry,
    EvidenceProvenanceValidator,
    ProvenanceValidationStatus,
    normalize_evidence_text,
)
from viirr_ontology.correction.executor import TargetedCorrectionExecutor
from viirr_ontology.correction.retrieval_adapter import MockRetrievalBackend, PageRegionRetrievalAdapter


def test_safe_normalization_preserves_semantics():
    """Whitespace and unicode NFKC normalize cleanly, while numbers, units, and negations are preserved."""
    raw = "Hồ  Hòa   Bình   có   mực nước dâng bình thường 117 m khi không xả lũ."
    norm = normalize_evidence_text(raw)
    assert "117 m" in norm
    assert "không xả lũ" in norm
    assert "  " not in norm

    # Changing a number must NOT match
    altered_num = "Hồ Hòa Bình có mực nước dâng bình thường 118 m khi không xả lũ."
    assert norm != normalize_evidence_text(altered_num)

    # Removing a negation must NOT match
    altered_neg = "Hồ Hòa Bình có mực nước dâng bình thường 117 m khi xả lũ."
    assert norm != normalize_evidence_text(altered_neg)

    # Changing a unit must NOT match
    altered_unit = "Hồ Hòa Bình có mực nước dâng bình thường 117 cm khi không xả lũ."
    assert norm != normalize_evidence_text(altered_unit)


def test_provenance_accepts_matching_canonical_content():
    """Evidence with matching registered content is marked CONTENT_VERIFIED."""
    validator = EvidenceProvenanceValidator()
    canonical = "Hồ Hòa Bình có mực nước dâng bình thường 117 m."
    validator.register_verified_index_evidence("DOC_740", 1, "REG_001", content=canonical)

    item = EvidenceItem(
        evidence_id="REG_001",
        doc_id="DOC_740",
        page_id="P1",
        page_number=1,
        text="Hồ Hòa Bình có mực nước dâng bình thường 117 m.",
    )

    status, reason = validator.validate_provenance(item, require_index_verification=True)
    assert status == ProvenanceValidationStatus.CONTENT_VERIFIED
    assert "PROVENANCE_CONTENT_VERIFIED" in reason


def test_provenance_rejects_altered_numeric_value():
    """Valid (doc_id, page, evidence_id) with altered number is rejected as CONTENT_MISMATCH."""
    validator = EvidenceProvenanceValidator()
    canonical = "Mực nước lũ thiết kế là 120.0 m."
    validator.register_verified_index_evidence("DOC_740", 2, "REG_NUM_01", content=canonical)

    # Adversarial item: valid ID, but number changed to 125.0 m
    adversarial_item = EvidenceItem(
        evidence_id="REG_NUM_01",
        doc_id="DOC_740",
        page_id="P2",
        page_number=2,
        text="Mực nước lũ thiết kế là 125.0 m.",
    )

    status, reason = validator.validate_provenance(adversarial_item, require_index_verification=True)
    assert status == ProvenanceValidationStatus.UNVERIFIED
    assert "CONTENT_MISMATCH" in reason


def test_provenance_rejects_altered_legal_negation():
    """Valid ID with stripped negation (không/chưa/cấm) is rejected."""
    validator = EvidenceProvenanceValidator()
    canonical = "Tuyệt đối không được mở cửa van xả đáy trong giai đoạn này."
    validator.register_verified_index_evidence("DOC_740", 3, "REG_NEG_01", content=canonical)

    # Adversarial item: 'không được' omitted
    adversarial_item = EvidenceItem(
        evidence_id="REG_NEG_01",
        doc_id="DOC_740",
        page_id="P3",
        page_number=3,
        text="Tuyệt đối được mở cửa van xả đáy trong giai đoạn này.",
    )

    status, reason = validator.validate_provenance(adversarial_item, require_index_verification=True)
    assert status == ProvenanceValidationStatus.UNVERIFIED
    assert "CONTENT_MISMATCH" in reason


def test_provenance_rejects_altered_unit():
    """Valid ID with changed unit (m3/s -> m3/ngày) is rejected."""
    validator = EvidenceProvenanceValidator()
    canonical = "Lưu lượng xả qua tràn lớn nhất là 2800 m3/s."
    validator.register_verified_index_evidence("DOC_740", 4, "REG_UNIT_01", content=canonical)

    # Adversarial item: unit modified
    adversarial_item = EvidenceItem(
        evidence_id="REG_UNIT_01",
        doc_id="DOC_740",
        page_id="P4",
        page_number=4,
        text="Lưu lượng xả qua tràn lớn nhất là 2800 m3/h.",
    )

    status, reason = validator.validate_provenance(adversarial_item, require_index_verification=True)
    assert status == ProvenanceValidationStatus.UNVERIFIED
    assert "CONTENT_MISMATCH" in reason


def test_separate_index_identity_and_content_tracking():
    """Validator distinguishes INDEX_VERIFIED from CONTENT_VERIFIED."""
    validator = EvidenceProvenanceValidator()
    # Register ID only, without canonical content
    validator.register_verified_index_evidence("DOC_740", 5, "REG_ID_ONLY")

    item = EvidenceItem(
        evidence_id="REG_ID_ONLY",
        doc_id="DOC_740",
        page_id="P5",
        page_number=5,
        text="Any text content.",
    )

    status, reason = validator.validate_provenance(item, require_index_verification=True)
    assert status == ProvenanceValidationStatus.INDEX_VERIFIED
    assert "PROVENANCE_INDEX_VERIFIED" in reason

    # Now register with canonical content
    validator.register_verified_index_evidence("DOC_740", 5, "REG_WITH_CONTENT", content="Official Text.")
    matching_item = EvidenceItem(
        evidence_id="REG_WITH_CONTENT",
        doc_id="DOC_740",
        page_id="P5",
        page_number=5,
        text="Official Text.",
    )
    status_c, _ = validator.validate_provenance(matching_item, require_index_verification=True)
    assert status_c == ProvenanceValidationStatus.CONTENT_VERIFIED


def test_live_correction_executor_rejects_altered_content_and_prevents_false_support():
    """In live mode, an evidence item with valid ID but tampered content cannot promote a claim."""
    canonical_text = "Hồ Thác Bà có dung tích toàn bộ 2490 triệu m3."
    tampered_text = "Hồ Thác Bà có dung tích toàn bộ 9999 triệu m3."

    validator = EvidenceProvenanceValidator()
    validator.register_verified_index_evidence("DOC_740", 1, "REG_THACBA", content=canonical_text)

    # Mock backend returns item with valid ID but tampered text
    backend = MockRetrievalBackend()
    backend.add_response(
        "DOC_740",
        [
            EvidenceItem(
                evidence_id="REG_THACBA",
                doc_id="DOC_740",
                page_id="P1",
                page_number=1,
                text=tampered_text,
            )
        ],
    )
    adapter = PageRegionRetrievalAdapter(backend=backend)

    claim = TechnicalClaim(
        claim_id="CLAIM_TB",
        claim_text="Hồ Thác Bà có dung tích toàn bộ 2490 triệu m3",
        subject="Hồ Thác Bà",
        parameter="dung tích toàn bộ",
        value=2490.0,
        unit="triệu m3",
        document_scope="DOC_740",
    )

    executor = TargetedCorrectionExecutor(
        retrieval_adapter=adapter,
        provenance_validator=validator,
        require_index_verification=True,
        require_content_verification=True,
    )

    result = executor.correct_claim(claim, EvidenceSet(query_id="Q_TB"))
    # Candidate was rejected because content differed from canonical index
    assert result.final_status != "SUPPORTED"
    assert result.stop_reason in (
        "UNRESOLVED_DOCUMENT_SCOPE_CONFLICT",
        "UNTRUSTED_SOURCE_PROVENANCE_REJECTED",
        "NO_NEW_EVIDENCE",
    )


def test_synthetic_mode_isolation():
    """Synthetic mode preserves isolated unit testing without requiring canonical content."""
    validator = EvidenceProvenanceValidator()
    item = EvidenceItem(
        evidence_id="SYN_EV_01",
        doc_id="DOC_SYN",
        page_id="P1",
        page_number=1,
        text="Synthetic test evidence.",
    )

    executor = TargetedCorrectionExecutor(
        provenance_validator=validator,
        synthetic_mode=True,
    )
    status, reason = executor.provenance_validator.validate_provenance(
        item,
        require_index_verification=executor.require_index_verification,
        require_content_verification=executor.require_content_verification,
    )
    assert status == ProvenanceValidationStatus.SYNTACTIC_VALID


def test_content_only_registration_rejected_in_strict_index_mode():
    """Independent reviewer reproduction: Canonical content entry for unindexed item cannot bypass index check.

    An EvidenceProvenanceValidator constructed with a canonical content entry for (DOC_NOT_INDEXED, 1, EV_GHOST)
    and an empty trusted-index identity set MUST NOT return CONTENT_VERIFIED when require_index_verification=True.
    """
    validator = EvidenceProvenanceValidator()
    # Manually insert into trusted_content without registering into trusted_index
    norm_doc = "DOC_NOT_INDEXED"
    citation_key = (norm_doc, 1, "EV_GHOST")
    validator.trusted_content[citation_key] = "Matching ghost text"
    # trusted_index remains EMPTY

    item = EvidenceItem(
        evidence_id="EV_GHOST",
        doc_id="DOC_NOT_INDEXED",
        page_id="P1",
        page_number=1,
        text="Matching ghost text",
    )

    # 1. When index is required but trusted_index is empty -> fail closed
    status, reason = validator.validate_provenance(
        item,
        require_index_verification=True,
        require_content_verification=True,
    )
    assert status == ProvenanceValidationStatus.UNVERIFIED
    assert "TRUSTED_SOURCE_INDEX_UNAVAILABLE" in reason

    # 2. When trusted_index has other documents but not EV_GHOST -> untrusted identity
    validator.trusted_index.add(("DOC_LEGIT", 1, "EV_LEGIT"))
    status2, reason2 = validator.validate_provenance(
        item,
        require_index_verification=True,
        require_content_verification=True,
    )
    assert status2 == ProvenanceValidationStatus.UNVERIFIED
    assert "UNTRUSTED_SOURCE_IDENTITY" in reason2


def test_unindexed_item_matching_content_cannot_receive_content_verified():
    """Even if require_index_verification=False, matching canonical content on an unindexed item cannot be CONTENT_VERIFIED."""
    validator = EvidenceProvenanceValidator()
    citation_key = ("DOC_UNINDEXED", 1, "EV_MATCH")
    validator.trusted_content[citation_key] = "Exact matching canonical text"

    item = EvidenceItem(
        evidence_id="EV_MATCH",
        doc_id="DOC_UNINDEXED",
        page_id="P1",
        page_number=1,
        text="Exact matching canonical text",
    )

    # When require_index_verification is False, it cannot receive CONTENT_VERIFIED because citation identity is unindexed
    status, reason = validator.validate_provenance(
        item,
        require_index_verification=False,
        require_content_verification=False,
    )
    assert status != ProvenanceValidationStatus.CONTENT_VERIFIED
    assert status == ProvenanceValidationStatus.SYNTACTIC_VALID
    assert "CONTENT_MATCH_BUT_INDEX_UNVERIFIED" in reason

