from __future__ import annotations

import csv
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import fitz

from src.common.io_utils import normalize_text, read_jsonl, repair_mojibake, sha256_file, sha256_record, slug_source


DATE_DMY = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b")
DATE_WORDS = re.compile(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(20\d{2})", re.I)
HEADING = re.compile(r"^(?:PHẦN|CHƯƠNG|MỤC|ĐIỀU|I{1,3}|IV|V?I{0,3}|\d+(?:\.\d+)*)(?:[.\s:–-])", re.I)
CAPTION = re.compile(r"^(?:Bảng|Biểu|Hình|Sơ đồ|Phụ lục)\s*\d*", re.I)


def _split_csv(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _catalog() -> dict[str, dict]:
    result: dict[str, dict] = {}
    path = Path("data/manifests/source_catalog.csv")
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                row = repair_mojibake(row)
                result[row["source_id"]] = row
    return result


def load_sources() -> list[dict]:
    catalog = _catalog()
    rows: list[dict] = []
    for raw in read_jsonl("data/manifests/download_manifest.jsonl"):
        raw = repair_mojibake(raw)
        cat = catalog.get(raw.get("source_id", ""), {})
        url = raw.get("source_url") or cat.get("document_url") or ""
        publication_date = cat.get("publication_date") or None
        track = raw.get("track") or ("core_long" if "core_long" in raw.get("local_path", "") else "temporal")
        title = raw.get("document_title") or cat.get("document_title") or Path(raw.get("local_path", "unknown")).stem
        doc_type = raw.get("document_type") or cat.get("document_type") or "UNKNOWN"
        classification_text = f"{title} {doc_type}".lower()
        if "bản tin" in classification_text or "bulletin" in classification_text or ("tuần" in classification_text and "báo cáo tổng kết" not in classification_text):
            track = "temporal"
        rows.append({
            "source_id": raw.get("source_id"),
            "local_path": raw.get("local_path") or raw.get("raw_pdf_path"),
            "source_url": url,
            "landing_page_url": raw.get("landing_page_url") or cat.get("page_url"),
            "source_domain": urlparse(url).netloc.lower(),
            "source_agency": raw.get("agency") or cat.get("agency") or "UNKNOWN",
            "title": title,
            "doc_type": doc_type,
            "publication_date": publication_date,
            "reporting_period": None,
            "effective_date": None,
            "document_number": None,
            "version_status": "UNKNOWN",
            "core_or_temporal": track,
            "basin": _split_csv(raw.get("basin") or cat.get("basin")),
            "province": _split_csv(raw.get("province") or cat.get("province")),
            "redistribution_status": raw.get("redistribution_status") if raw.get("redistribution_status") in {"CLEAR", "UNCLEAR", "RESTRICTED"} else "UNCLEAR",
            "legacy_doc_id": raw.get("doc_id"),
            "download_timestamp": raw.get("download_timestamp"),
        })
    rows.extend(read_jsonl("configs/supplemental_sources.jsonl"))
    return rows


def _year(source: dict, first_text: str) -> int | None:
    for field in (source.get("publication_date"), (source.get("reporting_period") or {}).get("normalized_start")):
        if field and re.match(r"^20\d{2}", field):
            return int(field[:4])
    matches = DATE_WORDS.findall(first_text) + [(d, m, y) for d, m, y in DATE_DMY.findall(first_text)]
    return int(matches[0][2]) if matches else None


def _period_from_text(text: str, publication_date: str | None) -> dict | None:
    dates: list[str] = []
    for day, month, year in DATE_DMY.findall(text[:8000]):
        try:
            dates.append(f"{int(year):04d}-{int(month):02d}-{int(day):02d}")
        except ValueError:
            pass
    dates = sorted(set(dates))
    if len(dates) >= 2:
        return {"raw_period": f"{dates[0]} đến {dates[-1]}", "normalized_start": dates[0], "normalized_end": dates[-1], "period_type": "UNKNOWN"}
    if dates:
        return {"raw_period": dates[0], "normalized_start": dates[0], "normalized_end": dates[0], "period_type": "UNKNOWN"}
    if publication_date:
        return {"raw_period": publication_date, "normalized_start": publication_date, "normalized_end": publication_date, "period_type": "UNKNOWN"}
    return None


def _document_number(source: dict) -> str | None:
    if source.get("document_number"):
        return source["document_number"]
    match = re.search(r"\bsố\s+([0-9]+(?:/[0-9]{4})?/[A-ZĐa-zđ-]+)", source.get("title", ""), re.I)
    return match.group(1) if match else None


def _version_relations(source_id: str | None) -> dict:
    relations = {
        "SRC_CP_QD740_2019": {"amended_by": ["922/QĐ-TTg"], "same_series_documents": ["922/QĐ-TTg"]},
        "SRC_CP_QD922_2025": {"amends": ["740/QĐ-TTg"], "same_series_documents": ["740/QĐ-TTg"]},
        "SRC_CP_QD214_2018": {"amended_by": ["1500/QĐ-TTg"], "same_series_documents": ["1500/QĐ-TTg"]},
        "SRC_CP_QD1500_2020": {"amends": ["214/QĐ-TTg"], "same_series_documents": ["214/QĐ-TTg"]},
    }
    return relations.get(source_id or "", {})


def _composite_headers(matrix: list[list[str]]) -> tuple[list[str], list[list[str]], int]:
    matrix = [[normalize_text(cell or "").replace("\n", " ") for cell in row] for row in matrix]
    if not matrix:
        return [], [], 0
    width = max(len(row) for row in matrix)
    matrix = [row + [""] * (width - len(row)) for row in matrix]
    header_rows = 1
    if len(matrix) > 1:
        first_data = matrix[1]
        nonempty = sum(bool(x) for x in first_data)
        numeric = sum(bool(re.search(r"\d", x)) for x in first_data)
        if nonempty and (not first_data[0] or numeric <= max(1, nonempty // 3)):
            header_rows = 2
    headers: list[str] = []
    for col in range(width):
        parts = []
        for row in range(header_rows):
            value = matrix[row][col]
            if value and value not in parts:
                parts.append(value)
        headers.append(" — ".join(parts))
    return headers, matrix[header_rows:], header_rows


def _table_quality(headers: list[str], rows: list[list[str]]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if len(headers) < 2 or not rows:
        return "BROKEN", ["TABLE_TOO_SMALL"]
    empty_ratio = sum(not h for h in headers) / len(headers)
    nonempty_rows = [row for row in rows if sum(bool(c) for c in row) >= 2]
    if not nonempty_rows:
        return "BROKEN", ["NO_USABLE_ROWS"]
    if empty_ratio > 0.25:
        reasons.append("EMPTY_HEADERS")
    labels = [re.sub(r"\s+", " ", h.lower()).strip() for h in headers if h]
    if len(labels) != len(set(labels)):
        reasons.append("DUPLICATE_HEADERS")
    if sum(sum(bool(c) for c in row) for row in nonempty_rows) / (len(nonempty_rows) * len(headers)) < 0.5:
        reasons.append("SPARSE_TABLE")
    return ("PARTIAL" if reasons else "GOOD"), reasons


def _semantic_row_label(row: list[str]) -> str:
    for raw in row[:3]:
        value = normalize_text(raw).replace("\n", " ")
        if not value or re.fullmatch(r"\d+[.)]?", value):
            continue
        if len(value) <= 120:
            return value
    return ""


def _caption_for(table_bbox: fitz.Rect, blocks: list[tuple]) -> str | None:
    candidates = []
    for block in blocks:
        text = normalize_text(block[4])
        if not text or block[3] > table_bbox.y0 + 4:
            continue
        distance = table_bbox.y0 - block[3]
        if distance <= 100 and (CAPTION.match(text) or distance <= 30):
            candidates.append((distance, text))
    return min(candidates, default=(0, None), key=lambda x: x[0])[1]


def build_corpus() -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    documents: list[dict] = []
    pages: list[dict] = []
    regions: list[dict] = []
    tables: list[dict] = []
    migrations: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for source in load_sources():
        path = Path(source["local_path"])
        file_hash = sha256_file(path) if path.exists() else ""
        try:
            pdf = fitz.open(path)
            page_count = len(pdf)
            page_texts = [page.get_text("text") for page in pdf]
            first_text = normalize_text("\n".join(page_texts[:2]))
            text_pages = sum(bool(normalize_text(text)) for text in page_texts)
            text_ratio = text_pages / page_count if page_count else 0
            is_scanned = text_ratio < 0.5 or sum(map(len, page_texts)) < max(300, page_count * 80)
            if page_count == 0:
                acceptance, reason = "REJECT", "BROKEN_PDF"
            elif is_scanned:
                acceptance, reason = "NEEDS_OCR", "SCAN_ONLY"
            else:
                acceptance, reason = "ACCEPT", "TEXT_OK"
        except Exception:
            pdf = None
            page_count, page_texts, first_text, text_ratio, is_scanned = 0, [], "", 0.0, False
            acceptance, reason = "REJECT", "BROKEN_PDF"

        year = _year(source, first_text)
        domain = source.get("source_domain") or urlparse(source.get("source_url", "")).netloc
        doc_id = f"IRR_{slug_source(domain)}_{year}_{file_hash[:8]}" if year and file_hash else f"IRR_{slug_source(domain)}_UNKNOWN_{file_hash[:8] or 'MISSING'}"
        if source.get("legacy_doc_id") and source["legacy_doc_id"] != doc_id:
            migrations.append({"old_doc_id": source["legacy_doc_id"], "new_doc_id": doc_id, "reason": "canonical source prefix/year/hash"})

        period = source.get("reporting_period") or _period_from_text(first_text, source.get("publication_date"))
        doc = {
            "doc_id": doc_id,
            "title": source["title"],
            "source_url": source["source_url"],
            "landing_page_url": source.get("landing_page_url"),
            "source_domain": domain,
            "source_agency": source["source_agency"],
            "doc_type": source["doc_type"],
            "publication_date": source.get("publication_date"),
            "reporting_period": period,
            "effective_date": source.get("effective_date"),
            "document_number": _document_number(source),
            "version_status": source.get("version_status") if source.get("version_status") in {"CURRENT", "SUPERSEDED", "UNKNOWN"} else "UNKNOWN",
            "superseded_by": None, "supersedes": None, "amended_by": [], "amends": [], "same_series_documents": [],
            "core_or_temporal": source["core_or_temporal"],
            "basin": source.get("basin", []),
            "province": source.get("province", []),
            "language": "vi",
            "is_scanned": is_scanned,
            "ocr_used": False,
            "redistribution_status": source.get("redistribution_status", "UNCLEAR"),
            "sha256": file_hash,
            "download_timestamp": source.get("download_timestamp") or now,
            "local_path": source["local_path"],
            "page_count": page_count,
            "extractable_text_ratio": round(text_ratio, 3),
            "acceptance_status": acceptance,
            "acceptance_reason": reason,
        }
        doc.update(_version_relations(source.get("source_id")))
        doc["record_sha256"] = sha256_record(doc)
        documents.append(doc)
        if acceptance != "ACCEPT" or pdf is None:
            continue

        for page_index, page in enumerate(pdf):
            page_number = page_index + 1
            page_id = f"PAGE_{doc_id}_{page_number:04d}"
            raw_text = page_texts[page_index]
            normalized = normalize_text(raw_text)
            page_obj = {
                "page_id": page_id, "doc_id": doc_id, "page_number": page_number,
                "raw_text": raw_text, "normalized_text": normalized, "section_id": None,
                "ocr_status": "NOT_NEEDED", "layout_quality": "GOOD" if normalized else "PARTIAL", "metadata": {},
            }
            page_obj["sha256"] = sha256_record(page_obj)
            pages.append(page_obj)

            blocks = sorted(page.get_text("blocks"), key=lambda b: (round(b[1], 1), round(b[0], 1)))
            for order, block in enumerate(blocks):
                text = normalize_text(block[4])
                if len(text) < 2:
                    continue
                first_line = text.splitlines()[0]
                kind = "paragraph"
                if HEADING.match(first_line) and len(text) < 350:
                    kind = "heading"
                elif CAPTION.match(first_line) and len(text) < 500:
                    kind = "caption"
                elif text.startswith(("-", "+", "•")):
                    kind = "list"
                region = {
                    "region_id": f"REG_{doc_id}_P{page_number:04d}_B{order:03d}", "doc_id": doc_id,
                    "page_id": page_id, "page_number": page_number, "region_type": kind,
                    "reading_order": order, "raw_text": block[4], "normalized_text": text,
                    "bbox": [round(float(x), 2) for x in block[:4]], "section_id": None, "metadata": {},
                }
                region["sha256"] = sha256_record(region)
                regions.append(region)

            try:
                found = page.find_tables().tables
            except Exception:
                found = []
            for table_index, found_table in enumerate(found, start=1):
                matrix = found_table.extract() or []
                headers, body, header_rows = _composite_headers(matrix)
                quality, quality_reasons = _table_quality(headers, body)
                table_id = f"TAB_{doc_id}_P{page_number:04d}_{table_index:02d}"
                cells = []
                for row_index, row in enumerate(body):
                    for column_index, raw_cell in enumerate(row):
                        cells.append({
                            "row_index": row_index, "column_index": column_index,
                            "row_label": _semantic_row_label(row),
                            "column_label": headers[column_index] if column_index < len(headers) else "",
                            "raw_cell": raw_cell,
                        })
                caption = _caption_for(fitz.Rect(found_table.bbox), blocks)
                table = {
                    "table_id": table_id, "doc_id": doc_id, "page_id": page_id, "page_number": page_number,
                    "caption": caption, "headers": headers, "rows": body, "cells": cells,
                    "row_labels": [_semantic_row_label(row) for row in body],
                    "column_labels": headers, "merged_cell_info": {"header_rows": header_rows},
                    "raw_representation": matrix,
                    "normalized_representation": "\n".join(" | ".join(row) for row in [headers] + body),
                    "bbox": [round(float(x), 2) for x in found_table.bbox],
                    "quality_label": quality, "quality_reasons": quality_reasons,
                }
                table["sha256"] = sha256_record(table)
                tables.append(table)
                region = {
                    "region_id": f"REG_{table_id}", "doc_id": doc_id, "page_id": page_id,
                    "page_number": page_number, "region_type": "table", "reading_order": 1000 + table_index,
                    "raw_text": str(matrix), "normalized_text": table["normalized_representation"],
                    "bbox": table["bbox"], "section_id": None,
                    "metadata": {"table_id": table_id, "quality_label": quality},
                }
                region["sha256"] = sha256_record(region)
                regions.append(region)
    return documents, pages, regions, tables, migrations


def corpus_summary(documents: list[dict], pages: list[dict], regions: list[dict], tables: list[dict]) -> dict:
    return {
        "documents": len(documents),
        "acceptance": dict(Counter(d["acceptance_status"] for d in documents)),
        "accepted_core_long": sum(d["acceptance_status"] == "ACCEPT" and d["core_or_temporal"] == "core_long" for d in documents),
        "accepted_temporal": sum(d["acceptance_status"] == "ACCEPT" and d["core_or_temporal"] == "temporal" for d in documents),
        "pages": len(pages), "regions": len(regions), "tables": len(tables),
        "table_quality": dict(Counter(t["quality_label"] for t in tables)),
    }
