"""Build the B1 indexable view from frozen source artifacts only."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .io_utils import iter_jsonl, load_config, sha256, write_json, write_jsonl


def _table_raw_text(table: dict) -> str:
    raw = table.get("raw_representation") or []
    if isinstance(raw, str):
        return raw
    return "\n".join(" | ".join(str(cell) for cell in row) if isinstance(row, list) else str(row) for row in raw)


def build_indexable_view(root: Path) -> dict:
    config = load_config(root)
    source = config["source"]
    units: list[dict] = []
    for region in iter_jsonl(root / source["regions"]):
        index_text = str(region.get("normalized_text") or region.get("raw_text") or "").strip()
        if not region.get("qa_eligible") or not index_text:
            continue
        units.append({
            "evidence_id": region["region_id"], "doc_id": region["doc_id"],
            "page_id": region["page_id"], "page_number": region["page_number"],
            "unit_type": "TEXT_REGION", "index_text": index_text,
            "raw_text": region.get("raw_text") or "", "source_sha256": region.get("sha256"),
        })
    for table in iter_jsonl(root / source["tables"]):
        if table.get("structural_quality") != "GOOD" or table.get("semantic_quality") != "GOOD":
            continue
        index_text = str(table.get("normalized_representation") or "").strip()
        if not index_text:
            continue
        units.append({
            "evidence_id": table["table_id"], "doc_id": table["doc_id"],
            "page_id": table["page_id"], "page_number": table["page_number"],
            "unit_type": "TABLE_REGION", "index_text": index_text,
            "raw_text": _table_raw_text(table), "source_sha256": table.get("sha256"),
        })
    units.sort(key=lambda row: row["evidence_id"])
    if len({row["evidence_id"] for row in units}) != len(units):
        raise ValueError("Duplicate indexable evidence IDs")
    write_jsonl(root / config["processed"]["evidence_units"], units)

    pages = []
    for page in iter_jsonl(root / source["pages"]):
        text = str(page.get("normalized_text") or page.get("raw_text") or "").strip()
        pages.append({
            "page_id": page["page_id"], "doc_id": page["doc_id"],
            "page_number": page["page_number"], "index_text": text,
            "raw_text": page.get("raw_text") or "", "source_sha256": page.get("sha256"),
        })
    pages.sort(key=lambda row: row["page_id"])
    write_jsonl(root / config["processed"]["pages"], pages)

    benchmark_source = root / source["benchmark"]
    benchmark_target = root / "data" / "benchmark"
    benchmark_target.mkdir(parents=True, exist_ok=True)
    for name in ("all_qa.jsonl", "train.jsonl", "dev.jsonl", "candidate_test.jsonl"):
        shutil.copy2(benchmark_source / name, benchmark_target / name)
    for name in ("minimal_negatives.jsonl", "hard_nonminimal_negatives.jsonl"):
        target = benchmark_target / "negatives" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(benchmark_source / "negatives" / name, target)

    inputs = [root / source[key] for key in ("documents", "pages", "regions", "tables")]
    inputs.extend(benchmark_source / name for name in
                  ("all_qa.jsonl", "train.jsonl", "dev.jsonl", "candidate_test.jsonl",
                   "negatives/minimal_negatives.jsonl", "negatives/hard_nonminimal_negatives.jsonl"))
    manifest = {
        "adapter": "B1_FROZEN_SOURCE_VIEW_V1", "index_contains_qa_or_gold": False,
        "counts": {"evidence_units": len(units), "text_regions": sum(r["unit_type"] == "TEXT_REGION" for r in units),
                   "table_regions": sum(r["unit_type"] == "TABLE_REGION" for r in units), "pages": len(pages)},
        "inputs": [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
                    "sha256": sha256(path)} for path in inputs],
    }
    write_json(root / "data" / "processed" / "B1_INPUT_MANIFEST.json", manifest)
    return manifest

