"""Unit and integration tests for Stage 3 Pre-Benchmark Gate:
1. Structural metadata trust verification (rejecting forged table_ids, relation type mismatch, parser-backed links).
2. Strict document identity & version matching (version required, contradictory doc_id vs document_number).
3. P5 retrieval response contract (exact frozen P5 shape, malformed response rejection, genuine empty list).
"""

from typing import Any, Optional
import pytest

from viirr_ontology.schema.claim import ClaimPolarity, TechnicalClaim
from viirr_ontology.schema.evidence import (
    EvidenceItem,
    EvidenceRelation,
    EvidenceSet,
)
from viirr_ontology.verifier.ontology_verifier import OntologyConstraintVerifier
from viirr_ontology.correction.planner import EvidenceCorrectionPlanner
from viirr_ontology.correction.retrieval_adapter import (
    MockRetrievalBackend,
    PageRegionRetrievalAdapter,
    RealRetrievalBackend,
)
from viirr_ontology.correction.executor import TargetedCorrectionExecutor
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


# =============================================================================
# 1. STRUCTURAL METADATA & TRUST BOUNDARY DEFECT TESTS
# =============================================================================

def test_forged_table_id_untrusted_injected_remains_insufficient():
    """Defect 1 Reproduction & Fix:
    Two EvidenceItem objects declare self-declared table_id='UNTRUSTED_INJECTED'.
    Without parser-backed trusted source registration, this metadata must be REJECTED.
    The executor must NOT promote this to a verified table_row_to_header relation,
    and the claim must remain INSUFFICIENT (preventing false SUPPORTED).
    """
    verifier = OntologyConstraintVerifier()
    planner = EvidenceCorrectionPlanner()
    backend = MockRetrievalBackend()
    adapter = PageRegionRetrievalAdapter(backend)
    executor = TargetedCorrectionExecutor(verifier=verifier, retrieval_adapter=adapter, planner=planner)

    claim = TechnicalClaim(
        claim_id="C_ADVERSARIAL_FORGED_TABLE",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_ROW_ADVERSARIAL"],
    )

    # Both row and injected header claim table_id="UNTRUSTED_INJECTED"
    initial_ev = EvidenceSet(
        query_id="Q_ADV_FORGED",
        evidence_items=[
            _item(
                "E_ROW_ADVERSARIAL",
                "Hồ Hòa Bình | 117 m",
                doc_id="DOC_ATTACK",
                page=5,
                metadata={"table_id": "UNTRUSTED_INJECTED"},
            )
        ],
    )

    injected_header = _item(
        "E_HEADER_INJECTED",
        "Bảng thông số kỹ thuật tiêu đề cột: Mực nước dâng bình thường (m)",
        doc_id="DOC_ATTACK",
        page=5,
        metadata={"table_id": "UNTRUSTED_INJECTED"},
    )
    backend.register_fixture(r".*", [injected_header])

    res = executor.correct_claim(claim, initial_ev, budget=2)

    # Must NOT be falsely verified or supported
    assert res.initial_status == "INSUFFICIENT"
    assert res.final_status == "INSUFFICIENT", (
        f"Forged table_id must NOT produce SUPPORTED! Got {res.final_status}"
    )
    # Check that any created relation is unverified
    for rel in res.final_evidence_set.evidence_relations:
        assert not rel.verified, "Relation derived from untrusted table_id must have verified=False"


