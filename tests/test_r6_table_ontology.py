from __future__ import annotations

from viirr_retrieval.evidence_bundler import SourceFaithfulEvidenceBundler
from viirr_retrieval.ontology_query_guide import OntologyQueryGuide
from viirr_retrieval.table_aware import TableAwareEvidenceResolver


def _table_unit(text: str, table_id: str = "TAB_DOC_P0001_01") -> dict:
    return {
        "doc_id": "DOC",
        "page_id": "PAGE_DOC_0001",
        "page_number": 1,
        "evidence_id": table_id,
        "unit_type": "TABLE_REGION",
        "index_text": text,
        "raw_text": text,
        "source_sha256": "a" * 64,
    }


def test_query_guide_resolves_hydraulic_intent_without_answer_values():
    guide = OntologyQueryGuide()
    intent = guide.understand("Mực nước chết của hồ Dầu Tiếng là bao nhiêu?")

    assert intent.entity == "Dầu Tiếng"
    assert intent.parameter == "mực nước chết"
    assert intent.expected_dimension == "LENGTH"
    assert intent.expected_units == ["m"]
    assert not any(char.isdigit() for term in intent.expansion_terms() for char in term)


def test_table_parser_preserves_exact_cell_coordinates_and_negative_value():
    unit = _table_unit(
        "TT | Tên cống | Cao trình đáy (m) | Mực nước hiện tại (m)\n"
        "1 | Bến Hiệp | -2,4 | 0,26\n"
        "2 | Dục Dương | -3,3 | 0,02"
    )
    resolver = TableAwareEvidenceResolver([unit])

    fact = next(f for f in resolver.facts if f.evidence_id == "TAB_DOC_P0001_01_R001_C002")
    assert fact.entity == "Dục Dương"
    assert fact.parameter == "Cao trình đáy (m)"
    assert fact.raw_value == "-3,3"
    assert fact.numeric_value == -3.3
    assert fact.unit == "m"
    assert fact.original_raw_text == unit["raw_text"]


def test_table_resolver_binds_multiple_entities_to_requested_parameter():
    unit = _table_unit(
        "Tên huyện | Diện tích (km2) | Dân số\n"
        "Càng Long | 293,9 | 100\n"
        "Cầu Kè | 245 | 200\n"
        "Cầu Ngang | 326 | 300"
    )
    resolver = TableAwareEvidenceResolver([unit])
    question = "Diện tích (tính theo km2) của Càng Long, Cầu Kè và Cầu Ngang lần lượt là bao nhiêu?"
    rows = resolver.resolve(question, [{"page_id": "PAGE_DOC_0001"}], max_facts=3)

    assert [row["evidence_id"] for row in rows] == [
        "TAB_DOC_P0001_01_R000_C001",
        "TAB_DOC_P0001_01_R001_C001",
        "TAB_DOC_P0001_01_R002_C001",
    ]
    assert [row["raw_value"] for row in rows] == ["293,9", "245", "326"]


def test_bundler_preserves_parser_provenance_and_marks_only_structural_cell_verified():
    unit = _table_unit("Tên cống | Cao trình đáy (m)\nDục Dương | -3,3")
    resolver = TableAwareEvidenceResolver([unit])
    cell = resolver.resolve(
        "Cao trình đáy của Dục Dương là bao nhiêu?",
        [{"page_id": "PAGE_DOC_0001"}],
        max_facts=1,
    )[0]

    bundle = SourceFaithfulEvidenceBundler().bundle_evidence_unit(cell)
    evidence = bundle.to_evidence_item()
    assert bundle.relationship_status == "VERIFIED_STRUCTURAL"
    assert bundle.table_id == "TAB_DOC_P0001_01"
    assert bundle.row_id == "R000"
    assert bundle.column_id == "C001"
    assert evidence.page_id == "PAGE_DOC_0001"
    assert evidence.provenance_metadata["structural_metadata"]["structural_source"] == "parser_pipe_grid"


def test_plain_table_block_is_not_promoted_to_verified_relation():
    unit = _table_unit("Tên hồ | Mực nước (m)\nHồ X | 12")
    bundle = SourceFaithfulEvidenceBundler().bundle_evidence_unit(unit)
    assert bundle.relationship_status == "RELATION_UNVERIFIED"

