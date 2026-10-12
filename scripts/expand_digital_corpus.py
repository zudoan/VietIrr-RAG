import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests, fitz, urllib.parse, urllib3, json, hashlib
from pathlib import Path
from datetime import datetime

urllib3.disable_warnings()
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
base_api = 'https://cucthuyloi.gov.vn/DesktopModules/cmsview/api/AdminForm/list'

# We query categories:
# 125 (Bắc Bộ)
# 126 (Trung Bộ)
# 127 (Tây Nguyên & Đông Nam Bộ)
# 128 (ĐBSCL)
# 129 (CLN Bắc Bộ)
# 130 (CLN ĐNB & ĐBSCL)

target_categories = [
    (125, "Bắc Bộ", "Sông Hồng - Thái Bình", "Bắc Bộ"),
    (126, "Trung Bộ", "Sông Mã, Sông Cả, Vu Gia - Thu Bồn, Ba", "Trung Bộ"),
    (127, "Tây Nguyên - ĐNB", "Sê San, Srêpôk, Đồng Nai", "Tây Nguyên"),
    (128, "ĐBSCL", "Đồng bằng Sông Cửu Long", "ĐBSCL"),
    (129, "CLN Bắc Bộ", "Sông Cầu, Sông Nhuệ - Đáy, Bắc Hưng Hải", "Bắc Ninh, Thái Nguyên, Vĩnh Phúc"),
    (130, "CLN Nam Bộ", "ĐBSCL, Sông Đồng Nai", "Cần Thơ, Hậu Giang, Vĩnh Long")
]

print("Scanning Cucthuyloi categories for additional Quality A documents...")
candidates_to_download = []

for cat_id, cat_label, basin_desc, prov_desc in target_categories:
    params = {'PortalId': 0, 'AdminFormCatId': cat_id, 'Keyword': '', 'pageindex': 1, 'pagesize': 15}
    try:
        r = requests.get(base_api, params=params, headers=headers, verify=False, timeout=8)
        if r.status_code == 200:
            items = r.json().get('ListData', [])
            for item in items:
                fn = item.get('AdminFormFilename', '')
                title = item.get('AdminFormName', '')
                if fn and fn.endswith('.pdf'):
                    candidates_to_download.append({
                        "cat_id": cat_id,
                        "cat_label": cat_label,
                        "basin": basin_desc,
                        "province": prov_desc,
                        "title": title,
                        "filename": fn
                    })
    except Exception as e:
        print(f"Error querying cat {cat_id}: {e}")

print(f"Found {len(candidates_to_download)} candidate files. Downloading and testing digital text...")
added = 0
manifest_file = Path("data/manifests/download_manifest.jsonl")

# Load existing doc_ids or filenames
existing_fns = set()
if manifest_file.exists():
    with open(manifest_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                existing_fns.add(json.loads(line).get("original_filename"))

for cand in candidates_to_download:
    fn_path = cand["filename"]
    orig_fn = Path(fn_path).name
    if orig_fn in existing_fns:
        continue
        
    url = 'https://cucthuyloi.gov.vn' + urllib.parse.quote(fn_path)
    try:
        res = requests.get(url, headers=headers, verify=False, timeout=15)
        if res.status_code != 200 or len(res.content) < 1000:
            continue
            
        doc = fitz.open(stream=res.content, filetype='pdf')
        pages = len(doc)
        total_chars = sum(len(p.get_text().strip()) for p in doc)
        ext_pages = sum(1 for p in doc if len(p.get_text().strip()) > 80)
        ext_ratio = ext_pages / max(1, pages)
        
        # Only accept Quality A: extractable ratio > 0.8 and chars > 2000
        if ext_ratio >= 0.8 and total_chars > 2000:
            track = "core_long" if pages >= 10 else "temporal"
            target_path = Path(f"data/raw/{track}/{orig_fn}")
            with open(target_path, "wb") as f:
                f.write(res.content)
                
            sha256 = hashlib.sha256(res.content).hexdigest()
            doc_id = f"IRR_CTL_2025_{sha256[:8]}"
            
            # Count table candidates
            tabs_count = 0
            for p in doc:
                try:
                    tabs = p.find_tables()
                    if tabs and tabs.tables:
                        tabs_count += len(tabs.tables)
                except:
                    pass
            
            rec = {
                "doc_id": doc_id,
                "source_id": f"SRC_CTL_{cand['cat_id']}_{doc_id}",
                "original_filename": orig_fn,
                "local_path": str(target_path).replace("\\", "/"),
                "source_url": url,
                "landing_page_url": "https://cucthuyloi.gov.vn/du-bao-nguon-nuoc",
                "agency": "Cục Quản lý và Xây dựng công trình thủy lợi (Cục Thủy lợi)",
                "document_title": cand["title"],
                "document_type": "Báo cáo DBNN & Giám sát CLN",
                "basin": cand["basin"],
                "province": cand["province"],
                "reservoir": "Hệ thống thủy lợi & hồ chứa",
                "track": track,
                "download_timestamp": datetime.now().isoformat(),
                "sha256": sha256,
                "bytes": len(res.content),
                "mime_type": "application/pdf",
                "http_status": 200,
                "actual_pages": pages,
                "page_count": pages,
                "character_count": total_chars,
                "extractable_pages": ext_pages,
                "extractable_text_ratio": round(ext_ratio, 3),
                "scanned_page_ratio": round(1.0 - ext_ratio, 3),
                "table_candidate_count": tabs_count,
                "image_heavy_ratio": 0.0,
                "quality_label": "A",
                "parser_status": "CLEAN_DIGITAL",
                "acceptance_status": "ACCEPTED",
                "version_status": "CURRENT"
            }
            
            with open(manifest_file, "a", encoding="utf-8") as mf:
                mf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                
            existing_fns.add(orig_fn)
            added += 1
            print(f"Added [{doc_id}] ({track}) {orig_fn:30s} | Pgs: {pages:2d} | Chars: {total_chars:6d} | Tabs: {tabs_count}")
            
            if added >= 25:
                break
    except Exception as e:
        pass

print(f"\nSuccessfully added {added} new Quality A documents to VietIrrDocBench!")
