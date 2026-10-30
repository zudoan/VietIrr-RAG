"""
TEST: REAL M3 SourceFaithfulEvidenceAllocator INTEGRATION
Verifies that the frozen M3 allocator consumes authentic V4 index and produces
the exact 5-unit evidence budget with diversity cap (max 2 per page).
"""

import json
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))
sys.path.insert(0, str(WORKSPACE / "src"))

from viirr_retrieval.evidence_allocator import SourceFaithfulEvidenceAllocator


def test_real_m3_allocation():
    pages_path = WORKSPACE / "outputs/V4_EXPERIMENT/index/pages_v4.jsonl"
    units_path = WORKSPACE / "outputs/V4_EXPERIMENT/index/evidence_units_v4.jsonl"

    pages = [json.loads(line) for line in open(pages_path, encoding="utf-8") if line.strip()]
    units = [json.loads(line) for line in open(units_path, encoding="utf-8") if line.strip()]

    page_by_id = {p["page_id"]: p for p in pages}
    page_to_unit_indexes = {}
    for idx, u in enumerate(units):
        pid = u["page_id"]
        page_to_unit_indexes.setdefault(pid, []).append(idx)

    # Use first 5 pages of QĐ 1606
    qd1606_pages = [p for p in pages if p["doc_id"] == "IRR_CP_2019_89661cdf"][:5]
    assert len(qd1606_pages) == 5

    allocator = SourceFaithfulEvidenceAllocator(max_units_budget=5, max_per_page=2)
    allocated = allocator.allocate_evidence(
        ranked_pages=qd1606_pages,
        page_to_unit_indices=page_to_unit_indexes,
        units_corpus=units,
        query="Mực nước dâng bình thường hồ Dầu Tiếng là bao nhiêu?",
    )

    assert len(allocated) == 5, f"Expected 5 allocated units, got {len(allocated)}"
    
    # Check max 2 per page diversity
    page_counts = {}
    for it in allocated:
        pid = it["page_id"]
        page_counts[pid] = page_counts.get(pid, 0) + 1

    for pid, cnt in page_counts.items():
        assert cnt <= 2, f"Page {pid} exceeded diversity cap with {cnt} units"

    print(f"[PASS] Real M3 successfully allocated {len(allocated)} units across {len(page_counts)} distinct pages.")
    for idx, it in enumerate(allocated, 1):
        print(f"  {idx}. Evidence ID: {it['evidence_id']} (Page {it['page_number']}) | Score: {it.get('allocated_score', 0.0):.2f}")


if __name__ == "__main__":
    test_real_m3_allocation()
