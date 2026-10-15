"""Build the isolated V4 corpus metadata and coverage artifacts.

This script does not acquire files.  It inventories already-screened local
PDFs, copies no legacy PDFs, and references the 89 accepted V3.2 documents by
immutable source path and checksum.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RAW = ROOT / "data/v4_corpus/raw"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


NEW_DOCS = [
    {
        "candidate_id": "SRC-V41-001", "filename": "V4_BNH_QTVH_MAIN_2025.pdf",
        "doc_id": "V4_CTTL_2025_77c60f84", "publisher": "Bộ Nông nghiệp và Môi trường / Cục Quản lý và Xây dựng công trình thủy lợi",
        "title": "Quyết định 1318/QĐ-BNNMT và Quy trình vận hành hệ thống công trình thủy lợi Bắc Nam Hà",
        "publication_date": "2025-05-07", "validity": "ISSUED_CURRENT_AS_OBSERVED; replaces 5470/QĐ-BNN-TCTL (2016)",
        "geography": "Hà Nam; Nam Định", "facility": "Hệ thống công trình thủy lợi Bắc Nam Hà",
        "domain": "D01;D02;D04", "subdomain": "facility inventory; irrigation/drainage operation; allocation",
        "gap": "G01,G02,G04", "url": "https://www.cucthuyloi.gov.vn/Portals/0/DocumentFiles/2182_1_QTVH%20HTTL%20B%E1%BA%AFc%20Nam%20H%C3%A0.pdf",
        "status": "ACCEPT", "reason": "Official-domain PDF; signed decision number/date are present; extractable native text; unique checksum.",
        "redistribution": "OFFICIAL_PUBLIC_DOWNLOAD; retain source URL and do not assert open license",
    },
    {
        "candidate_id": "SRC-V41-002", "filename": "V4_BNH_WATER_PLAN_2021.pdf",
        "doc_id": "V4_IWRP_2021_3031564c", "publisher": "Viện Quy hoạch Thủy lợi",
        "title": "Dự báo nguồn nước và kế hoạch sử dụng nước vụ Đông Xuân 2020-2021 lưu vực sông Châu",
        "publication_date": "2021", "validity": "HISTORICAL_SEASONAL_REPORT",
        "geography": "Hà Nam; Nam Định", "facility": "Hệ thống Bắc Nam Hà / lưu vực sông Châu",
        "domain": "D03;D04", "subdomain": "water availability; irrigation demand; drought scenario",
        "gap": "G04,G05", "url": "https://iwrp.gov.vn/upload/medias/SChauDX_2021.pdf",
        "status": "ACCEPT", "reason": "Official institute PDF; native text and tables; entity/season/units explicitly stated; unique checksum.",
        "redistribution": "OFFICIAL_PUBLIC_DOWNLOAD; retain source URL and do not assert open license",
    },
    {
        "candidate_id": "SRC-V41-003", "filename": "V4_CLCB_QTVH_DRAFT_2024.pdf",
        "doc_id": "V4_CTTL_2024_dda51c21", "publisher": "Cục Thủy lợi",
        "title": "Dự thảo Quy trình vận hành hệ thống công trình thủy lợi Cái Lớn–Cái Bé",
        "publication_date": "2024", "validity": "DRAFT_NOT_APPLICABLE_AS_LAW",
        "geography": "Kiên Giang; Hậu Giang; Bạc Liêu; Sóc Trăng; Cà Mau", "facility": "Hệ thống Cái Lớn–Cái Bé",
        "domain": "D01;D02;D04;D05", "subdomain": "facility inventory; draft operation; salinity control",
        "gap": "G01,G02,G04,G07", "url": "https://www.cucthuyloi.gov.vn/Portals/0/DocumentFiles/2144_1_QTVH%20HTCTTL%20C%C3%A1i%20L%E1%BB%9Bn%20-%20C%C3%A1i%20Be%20%28final%29.pdf",
        "status": "ACCEPT", "reason": "Official-domain, extractable PDF and unique checksum; accepted as a draft reference only, never as an effective legal rule.",
        "redistribution": "OFFICIAL_PUBLIC_DOWNLOAD; draft; retain source URL; no open-license claim",
    },
    {
        "candidate_id": "SRC-V41-004", "filename": "V4_CT02_ATCT_2025.pdf",
        "doc_id": "V4_BNNMT_2025_594e7382", "publisher": "Bộ Nông nghiệp và Môi trường",
        "title": "Chỉ thị 02/CT-BNNMT về tăng cường bảo đảm an toàn công trình đê điều, thủy lợi mùa mưa lũ 2025",
        "publication_date": "2025-05-08", "validity": "ISSUED_2025_SEASONAL_DIRECTIVE",
        "geography": "Việt Nam", "facility": "Đê điều và công trình thủy lợi",
        "domain": "D06;D02", "subdomain": "dam/facility safety; inspection and preparedness duties",
        "gap": "G06", "url": "https://phongchongthientai.mard.gov.vn/FileUpload/2025-05/znNKG-sD20SBoGzBChi%20thi%20so%2002%20CT-BNN%20ngay%208.5.2025%20ve%20Tang%20cuong%20dam%20bao%20ATCT%20De%20dieu%2C%20TL%20mua%20mua%20lu%202025.pdf",
        "status": "ACCEPT", "reason": "Official ministry PDF with signature block and source-traceable publication; native text; unique checksum.",
        "redistribution": "OFFICIAL_PUBLIC_DOWNLOAD; retain source URL and do not assert open license",
    },
]

OTHER_CANDIDATES = [
    ("SRC-V41-005", "Duplicate Bắc Nam Hà PDF returned by DocumentFiles/2184", "Cục Thủy lợi", "REJECT", "Byte-identical SHA-256 to SRC-V41-001; no second corpus document."),
    ("SRC-V41-006", "Draft TCVN design of concrete dams", "Bộ NN&PTNT consultation portal", "BLOCKED", "Official URL found, but download failed; content not locally verified."),
    ("SRC-V41-007", "Chỉ thị 2592/CT-BNN-TL (2024)", "Bộ NN&PTNT", "REVIEW", "Landing page and attachment identified; PDF not downloaded in this run."),
    ("SRC-V41-008", "Nghị định 114/2018/NĐ-CP on dam safety", "Chính phủ", "REVIEW", "Authoritative legal text should be acquired from primary government source; aggregator result rejected as evidence."),
    ("SRC-V41-009", "Current Đại Lải reservoir operation procedure 2394/QĐ-BNNMT", "Cục Thủy lợi", "REVIEW", "Official listing found; direct attachment/version not resolved."),
    ("SRC-V41-010", "Bắc Nam Hà weekly forecast 10–16/07/2020", "Viện Quy hoạch Thủy lợi", "REVIEW", "Official PDF indexed; useful historical relation but low priority after SRC-V41-002."),
    ("SRC-V41-011", "Bắc Nam Hà monthly forecast October 2020", "Viện Quy hoạch Thủy lợi", "REVIEW", "Official PDF indexed; not downloaded; potential same-system time series."),
    ("SRC-V41-012", "Sông Nhuệ water-quality monitoring synthesis", "Cục Thủy lợi", "REVIEW", "Official PDF indexed; may deepen rule+observation use case; not downloaded."),
    ("SRC-V41-013", "Cái Lớn–Cái Bé consultation article", "Viện Quy hoạch Thủy lợi miền Nam", "REJECT", "HTML context, not a source PDF; retained only as discovery provenance."),
    ("SRC-V41-014", "Cái Lớn–Cái Bé operation drill 2023", "Viện Quy hoạch Thủy lợi", "REJECT", "HTML news item, not a complete operational record or PDF."),
    ("SRC-V41-015", "Cái Lớn–Cái Bé impact assessment article", "Viện Quy hoạch Thủy lợi", "REJECT", "HTML summary only; cannot replace underlying report."),
    ("SRC-V41-016", "Cái Lớn–Cái Bé official commissioning article", "Cục PCTT", "REJECT", "HTML secondary event report; not a technical dossier."),
    ("SRC-V41-017", "An Giang hydro-meteorological bulletin April 2026", "UBND tỉnh An Giang", "REVIEW", "Official PDF found; future-dated relative to legacy series and not downloaded."),
    ("SRC-V41-018", "Kien Giang irrigation master-plan report", "UBND tỉnh Kiên Giang", "REVIEW", "Official PDF indexed; old planning report requires version and extraction review."),
    ("SRC-V41-019", "Consolidated disaster-prevention circular", "Cục PCTT", "REVIEW", "Official PDF accessible in search; legal consolidation/version status requires verification."),
    ("SRC-V41-020", "National dam safety draft standard for penstocks", "Bộ NN&PTNT consultation portal", "REVIEW", "Official consultation PDF found; draft only and not downloaded."),
]


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def build_sources() -> None:
    accepted_rows = []
    for doc in NEW_DOCS:
        path = RAW / doc["filename"]
        reader = PdfReader(str(path))
        texts = [p.extract_text() or "" for p in reader.pages]
        digest = sha256(path)
        assert digest.startswith(doc["doc_id"].rsplit("_", 1)[-1])
        parsed = {
            "doc_id": doc["doc_id"], "source_pdf": str(path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": digest, "parser": f"pypdf-{__import__('pypdf').__version__}",
            "pages": [{"page_number": i + 1, "text": text, "char_count": len(text)} for i, text in enumerate(texts)],
            "warning": "Machine extraction only; not approved as gold evidence without locator-level human review.",
        }
        parsed_path = ROOT / "data/v4_corpus/parsed" / f"{doc['doc_id']}.json"
        parsed_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        accepted_rows.append({**doc, "sha256": digest, "size_bytes": path.stat().st_size,
                              "page_count": len(reader.pages), "extracted_chars": sum(map(len, texts)),
                              "pdf_accessibility": "DOWNLOADED_PDF_MAGIC_OK", "extraction_feasibility": "NATIVE_TEXT_EXTRACTABLE",
                              "duplicate_status": "UNIQUE_SHA256", "human_validated": False})

    candidate_rows = []
    for d in accepted_rows:
        candidate_rows.append({k: d.get(k, "") for k in ["candidate_id", "title", "publisher", "url", "publication_date", "geography", "facility", "domain", "gap", "status", "reason"]})
    urls = {
        "SRC-V41-005": "https://www.cucthuyloi.gov.vn/Portals/0/DocumentFiles/2184_1_QTVH%20HTTL%20B%E1%BA%AFc%20Nam%20H%C3%A0.pdf",
        "SRC-V41-006": "https://www.mard.gov.vn/VanBanLayYKien/VBPLFile/TCVN-TKdapBT.pdf",
        "SRC-V41-007": "https://phongchongthientai.mard.gov.vn/VanBan/Pages/chi-thi-so-2592-ct-bnn-tl.aspx",
        "SRC-V41-008": "https://vanban.chinhphu.vn/",
        "SRC-V41-009": "https://www.cucthuyloi.gov.vn/",
        "SRC-V41-010": "https://iwrp.gov.vn/upload/medias/sChau_Tuan_10.7-16.7.2020.pdf",
        "SRC-V41-011": "https://iwrp.gov.vn/upload/medias/sChau_thang_10_2020.pdf",
        "SRC-V41-012": "https://www.cucthuyloi.gov.vn/Portals/0/DocumentFiles/2170_1_Gi%C3%A1m%20s%C3%A1t%20CLN_BCTH_S%C3%B4ng%20Nhue.pdf",
        "SRC-V41-013": "https://siwrp.org.vn/tin-tuc/hoi-thao-tham-van-%E2%80%9Cquy-trinh-van-hanh-he-thong-thuy-loi-cai-lon-cai-be-giai-doan-1%E2%80%9D_2799.html",
        "SRC-V41-014": "https://iwrp.gov.vn/d1948/.html",
        "SRC-V41-015": "https://iwrp.gov.vn/d1850/van-ban-phap-ly.html",
        "SRC-V41-016": "https://phongchongthientai.mard.gov.vn/Pages/kien-giang-khanh-thanh-du-an-he-thong-thuy-loi-cai-lon--cai-be.aspx",
        "SRC-V41-017": "https://angiang.gov.vn/sites/default/files/2026/04/tap-tin-dinh-kem/agiakttvhm202604211700signed.pdf",
        "SRC-V41-018": "https://vinhdieu.angiang.gov.vn/sites/default/files/OldFiles/01-Bao_cao_tong_hop_QHTL_Kien_Giang_201809170229447870.pdf",
        "SRC-V41-019": "https://phongchongthientai.mard.gov.vn/VanBan/VanBan/3.9.%20TT%2002%20H%E1%BB%A3p%20nh%E1%BA%A5t.pdf",
        "SRC-V41-020": "https://www.mard.gov.vn/VanBanLayYKien/VBPLFile/DT-cucQLXDCT-250422.pdf",
    }
    for cid, title, publisher, status, reason in OTHER_CANDIDATES:
        candidate_rows.append({"candidate_id": cid, "title": title, "publisher": publisher, "url": urls[cid],
                               "publication_date": "", "geography": "", "facility": "", "domain": "", "gap": "",
                               "status": status, "reason": reason})
    write_csv(HERE / "NEW_SOURCE_CANDIDATES.csv", candidate_rows, list(candidate_rows[0]))

    screening_fields = ["candidate_id", "doc_id", "publisher", "title", "publication_date", "validity", "geography", "facility",
                        "domain", "subdomain", "related_existing_documents", "gap", "url", "duplicate_status", "pdf_accessibility",
                        "extraction_feasibility", "redistribution", "sha256", "size_bytes", "page_count", "human_validated", "status", "reason"]
    screening = []
    for d in accepted_rows:
        related = "IRR_CTL_2025_c3d033a0;IRR_CTL_2025_57989573" if "CLCB" in d["filename"] else ""
        screening.append({**d, "related_existing_documents": related})
    for row in candidate_rows[4:]:
        screening.append({**row, "doc_id": "", "validity": "UNRESOLVED", "subdomain": "", "related_existing_documents": "",
                          "duplicate_status": "DUPLICATE_SHA256" if row["candidate_id"] == "SRC-V41-005" else "NOT_FULLY_CHECKED",
                          "pdf_accessibility": "NOT_IN_LOCAL_CORPUS", "extraction_feasibility": "NOT_TESTED", "redistribution": "UNRESOLVED",
                          "sha256": "", "size_bytes": "", "page_count": "", "human_validated": False})
    write_csv(HERE / "NEW_SOURCE_SCREENING.csv", screening, screening_fields)

    # Immutable references to the 89 legacy accepted records plus four new sources.
    with (ROOT / "reports/document_inventory/ALL_PDF_DOCUMENT_INVENTORY.csv").open(encoding="utf-8-sig", newline="") as f:
        legacy = [r for r in csv.DictReader(f) if r["corpus_status"] == "ACCEPT"]
    assert len(legacy) == 89
    manifest = []
    for r in legacy:
        p = ROOT / r["local_path"]
        manifest.append({"doc_id": r["doc_id"], "corpus_layer": "LEGACY_V3_2_REFERENCE", "source_title": r["title"],
                         "publisher": r["source_agency"], "source_url": r["source_url"], "local_path": r["local_path"],
                         "sha256": sha256(p), "source_lineage": "V3.2 ACCEPT -> V4.0 document human acceptance -> V4.1 immutable reference",
                         "source_human_validated": r["human_review_status"] == "ACCEPTED", "qa_human_validated": False,
                         "redistribution": "REFERENCED_IN_PLACE_NOT_COPIED", "status": "ACCEPT"})
    for d in accepted_rows:
        manifest.append({"doc_id": d["doc_id"], "corpus_layer": "V4_1_NEW_SOURCE", "source_title": d["title"],
                         "publisher": d["publisher"], "source_url": d["url"], "local_path": f"data/v4_corpus/raw/{d['filename']}",
                         "parsed_path": f"data/v4_corpus/parsed/{d['doc_id']}.json", "sha256": d["sha256"],
                         "source_lineage": f"V4.1 targeted discovery {d['candidate_id']} -> PDF download -> magic/checksum/text screening",
                         "source_human_validated": False, "qa_human_validated": False, "validity": d["validity"],
                         "redistribution": d["redistribution"], "status": "ACCEPT"})
    with (HERE / "V4_CORPUS_MANIFEST.jsonl").open("w", encoding="utf-8") as f:
        for row in manifest: f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (ROOT / "data/v4_corpus/metadata/v4_corpus_manifest.jsonl").open("w", encoding="utf-8") as f:
        for row in manifest: f.write(json.dumps(row, ensure_ascii=False) + "\n")

    packs = {
        "schema_version": "1.0", "gold_relation_policy": "Only VERIFIED relations may support cross-document QA; current records require human relation review.",
        "packs": [
            {"pack_id": "PACK_BAC_NAM_HA", "system": "Hệ thống công trình thủy lợi Bắc Nam Hà", "status": "REVIEW_REQUIRED",
             "documents": ["V4_CTTL_2025_77c60f84", "V4_IWRP_2021_3031564c"],
             "relations": [{"subject": "V4_IWRP_2021_3031564c", "predicate": "historical_operation_context_for", "object": "Hệ thống Bắc Nam Hà",
                            "evidence": "Report names Bắc Nam Hà and cites 5470/QĐ-BNN-TCTL; 1318/QĐ-BNNMT states it replaces 5470.",
                            "status": "MANIFEST_RELATION_PENDING_HUMAN"}],
             "coverage": ["facility inventory", "operation procedure", "irrigation demand", "drought/shortage scenario"]},
            {"pack_id": "PACK_CAI_LON_CAI_BE", "system": "Hệ thống Cái Lớn–Cái Bé", "status": "REVIEW_REQUIRED",
             "documents": ["V4_CTTL_2024_dda51c21", "IRR_CTL_2025_c3d033a0", "IRR_CTL_2025_57989573"],
             "relations": [{"subject": "V4_CTTL_2024_dda51c21", "predicate": "draft_governance_context_for", "object": "IRR_CTL_2025_c3d033a0",
                            "evidence": "All sources explicitly name HTCTTL Cái Lớn–Cái Bé; draft appendix names environmental control points. Applicability not yet human-reviewed.",
                            "status": "MANIFEST_RELATION_PENDING_HUMAN"}],
             "coverage": ["facility inventory", "draft operation", "water-quality forecast", "salinity-control context"]}
        ]}
    (HERE / "LINKED_DOCUMENT_PACKS.json").write_text(json.dumps(packs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"legacy": len(legacy), "new": len(accepted_rows), "manifest": len(manifest),
                      "screened": len(screening), "statuses": Counter(x["status"] for x in screening)}, default=dict))


if __name__ == "__main__":
    build_sources()
