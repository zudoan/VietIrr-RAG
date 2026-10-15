"""Build an auditable inventory of every local source PDF.

The inventory separates canonical manifest records from physical PDFs that are
present on disk but not admitted to the canonical corpus. Content profiles are
conservative, metadata-derived descriptions of what a qualified reviewer may
extract; they are not human-verified labels.
"""

from __future__ import annotations

import csv
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORT_DIR = ROOT / "reports" / "document_inventory"


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def plain(value: Any) -> str:
    text = "" if value is None else str(value)
    return "".join(
        char for char in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(char) != "Mn"
    ).replace("đ", "d")


def joined(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return "" if value is None else str(value)


def content_profile(record: dict[str, Any]) -> tuple[str, str, str]:
    title = plain(record.get("title"))
    doc_type = plain(record.get("doc_type"))
    source_id = str(record.get("source_id") or "")

    direct: dict[str, tuple[str, str, str]] = {
        "V3_MARD_COMMUNE_IRRIGATION_HANDBOOK": (
            "Sổ tay quản lý thủy lợi cấp xã",
            "Nhiệm vụ, thẩm quyền, quy trình phối hợp, quản lý công trình thủy lợi, phòng chống thiên tai và biểu mẫu/hướng dẫn thực hiện ở cấp xã.",
            "QA quy trình–trách nhiệm; tra cứu nhiệm vụ; evidence theo điều/mục."
        ),
        "V3_MEKONG_WATER_RESOURCES_2021": (
            "Báo cáo tổng kết tài nguyên nước/mùa lũ Mê Công",
            "Diễn biến mưa–lũ, mực nước/lưu lượng, vận hành hồ, điều kiện thủy văn và nhận định mùa lũ Mê Công năm 2021.",
            "QA thời gian; so sánh trạm/giai đoạn; truy xuất bảng và nhận định thủy văn."
        ),
        "V3_PCTT_DAM_HUONG_2023": (
            "Báo cáo tình huống vận hành hồ khi lũ",
            "Diễn biến trận lũ sông Hương 11/2023, mưa/lưu lượng/mực nước, quyết định vận hành hồ, tác động hạ du và bài học vận hành.",
            "QA sự kiện; chuỗi thời gian; quan hệ vận hành–tác động; evidence nhiều trang."
        ),
        "V3_PCTT_SREX_VN": (
            "Báo cáo rủi ro thiên tai và khí hậu quốc gia",
            "Hiểm họa khí hậu, cực đoan thời tiết, phơi bày, tính dễ bị tổn thương, thiệt hại lịch sử, kịch bản và khuyến nghị quản lý rủi ro.",
            "QA tổng hợp/chính sách; số liệu thống kê; so sánh vùng và loại thiên tai."
        ),
        "V3_PCTT_MONITORING_FRAMEWORK": (
            "Khung theo dõi, đánh giá chiến lược",
            "Mục tiêu, chỉ tiêu, đơn vị chịu trách nhiệm, nguồn kiểm chứng, mốc thời gian và cơ chế theo dõi thực hiện chiến lược phòng chống thiên tai.",
            "QA chỉ tiêu–cơ quan–thời hạn; bảng theo dõi; provenance pháp lý."
        ),
        "V3_PCTT_DYKE_HISTORY": (
            "Tài liệu lịch sử đê điều Việt Nam",
            "Lịch sử hình thành hệ thống đê, các trận lũ, công trình, chính sách quản lý đê điều và kinh nghiệm phòng chống lũ theo thời kỳ/vùng.",
            "QA lịch sử; timeline; thực thể công trình/địa danh; tổng hợp nhiều đoạn."
        ),
        "V3_PCTT_REGULATION": (
            "Văn bản quy định phòng chống thiên tai",
            "Yêu cầu pháp lý, đối tượng áp dụng, trách nhiệm, tiêu chí, hồ sơ và thủ tục liên quan đến phòng chống thiên tai.",
            "QA pháp lý; nghĩa vụ–chủ thể; điều khoản và điều kiện áp dụng."
        ),
        "V3_PCTT_HEAVY_RAIN_2025": (
            "Công điện/văn bản chỉ đạo ứng phó mưa lớn",
            "Dự báo rủi ro mưa lớn, lũ quét, sạt lở; khu vực ảnh hưởng; nhiệm vụ ứng phó và cơ quan chịu trách nhiệm.",
            "QA cảnh báo–khu vực–hành động; truy xuất trách nhiệm."
        ),
        "V3_PCTT_WATER_INFRASTRUCTURE_ASSESSMENT": (
            "Báo cáo đánh giá hạ tầng cấp nước",
            "Hiện trạng công trình/cấp nước, phạm vi phục vụ, công suất, nhu cầu, thiếu hụt, chất lượng dịch vụ và đề xuất đầu tư/quản lý.",
            "QA hiện trạng; số liệu công suất/phạm vi; so sánh địa phương; bảng thống kê."
        ),
        "V3_PCTT_CBRDM_MANUAL": (
            "Sổ tay quản lý rủi ro thiên tai dựa vào cộng đồng",
            "Khái niệm, quy trình đánh giá rủi ro, lập kế hoạch, tham vấn cộng đồng, phân công và công cụ/biểu mẫu thực hành.",
            "QA quy trình; bước–đầu ra; vai trò các bên; checklist."
        ),
        "V3_PCTT_BULLETIN_2023_07": (
            "Bản tin thiên tai tháng",
            "Sự kiện thiên tai, địa bàn, thời gian, thiệt hại, công tác ứng phó và cảnh báo trong tháng 07/2023.",
            "QA sự kiện–thời gian–địa điểm; thống kê thiệt hại; diễn biến theo tháng."
        ),
        "V3_PCTT_BULLETIN_2023_08": (
            "Bản tin thiên tai tháng",
            "Sự kiện thiên tai, địa bàn, thời gian, thiệt hại, công tác ứng phó và cảnh báo trong tháng 08/2023.",
            "QA sự kiện–thời gian–địa điểm; thống kê thiệt hại; diễn biến theo tháng."
        ),
        "V3_PCTT_BULLETIN_2024_09": (
            "Bản tin thiên tai tháng",
            "Sự kiện thiên tai, địa bàn, thời gian, thiệt hại, công tác ứng phó và cảnh báo trong tháng 09/2024.",
            "QA sự kiện–thời gian–địa điểm; thống kê thiệt hại; diễn biến theo tháng."
        ),
        "V3_PCTT_CONFERENCE_2022": (
            "Kỷ yếu/tài liệu hội nghị phòng chống thiên tai",
            "Nhiều báo cáo về hiện trạng, chính sách, bài học, số liệu và kế hoạch phòng chống thiên tai của các cơ quan/địa phương.",
            "Chỉ dùng sau khi tách bài/section; QA tổng hợp cần kiểm tra tác giả và phạm vi từng báo cáo."
        ),
        "V3_PCTT_WHITE_BOOK_2023": (
            "Sách trắng phòng chống thiên tai",
            "Tổng quan thiên tai năm 2023, thiệt hại, hoạt động ứng phó, nguồn lực, chính sách và bài học theo loại thiên tai/địa phương.",
            "QA thống kê năm; sự kiện–thiệt hại–ứng phó; evidence bảng/biểu đồ."
        ),
    }
    if source_id in direct:
        return direct[source_id]

    if "quy trinh van hanh lien ho" in doc_type or "quy trinh van hanh lien ho" in title:
        return (
            "Quy trình pháp lý vận hành liên hồ chứa",
            "Danh mục hồ; mực nước giới hạn; mùa lũ/mùa cạn; ngưỡng và lưu lượng xả; thứ tự vận hành; tình huống bất thường; trách nhiệm và hiệu lực văn bản.",
            "QA điều kiện–hành động; tra cứu ngưỡng; quan hệ hồ–lưu vực; đối chiếu phiên bản văn bản."
        )
    if "lich lay nuoc" in title or "water_supply_plan" in doc_type:
        return (
            "Kế hoạch/lịch lấy nước phục vụ sản xuất",
            "Đợt và thời gian lấy nước, khu vực phục vụ, diện tích gieo cấy, mực nước/vận hành công trình, nhiệm vụ của địa phương và đơn vị quản lý.",
            "QA lịch–địa bàn–diện tích; tra cứu đợt lấy nước; bảng kế hoạch."
        )
    if any(term in title for term in ("chat luong nuoc", "quan trac")) or "water_quality" in doc_type or "chat luong nuoc" in doc_type:
        return (
            "Quan trắc/giám sát và dự báo chất lượng nước",
            "Điểm/trạm lấy mẫu; thời gian; pH, DO, BOD/COD, TSS, NH4+, NO2-/NO3-, PO4, độ mặn/WQI và chỉ tiêu liên quan; mức đạt quy chuẩn; diễn biến và khuyến nghị vận hành.",
            "QA trạm–chỉ tiêu–thời gian; so sánh quy chuẩn; bảng quan trắc; cảnh báo chất lượng nước."
        )
    if "an toan" in title and "ho" in title:
        return (
            "Báo cáo an toàn hồ chứa và chất lượng nước",
            "Hiện trạng hồ/công trình, mực nước/dung tích, dấu hiệu mất an toàn, kết quả kiểm tra/quan trắc chất lượng nước và kiến nghị xử lý.",
            "QA hồ–trạng thái–thời gian; sự cố/khuyến nghị; số liệu bảng nếu numeric-safe."
        )
    if "ban tin dot xuat" in title or ("bao so" in title and "mua" in title):
        return (
            "Bản tin thủy văn/nguồn nước đột xuất do bão",
            "Nhận định mưa, bão và ảnh hưởng đến lưu vực Mê Công/ĐBSCL; phạm vi, thời gian, diễn biến nguồn nước và cảnh báo vận hành/ứng phó.",
            "QA sự kiện–thời gian–khu vực; liên kết bão–mưa–nguồn nước; cảnh báo ngắn hạn."
        )
    if "du bao lu" in doc_type or "van hanh ho" in title:
        return (
            "Bản tin dự báo lũ và vận hành hồ chứa",
            "Mưa, mực nước, lưu lượng đến/xả, dự báo lũ, dung tích hồ, chế độ vận hành và cảnh báo hạ du theo thời điểm.",
            "QA temporal; so sánh quan trắc–dự báo; chuỗi vận hành hồ."
        )
    if any(term in title for term in ("du bao nguon nuoc", "db nguon nuoc", "dbnn", "dien bien nguon nuoc")) or "du bao nguon nuoc" in doc_type:
        return (
            "Bản tin/báo cáo dự báo nguồn nước và kế hoạch sử dụng nước",
            "Mưa; mực nước/lưu lượng; dung tích hồ; nguồn nước hiện trạng và dự báo; nhu cầu/diện tích sản xuất; cân bằng, thiếu hụt và khuyến nghị sử dụng nước theo vùng và thời gian.",
            "QA temporal; trạm/hồ–chỉ tiêu; so sánh kỳ; bảng cân bằng và kế hoạch sử dụng nước."
        )
    if "bao cao dbnn" in doc_type:
        return (
            "Báo cáo nguồn nước hoặc giám sát chất lượng nước",
            "Các trường nguồn nước/chất lượng nước, địa điểm, thời gian, giá trị quan trắc/dự báo, bảng biểu và khuyến nghị; cần xác định nhánh nội dung từ tiêu đề/section trước khi gán metric.",
            "QA theo section sau phân loại thủ công; không gán metric chỉ từ nhãn doc_type tổng quát."
        )
    return (
        "Tài liệu tài nguyên nước/thủy lợi chính thức",
        "Nội dung chuyên ngành theo tiêu đề, gồm thực thể công trình/địa bàn, mốc thời gian, quy định, số liệu và bảng biểu nếu hiện diện.",
        "Chỉ xây QA sau khi kiểm tra trực tiếp section, bảng và ngữ cảnh nguồn."
    )


def md_cell(value: Any) -> str:
    return joined(value).replace("|", "\\|").replace("\n", " ").strip()


def main() -> None:
    documents = list(read_jsonl(DATA / "documents.jsonl"))

    pages: dict[str, Counter[str]] = defaultdict(Counter)
    for row in read_jsonl(DATA / "pages.jsonl"):
        stat = pages[str(row.get("doc_id"))]
        stat["parsed_pages"] += 1
        stat["numeric_safe_pages"] += int(row.get("numeric_safe") is True)
        stat["ocr_pages"] += int(str(row.get("text_extraction") or "").upper() == "OCR")

    regions: dict[str, Counter[str]] = defaultdict(Counter)
    for row in read_jsonl(DATA / "regions.jsonl"):
        stat = regions[str(row.get("doc_id"))]
        stat["regions"] += 1
        stat["qa_eligible_regions"] += int(row.get("qa_eligible") is True)
        stat["numeric_safe_regions"] += int(row.get("numeric_safe") is True)

    tables: dict[str, Counter[str]] = defaultdict(Counter)
    for row in read_jsonl(DATA / "tables.jsonl"):
        stat = tables[str(row.get("doc_id"))]
        stat["tables"] += 1
        stat[f"structural_{str(row.get('structural_quality') or 'UNKNOWN').lower()}"] += 1
        stat[f"semantic_{str(row.get('semantic_quality') or 'UNKNOWN').lower()}"] += 1
        stat["semantic_tuples"] += len(row.get("semantic_tuples") or [])

    rows: list[dict[str, Any]] = []
    canonical_paths: set[str] = set()
    for document in documents:
        doc_id = str(document["doc_id"])
        path = str(document.get("local_path") or "")
        canonical_paths.add(path.replace("\\", "/").lower())
        category, extractable, uses = content_profile(document)
        local_file = ROOT / path
        limitations = ["Chưa human-validated"]
        if document.get("acceptance_status") != "ACCEPT":
            limitations.append(f"REJECT: {document.get('acceptance_reason') or 'không rõ lý do'}")
        if document.get("is_scanned"):
            limitations.append("PDF scan")
        if document.get("ocr_used"):
            limitations.append("OCR; phải đối chiếu ảnh trang")
        if document.get("ocr_numeric_qa_allowed") is False:
            limitations.append("Không cho phép dùng số OCR làm gold tự động")
        if float(document.get("usable_page_ratio") or 0.0) < 0.8:
            limitations.append("Tỷ lệ trang usable thấp")
        if tables[doc_id]["tables"] and tables[doc_id]["semantic_good"] == 0:
            limitations.append("Không có bảng semantic GOOD")

        rows.append({
            "inventory_id": "",
            "doc_id": doc_id,
            "canonical_manifest": True,
            "corpus_status": document.get("acceptance_status"),
            "acceptance_reason": document.get("acceptance_reason"),
            "track": document.get("core_or_temporal"),
            "title": document.get("title"),
            "document_type_manifest": document.get("doc_type"),
            "content_category_review": category,
            "source_agency": document.get("source_agency"),
            "source_domain": document.get("source_domain"),
            "source_id": document.get("source_id"),
            "source_url": document.get("source_url"),
            "landing_page_url": document.get("landing_page_url"),
            "publication_date": document.get("publication_date"),
            "basin": joined(document.get("basin")),
            "province": joined(document.get("province")),
            "page_count_manifest": document.get("page_count"),
            "parsed_pages": pages[doc_id]["parsed_pages"],
            "numeric_safe_pages": pages[doc_id]["numeric_safe_pages"],
            "ocr_pages": pages[doc_id]["ocr_pages"],
            "regions": regions[doc_id]["regions"],
            "qa_eligible_regions": regions[doc_id]["qa_eligible_regions"],
            "numeric_safe_regions": regions[doc_id]["numeric_safe_regions"],
            "tables": tables[doc_id]["tables"],
            "tables_structural_good": tables[doc_id]["structural_good"],
            "tables_structural_partial": tables[doc_id]["structural_partial"],
            "tables_structural_broken": tables[doc_id]["structural_broken"],
            "tables_semantic_good": tables[doc_id]["semantic_good"],
            "semantic_tuples": tables[doc_id]["semantic_tuples"],
            "is_scanned": document.get("is_scanned"),
            "ocr_used": document.get("ocr_used"),
            "ocr_numeric_qa_allowed": document.get("ocr_numeric_qa_allowed"),
            "usable_page_ratio": document.get("usable_page_ratio"),
            "human_validated": document.get("human_validated"),
            "local_path": path,
            "local_file_exists": local_file.is_file(),
            "file_size_bytes": local_file.stat().st_size if local_file.is_file() else 0,
            "information_can_extract": extractable,
            "recommended_uses": uses,
            "limitations": "; ".join(limitations),
            "assessment_basis": "manifest + parsed artifact counts; content profile inferred conservatively from official title/type",
        })

    acquisition_path = ROOT / "reports" / "v3_source_acquisition_audit.json"
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8-sig"))
    for item in acquisition.get("sources", []):
        path = str(item.get("local_path") or "")
        if not path or path.replace("\\", "/").lower() in canonical_paths:
            continue
        local_file = ROOT / path
        pseudo = {
            "title": Path(path).stem.replace("_", " "),
            "doc_type": "official_water_resource_document",
            "source_id": item.get("source_id"),
        }
        category, extractable, uses = content_profile(pseudo)
        rows.append({
            "inventory_id": "",
            "doc_id": "",
            "canonical_manifest": False,
            "corpus_status": "REVIEW_NOT_IN_CANONICAL_MANIFEST",
            "acceptance_reason": item.get("quality_gate"),
            "track": "v3_official_unadmitted",
            "title": pseudo["title"],
            "document_type_manifest": "not_in_canonical_manifest",
            "content_category_review": category,
            "source_agency": item.get("agency"),
            "source_domain": "phongchongthientai.mard.gov.vn",
            "source_id": item.get("source_id"),
            "source_url": item.get("url"),
            "landing_page_url": "",
            "publication_date": "",
            "basin": "",
            "province": "",
            "page_count_manifest": item.get("pages"),
            "parsed_pages": 0,
            "numeric_safe_pages": 0,
            "ocr_pages": 0,
            "regions": 0,
            "qa_eligible_regions": 0,
            "numeric_safe_regions": 0,
            "tables": 0,
            "tables_structural_good": 0,
            "tables_structural_partial": 0,
            "tables_structural_broken": 0,
            "tables_semantic_good": 0,
            "semantic_tuples": 0,
            "is_scanned": "",
            "ocr_used": "",
            "ocr_numeric_qa_allowed": False,
            "usable_page_ratio": item.get("text_page_ratio"),
            "human_validated": False,
            "local_path": path,
            "local_file_exists": local_file.is_file(),
            "file_size_bytes": local_file.stat().st_size if local_file.is_file() else 0,
            "information_can_extract": extractable,
            "recommended_uses": uses,
            "limitations": "Chưa vào canonical manifest; quality gate REVIEW; chưa parse; chưa human-validated",
            "assessment_basis": "v3 acquisition audit only; content profile inferred conservatively from official title/type",
        })

    rows.sort(key=lambda row: (
        0 if row["corpus_status"] == "ACCEPT" else 1 if row["corpus_status"] == "REJECT" else 2,
        str(row["content_category_review"]), str(row["title"]), str(row["local_path"]),
    ))
    for index, row in enumerate(rows, start=1):
        row["inventory_id"] = f"PDF_{index:03d}"

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = REPORT_DIR / "ALL_PDF_DOCUMENT_INVENTORY.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    status_counts = Counter(str(row["corpus_status"]) for row in rows)
    type_counts = Counter(str(row["content_category_review"]) for row in rows if row["corpus_status"] == "ACCEPT")
    agency_counts = Counter(str(row["source_agency"]) for row in rows if row["corpus_status"] == "ACCEPT")
    summary = {
        "physical_pdf_files": len(list((DATA / "raw").rglob("*.pdf"))),
        "inventory_rows": len(rows),
        "canonical_manifest_records": len(documents),
        "canonical_accepted": status_counts["ACCEPT"],
        "canonical_rejected": status_counts["REJECT"],
        "physical_not_in_canonical_manifest": status_counts["REVIEW_NOT_IN_CANONICAL_MANIFEST"],
        "human_validated_documents": sum(row["human_validated"] is True for row in rows),
        "status_counts": dict(status_counts),
        "accepted_content_categories": dict(sorted(type_counts.items())),
        "accepted_source_agencies": dict(sorted(agency_counts.items())),
        "method_note": "Content categories and extractable-information descriptions are conservative metadata-derived review aids, not human labels.",
    }
    (REPORT_DIR / "INVENTORY_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Kiểm kê nguồn và khả năng khai thác toàn bộ PDF",
        "",
        "## Kết luận kiểm kê",
        "",
        f"- Có **{summary['physical_pdf_files']} PDF vật lý** trong `data/raw`.",
        f"- Manifest chuẩn có **{summary['canonical_manifest_records']} document record**: "
        f"**{summary['canonical_accepted']} ACCEPT**, **{summary['canonical_rejected']} REJECT**.",
        f"- Có **{summary['physical_not_in_canonical_manifest']} PDF** ở trạng thái review nhưng không nằm trong manifest chuẩn.",
        f"- Số tài liệu được xác nhận `human_validated=true`: **{summary['human_validated_documents']}**.",
        "- `ACCEPT` ở đây chỉ là đạt gate kỹ thuật/parsing, không có nghĩa nội dung hay QA đã được người kiểm chứng.",
        "- Cột `Thông tin có thể khai thác` là mô tả thận trọng dựa trên nguồn, tiêu đề, loại tài liệu và thống kê artifact; không phải nhãn gold.",
        "",
        "## Nhóm tài liệu ACCEPT",
        "",
        "| Nhóm nội dung | Số tài liệu |",
        "|---|---:|",
    ]
    for key, count in sorted(type_counts.items(), key=lambda pair: (-pair[1], pair[0])):
        lines.append(f"| {md_cell(key)} | {count} |")
    lines.extend([
        "",
        "## Cơ quan nguồn của tài liệu ACCEPT",
        "",
        "| Cơ quan | Số tài liệu |",
        "|---|---:|",
    ])
    for key, count in sorted(agency_counts.items(), key=lambda pair: (-pair[1], pair[0])):
        lines.append(f"| {md_cell(key)} | {count} |")

    def add_table(title: str, selected: list[dict[str, Any]]) -> None:
        lines.extend([
            "",
            f"## {title}",
            "",
            "| # | Doc ID | Tài liệu và nguồn | Thể loại | Phạm vi/kỹ thuật | Thông tin có thể khai thác | Cảnh báo |",
            "|---:|---|---|---|---|---|---|",
        ])
        for row in selected:
            source = f"**{md_cell(row['title'])}**<br>{md_cell(row['source_agency'])}<br>[PDF nguồn]({row['source_url']})"
            technical = (
                f"track={md_cell(row['track'])}; pages={row['page_count_manifest']}; "
                f"parsed={row['parsed_pages']}; regions={row['regions']}; tables={row['tables']}; "
                f"semantic-good={row['tables_semantic_good']}; numeric-safe-pages={row['numeric_safe_pages']}"
            )
            lines.append(
                f"| {row['inventory_id']} | {md_cell(row['doc_id']) or '—'} | {source} | "
                f"{md_cell(row['content_category_review'])} | {technical} | "
                f"{md_cell(row['information_can_extract'])} | {md_cell(row['limitations'])} |"
            )

    add_table("89 tài liệu được manifest đánh dấu ACCEPT", [row for row in rows if row["corpus_status"] == "ACCEPT"])
    add_table("5 tài liệu bị REJECT — không dùng để tạo gold QA", [row for row in rows if row["corpus_status"] == "REJECT"])
    add_table(
        "2 PDF vật lý chưa được nhận vào canonical manifest",
        [row for row in rows if row["corpus_status"] == "REVIEW_NOT_IN_CANONICAL_MANIFEST"],
    )
    lines.extend([
        "",
        "## Quy tắc sử dụng an toàn",
        "",
        "1. Chỉ xem một fact là ground truth sau khi người review mở đúng PDF/trang/vùng và xác minh.",
        "2. Không dùng số từ trang OCR khi `numeric_safe=false` hoặc `ocr_numeric_qa_allowed=false`.",
        "3. Không dùng tài liệu REJECT hoặc chưa vào canonical manifest để tạo QA trước khi audit lại.",
        "4. Với bảng `PARTIAL/BROKEN` hoặc không có `semantic_good`, phải đọc bảng gốc; không tin tuple tự động.",
        "5. Với bản tin theo ngày/tuần/tháng, split theo series/family để tránh leakage thời gian và template.",
        "",
    ])
    (REPORT_DIR / "ALL_PDF_DOCUMENT_INVENTORY.md").write_text("\n".join(lines), encoding="utf-8")

    # Keep the CLI summary printable on Windows consoles that still use a
    # legacy code page; the generated files remain UTF-8 Vietnamese.
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
