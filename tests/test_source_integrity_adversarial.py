"""
Adversarial Source-Integrity Tests for VietIRR-RAG Evidence Bundler.

Validates that:
1. The evidence bundler NEVER fabricates source text matching false claims.
2. Contradictory values (45m vs 95m) remain faithful to the original source text.
3. Unit mismatches ('m' vs 'triệu m3') are preserved without alteration.
4. Entity mismatches ('Tả Trạch' vs 'Hương Điền') are preserved faithfully.
5. Incomplete table relationships are explicitly flagged as RELATION_UNVERIFIED.
6. The system NEVER forces a false-supported verification outcome.
"""

import pytest
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "src"))
sys.path.insert(0, str(WORKSPACE))

from viirr_retrieval.evidence_bundler import EvidenceBundle, SourceFaithfulEvidenceBundler


@pytest.fixture
def bundler():
    return SourceFaithfulEvidenceBundler()


def test_adversarial_wrong_value(bundler):
    """
    Scenario 1: Source PDF contains 45.0 m.
    Adversarial claim states: "Mực nước hồ Tả Trạch là 95.0 m".
    Expected: raw_source_text remains 45.0 m, extracted_value is 45.0, NOT 95.0.
    """
    raw_unit = {
        "doc_id": "IRR_GOV_2023_QTVH",
        "page_number": 12,
        "evidence_id": "TAB_001_P0012_01",
        "unit_type": "table",
        "raw_text": "Mực nước dâng bình thường hồ Tả Trạch: 45.0 m.",
    }
    bundle = bundler.bundle_evidence_unit(raw_unit)

    # Assert immutability of source text
    assert "45.0 m" in bundle.raw_source_text
    assert "95.0" not in bundle.raw_source_text
    assert bundle.extracted_value == 45.0
    assert bundle.extracted_value != 95.0


def test_adversarial_wrong_unit(bundler):
    """
    Scenario 2: Source PDF contains unit 'm'.
    Adversarial claim asserts unit 'triệu m3'.
    Expected: extracted_unit is 'm', NOT 'triệu m3'.
    """
    raw_unit = {
        "doc_id": "IRR_CTL_2024_001",
        "page_number": 5,
        "evidence_id": "REG_005",
        "unit_type": "paragraph",
        "raw_text": "Cao trình đỉnh đập hồ Núi Cốc là 48.5 m.",
    }
    bundle = bundler.bundle_evidence_unit(raw_unit)

    assert bundle.extracted_unit == "m"
    assert bundle.extracted_unit != "triệu m3"


def test_adversarial_wrong_facility(bundler):
    """
    Scenario 3: Source PDF describes 'Tả Trạch'.
    Adversarial claim asserts data for 'Hương Điền'.
    Expected: extracted_entity is 'Tả Trạch', NOT 'Hương Điền'.
    """
    raw_unit = {
        "doc_id": "IRR_GOV_2023_01",
        "page_number": 3,
        "evidence_id": "REG_003",
        "unit_type": "paragraph",
        "raw_text": "Hồ Tả Trạch có dung tích phòng lũ là 120 triệu m3.",
    }
    bundle = bundler.bundle_evidence_unit(raw_unit)

    assert bundle.extracted_entity == "Tả Trạch"
    assert bundle.extracted_entity != "Hương Điền"


def test_adversarial_wrong_column_parameter(bundler):
    """
    Scenario 4: Source PDF specifies 'mực nước chết' 23.0 m.
    Adversarial claim claims 'mực nước dâng bình thường' is 23.0 m.
    Expected: extracted_parameter is 'mực nước chết'.
    """
    raw_unit = {
        "doc_id": "IRR_GOV_2023_01",
        "page_number": 4,
        "evidence_id": "TAB_004",
        "unit_type": "table",
        "raw_text": "Mực nước chết: 23.0 m; Dung tích chết: 15 triệu m3.",
    }
    bundle = bundler.bundle_evidence_unit(raw_unit)

    assert bundle.extracted_parameter == "mực nước chết"
    assert bundle.extracted_parameter != "mực nước dâng bình thường"


def test_adversarial_wrong_operating_condition(bundler):
    """
    Scenario 5: Source PDF specifies 'mùa lũ'.
    Adversarial claim claims condition is 'mùa cạn'.
    Expected: condition is 'mùa lũ'.
    """
    raw_unit = {
        "doc_id": "IRR_GOV_2023_02",
        "page_number": 7,
        "evidence_id": "REG_007",
        "unit_type": "paragraph",
        "raw_text": "Trong mùa lũ, mực nước cao nhất trước lũ hồ Hương Điền là 56.0 m.",
    }
    bundle = bundler.bundle_evidence_unit(raw_unit)

    assert bundle.condition == "mùa lũ"
    assert bundle.condition != "mùa cạn"


def test_unverified_table_relation_flagging(bundler):
    """
    Scenario 6: Text has isolated numbers without clear layout grid.
    Expected: relationship_status must be 'RELATION_UNVERIFIED', NOT artificially verified.
    """
    raw_unit = {
        "doc_id": "IRR_CTL_2019_SCAN",
        "page_number": 1,
        "evidence_id": "REG_NO_GRID",
        "unit_type": "paragraph",
        "raw_text": "Báo cáo tình hình nguồn nước tuần qua. Không có số liệu đo đạc cụ thể.",
    }
    bundle = bundler.bundle_evidence_unit(raw_unit)

    assert bundle.relationship_status == "RELATION_UNVERIFIED"
    assert bundle.confidence <= 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
