"""Build the canonical V3 corpus from native PDFs and audited OCR caches."""

from __future__ import annotations

import calendar
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.acquire_v3_official_sources import SOURCES as V3_SOURCES
from src.common.io_utils import repair_mojibake, sha256_file, slug_source
from src.parsing.canonical_parser import load_sources
from src.structure.semantic_table_parser import SemanticTableParser, clean, fold


PARSED = ROOT / "data" / "parsed"
SOURCE = ROOT / "data" / "source"
OCR = ROOT / "data" / "ocr" / "v3"
SNAPSHOT = ROOT / "data" / "v3_input_snapshot"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def record_hash(row: dict) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def year_from(*values: str | None) -> int | None:
    for value in values:
        match = re.search(r"\b(20\d{2})\b", str(value or ""))
        if match:
            return int(match.group(1))
    return None


def reporting_period(title: str, supplied: dict | None, publication_date: str | None) -> tuple[dict | None, dict]:
    if supplied and supplied.get("normalized_start") and supplied.get("normalized_end"):
        return supplied, {"source": "official_source_metadata", "raw": supplied.get("raw_period"), "confidence": 0.98}
    text = clean(title)
    # Explicit ranges in titles/headers only; never min/max across body dates.
    match = re.search(r"(?:từ\s*(?:ngày\s*)?)?(\d{1,2})[/-](\d{1,2})(?:[/-](20\d{2}))?\s*(?:đến|[-–÷])\s*(?:ngày\s*)?(\d{1,2})[/-](\d{1,2})[/-](20\d{2})", text, re.I)
    if match:
        d1, m1, y1, d2, m2, y2 = match.groups()
        y1 = y1 or y2
        period = {"raw_period": match.group(0), "normalized_start": f"{int(y1):04d}-{int(m1):02d}-{int(d1):02d}", "normalized_end": f"{int(y2):04d}-{int(m2):02d}-{int(d2):02d}", "period_type": "EXPLICIT_RANGE"}
        return period, {"source": "document_title", "raw": match.group(0), "confidence": 0.96}
    match = re.search(r"tháng\s*(\d{1,2})\s*(?:/|năm\s*)\s*(20\d{2})", text, re.I)
    if match:
        month, year = map(int, match.groups())
        period = {"raw_period": match.group(0), "normalized_start": f"{year:04d}-{month:02d}-01", "normalized_end": f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}", "period_type": "MONTH"}
        return period, {"source": "document_title", "raw": match.group(0), "confidence": 0.92}
    match = re.search(r"\b(?:năm|mùa|vụ)[^\d]{0,12}(20\d{2})(?:\s*[-–]\s*(20\d{2}))?", text, re.I)
    if match:
        y1, y2 = int(match.group(1)), int(match.group(2) or match.group(1))
        period = {"raw_period": match.group(0), "normalized_start": f"{y1:04d}-01-01", "normalized_end": f"{y2:04d}-12-31", "period_type": "YEAR_OR_SEASON"}
        return period, {"source": "document_title", "raw": match.group(0), "confidence": 0.78}
    if publication_date:
        return None, {"source": "unresolved", "raw": None, "confidence": 0.0, "note": "publication_date is not treated as reporting period"}
    return None, {"source": "unresolved", "raw": None, "confidence": 0.0}


def role_for(text: str) -> str:
    value = clean(text)
    f = fold(value)
    if re.match(r"^(dieu|điều)\s+\d+", f):
        return "ARTICLE_HEADING"
    if re.match(r"^(chuong|chương|phan|phần|muc|mục)\s+", f):
        return "SECTION_HEADING"
    if re.match(r"^(bang|bảng|bieu|biểu|phu luc|phụ lục)\s*\d*", f):
        return "TABLE_CAPTION"
    if any(term in f for term in ("phai van hanh", "thuc hien", "khong duoc", "co trach nhiem", "yeu cau", "dam bao")):
        return "OPERATIONAL_RULE"
    if len(value) < 100 and (value.isupper() or value.endswith(":")):
        return "HEADING"
    return "PARAGRAPH"


