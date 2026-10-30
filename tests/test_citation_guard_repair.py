"""Regression tests for Phase 1 Citation Guard root-cause repair.

Covers:
- V3_1_CHAL_00101: Coordinate sluice clause retains BOTH Hàm Giang and Long Hiệp citations.
- V3_1_CHAL_00128: Coordinate sluice clause retains BOTH Bắc Trang and Bông Bót citations.
- V3_1_CHAL_00022: Multi-document An Long retain both citations.
- V3_CORE_00111: Rejects irrelevant citation while keeping valid supporting citations.
- Fabricated citation rejection invariant.
"""

import json
from pathlib import Path
import pytest

from viirr_rag.pipeline import (
    Evidence,
    build_context,
    enforce_citation_grounding,
    parse_generation,
)

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = ROOT / "research/ontology_final_consistency/EXACT_SAME_RUN_EVIDENCE_SNAPSHOTS.json"


@pytest.fixture(scope="module")
def snapshots_by_id():
    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {s["qa_id"]: s for s in data["snapshots"]}


def test_v3_1_chal_00101_retains_both_citations(snapshots_by_id):
    """V3_1_CHAL_00101: Both Ham Giang and Long Hiep citations must be retained."""
    snap = snapshots_by_id["V3_1_CHAL_00101"]
    parsed = parse_generation(snap["raw_qwen_output"])
    ev_objs = [
        Evidence(
            rank=u["rank"],
            evidence_id=u["evidence_id"],
            doc_id=u["doc_id"],
            page_id=u["page_id"],
            page_number=u["page_number"],
            unit_type=u["unit_type"],
            score=u["score"],
            text=u["text"],
            source="r6_allocator",
        )
        for u in snap["allocated_evidence_items"]
    ]
    ctx = build_context(ev_objs, budget_tokens=4000)
    res, audit = enforce_citation_grounding(parsed, ctx)

    assert audit["action"] == "PASS"
    retained_ids = [c["evidence_id"] for c in res.citations]
    assert "TAB_IRR_CTL_2024_9a520097_P0056_01_R005_C005" in retained_ids
    assert "TAB_IRR_CTL_2024_9a520097_P0056_01_R011_C005" in retained_ids
    assert len(retained_ids) == 2


def test_v3_1_chal_00101_comma_variant_retains_both_citations(snapshots_by_id):
    """V3_1_CHAL_00101: Live comma-separated variant must retain BOTH citations."""
    snap = snapshots_by_id["V3_1_CHAL_00101"]
    raw_comma = json.dumps({
        "answer": "Cao trình đáy cống Hàm Giang là -3 m, cống Long Hiệp là -2 m.",
        "citations": [
            {"doc_id": "IRR_CTL_2024_9a520097", "page_number": 56, "evidence_id": "TAB_IRR_CTL_2024_9a520097_P0056_01_R005_C005"},
            {"doc_id": "IRR_CTL_2024_9a520097", "page_number": 56, "evidence_id": "TAB_IRR_CTL_2024_9a520097_P0056_01_R011_C005"}
        ],
        "abstained": False,
        "abstention_reason": "",
        "evidence_supported": True
    })
    parsed = parse_generation(raw_comma)
    ev_objs = [
        Evidence(
            rank=u["rank"],
            evidence_id=u["evidence_id"],
            doc_id=u["doc_id"],
            page_id=u["page_id"],
            page_number=u["page_number"],
            unit_type=u["unit_type"],
            score=u["score"],
            text=u["text"],
            source="r6_allocator",
        )
        for u in snap["allocated_evidence_items"]
    ]
    ctx = build_context(ev_objs, budget_tokens=4000)
    res, audit = enforce_citation_grounding(parsed, ctx)

    assert audit["action"] == "PASS"
    retained_ids = [c["evidence_id"] for c in res.citations]
    assert "TAB_IRR_CTL_2024_9a520097_P0056_01_R005_C005" in retained_ids
    assert "TAB_IRR_CTL_2024_9a520097_P0056_01_R011_C005" in retained_ids
    assert len(retained_ids) == 2



def test_v3_1_chal_00128_retains_both_citations(snapshots_by_id):
    """V3_1_CHAL_00128: Both Bac Trang and Bong Bot citations must be retained."""
    snap = snapshots_by_id["V3_1_CHAL_00128"]
    parsed = parse_generation(snap["raw_qwen_output"])
    ev_objs = [
        Evidence(
            rank=u["rank"],
            evidence_id=u["evidence_id"],
            doc_id=u["doc_id"],
            page_id=u["page_id"],
            page_number=u["page_number"],
            unit_type=u["unit_type"],
            score=u["score"],
            text=u["text"],
            source="r6_allocator",
        )
        for u in snap["allocated_evidence_items"]
    ]
    ctx = build_context(ev_objs, budget_tokens=4000)
    res, audit = enforce_citation_grounding(parsed, ctx)

    assert audit["action"] == "PASS"
    retained_ids = [c["evidence_id"] for c in res.citations]
    assert "TAB_IRR_CTL_2024_9a520097_P0056_01_R007_C005" in retained_ids
    assert "TAB_IRR_CTL_2024_9a520097_P0056_01_R014_C005" in retained_ids
    assert len(retained_ids) == 2


def test_v3_core_00111_filters_irrelevant_citation(snapshots_by_id):
    """V3_CORE_00111: Valid citations retained, but irrelevant page 17 citation dropped."""
    snap = snapshots_by_id["V3_CORE_00111"]
    parsed = parse_generation(snap["raw_qwen_output"])
    ev_objs = [
        Evidence(
            rank=u["rank"],
            evidence_id=u["evidence_id"],
            doc_id=u["doc_id"],
            page_id=u["page_id"],
            page_number=u["page_number"],
            unit_type=u["unit_type"],
            score=u["score"],
            text=u["text"],
            source="r6_allocator",
        )
        for u in snap["allocated_evidence_items"]
    ]
    ctx = build_context(ev_objs, budget_tokens=4000)
    res, audit = enforce_citation_grounding(parsed, ctx)

    assert audit["action"] == "PASS"
    retained_ids = [c["evidence_id"] for c in res.citations]
    assert "REG_IRR_CTL_2025_b0541877_P0001_B010" in retained_ids
    assert "REG_IRR_CTL_2025_787e653b_P0012_B002" in retained_ids
    assert "REG_IRR_CTL_2025_787e653b_P0017_B002" not in retained_ids
    assert len(retained_ids) == 2


def test_fabricated_citation_rejected():
    """Ensure that fabricated citation IDs are never retained."""
    ev = Evidence(
        rank=1,
        evidence_id="REG_REAL_001",
        doc_id="DOC_REAL",
        page_id="P1",
        page_number=1,
        unit_type="TEXT_REGION",
        score=1.0,
        text="Mực nước hồ A là 50 m.",
        source="r6_allocator",
    )
    ctx = build_context([ev], budget_tokens=1000)
    raw = json.dumps({
        "answer": "Mực nước hồ A là 50 m.",
        "citations": [
            {"doc_id": "DOC_REAL", "page_number": 1, "evidence_id": "FABRICATED_ID_999"},
        ],
        "abstained": False,
        "abstention_reason": "",
        "evidence_supported": True,
    })
    parsed = parse_generation(raw)
    res, audit = enforce_citation_grounding(parsed, ctx)
    assert audit["action"] == "ABSTAIN"
    assert len(res.citations) == 0
