import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
import json
import re
from pathlib import Path
import fitz

# Irrigation domain keywords for entity/metric extraction
METRIC_KEYWORDS = {
    "WaterLevel": ["mực nước", "mực nước hồ", "mực nước thượng lưu", "mực nước hạ lưu", "mndbt", "mnc", "mngc"],
    "ReservoirStorage": ["dung tích", "dung tích trữ", "dung tích hữu ích", "dung tích toàn bộ", "dung tích phòng lũ"],
    "StoragePercentage": ["tỷ lệ trữ", "phần trăm dung tích", "% dung tích"],
    "Inflow": ["lưu lượng đến", "dòng chảy đến", "lưu lượng về hồ", "q đến"],
    "Outflow": ["lưu lượng xả", "lưu lượng qua tràn", "lưu lượng phát điện", "tổng lưu lượng xả", "q xả"],
    "Rainfall": ["lượng mưa", "mưa ngày", "mưa đợt", "tổng lượng mưa"],
    "Salinity": ["độ mặn", "ranh mặn", "mặn 1g/l", "mặn 4g/l", "nồng độ muối"],
    "WaterQuality": ["wqi", "do", "cod", "bod", "tss", "amoni", "nh4+", "coliform", "chất lượng nước"],
    "IrrigatedArea": ["diện tích tưới", "diện tích lấy nước", "diện tích gieo cấy"],
    "WaterDemand": ["nhu cầu nước", "lượng nước yêu cầu"],
    "WaterSupply": ["khả năng cấp nước", "cấp nước tưới", "cấp nước sinh hoạt"]
}

UNIT_PATTERNS = [
    (r"\bm3/s\b", "m3/s"),
    (r"\bm3\b", "m3"),
    (r"\btriệu\s+m3\b", "trieu m3"),
    (r"\btỷ\s+m3\b", "ty m3"),
    (r"\bmm\b", "mm"),
    (r"\bha\b", "ha"),
    (r"\bmg/l\b", "mg/L"),
    (r"\bg/l\b", "g/L"),
    (r"\b‰\b", "‰"),
    (r"\b%\b", "%"),
    (r"\bm\b(?!\w)", "m")
]

def normalize_text(text):
    if not text:
        return ""
    # Normalize excessive spaces, non-breaking spaces
    text = text.replace('\xa0', ' ').replace('\u200b', '')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def detect_metrics(text):
    text_lower = text.lower()
    found = []
    for metric, kws in METRIC_KEYWORDS.items():
        if any(kw in text_lower for kw in kws):
            found.append(metric)
    return found

def detect_units(text):
    found = []
    for pat, norm in UNIT_PATTERNS:
        if re.search(pat, text, re.I):
            found.append(norm)
    return list(set(found))

