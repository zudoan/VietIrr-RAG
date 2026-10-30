from __future__ import annotations

import pytest
from viirr_retrieval.table_aware import TableAwareEvidenceResolver


def _create_synthetic_table_units() -> list[dict]:
    unit1 = {
        "doc_id": "DOC_01",
        "document_id": "DOC_01",
        "page_id": "PAGE_DOC_01_0001",
        "page_number": 1,
        "evidence_id": "TAB_DOC_01_P0001_01",
        "table_id": "TAB_DOC_01_P0001_01",
        "unit_type": "TABLE_REGION",
        "index_text": (
            "TT | Trạm | Mực nước thực đo (m) — 02/10 | Mực nước dự báo (m) — 05/10\n"
            "1 | Tri Tôn | 2,02 | 1,94\n"
            "2 | Vĩnh Điều | 1,49 | 1,46"
        ),
        "raw_text": (
            "TT | Trạm | Mực nước thực đo (m) — 02/10 | Mực nước dự báo (m) — 05/10\n"
            "1 | Tri Tôn | 2,02 | 1,94\n"
            "2 | Vĩnh Điều | 1,49 | 1,46"
        ),
        "source_sha256": "1" * 64,
    }
    unit2 = {
        "doc_id": "DOC_01",
        "document_id": "DOC_01",
        "page_id": "PAGE_DOC_01_0001",
        "page_number": 1,
        "evidence_id": "TAB_DOC_01_P0001_02",
        "table_id": "TAB_DOC_01_P0001_02",
        "unit_type": "TABLE_REGION",
        "index_text": (
            "TT | Hồ chứa | Dung tích thiết kế (triệu m3) | Dung tích hiện tại (triệu m3)\n"
            "1 | Dầu Tiếng | 1580,0 | 1120,5"
        ),
        "raw_text": (
            "TT | Hồ chứa | Dung tích thiết kế (triệu m3) | Dung tích hiện tại (triệu m3)\n"
            "1 | Dầu Tiếng | 1580,0 | 1120,5"
        ),
        "source_sha256": "2" * 64,
    }
    return [unit1, unit2]


@pytest.fixture
def table_resolver():
    units = _create_synthetic_table_units()
    return TableAwareEvidenceResolver(units)


def test_valid_table_cell(table_resolver):
    valid_cell = {
        "evidence_id": "TAB_DOC_01_P0001_01_R000_C002",
        "doc_id": "DOC_01",
        "page_id": "PAGE_DOC_01_0001",
        "page_number": 1,
        "table_id": "TAB_DOC_01_P0001_01",
        "unit_type": "TABLE_CELL",
    }
    parent = _create_synthetic_table_units()[0]
    is_valid, status, fact = table_resolver.validate_cell(valid_cell, parent)
    assert is_valid is True
    assert status == "RELATION_VALID"
    assert fact is not None
    assert fact.entity == "Tri Tôn"
    assert fact.numeric_value == 2.02
    assert fact.unit == "m"


def test_wrong_parent_table(table_resolver):
    # Valid cell ID from table 1 presented with parent unit from table 2
    cell = {
        "evidence_id": "TAB_DOC_01_P0001_01_R000_C002",
        "doc_id": "DOC_01",
        "page_id": "PAGE_DOC_01_0001",
        "page_number": 1,
        "table_id": "TAB_DOC_01_P0001_01",
        "unit_type": "TABLE_CELL",
    }
    wrong_parent = _create_synthetic_table_units()[1]  # TAB_DOC_01_P0001_02
    is_valid, status, fact = table_resolver.validate_cell(cell, wrong_parent)
    assert is_valid is False
    assert "LOCATION_INVALID: Parent table ID mismatch" in status


def test_wrong_page_number(table_resolver):
    cell = {
        "evidence_id": "TAB_DOC_01_P0001_01_R000_C002",
        "doc_id": "DOC_01",
        "page_id": "PAGE_DOC_01_0001",
        "page_number": 99,  # Wrong page
        "table_id": "TAB_DOC_01_P0001_01",
        "unit_type": "TABLE_CELL",
    }
    parent = _create_synthetic_table_units()[0]
    is_valid, status, fact = table_resolver.validate_cell(cell, parent)
    assert is_valid is False
    assert "LOCATION_INVALID: Page number mismatch" in status


def test_wrong_document_id(table_resolver):
    cell = {
        "evidence_id": "TAB_DOC_01_P0001_01_R000_C002",
        "doc_id": "DOC_FAKE_99",  # Wrong doc
        "page_id": "PAGE_DOC_01_0001",
        "page_number": 1,
        "table_id": "TAB_DOC_01_P0001_01",
        "unit_type": "TABLE_CELL",
    }
    parent = _create_synthetic_table_units()[0]
    is_valid, status, fact = table_resolver.validate_cell(cell, parent)
    assert is_valid is False
    assert "LOCATION_INVALID: Document ID mismatch" in status


def test_nonexistent_child_cell_id(table_resolver):
    # Parent table exists, but child cell coordinate R999_C999 does not exist in the table
    cell = {
        "evidence_id": "TAB_DOC_01_P0001_01_R999_C999",
        "doc_id": "DOC_01",
        "page_id": "PAGE_DOC_01_0001",
        "page_number": 1,
        "table_id": "TAB_DOC_01_P0001_01",
        "unit_type": "TABLE_CELL",
    }
    parent = _create_synthetic_table_units()[0]
    is_valid, status, fact = table_resolver.validate_cell(cell, parent)
    assert is_valid is False
    assert "IDENTITY_INVALID: Unknown table cell ID" in status


def test_multiple_tables_on_same_page(table_resolver):
    # Two tables on PAGE_DOC_01_0001
    parent1 = _create_synthetic_table_units()[0]
    parent2 = _create_synthetic_table_units()[1]

    cell1 = {
        "evidence_id": "TAB_DOC_01_P0001_01_R001_C003",
        "doc_id": "DOC_01",
        "page_id": "PAGE_DOC_01_0001",
        "page_number": 1,
        "table_id": "TAB_DOC_01_P0001_01",
    }
    cell2 = {
        "evidence_id": "TAB_DOC_01_P0001_02_R000_C003",
        "doc_id": "DOC_01",
        "page_id": "PAGE_DOC_01_0001",
        "page_number": 1,
        "table_id": "TAB_DOC_01_P0001_02",
    }

    # Cross validation: cell1 with parent2 should fail
    is_valid_cross, status_cross, _ = table_resolver.validate_cell(cell1, parent2)
    assert is_valid_cross is False
    assert "LOCATION_INVALID" in status_cross

    # Proper validation: cell1 with parent1 and cell2 with parent2 must pass
    ok1, status1, fact1 = table_resolver.validate_cell(cell1, parent1)
    ok2, status2, fact2 = table_resolver.validate_cell(cell2, parent2)
    assert ok1 is True and status1 == "RELATION_VALID" and fact1.entity == "Vĩnh Điều"
    assert ok2 is True and status2 == "RELATION_VALID" and fact2.entity == "Dầu Tiếng"