def ocr_blocks(text: str) -> list[str]:
    """Reconstruct paragraph-size OCR regions while preserving headings."""
    output: list[str] = []
    current: list[str] = []
    for line in (clean(v) for v in text.splitlines()):
        if not line:
            continue
        role = role_for(line)
        if role in {"ARTICLE_HEADING", "SECTION_HEADING", "HEADING"}:
            if current:
                output.append(clean(" ".join(current))); current = []
            output.append(line)
            continue
        current.append(line)
        if len(" ".join(current)) >= 420:
            output.append(clean(" ".join(current))); current = []
    if current:
        output.append(clean(" ".join(current)))
    return output


def source_rows() -> list[dict]:
    rows = []
    for source in load_sources():
        row = repair_mojibake(dict(source))
        row["origin"] = "legacy_official_acquisition"
        rows.append(row)
    audit = json.loads((ROOT / "reports" / "v3_source_acquisition_audit.json").read_text(encoding="utf-8"))["sources"]
    by_id = {r["source_id"]: r for r in audit}
    for source in V3_SOURCES:
        acquired = by_id.get(source["source_id"], {})
        if acquired.get("quality_gate") != "PASS":
            continue
        title = Path(source["filename"]).stem.replace("_", " ")
        rows.append({
            "source_id": source["source_id"], "local_path": acquired["local_path"], "source_url": source["url"],
            "landing_page_url": None, "source_domain": urlparse(source["url"]).netloc.lower(),
            "source_agency": source["agency"], "source_group": source["group"], "title": title,
            "doc_type": "official_water_resource_document",
            "publication_date": None, "reporting_period": None, "effective_date": None,
            "document_number": None, "version_status": "UNKNOWN",
            "core_or_temporal": "temporal" if "BULLETIN" in source["source_id"] or "HEAVY_RAIN" in source["source_id"] else "core_long",
            "basin": ["Mê Công"] if "MEKONG" in source["source_id"] else (["Sông Hương"] if "HUONG" in source["source_id"] else []),
            "province": [], "redistribution_status": "UNCLEAR", "legacy_doc_id": None,
            "download_timestamp": datetime.now(timezone.utc).isoformat(), "origin": "v3_official_expansion",
        })
    # Deduplicate byte-identical reuploads before parsing.
    unique, seen = [], set()
    for row in rows:
        path = ROOT / row["local_path"]
        if not path.exists():
            continue
        digest = sha256_file(path)
        if digest in seen:
            continue
        seen.add(digest)
        row["sha256"] = digest
        unique.append(row)
    return unique


def load_ocr(source_id: str) -> dict[int, dict]:
    return {int(r["page_number"]): r for r in read_jsonl(OCR / f"{source_id}.jsonl")}


def make_doc_id(source: dict, title: str, first_text: str) -> str:
    old_docs = read_jsonl(SNAPSHOT / "data__documents.jsonl")
    old = next((d for d in old_docs if d.get("sha256") == source["sha256"]), None)
    if old:
        return old["doc_id"]
    year = year_from(source.get("publication_date"), title, first_text)
    prefix = slug_source(source.get("source_domain") or source.get("source_group") or "OFFICIAL")
    return f"IRR_{prefix}_{year or 'UNKNOWN'}_{source['sha256'][:8]}"