def test_relation_type_mismatch_table_id_cannot_certify_clause_or_version():
    """Defect 1 Requirement:
    Validate that each structural relationship type is supported by its actual source relationship.
    Do NOT certify evidence_to_version or clause_to_condition merely because two regions share a table_id.
    """
    trusted_registry = TrustedSourceStructureRegistry()
    struct_verifier = StructuralRelationVerifier(trusted_structure_registry=trusted_registry)

    # Register genuine table for both items
    trusted_registry.register_table_unit("DOC_740", 1, "E_ROW", "TAB_01")
    trusted_registry.register_table_unit("DOC_740", 1, "E_COND", "TAB_01")

    item_source = _item("E_ROW", "Thông số hàng", doc_id="DOC_740", page=1, metadata={"table_id": "TAB_01"})
    item_target = _item("E_COND", "Điều kiện áp dụng", doc_id="DOC_740", page=1, metadata={"table_id": "TAB_01"})

    # Attempt to verify clause_to_condition using table_id
    verified_clause, reason_clause = struct_verifier.verify_relation(
        source_item=item_source,
        target_item=item_target,
        candidate_relation_type="clause_to_condition",
    )
    assert not verified_clause, "table_id must NOT verify clause_to_condition"
    assert "mismatched_relation_type" in reason_clause

    # Attempt to verify evidence_to_version using table_id
    verified_ver, reason_ver = struct_verifier.verify_relation(
        source_item=item_source,
        target_item=item_target,
        candidate_relation_type="evidence_to_version",
    )
    assert not verified_ver, "table_id must NOT verify evidence_to_version"
    assert "mismatched_relation_type" in reason_ver

    # But genuine table relation with trusted parser registration IS accepted
    verified_table, reason_table = struct_verifier.verify_relation(
        source_item=item_source,
        target_item=item_target,
        candidate_relation_type="table_row_to_header",
    )
    assert verified_table, f"Trusted table_row_to_header must succeed, got {reason_table}"


def test_verified_parser_backed_table_link_succeeds():
    """Defect 1 Positive:
    When authoritative parser metadata is registered in TrustedSourceStructureRegistry,
    the structural relation is certified and claim is SUPPORTED.
    """
    verifier = OntologyConstraintVerifier()
    planner = EvidenceCorrectionPlanner()
    backend = MockRetrievalBackend()
    adapter = PageRegionRetrievalAdapter(backend)
    executor = TargetedCorrectionExecutor(verifier=verifier, retrieval_adapter=adapter, planner=planner)

    # Explicitly register authoritative parser metadata
    executor.register_trusted_table_unit("DOC_GENUINE", 4, "E_ROW_REAL", "TAB_HYDRAULIC_01")
    executor.register_trusted_table_unit("DOC_GENUINE", 4, "E_HEADER_REAL", "TAB_HYDRAULIC_01")

    claim = TechnicalClaim(
        claim_id="C_PARSER_BACKED",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_ROW_REAL"],
    )

    initial_ev = EvidenceSet(
        query_id="Q_PARSER_REAL",
        evidence_items=[
            _item(
                "E_ROW_REAL",
                "Hồ Hòa Bình | 117 m",
                doc_id="DOC_GENUINE",
                page=4,
                metadata={"table_id": "TAB_HYDRAULIC_01"},
            )
        ],
    )

    header_item = _item(
        "E_HEADER_REAL",
        "Bảng thông số kỹ thuật tiêu đề cột: Mực nước dâng bình thường (m)",
        doc_id="DOC_GENUINE",
        page=4,
        metadata={"table_id": "TAB_HYDRAULIC_01"},
    )
    backend.register_fixture(r".*", [header_item])

    res = executor.correct_claim(claim, initial_ev, budget=2)
    assert res.initial_status == "INSUFFICIENT"
    assert res.final_status == "SUPPORTED"
    verified_rels = [r for r in res.final_evidence_set.evidence_relations if r.verified]
    assert len(verified_rels) >= 1
    assert verified_rels[0].relation_type == "table_row_to_header"


# =============================================================================
# 2. DOCUMENT IDENTITY & VERSION VALIDATION DEFECT TESTS
# =============================================================================

