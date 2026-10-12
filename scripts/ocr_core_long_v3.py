"""OCR the ten frozen core-long scan PDFs with auditable page confidence.

Numeric evidence is deliberately disabled for OCR-derived pages.  The OCR is
used to recover headings and prose; any numeric QA must come from a native text
layer or a later human verification pass.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".vendor"))
sys.path.insert(0, str(ROOT))

import fitz
from PIL import Image, ImageDraw
from rapidocr import RapidOCR
from rapidocr.utils.typings import LangRec, ModelType, OCRVersion

from src.parsing.canonical_parser import load_sources


OUT = ROOT / "data" / "ocr" / "v3"
SAMPLES = ROOT / "reports" / "v3_ocr_samples"
AUDIT = ROOT / "reports" / "V3_OCR_AUDIT.json"


def page_quality(text: str, scores: list[float]) -> str:
    mean = statistics.fmean(scores) if scores else 0.0
    if len(text) >= 350 and mean >= 0.90:
        return "GOOD"
    if len(text) >= 100 and mean >= 0.82:
        return "PARTIAL"
    return "BROKEN"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SAMPLES.mkdir(parents=True, exist_ok=True)
    sources = [s for s in load_sources() if s.get("core_or_temporal") == "core_long"]
    scan_sources = []
    for source in sources:
        path = ROOT / source["local_path"]
        if not path.exists():
            continue
        doc = fitz.open(path)
        chars = [len(page.get_text("text").strip()) for page in doc]
        if sum(c >= 80 for c in chars) / max(len(chars), 1) < 0.70 or sum(chars) < max(300, len(chars) * 80):
            scan_sources.append(source)

    engine = RapidOCR(params={
        "Rec.lang_type": LangRec.LATIN,
        "Rec.ocr_version": OCRVersion.PPOCRV5,
        "Rec.model_type": ModelType.MOBILE,
    })
    audits = []
    for doc_index, source in enumerate(scan_sources, 1):
        path = ROOT / source["local_path"]
        pdf = fitz.open(path)
        cache_path = OUT / f"{source['source_id']}.jsonl"
        cached = {}
        if cache_path.exists():
            for line in cache_path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                cached[row["page_number"]] = row
        rows = []
        sample_pages = sorted({1, max(1, len(pdf) // 3), max(1, 2 * len(pdf) // 3), len(pdf)})
        for page_number, page in enumerate(pdf, 1):
            if page_number in cached:
                row = cached[page_number]
            else:
                # 1.2x is a measured compromise for these clean 300-dpi scans:
                # line recognition remains readable while full-corpus OCR stays tractable.
                pix = page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False)
                result = engine(pix.tobytes("png"))
                text = "\n".join(result.txts or ())
                scores = [float(v) for v in (result.scores or ())]
                row = {
                    "source_id": source["source_id"],
                    "local_path": source["local_path"],
                    "page_number": page_number,
                    "text": text,
                    "mean_line_confidence": round(statistics.fmean(scores), 4) if scores else 0.0,
                    "min_line_confidence": round(min(scores), 4) if scores else 0.0,
                    "line_count": len(scores),
                    "quality": page_quality(text, scores),
                    "numeric_safe": False,
                    "ocr_engine": "RapidOCR PP-OCRv5 latin mobile",
                }
            rows.append(row)
            # Persist every page so an interrupted long OCR run is resumable.
            cache_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
            if page_number in sample_pages:
                sample = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                sample.save(SAMPLES / f"{source['source_id']}_p{page_number:03d}.png")
            if page_number % 10 == 0 or page_number == len(pdf):
                print(f"OCR {doc_index}/{len(scan_sources)} {source['source_id']} page {page_number}/{len(pdf)}", flush=True)
        counts = {q: sum(r["quality"] == q for r in rows) for q in ("GOOD", "PARTIAL", "BROKEN")}
        sample_paths = [SAMPLES / f"{source['source_id']}_p{p:03d}.png" for p in sample_pages]
        opened = [Image.open(p).convert("RGB") for p in sample_paths if p.exists()]
        if opened:
            thumb_w = 500
            thumbs = []
            for img in opened:
                thumb = img.copy()
                thumb.thumbnail((thumb_w, 700))
                thumbs.append(thumb)
            sheet = Image.new("RGB", (thumb_w * len(thumbs), max(i.height for i in thumbs) + 60), "white")
            draw = ImageDraw.Draw(sheet)
            for pos, (page_no, thumb) in enumerate(zip(sample_pages, thumbs)):
                sheet.paste(thumb, (pos * thumb_w, 50))
                draw.text((pos * thumb_w + 10, 15), f"page {page_no}", fill="black")
            sheet.save(SAMPLES / f"{source['source_id']}_contact_sheet.jpg", quality=88)
        usable_ratio = (counts["GOOD"] + counts["PARTIAL"]) / max(len(rows), 1)
        audits.append({
            "source_id": source["source_id"],
            "title": source["title"],
            "local_path": source["local_path"],
            "page_count": len(rows),
            "quality_counts": counts,
            "usable_page_ratio": round(usable_ratio, 4),
            "document_gate": "ACCEPT_TEXT_ONLY_NONNUMERIC" if usable_ratio >= 0.70 else "REJECT",
            "visual_audit_pages": sample_pages,
            "visual_audit_status": "SAMPLED_PENDING_HUMAN_VALIDATION",
            "numeric_qa_allowed": False,
        })
    AUDIT.write_text(json.dumps({
        "ocr_documents": audits,
        "human_validated": False,
        "policy": "OCR text may support nonnumeric prose QA only; numeric and threshold QA are prohibited.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"documents": len(audits), "accepted": sum(a["document_gate"].startswith("ACCEPT") for a in audits)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
