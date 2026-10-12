import sys
sys.stdout.reconfigure(encoding='utf-8')
import json
from pathlib import Path
import fitz

def audit_document(file_path):
    p = Path(file_path)
    if not p.exists():
        return {
            "page_count": 0,
            "character_count": 0,
            "extractable_pages": 0,
            "extractable_text_ratio": 0.0,
            "scanned_page_ratio": 1.0,
            "table_candidate_count": 0,
            "image_heavy_ratio": 0.0,
            "quality_label": "D",
            "parser_status": "FILE_NOT_FOUND"
        }
    
    try:
        doc = fitz.open(p)
    except Exception as e:
        return {
            "page_count": 0,
            "character_count": 0,
            "extractable_pages": 0,
            "extractable_text_ratio": 0.0,
            "scanned_page_ratio": 1.0,
            "table_candidate_count": 0,
            "image_heavy_ratio": 0.0,
            "quality_label": "D",
            "parser_status": f"CORRUPTED_PDF: {str(e)[:50]}"
        }
        
    page_count = len(doc)
    if page_count == 0:
        return {
            "page_count": 0,
            "character_count": 0,
            "extractable_pages": 0,
            "extractable_text_ratio": 0.0,
            "scanned_page_ratio": 1.0,
            "table_candidate_count": 0,
            "image_heavy_ratio": 0.0,
            "quality_label": "D",
            "parser_status": "EMPTY_PDF"
        }
        
    extractable_pages = 0
    total_chars = 0
    table_candidates = 0
    image_heavy_pages = 0
    
    for page_idx in range(page_count):
        page = doc[page_idx]
        text = page.get_text().strip()
        char_cnt = len(text)
        total_chars += char_cnt
        
        # Check text extractability: a real digital text page has > 80 chars
        if char_cnt >= 80:
            extractable_pages += 1
            
        # Detect table candidates
        try:
            tabs = page.find_tables()
            if tabs and len(tabs.tables) > 0:
                table_candidates += len(tabs.tables)
            else:
                lines = text.split("\n")
                num_count = sum(1 for line in lines if any(ch.isdigit() for ch in line))
                if len(lines) > 8 and (num_count / len(lines)) > 0.30:
                    table_candidates += 1
        except Exception:
            pass
            
        # Detect image heavy pages
        images = page.get_images()
        if len(images) > 0 and char_cnt < 100:
            image_heavy_pages += 1

    extractable_ratio = extractable_pages / page_count
    scanned_ratio = 1.0 - extractable_ratio
    image_heavy_ratio = image_heavy_pages / page_count
    
    if extractable_ratio >= 0.80 and total_chars > 2000:
        quality_label = "A" # Clean digital PDF
        parser_status = "CLEAN_DIGITAL"
    elif extractable_ratio >= 0.40 and total_chars > 800:
        quality_label = "B" # Mostly usable
        parser_status = "MOSTLY_USABLE"
    elif scanned_ratio >= 0.50 or total_chars < 800:
        quality_label = "C" # Scan / OCR required
        parser_status = "SCANNED_REQUIRES_OCR"
    else:
        quality_label = "D"
        parser_status = "POOR_QUALITY"
        
    return {
        "page_count": page_count,
        "character_count": total_chars,
        "extractable_pages": extractable_pages,
        "extractable_text_ratio": round(extractable_ratio, 3),
        "scanned_page_ratio": round(scanned_ratio, 3),
        "table_candidate_count": table_candidates,
        "image_heavy_ratio": round(image_heavy_ratio, 3),
        "quality_label": quality_label,
        "parser_status": parser_status
    }

def main():
    manifest_in = Path("data/manifests/download_manifest.jsonl")
    
    if not manifest_in.exists():
        print(f"Error: {manifest_in} not found.")
        return
        
    print(f"Auditing downloaded PDFs from {manifest_in} ...\n")
    audited_records = []
    
    with open(manifest_in, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            audit_res = audit_document(rec["local_path"])
            rec.update(audit_res)
            
            # Acceptance decision:
            # Quality A is fully accepted for benchmark core / gold QA
            # Quality B is accepted with caution
            # Quality C/D are flagged or rejected
            if rec["quality_label"] == "A":
                rec["acceptance_status"] = "ACCEPTED"
            elif rec["quality_label"] == "B":
                rec["acceptance_status"] = "ACCEPTED_PARTIAL"
            else:
                rec["acceptance_status"] = "REJECTED_SCAN"
                
            audited_records.append(rec)
            print(f"[{rec['doc_id']}] {rec['original_filename'][:28]:28s} | Pgs: {rec['page_count']:2d} | Chars: {rec['character_count']:6d} | Q: {rec['quality_label']} ({rec['acceptance_status']})")

    with open(manifest_in, "w", encoding="utf-8") as f:
        for r in audited_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\nAudit complete. Updated manifest with {len(audited_records)} records.")

if __name__ == "__main__":
    main()