def test_missing_version_when_explicit_version_required_returns_false():
    """Defect 2A Reproduction & Fix:
    Claim explicitly requests document version 2.0.
    Item has matching doc_id but has no document_version.
    Scope matching MUST return False (missing version must not count as verified match).
    """
    registry = DocumentIdentityRegistry()

    # Item with no version
    item_no_version = _item(
        "E_NO_VER",
        "Quy trình vận hành liên hồ chứa",
        doc_id="DOC_740",
        document_version=None,
    )

    # Claim requiring version 2.0
    match = registry.is_scope_matching(
        claim_scope="DOC_740",
        item_doc_id=item_no_version.doc_id,
        item_doc_number=item_no_version.document_number,
        item_doc_version=item_no_version.document_version,
        claim_version="2.0",
    )
    assert not match, "Claim requiring version 2.0 must NOT match item with no version"

    # When item actually has version 2.0, it should match
    item_v2 = _item(
        "E_V2",
        "Quy trình vận hành liên hồ chứa v2",
        doc_id="DOC_740",
        document_version="2.0",
    )
    match_v2 = registry.is_scope_matching(
        claim_scope="DOC_740",
        item_doc_id=item_v2.doc_id,
        item_doc_number=item_v2.document_number,
        item_doc_version=item_v2.document_version,
        claim_version="2.0",
    )
    assert match_v2, "Item with exact version 2.0 must match"


def test_contradictory_doc_id_and_document_number_rejected():
    """Defect 2B Reproduction & Fix:
    Claim requests DOC_A.
    Retrieved item has doc_id DOC_B but declares document_number DOC_A.
    Contradictory canonical doc_id and document_number without verified alias mapping MUST be rejected.
    """
    registry = DocumentIdentityRegistry()

    item_contradictory = _item(
        "E_CONTRADICTORY",
        "Nội dung văn bản quy chuẩn",
        doc_id="DOC_B",
        document_number="DOC_A",
    )

    match = registry.is_scope_matching(
        claim_scope="DOC_A",
        item_doc_id=item_contradictory.doc_id,
        item_doc_number=item_contradictory.document_number,
        item_doc_version=item_contradictory.document_version,
    )
    assert not match, "Contradictory doc_id DOC_B vs document_number DOC_A must return False"


def test_provenance_validation_statuses_and_source_index_verification():
    """Defect 2 Requirement:
    Define separate statuses for SYNTACTIC_VALID, INDEX_VERIFIED, and UNVERIFIED.
    Require source-index verification before promoting retrieved evidence in real-data mode.
    """
    validator = EvidenceProvenanceValidator()

    # 1. Syntactically invalid item (empty doc_id) -> UNVERIFIED
    bad_item = EvidenceItem("E_BAD", "", "P1", 1, text="Text")
    status, reason = validator.validate_provenance(bad_item, require_index_verification=False)
    assert status == ProvenanceValidationStatus.UNVERIFIED

    # 2. Syntactically valid item without index entry when index verification is not enforced -> SYNTACTIC_VALID
    unindexed_item = _item("E_SYNTAX", "Text", doc_id="DOC_UNKNOWN", page=1)
    status, reason = validator.validate_provenance(unindexed_item, require_index_verification=False)
    assert status == ProvenanceValidationStatus.SYNTACTIC_VALID

    # 3. In real-data mode where index verification IS required -> UNVERIFIED
    status_real, _ = validator.validate_provenance(unindexed_item, require_index_verification=True)
    assert status_real == ProvenanceValidationStatus.UNVERIFIED

    # 4. Item registered in source index -> INDEX_VERIFIED
    validator.register_verified_index_evidence(
        doc_id="DOC_INDEXED",
        page_number=1,
        evidence_id="E_CORPUS_01",
    )
    indexed_item = _item("E_CORPUS_01", "Text", doc_id="DOC_INDEXED", page=1)
    status_idx, reason_idx = validator.validate_provenance(indexed_item, require_index_verification=True)
    assert status_idx == ProvenanceValidationStatus.INDEX_VERIFIED


# =============================================================================
# 3. P5 RETRIEVAL CONTRACT & LIVE RETRIEVER ADAPTER TESTS
# =============================================================================

class MockP5FrozenRetriever:
    """Mock stub simulating the exact contract returned by WindowedPageRegionRetriever.retrieve()."""

    def __init__(self, response: Any):
        self.response = response

    def retrieve(self, question: str = "", region_top_k: int = 20, **kwargs: Any) -> Any:
        return self.response


class StubP5Evidence:
    """Stub representing a P5 Evidence object."""

    def __init__(
        self,
        evidence_id: str,
        doc_id: str,
        page_id: str,
        page_number: int,
        content: str,
        score: float,
        provenance: Optional[dict[str, Any]] = None,
    ):
        self.evidence_id = evidence_id
        self.doc_id = doc_id
        self.page_id = page_id
        self.page_number = page_number
        self.content = content
        self.score = score
        self.provenance = provenance or {}


