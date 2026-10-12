"""Acquire and quality-gate official V3 corpus expansion PDFs.

This script is intentionally independent from the legacy acquisition manifest.  It
only downloads a fixed, reviewable allow-list of official government documents
and emits an audit file; acceptance into the canonical corpus happens later.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "v3_official"
AUDIT = ROOT / "reports" / "v3_source_acquisition_audit.json"

SOURCES = [
    {
        "source_id": "V3_PCTT_DAM_HUONG_2023",
        "agency": "Cục Quản lý đê điều và Phòng, chống thiên tai",
        "group": "PCTT",
        "filename": "dam_operations_huong_2023.pdf",
        "url": "https://phongchongthientai.mard.gov.vn/FileUpload/2024-07/NtFBgtdVuEG57-n5240627%20VIET_ST_Report_Dam%20Operations%20in%20the%20November%202023%20Flood%20of%20the%20Huong%20River%20%281%29.pdf",
    },
    {
        "source_id": "V3_PCTT_SREX_VN",
        "agency": "Cục Quản lý đê điều và Phòng, chống thiên tai",
        "group": "PCTT",
        "filename": "srex_vietnam_report.pdf",
        "url": "https://phongchongthientai.mard.gov.vn/PublishingImages/FileDinhKem/ccsfc170615020542bao-cao-srex-viet-nam_full.pdf",
    },
    {
        "source_id": "V3_PCTT_MONITORING_FRAMEWORK",
        "agency": "Cục Quản lý đê điều và Phòng, chống thiên tai",
        "group": "PCTT",
        "filename": "khung_theo_doi_chien_luoc.pdf",
        "url": "https://phongchongthientai.mard.gov.vn/PublishingImages/FileDinhKem/phe-duyet-khung-theo-doi-danh-gia-thuc-hien-chien-luoc.pdf",
    },
    {
        "source_id": "V3_PCTT_DYKE_HISTORY",
        "agency": "Cục Quản lý đê điều và Phòng, chống thiên tai",
        "group": "PCTT",
        "filename": "lich_su_de_dieu_viet_nam.pdf",
        "url": "https://phongchongthientai.mard.gov.vn/FileUpload/2022-04/9xJcY7D4T0aXzGIILich%20su%20de%20dieu%20Viet%20Nam-Final-1.pdf",
    },
    {
        "source_id": "V3_PCTT_REGULATION",
        "agency": "Cục Quản lý đê điều và Phòng, chống thiên tai",
        "group": "PCTT",
        "filename": "thong_tu_yeu_cau_pctt.pdf",
        "url": "https://phongchongthientai.mard.gov.vn/FileUpload/2021-11/8lzbN8kVEk6Y6vu6Thong%20tu%20yeu%20cau%20PCTT.pdf",
    },
    {
        "source_id": "V3_PCTT_BULLETIN_2024_09",
        "agency": "Cục Quản lý đê điều và Phòng, chống thiên tai",
        "group": "PCTT",
        "filename": "ban_tin_thien_tai_2024_09.pdf",
        "url": "https://phongchongthientai.mard.gov.vn/FileUpload/2024-11/CrJgZR5oXUOoIMrvLVP%2003-T10.2024%20BAN%20TIN%20THIEN%20TAI%20SO%209-TH%20%281%29.pdf",
    },
    {
        "source_id": "V3_PCTT_CONFERENCE_2022",
        "agency": "Cục Quản lý đê điều và Phòng, chống thiên tai",
        "group": "PCTT",
        "filename": "hoi_nghi_toan_quoc_2022.pdf",
        "url": "https://phongchongthientai.mard.gov.vn/FileUpload/2022-04/PKgWNcN1bER7MDn8Tai%20lieu%20hoi%20nghi%20toan%20quoc%202022-dang%20web.pdf",
    },
    {
        "source_id": "V3_PCTT_HEAVY_RAIN_2025",
        "agency": "Cục Quản lý đê điều và Phòng, chống thiên tai",
        "group": "PCTT",
        "filename": "chu_dong_ung_pho_mua_lon_2025.pdf",
        "url": "https://phongchongthientai.mard.gov.vn/FileUpload/2025-06/E33u3JjQ3ke9UtpCCV%20%20ve%20chu%20dong%20ung%20pho%20voi%20mua%20lon%20-%20lu%20quet%20-%20sat%20lo%20dat%20%281%29.pdf",
    },
    {
        "source_id": "V3_PCTT_WHITE_BOOK_2023",
        "agency": "Cục Quản lý đê điều và Phòng, chống thiên tai",
        "group": "PCTT",
        "filename": "sach_trang_2023.pdf",
        "url": "https://phongchongthientai.mard.gov.vn/FileUpload/2024-05/Hpk9nDyULkuEzfd500.%20S%C3%A1ch%20tr%E1%BA%AFng%20n%C4%83m%202023%20%28full%29.pdf",
    },
    {
        "source_id": "V3_PCTT_CBRDM_MANUAL",
        "agency": "Cục Quản lý đê điều và Phòng, chống thiên tai",
        "group": "PCTT",
        "filename": "cbrdm_manual.pdf",
        "url": "https://phongchongthientai.mard.gov.vn/PublishingImages/TruyenThong/CIS/CBRDM%20manual.pdf",
    },
    {
        "source_id": "V3_PCTT_BULLETIN_2023_08",
        "agency": "Cục Quản lý đê điều và Phòng, chống thiên tai",
        "group": "PCTT",
        "filename": "ban_tin_thien_tai_2023_08.pdf",
        "url": "https://phongchongthientai.mard.gov.vn/FileUpload/2023-09/6tCxliYGQEq0W5UqBAN%20TIN%20THIEN%20TAI%20T8.%202023.pdf",
    },
    {
        "source_id": "V3_PCTT_BULLETIN_2023_07",
        "agency": "Cục Quản lý đê điều và Phòng, chống thiên tai",
        "group": "PCTT",
        "filename": "ban_tin_thien_tai_2023_07.pdf",
        "url": "https://phongchongthientai.mard.gov.vn/FileUpload/2023-09/8MZH1GwaoEWNb1mzBAN%20TIN%20THIEN%20TAI%20T7.%202023.pdf",
    },
    {
        "source_id": "V3_NCHMF_SEASONAL_2019_09",
        "agency": "Trung tâm Dự báo khí tượng thủy văn quốc gia",
        "group": "NCHMF",
        "filename": "khi_hau_6_thang_2019_09.pdf",
        "url": "https://nchmf.gov.vn/upload/file/2019/9/13/goc_dbqg_kh6t_20190915_1700.pdf",
    },
    {
        "source_id": "V3_NCHMF_SEASONAL_2019_04",
        "agency": "Trung tâm Dự báo khí tượng thủy văn quốc gia",
        "group": "NCHMF",
        "filename": "khi_hau_6_thang_2019_04.pdf",
        "url": "https://nchmf.gov.vn/Upload/File/2019/4/12/goc_DBQG_KH6T_20190412_1700.pdf",
    },
    {
        "source_id": "V3_NCHMF_SEASONAL_2019_07",
        "agency": "Trung tâm Dự báo khí tượng thủy văn quốc gia",
        "group": "NCHMF",
        "filename": "khi_hau_6_thang_2019_07.pdf",
        "url": "https://www.nchmf.gov.vn/Upload/File/2019/7/18/goc_DBQG_KH6T_20190715_1700.pdf",
    },
    {
        "source_id": "V3_NCHMF_MONTHLY_2019_08",
        "agency": "Trung tâm Dự báo khí tượng thủy văn quốc gia",
        "group": "NCHMF",
        "filename": "khi_hau_1_thang_2019_08.pdf",
        "url": "https://www.nchmf.gov.vn/Upload/File/2019/8/1/goc_DBQG_KH1T_20190801_1100.pdf",
    },
    {
        "source_id": "V3_MEKONG_WATER_RESOURCES_2021",
        "agency": "Ủy ban sông Mê Công Việt Nam",
        "group": "VNMC",
        "filename": "tong_ket_tai_nguyen_nuoc_mekong_2021.pdf",
        "url": "https://phongchongthientai.mard.gov.vn/FileUpload/2022-01/wR7Nu27NtkGxFDeHB%C3%A1o%20c%C3%A1o%20t%E1%BB%95ng%20k%E1%BA%BFt%20m%C3%B9a%20l%C5%A9%20n%C4%83m%202021_UBMC_Signed%20%281%29_Signed.pdf",
    },
    {
        "source_id": "V3_PCTT_WATER_INFRASTRUCTURE_ASSESSMENT",
        "agency": "Cục Quản lý đê điều và Phòng, chống thiên tai",
        "group": "PCTT",
        "filename": "danh_gia_ha_tang_nuoc_sach.pdf",
        "url": "https://phongchongthientai.mard.gov.vn/FileUpload/2025-06/vfmO0ZAzo0yHZU1Yvmsa_bao_cao_tv_tt.pdf",
    },
    {
        "source_id": "V3_MARD_COMMUNE_IRRIGATION_HANDBOOK",
        "agency": "Bộ Nông nghiệp và Môi trường",
        "group": "MARD_LEGAL",
        "filename": "so_tay_cap_xa_thuy_loi_2026.pdf",
        "url": "https://phongchongthientai.mard.gov.vn/FileUpload/2026-05/XEzKidJ5ykKQcdHTsotay-cap-xa-vu-pc-.pdf",
    },
]


def pdf_audit(path: Path) -> dict:
    try:
        doc = fitz.open(path)
        chars = [len(re.sub(r"\s+", "", page.get_text("text"))) for page in doc]
        pages = len(chars)
        text_pages = sum(n >= 80 for n in chars)
        total_chars = sum(chars)
        return {
            "valid_pdf": True,
            "pages": pages,
            "text_pages": text_pages,
            "text_page_ratio": round(text_pages / pages, 4) if pages else 0.0,
            "total_nonspace_chars": total_chars,
            "avg_nonspace_chars_per_page": round(total_chars / pages, 1) if pages else 0.0,
            "quality_gate": "PASS" if pages >= 2 and text_pages / max(pages, 1) >= 0.70 else "REVIEW",
        }
    except Exception as exc:  # audit must record, rather than hide, malformed downloads
        return {"valid_pdf": False, "quality_gate": "REJECT", "error": str(exc)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for source in SOURCES:
        row = dict(source)
        path = OUT / source["filename"]
        try:
            if not path.exists() or path.stat().st_size < 1024:
                request = urllib.request.Request(source["url"], headers={"User-Agent": "VietIrrDocBench/3.0 research corpus"})
                with urllib.request.urlopen(request, timeout=90) as response:
                    path.write_bytes(response.read())
            payload = path.read_bytes()
            row.update({"local_path": path.relative_to(ROOT).as_posix(), "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
            row.update(pdf_audit(path))
        except Exception as exc:
            row.update({"valid_pdf": False, "quality_gate": "REJECT", "error": str(exc)})
        rows.append(row)
        print(json.dumps({k: row.get(k) for k in ("source_id", "quality_gate", "pages", "error")}, ensure_ascii=False))
    AUDIT.write_text(json.dumps({"sources": rows}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