def detect_periods(text):
    # Detect dates, weeks, months, seasons
    periods = []
    dates = re.findall(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{1,2}\s+tháng\s+\d{1,2}(?:\s+năm\s+\d{4})?\b', text, re.I)
    periods.extend(dates[:3])
    seasons = re.findall(r'\b(?:mùa lũ|mùa kiệt|mùa khô|vụ hè thu|vụ đông xuân|vụ mùa|tuần \d+|tháng \d+)\b', text, re.I)
    periods.extend(seasons[:3])
    return list(set(periods))

def parse_document(doc_record):
    doc_id = doc_record["doc_id"]
    file_path = Path(doc_record["local_path"])
    
    if not file_path.exists():
        return None
        
    pdf = fitz.open(file_path)
    page_count = len(pdf)
    
    parsed_doc = {
        "doc_id": doc_id,
        "title": doc_record["document_title"],
        "agency": doc_record["agency"],
        "doc_type": doc_record["document_type"],
        "basin": [b.strip() for b in doc_record["basin"].split(",") if b.strip()],
        "province": [p.strip() for p in doc_record["province"].split(",") if p.strip()],
        "reservoirs": [r.strip() for r in doc_record["reservoir"].split(",") if r.strip()],
        "publication_date": doc_record["download_timestamp"][:10],
        "reporting_period": doc_record.get("reporting_period", "CURRENT"),
        "version_status": doc_record.get("version_status", "CURRENT"),
        "page_count": page_count,
        "pages": [],
        "sections": []
    }
    
    regions = []
    tables = []
    
    current_section = {
        "section_id": f"SEC_{doc_id}_0",
        "section_title": "Mở đầu",
        "section_level": 1,
        "parent_section": None
    }
    parsed_doc["sections"].append(current_section)
    section_counter = 1
    
    for page_num in range(1, page_count + 1):
        page = pdf[page_num - 1]
        raw_page_text = page.get_text()
        norm_page_text = normalize_text(raw_page_text)
        page_id = f"PAGE_{doc_id}_{page_num}"
        
        # Save page schema
        page_obj = {
            "doc_id": doc_id,
            "page_id": page_id,
            "page_number": page_num,
            "raw_text": raw_page_text,
            "normalized_text": norm_page_text,
            "section_id": current_section["section_id"]
        }
        parsed_doc["pages"].append(page_obj)
        
        # 1. Extract PyMuPDF Tables
        extracted_tables = []
        try:
            tabs = page.find_tables()
            for t_idx, tab in enumerate(tabs.tables):
                t_df = tab.extract()
                if not t_df or len(t_df) < 2:
                    continue
                header = [str(c).strip() if c is not None else "" for c in t_df[0]]
                rows = []
                for r in t_df[1:]:
                    rows.append([str(c).strip() if c is not None else "" for c in r])
                    
                table_id = f"TAB_{doc_id}_P{page_num}_{t_idx+1}"
                
                # Check status
                status = "GOOD"
                if any(len(r) != len(header) for r in rows):
                    status = "PARTIAL"
                if len(header) <= 1 or len(rows) == 0:
                    status = "BROKEN"
                    
                # Format markdown table representation
                md_lines = []
                md_lines.append("| " + " | ".join(header) + " |")
                md_lines.append("| " + " | ".join(["---"] * len(header)) + " |")
                for r in rows:
                    md_lines.append("| " + " | ".join(r) + " |")
                norm_repr = "\n".join(md_lines)
                
                tab_obj = {
                    "table_id": table_id,
                    "doc_id": doc_id,
                    "page_number": page_num,
                    "caption": f"Bảng số liệu trang {page_num}",
                    "header": header,
                    "rows": rows,
                    "columns": header,
                    "raw_representation": str(t_df),
                    "normalized_representation": norm_repr,
                    "extraction_status": status,
                    "bbox": list(tab.bbox)
                }
                tables.append(tab_obj)
                extracted_tables.append(tab_obj)
        except Exception:
            pass
            
        # 2. Extract Blocks / Regions
        blocks = page.get_text("blocks")
        # blocks: (x0, y0, x1, y1, text, block_no, block_type)
        reading_order = 0
        for blk in blocks:
            b_text = blk[4].strip()
            if not b_text:
                continue
            norm_b_text = normalize_text(b_text)
            if len(norm_b_text) < 3:
                continue
                
            bbox = [round(blk[0], 1), round(blk[1], 1), round(blk[2], 1), round(blk[3], 1)]
            
            # Determine region type
            region_type = "paragraph"
            
            # Heading heuristics
            first_line = norm_b_text.split("\n")[0].strip()
            if re.match(r'^(?:[I|V|X]+\.|\d+\.|\d+\.\d+|PHẦN|CHƯƠNG|MỤC|[A-Z\s]{4,}:)', first_line) and len(first_line) < 120 and len(norm_b_text) < 250:
                region_type = "heading"
                sec_id = f"SEC_{doc_id}_{section_counter}"
                section_counter += 1
                current_section = {
                    "section_id": sec_id,
                    "section_title": first_line,
                    "section_level": 2 if '.' in first_line[:3] else 1,
                    "parent_section": "SEC_ROOT"
                }
                parsed_doc["sections"].append(current_section)
            elif first_line.lower().startswith(("bảng", "hình", "sơ đồ", "biểu đồ")):
                region_type = "caption"
            elif norm_b_text.startswith(("-", "+", "*", "•")) or "\n-" in norm_b_text:
                region_type = "list"
            elif any(t["bbox"][1] <= bbox[1] <= t["bbox"][3] for t in extracted_tables):
                region_type = "table"
                
            reg_id = f"REG_{doc_id}_P{page_num}_{reading_order:02d}"
            
            reg_obj = {
                "region_id": reg_id,
                "doc_id": doc_id,
                "page_id": page_id,
                "page_number": page_num,
                "section_id": current_section["section_id"],
                "region_type": region_type,
                "reading_order": reading_order,
                "raw_text": b_text,
                "normalized_text": norm_b_text,
                "bbox": bbox,
                "entities": parsed_doc["reservoirs"] + parsed_doc["basin"],
                "metrics": detect_metrics(norm_b_text),
                "time_periods": detect_periods(norm_b_text),
                "units": detect_units(norm_b_text)
            }
            regions.append(reg_obj)
            reading_order += 1

    return parsed_doc, regions, tables

def main():
    manifest_file = Path("data/manifests/download_manifest.jsonl")
    parsed_dir = Path("data/parsed")
    regions_dir = Path("data/regions")
    tables_dir = Path("data/tables")
    
    accepted_docs = []
    with open(manifest_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                if rec.get("acceptance_status") == "ACCEPTED":
                    accepted_docs.append(rec)
                    
    print(f"Beginning structured parsing of {len(accepted_docs)} accepted documents...")
    
    total_parsed_pages = 0
    total_regions = 0
    total_tables = 0
    usable_tables = 0
    
    for doc_rec in accepted_docs:
        doc_id = doc_rec["doc_id"]
        res = parse_document(doc_rec)
        if not res:
            continue
        p_doc, regs, tabs = res
        
        # Save parsed document JSON
        with open(parsed_dir / f"{doc_id}.json", "w", encoding="utf-8") as f:
            json.dump(p_doc, f, ensure_ascii=False, indent=2)
            
        # Save regions JSONL
        with open(regions_dir / f"{doc_id}_regions.jsonl", "w", encoding="utf-8") as f:
            for r in regs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                
        # Save tables JSONL
        with open(tables_dir / f"{doc_id}_tables.jsonl", "w", encoding="utf-8") as f:
            for t in tabs:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
                
        total_parsed_pages += len(p_doc["pages"])
        total_regions += len(regs)
        total_tables += len(tabs)
        usable_tables += sum(1 for t in tabs if t["extraction_status"] in ["GOOD", "PARTIAL"])
        
        print(f"[{doc_id}] Pgs: {len(p_doc['pages']):2d} | Secs: {len(p_doc['sections']):2d} | Regs: {len(regs):3d} | Tabs: {len(tabs):2d}")

    print("\n--- Parsing Pipeline Complete ---")
    print(f"Parsed Documents: {len(accepted_docs)}")
    print(f"Total Pages:      {total_parsed_pages}")
    print(f"Total Regions:    {total_regions}")
    print(f"Total Tables:     {total_tables} (Usable: {usable_tables})")

if __name__ == "__main__":
    main()