def test_real_retrieval_backend_contract_success():
    """Requirement 3 Contract Test:
    Read actual P5 retrieval contract:
    - evidence: list of Evidence objects
    - selected_page_ids: list of str
    - latency_ms: float
    Preserve original P5 evidence IDs, doc IDs, page IDs, page numbers, scores, and content.
    """
    stub_evidence = [
        StubP5Evidence(
            evidence_id="EV_001",
            doc_id="IRR_GOV_2023_29fb8ed6",
            page_id="IRR_GOV_2023_29fb8ed6_p4",
            page_number=4,
            content="Hồ Hòa Bình có mực nước dâng bình thường 117 m.",
            score=0.885,
            provenance={"parser": "vietirr_pdf", "table_id": "TAB_PARAM_01"},
        ),
        StubP5Evidence(
            evidence_id="EV_002",
            doc_id="IRR_GOV_2023_29fb8ed6",
            page_id="IRR_GOV_2023_29fb8ed6_p5",
            page_number=5,
            content="Mực nước lũ thiết kế là 120 m.",
            score=0.762,
            provenance={"parser": "vietirr_pdf"},
        ),
    ]

    p5_response = {
        "evidence": stub_evidence,
        "selected_page_ids": ["IRR_GOV_2023_29fb8ed6_p4", "IRR_GOV_2023_29fb8ed6_p5"],
        "latency_ms": 42.5,
    }

    retriever_stub = MockP5FrozenRetriever(p5_response)
    backend = RealRetrievalBackend(retriever_instance=retriever_stub)
    adapter = PageRegionRetrievalAdapter(backend)

    results = adapter.search_regions(query="mực nước dâng bình thường", top_k=2)

    assert len(results) == 2
    # Verify preservation of P5 attributes
    it1 = results[0]
    assert it1.evidence_id == "EV_001"
    assert it1.doc_id == "IRR_GOV_2023_29fb8ed6"
    assert it1.page_id == "IRR_GOV_2023_29fb8ed6_p4"
    assert it1.page_number == 4
    assert it1.text == "Hồ Hòa Bình có mực nước dâng bình thường 117 m."
    assert it1.score == 0.885
    assert it1.provenance_metadata.get("table_id") == "TAB_PARAM_01"


def test_real_retrieval_backend_rejects_malformed_response():
    """Requirement 3 Test:
    Reject malformed retrieval responses (missing mandatory 'evidence' field or non-dict output)
    with ValueError rather than silently returning an empty list.
    """
    # 1. Non-dict output
    retriever_non_dict = MockP5FrozenRetriever("invalid string response")
    backend_bad1 = RealRetrievalBackend(retriever_instance=retriever_non_dict)
    with pytest.raises(ValueError, match="Malformed retrieval response: expected dict"):
        backend_bad1.search_regions("test query")

    # 2. Missing mandatory 'evidence' key (e.g. legacy 'evidence_rows')
    retriever_missing_evidence = MockP5FrozenRetriever({
        "evidence_rows": [],
        "selected_page_ids": [],
    })
    backend_bad2 = RealRetrievalBackend(retriever_instance=retriever_missing_evidence)
    with pytest.raises(ValueError, match="missing mandatory 'evidence'"):
        backend_bad2.search_regions("test query")


def test_real_retrieval_backend_genuine_empty_results():
    """Requirement 3 Test:
    Differentiate schema mismatch from genuine empty results ('evidence': []).
    """
    empty_p5_response = {
        "evidence": [],
        "selected_page_ids": [],
        "latency_ms": 15.2,
    }
    retriever_empty = MockP5FrozenRetriever(empty_p5_response)
    backend = RealRetrievalBackend(retriever_instance=retriever_empty)
    adapter = PageRegionRetrievalAdapter(backend)

    results = adapter.search_regions("nonexistent query", top_k=5)
    assert results == [], "Genuine empty result must return [] cleanly without exception"