def build() -> dict:
    PARSED.mkdir(parents=True, exist_ok=True)
    SOURCE.mkdir(parents=True, exist_ok=True)
    sources = source_rows()
    documents, pages, regions = [], [], []
    source_manifest = []
    for idx, source in enumerate(sources, 1):
        path = ROOT / source["local_path"]
        try:
            pdf = fitz.open(path)
        except Exception as exc:
            source_manifest.append({**source, "acceptance_status": "REJECT", "acceptance_reason": f"BROKEN_PDF: {exc}"})
            continue
        native = [clean(p.get_text("text")) for p in pdf]
        native_good = sum(len(t) >= 80 for t in native)
        native_scan = native_good / max(len(pdf), 1) < 0.70 or sum(map(len, native)) < max(300, len(pdf) * 80)
        ocr = load_ocr(source["source_id"])
        page_payloads = []
        for number, native_text in enumerate(native, 1):
            if native_scan and number in ocr and ocr[number]["quality"] in {"GOOD", "PARTIAL"}:
                item = ocr[number]
                page_payloads.append((str(item["text"]).strip(), "OCR", item["quality"], False, item.get("mean_line_confidence")))
            elif len(native_text) >= 80:
                page_payloads.append((native_text, "NATIVE_TEXT", "GOOD" if len(native_text) >= 300 else "PARTIAL", True, None))
            elif number in ocr and ocr[number]["quality"] in {"GOOD", "PARTIAL"}:
                item = ocr[number]
                page_payloads.append((str(item["text"]).strip(), "OCR", item["quality"], False, item.get("mean_line_confidence")))
            else:
                page_payloads.append((native_text, "UNUSABLE", "BROKEN", False, None))
        usable = sum(q in {"GOOD", "PARTIAL"} for _, _, q, _, _ in page_payloads)
        ratio = usable / max(len(pdf), 1)
        accepted = len(pdf) > 0 and ratio >= 0.70
        first_text = " ".join(t for t, _, q, _, _ in page_payloads[:3] if q != "BROKEN")
        title = clean(source.get("title") or path.stem)
        content_folded = fold(" ".join(t for t, _, q, _, _ in page_payloads if q != "BROKEN"))
        title_folded = fold(title)
        domain_mismatch = "quy trinh van hanh lien ho chua" in title_folded and not ("quy trinh van hanh" in content_folded and "ho chua" in content_folded)
        if domain_mismatch:
            accepted = False
        doc_id = make_doc_id(source, title, first_text)
        period, period_prov = reporting_period(title, source.get("reporting_period"), source.get("publication_date"))
        doc = {
            "doc_id": doc_id, "source_id": source["source_id"], "title": title,
            "source_url": source.get("source_url"), "landing_page_url": source.get("landing_page_url"),
            "source_domain": source.get("source_domain"), "source_agency": source.get("source_agency"),
            "source_group": source.get("source_group") or source.get("source_agency"), "doc_type": source.get("doc_type"),
            "publication_date": source.get("publication_date"), "document_reporting_period": period,
            "reporting_period_provenance": period_prov, "effective_date": source.get("effective_date"),
            "document_number": source.get("document_number"), "version_status": source.get("version_status", "UNKNOWN"),
            "core_or_temporal": source.get("core_or_temporal", "temporal"), "basin": source.get("basin", []),
            "province": source.get("province", []), "language": "vi", "is_scanned": native_scan,
            "ocr_used": any(kind == "OCR" for _, kind, _, _, _ in page_payloads),
            "ocr_numeric_qa_allowed": False if any(kind == "OCR" for _, kind, _, _, _ in page_payloads) else None,
            "redistribution_status": source.get("redistribution_status", "UNCLEAR"), "sha256": source["sha256"],
            "local_path": source["local_path"], "page_count": len(pdf), "usable_page_ratio": round(ratio, 4),
            "acceptance_status": "ACCEPT" if accepted else ("REJECT" if domain_mismatch or not len(pdf) else "NEEDS_OCR"),
            "acceptance_reason": "PAGE_LEVEL_TEXT_GATE" if accepted else ("TITLE_CONTENT_DOMAIN_MISMATCH" if domain_mismatch else "INSUFFICIENT_USABLE_PAGES"),
            "human_validated": False,
        }
        doc["record_sha256"] = record_hash(doc)
        documents.append(doc)
        source_manifest.append({**source, "doc_id": doc_id, "acceptance_status": doc["acceptance_status"], "usable_page_ratio": doc["usable_page_ratio"]})
        if not accepted:
            continue
        block_frequency = Counter()
        for page_number, (text, extraction, quality, _, _) in enumerate(page_payloads, 1):
            if quality == "BROKEN":
                continue
            if extraction == "NATIVE_TEXT":
                block_texts = [clean(b[4]) for b in pdf[page_number - 1].get_text("blocks") if clean(b[4])]
            else:
                block_texts = ocr_blocks(text)
            block_frequency.update(fold(v) for v in block_texts if 12 <= len(v) <= 180)
        current_section = None
        for page_number, (text, extraction, quality, numeric_safe, ocr_conf) in enumerate(page_payloads, 1):
            page_id = f"PAGE_{doc_id}_{page_number:04d}"
            page_obj = {
                "page_id": page_id, "doc_id": doc_id, "page_number": page_number,
                "raw_text": text, "normalized_text": clean(text), "text_extraction": extraction,
                "text_quality": quality, "numeric_safe": numeric_safe, "ocr_mean_confidence": ocr_conf,
                "page_width": round(pdf[page_number - 1].rect.width, 2), "page_height": round(pdf[page_number - 1].rect.height, 2),
            }
            page_obj["sha256"] = record_hash(page_obj)
            pages.append(page_obj)
            if quality == "BROKEN":
                continue
            if extraction == "NATIVE_TEXT":
                blocks = pdf[page_number - 1].get_text("blocks")
                candidates = [(b[:4], clean(b[4])) for b in blocks if clean(b[4])]
            else:
                # Reconstruct paragraphs; OCR does not provide benchmark-safe bounding boxes.
                candidates = [(None, block) for block in ocr_blocks(text)]
            for order, (bbox, block_text) in enumerate(candidates):
                if len(block_text) < 12:
                    continue
                role = "HEADER_FOOTER" if block_frequency[fold(block_text)] >= 3 and len(block_text) <= 180 else role_for(block_text)
                if role in {"ARTICLE_HEADING", "SECTION_HEADING", "HEADING"}:
                    current_section = block_text[:180]
                region = {
                    "region_id": f"REG_{doc_id}_P{page_number:04d}_B{order:03d}", "doc_id": doc_id,
                    "page_id": page_id, "page_number": page_number, "reading_order": order,
                    "region_type": role, "raw_text": block_text, "normalized_text": clean(block_text),
                    "bbox": [round(float(v), 2) for v in bbox] if bbox else None, "section_id": current_section,
                    "text_quality": quality, "text_extraction": extraction, "numeric_safe": numeric_safe,
                    "qa_eligible": role != "HEADER_FOOTER" and (quality == "GOOD" or (quality == "PARTIAL" and len(block_text) >= 80)),
                }
                region["sha256"] = record_hash(region)
                regions.append(region)
        print(f"CORPUS {idx}/{len(sources)} {doc_id} {doc['acceptance_status']} pages={len(pdf)}", flush=True)

    # Reuse frozen structural tables only as raw extraction; semantic meaning is rebuilt.
    accepted_ids = {d["doc_id"] for d in documents if d["acceptance_status"] == "ACCEPT"}
    parser = SemanticTableParser()
    tables = []
    for raw in read_jsonl(SNAPSHOT / "data__tables.jsonl"):
        if raw.get("doc_id") not in accepted_ids:
            continue
        table = parser.parse(raw)
        table["structural_quality"] = table.pop("quality_label", "UNKNOWN")
        table["sha256"] = record_hash({k: v for k, v in table.items() if k != "sha256"})
        tables.append(table)

    write_jsonl(PARSED / "documents.jsonl", documents)
    write_jsonl(PARSED / "pages.jsonl", pages)
    write_jsonl(PARSED / "regions.jsonl", regions)
    write_jsonl(PARSED / "tables.jsonl", tables)
    write_jsonl(SOURCE / "source_manifest.jsonl", source_manifest)
    # Compatibility mirrors; canonical V3 source of truth remains data/parsed/.
    for name in ("documents", "pages", "regions", "tables"):
        shutil.copy2(PARSED / f"{name}.jsonl", ROOT / "data" / f"{name}.jsonl")
    summary = {
        "documents_total": len(documents), "accepted_documents": sum(d["acceptance_status"] == "ACCEPT" for d in documents),
        "core_long_accepted": sum(d["acceptance_status"] == "ACCEPT" and d["core_or_temporal"] == "core_long" for d in documents),
        "temporal_accepted": sum(d["acceptance_status"] == "ACCEPT" and d["core_or_temporal"] == "temporal" for d in documents),
        "ocr_documents_accepted": sum(d["acceptance_status"] == "ACCEPT" and d["ocr_used"] for d in documents),
        "pages": len(pages), "regions": len(regions), "tables": len(tables),
        "semantic_good_tables": sum(t["semantic_quality"] == "GOOD" for t in tables),
        "semantic_tuples": sum(len(t["semantic_tuples"]) for t in tables),
        "source_groups": len({d["source_group"] for d in documents if d["acceptance_status"] == "ACCEPT"}),
    }
    (ROOT / "reports" / "v3_corpus_build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    build()
