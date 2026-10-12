import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
import hashlib
import json
import csv
from datetime import datetime
from pathlib import Path
import urllib.parse
import urllib3
import requests
import fitz

urllib3.disable_warnings()

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) VietIrrDocBench-Harvester/2.0'}

# 1. Official Core Long Documents (Inter-reservoir Operating Procedures & Long Seasonal Reports)
CORE_SOURCES = [
    {
        "source_id": "SRC_CP_QD740_2019",
        "agency": "Thủ tướng Chính phủ",
        "domain": "chinhphu.vn",
        "source_category": "Tier A4 — Cổng thông tin Chính phủ",
        "page_url": "http://vanban.chinhphu.vn/?pageid=27160&docid=197241",
        "document_url": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2019/06/740.signed.pdf",
        "document_title": "Quyết định số 740/QĐ-TTg ngày 17/06/2019 ban hành Quy trình vận hành liên hồ chứa trên lưu vực sông Hồng",
        "document_type": "Quy trình vận hành liên hồ chứa",
        "publication_date": "2019-06-17",
        "effective_date": "2019-06-17",
        "version_status": "AMENDED",
        "basin": "Sông Hồng",
        "province": "Hà Nội, Phú Thọ, Hòa Bình, Sơn La, Lai Châu, Tuyên Quang, Yên Bái",
        "reservoir": "Sơn La, Hòa Bình, Lai Châu, Bản Chát, Huội Quảng, Thác Bà, Tuyên Quang",
        "estimated_pages": 33,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "core_long",
        "notes": "Quy trình vận hành liên hồ chứa cốt lõi lưu vực sông Hồng; sửa đổi bởi QĐ 922/QĐ-TTg"
    },
    {
        "source_id": "SRC_CP_QD922_2025",
        "agency": "Thủ tướng Chính phủ",
        "domain": "chinhphu.vn",
        "source_category": "Tier A4 — Cổng thông tin Chính phủ",
        "page_url": "https://vanban.chinhphu.vn/?pageid=27160&docid=219763",
        "document_url": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2025/5/922-ttg.signed.pdf",
        "document_title": "Quyết định số 922/QĐ-TTg ngày 14/05/2025 sửa đổi bổ sung Quy trình vận hành liên hồ chứa trên lưu vực sông Hồng",
        "document_type": "Sửa đổi Quy trình vận hành liên hồ chứa",
        "publication_date": "2025-05-14",
        "effective_date": "2025-05-14",
        "version_status": "CURRENT",
        "basin": "Sông Hồng",
        "province": "Hà Nội, Phú Thọ, Hòa Bình, Sơn La, Lai Châu, Tuyên Quang, Yên Bái",
        "reservoir": "Sơn La, Hòa Bình, Lai Châu, Bản Chát, Huội Quảng, Thác Bà, Tuyên Quang",
        "estimated_pages": 12,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "core_long",
        "notes": "Văn bản sửa đổi, bổ sung cập nhật các quy định vận hành mùa lũ và mùa kiệt lưu vực sông Hồng"
    },
    {
        "source_id": "SRC_CP_QD1605_2019",
        "agency": "Thủ tướng Chính phủ",
        "domain": "chinhphu.vn",
        "source_category": "Tier A4 — Cổng thông tin Chính phủ",
        "page_url": "http://vanban.chinhphu.vn/?pageid=27160&docid=198334",
        "document_url": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2019/11/1605.signed.pdf",
        "document_title": "Quyết định số 1605/QĐ-TTg ngày 13/11/2019 ban hành Quy trình vận hành liên hồ chứa trên lưu vực sông Cả",
        "document_type": "Quy trình vận hành liên hồ chứa",
        "publication_date": "2019-11-13",
        "effective_date": "2019-11-13",
        "version_status": "CURRENT",
        "basin": "Sông Cả",
        "province": "Nghệ An, Hà Tĩnh",
        "reservoir": "Bản Vẽ, Khe Bố, Chi Khê, Bản Cánh",
        "estimated_pages": 28,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "core_long",
        "notes": "Quy trình vận hành liên hồ chứa sông Cả; quy định tích nước, điều tiết giảm lũ và cấp nước mùa kiệt"
    },
    {
        "source_id": "SRC_CP_QD1606_2019",
        "agency": "Thủ tướng Chính phủ",
        "domain": "chinhphu.vn",
        "source_category": "Tier A4 — Cổng thông tin Chính phủ",
        "page_url": "http://vanban.chinhphu.vn/?pageid=27160&docid=198335",
        "document_url": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2019/11/1606.signed.pdf",
        "document_title": "Quyết định số 1606/QĐ-TTg ngày 13/11/2019 ban hành Quy trình vận hành liên hồ chứa trên lưu vực sông Hương",
        "document_type": "Quy trình vận hành liên hồ chứa",
        "publication_date": "2019-11-13",
        "effective_date": "2019-11-13",
        "version_status": "CURRENT",
        "basin": "Sông Hương",
        "province": "Thừa Thiên Huế",
        "reservoir": "Tả Trạch, Bình Điền, Hương Điền",
        "estimated_pages": 26,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "core_long",
        "notes": "Quy trình vận hành liên hồ chứa sông Hương phục vụ giảm lũ cho TP Huế và hạ du"
    },
    {
        "source_id": "SRC_CP_QD1865_2019",
        "agency": "Thủ tướng Chính phủ",
        "domain": "chinhphu.vn",
        "source_category": "Tier A4 — Cổng thông tin Chính phủ",
        "page_url": "http://vanban.chinhphu.vn/?pageid=27160&docid=198642",
        "document_url": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2019/12/1865.signed.pdf",
        "document_title": "Quyết định số 1865/QĐ-TTg ngày 23/12/2019 ban hành Quy trình vận hành liên hồ chứa trên lưu vực sông Vu Gia - Thu Bồn",
        "document_type": "Quy trình vận hành liên hồ chứa",
        "publication_date": "2019-12-23",
        "effective_date": "2019-12-23",
        "version_status": "CURRENT",
        "basin": "Vu Gia - Thu Bồn",
        "province": "Quảng Nam, Đà Nẵng",
        "reservoir": "A Vương, Đak Mi 4, Sông Tranh 2, Sông Bung 2, Sông Bung 4",
        "estimated_pages": 32,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "core_long",
        "notes": "Quy trình vận hành liên hồ chứa hệ thống sông phức tạp Vu Gia - Thu Bồn"
    },
    {
        "source_id": "SRC_CP_QD1895_2019",
        "agency": "Thủ tướng Chính phủ",
        "domain": "chinhphu.vn",
        "source_category": "Tier A4 — Cổng thông tin Chính phủ",
        "page_url": "http://vanban.chinhphu.vn/?pageid=27160&docid=198675",
        "document_url": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2019/12/1895.signed.pdf",
        "document_title": "Quyết định số 1895/QĐ-TTg ngày 25/12/2019 ban hành Quy trình vận hành liên hồ chứa trên lưu vực sông Đồng Nai",
        "document_type": "Quy trình vận hành liên hồ chứa",
        "publication_date": "2019-12-25",
        "effective_date": "2019-12-25",
        "version_status": "CURRENT",
        "basin": "Sông Đồng Nai",
        "province": "Đồng Nai, Bình Dương, Bình Phước, Lâm Đồng, TP Hồ Chí Minh",
        "reservoir": "Trị An, Thác Mơ, Cần Đơn, Srok Phu Miêng, Đơn Dương, Đại Ninh, Hàm Thuận, Đa Mi",
        "estimated_pages": 38,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "core_long",
        "notes": "Quy trình vận hành liên hồ chứa lưu vực sông Đồng Nai (lưu vực kinh tế trọng điểm phía Nam)"
    },
    {
        "source_id": "SRC_CP_QD214_2018",
        "agency": "Thủ tướng Chính phủ",
        "domain": "chinhphu.vn",
        "source_category": "Tier A4 — Cổng thông tin Chính phủ",
        "page_url": "http://vanban.chinhphu.vn/?pageid=27160&docid=192837",
        "document_url": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2018/02/214.signed.pdf",
        "document_title": "Quyết định số 214/QĐ-TTg ngày 13/02/2018 ban hành Quy trình vận hành liên hồ chứa trên lưu vực sông Mã",
        "document_type": "Quy trình vận hành liên hồ chứa",
        "publication_date": "2018-02-13",
        "effective_date": "2018-02-13",
        "version_status": "AMENDED",
        "basin": "Sông Mã",
        "province": "Thanh Hóa, Sơn La, Hòa Bình",
        "reservoir": "Hủa Na, Cửa Đạt, Trung Sơn, Bá Thước 1, Bá Thước 2",
        "estimated_pages": 24,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "core_long",
        "notes": "Quy trình vận hành liên hồ chứa sông Mã; sửa đổi bởi QĐ 1500/QĐ-TTg"
    },
    {
        "source_id": "SRC_CP_QD1500_2020",
        "agency": "Thủ tướng Chính phủ",
        "domain": "chinhphu.vn",
        "source_category": "Tier A4 — Cổng thông tin Chính phủ",
        "page_url": "http://vanban.chinhphu.vn/?pageid=27160&docid=201214",
        "document_url": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2020/10/1500.signed.pdf",
        "document_title": "Quyết định số 1500/QĐ-TTg ngày 16/10/2020 sửa đổi, bổ sung Quy trình vận hành liên hồ chứa trên lưu vực sông Mã",
        "document_type": "Sửa đổi Quy trình vận hành liên hồ chứa",
        "publication_date": "2020-10-16",
        "effective_date": "2020-10-16",
        "version_status": "CURRENT",
        "basin": "Sông Mã",
        "province": "Thanh Hóa, Sơn La",
        "reservoir": "Hủa Na, Cửa Đạt, Trung Sơn, Bá Thước",
        "estimated_pages": 8,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "core_long",
        "notes": "Quyết định sửa đổi quy trình sông Mã bổ sung công trình thủy điện và điều kiện phòng lũ"
    },
    {
        "source_id": "SRC_CP_QD878_2018",
        "agency": "Thủ tướng Chính phủ",
        "domain": "chinhphu.vn",
        "source_category": "Tier A4 — Cổng thông tin Chính phủ",
        "page_url": "http://vanban.chinhphu.vn/?pageid=27160&docid=194380",
        "document_url": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2018/07/878.signed.pdf",
        "document_title": "Quyết định số 878/QĐ-TTg ngày 18/07/2018 ban hành Quy trình vận hành liên hồ chứa trên lưu vực sông Ba",
        "document_type": "Quy trình vận hành liên hồ chứa",
        "publication_date": "2018-07-18",
        "effective_date": "2018-07-18",
        "version_status": "CURRENT",
        "basin": "Sông Ba",
        "province": "Gia Lai, Phú Yên, Đắk Lắk",
        "reservoir": "Sông Ba Hạ, Sông Hinh, Krông Hnăng, Ayun Hạ, An Khê - Ka Nak",
        "estimated_pages": 22,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "core_long",
        "notes": "Quy trình vận hành liên hồ chứa lưu vực sông Ba phục vụ cắt lũ và cấp nước Nam Trung Bộ"
    },
    {
        "source_id": "SRC_CP_QD1201_2019",
        "agency": "Thủ tướng Chính phủ",
        "domain": "chinhphu.vn",
        "source_category": "Tier A4 — Cổng thông tin Chính phủ",
        "page_url": "http://vanban.chinhphu.vn/?pageid=27160&docid=197920",
        "document_url": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2019/09/1201.signed.pdf",
        "document_title": "Quyết định số 1201/QĐ-TTg ngày 17/09/2019 ban hành Quy trình vận hành liên hồ chứa trên lưu vực sông Srêpôk",
        "document_type": "Quy trình vận hành liên hồ chứa",
        "publication_date": "2019-09-17",
        "effective_date": "2019-09-17",
        "version_status": "CURRENT",
        "basin": "Srêpôk",
        "province": "Đắk Lắk, Đắk Nông",
        "reservoir": "Buôn Tua Srah, Buôn Kuốp, Srêpôk 3, Srêpôk 4, Dray Hlinh",
        "estimated_pages": 20,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "core_long",
        "notes": "Quy trình vận hành liên hồ chứa sông Srêpôk (lưu vực Tây Nguyên)"
    },
    # Cục Thủy Lợi Core Long Documents
    {
        "source_id": "SRC_CTL_DBNN_TAYNGUYEN_2025",
        "agency": "Cục Quản lý và Xây dựng công trình thủy lợi (Cục Thủy lợi)",
        "domain": "cucthuyloi.gov.vn",
        "source_category": "Tier A1 — Cục Thủy lợi",
        "page_url": "https://cucthuyloi.gov.vn/du-bao-nguon-nuoc",
        "document_url": "https://cucthuyloi.gov.vn/Portals/0/2025/D%E1%BB%B1%20b%C3%A1o%20NN/ban-tin-vu-mua-tn.pdf",
        "document_title": "Bản tin dự báo vụ Mùa 2025: Kế hoạch sử dụng nước vùng Tây Nguyên",
        "document_type": "Báo cáo dự báo nguồn nước & KHSDN",
        "publication_date": "2025-05-15",
        "effective_date": "2025-05-15",
        "version_status": "CURRENT",
        "basin": "Sê San, Srêpôk",
        "province": "Kon Tum, Gia Lai, Đắk Lắk, Đắk Nông, Lâm Đồng",
        "reservoir": "Ayun Hạ, Krông Búc Hạ, Ea Kao, Hồ Lắk",
        "estimated_pages": 14,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "core_long",
        "notes": "Báo cáo quy hoạch nguồn nước, dung tích trữ hồ thủy lợi và kế hoạch cấp nước tưới nông nghiệp vụ Mùa Tây Nguyên"
    },
    {
        "source_id": "SRC_CTL_DBNN_NAMTRUNGBO_2025",
        "agency": "Cục Quản lý và Xây dựng công trình thủy lợi (Cục Thủy lợi)",
        "domain": "cucthuyloi.gov.vn",
        "source_category": "Tier A1 — Cục Thủy lợi",
        "page_url": "https://cucthuyloi.gov.vn/du-bao-nguon-nuoc",
        "document_url": "https://cucthuyloi.gov.vn/Portals/0/2025/D%E1%BB%B1%20b%C3%A1o%20NN/ntb_vu-he-thu-21-4.pdf",
        "document_title": "Bản tin dự báo nguồn nước và kế hoạch sử dụng nước vùng Nam Trung Bộ - Vụ Hè Thu 2025",
        "document_type": "Báo cáo dự báo nguồn nước & KHSDN",
        "publication_date": "2025-04-21",
        "effective_date": "2025-04-21",
        "version_status": "CURRENT",
        "basin": "Thu Bồn, Trà Khúc, Kôn - Hà Thanh, Ba, Cái Nha Trang",
        "province": "Đà Nẵng, Quảng Nam, Quảng Ngãi, Bình Định, Phú Yên, Khánh Hòa, Ninh Thuận, Bình Thuận",
        "reservoir": "Định Bình, Núi Một, Nước Trong, Sông Hinh, Sông Sắt",
        "estimated_pages": 21,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "core_long",
        "notes": "Báo cáo 21 trang với đầy đủ bảng dung tích trữ hồ chứa, cân bằng nước, nguy cơ hạn hán Nam Trung Bộ"
    },
    {
        "source_id": "SRC_CTL_CLN_OMON_XANO_2025",
        "agency": "Cục Quản lý và Xây dựng công trình thủy lợi (Cục Thủy lợi)",
        "domain": "cucthuyloi.gov.vn",
        "source_category": "Tier A1 — Cục Thủy lợi",
        "page_url": "https://cucthuyloi.gov.vn/du-bao-nguon-nuoc",
        "document_url": "https://cucthuyloi.gov.vn/Portals/0/2025/D%E1%BB%B1%20b%C3%A1o%20CLN/omxn_tuan_11_2025.pdf",
        "document_title": "Giám sát, dự báo chất lượng nước trong hệ thống thủy lợi Ô Môn Xà No tuần 11 năm 2025",
        "document_type": "Báo cáo giám sát chất lượng nước hệ thống thủy lợi",
        "publication_date": "2025-03-20",
        "effective_date": "2025-03-20",
        "version_status": "CURRENT",
        "basin": "Đồng bằng Sông Cửu Long (Sông Hậu)",
        "province": "Cần Thơ, Hậu Giang, Kiên Giang",
        "reservoir": "Hệ thống thủy lợi Ô Môn Xà No",
        "estimated_pages": 12,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "core_long",
        "notes": "Báo cáo chuyên đề 12 trang giám sát nồng độ DO, COD, TSS, amoni và xâm nhập mặn vùng ĐBSCL"
    },
    {
        "source_id": "SRC_CTL_CLN_NAM_MANG_THIT_2025",
        "agency": "Cục Quản lý và Xây dựng công trình thủy lợi (Cục Thủy lợi)",
        "domain": "cucthuyloi.gov.vn",
        "source_category": "Tier A1 — Cục Thủy lợi",
        "page_url": "https://cucthuyloi.gov.vn/du-bao-nguon-nuoc",
        "document_url": "https://cucthuyloi.gov.vn/Portals/0/2025/D%E1%BB%B1%20b%C3%A1o%20CLN/nmt_tuan_11_2025.pdf",
        "document_title": "Giám sát, dự báo chất lượng nước trong hệ thống thủy lợi Nam Măng Thít tuần 11 năm 2025",
        "document_type": "Báo cáo giám sát chất lượng nước hệ thống thủy lợi",
        "publication_date": "2025-03-20",
        "effective_date": "2025-03-20",
        "version_status": "CURRENT",
        "basin": "Đồng bằng Sông Cửu Long (Sông Tiền - Sông Hậu)",
        "province": "Vĩnh Long, Trà Vinh",
        "reservoir": "Hệ thống thủy lợi Nam Măng Thít",
        "estimated_pages": 14,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "core_long",
        "notes": "Báo cáo chi tiết 14 trang đánh giá chất lượng nước mặt và kiểm soát mặn hệ thống Nam Măng Thít"
    },
    {
        "source_id": "SRC_CTL_CLN_HO_NUI_COC_2025",
        "agency": "Cục Quản lý và Xây dựng công trình thủy lợi (Cục Thủy lợi)",
        "domain": "cucthuyloi.gov.vn",
        "source_category": "Tier A1 — Cục Thủy lợi",
        "page_url": "https://cucthuyloi.gov.vn/du-bao-nguon-nuoc",
        "document_url": "https://cucthuyloi.gov.vn/Portals/0/2025/D%E1%BB%B1%20b%C3%A1o%20CLN/nuicoc_t4th4-2025.pdf",
        "document_title": "Giám sát và dự báo chất lượng nước hồ Núi Cốc - Bản tin dự báo tuần 4 tháng 04/2025",
        "document_type": "Báo cáo an toàn và chất lượng nước hồ chứa",
        "publication_date": "2025-04-25",
        "effective_date": "2025-04-25",
        "version_status": "CURRENT",
        "basin": "Sông Cầu (Lưu vực sông Thái Bình)",
        "province": "Thái Nguyên",
        "reservoir": "Hồ Núi Cốc",
        "estimated_pages": 12,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "core_long",
        "notes": "12 trang bảng số liệu đo đạc, WQI, thông số dinh dưỡng và cảnh báo nguồn nước cấp hồ Núi Cốc"
    },
    {
        "source_id": "SRC_CTL_CLN_HO_DAI_LAI_2025",
        "agency": "Cục Quản lý và Xây dựng công trình thủy lợi (Cục Thủy lợi)",
        "domain": "cucthuyloi.gov.vn",
        "source_category": "Tier A1 — Cục Thủy lợi",
        "page_url": "https://cucthuyloi.gov.vn/du-bao-nguon-nuoc",
        "document_url": "https://cucthuyloi.gov.vn/Portals/0/2025/D%E1%BB%B1%20b%C3%A1o%20CLN/dailai_t4th4-2025.pdf",
        "document_title": "Giám sát và dự báo chất lượng nước hồ Đại Lải - Bản tin dự báo tuần 4 tháng 04/2025",
        "document_type": "Báo cáo an toàn và chất lượng nước hồ chứa",
        "publication_date": "2025-04-25",
        "effective_date": "2025-04-25",
        "version_status": "CURRENT",
        "basin": "Sông Cà Lồ (Lưu vực sông Hồng)",
        "province": "Vĩnh Phúc",
        "reservoir": "Hồ Đại Lải",
        "estimated_pages": 11,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "core_long",
        "notes": "11 trang bảng số liệu WQI, vi sinh vật, phú dưỡng và nguồn nước tưới cấp hồ Đại Lải"
    },
    {
        "source_id": "SRC_CTL_CLN_BAC_HUNG_HAI_2025",
        "agency": "Cục Quản lý và Xây dựng công trình thủy lợi (Cục Thủy lợi)",
        "domain": "cucthuyloi.gov.vn",
        "source_category": "Tier A1 — Cục Thủy lợi",
        "page_url": "https://cucthuyloi.gov.vn/du-bao-nguon-nuoc",
        "document_url": "https://cucthuyloi.gov.vn/Portals/0/2025/D%E1%BB%B1%20b%C3%A1o%20CLN/bhh_tuan4_thang4_22-4-30.pdf",
        "document_title": "Bản tin dự báo chất lượng nước hệ thống thủy lợi Bắc Hưng Hải tuần 4 tháng 4 năm 2025",
        "document_type": "Báo cáo giám sát chất lượng nước hệ thống thủy lợi",
        "publication_date": "2025-04-22",
        "effective_date": "2025-04-22",
        "version_status": "CURRENT",
        "basin": "Sông Hồng - Sông Thái Bình",
        "province": "Hà Nội, Bắc Ninh, Hưng Yên, Hải Dương",
        "reservoir": "Đại thủy nông Bắc Hưng Hải",
        "estimated_pages": 11,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "core_long",
        "notes": "Báo cáo giám sát ô nhiễm và vận hành cống Xuân Quan, Cầu Cất, Kênh Cầu Xe hệ thống Bắc Hưng Hải"
    }
]

# 2. Official Temporal Operational Documents (Daily, Weekly, Monthly Bulletins)
TEMPORAL_SOURCES = [
    {
        "source_id": "SRC_SIWRP_DB_20261006",
        "agency": "Viện Quy hoạch Thủy lợi Miền Nam (SIWRP)",
        "domain": "siwrp.org.vn",
        "source_category": "Tier B — Viện Quy hoạch Thủy lợi",
        "page_url": "https://siwrp.org.vn",
        "document_url": "https://siwrp.org.vn/admin/upload/BantinDBngay-20261006.pdf",
        "document_title": "Bản tin dự báo nguồn nước ĐBSCL ngày 06 tháng 10 năm 2026",
        "document_type": "Bản tin dự báo nguồn nước ngày",
        "publication_date": "2026-10-06",
        "effective_date": "2026-10-06",
        "version_status": "CURRENT",
        "basin": "Đồng bằng Sông Cửu Long",
        "province": "An Giang, Đồng Tháp, Cần Thơ, Vĩnh Long, Tiền Giang, Bến Tre",
        "reservoir": "Hạ lưu sông Mê Công",
        "estimated_pages": 6,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "MEDIUM",
        "track": "temporal",
        "notes": "Bản tin thủy văn và dự báo mực nước lũ, triều cường ngày 06/10/2026"
    },
    {
        "source_id": "SRC_SIWRP_DB_20261005",
        "agency": "Viện Quy hoạch Thủy lợi Miền Nam (SIWRP)",
        "domain": "siwrp.org.vn",
        "source_category": "Tier B — Viện Quy hoạch Thủy lợi",
        "page_url": "https://siwrp.org.vn",
        "document_url": "https://siwrp.org.vn/admin/upload/BantinDBngay-20261005.pdf",
        "document_title": "Bản tin dự báo nguồn nước ĐBSCL ngày 05 tháng 10 năm 2026",
        "document_type": "Bản tin dự báo nguồn nước ngày",
        "publication_date": "2026-10-05",
        "effective_date": "2026-10-05",
        "version_status": "CURRENT",
        "basin": "Đồng bằng Sông Cửu Long",
        "province": "An Giang, Đồng Tháp, Cần Thơ, Vĩnh Long",
        "reservoir": "Hạ lưu sông Mê Công",
        "estimated_pages": 6,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "MEDIUM",
        "track": "temporal",
        "notes": "Bản tin mực nước các trạm Tân Châu, Châu Đốc ngày 05/10/2026"
    },
    {
        "source_id": "SRC_SIWRP_DB_20261004",
        "agency": "Viện Quy hoạch Thủy lợi Miền Nam (SIWRP)",
        "domain": "siwrp.org.vn",
        "source_category": "Tier B — Viện Quy hoạch Thủy lợi",
        "page_url": "https://siwrp.org.vn",
        "document_url": "https://siwrp.org.vn/admin/upload/BantinDBngay-20261004.pdf",
        "document_title": "Bản tin dự báo nguồn nước ĐBSCL ngày 04 tháng 10 năm 2026",
        "document_type": "Bản tin dự báo nguồn nước ngày",
        "publication_date": "2026-10-04",
        "effective_date": "2026-10-04",
        "version_status": "CURRENT",
        "basin": "Đồng bằng Sông Cửu Long",
        "province": "An Giang, Đồng Tháp, Cần Thơ",
        "reservoir": "Hạ lưu sông Mê Công",
        "estimated_pages": 7,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "MEDIUM",
        "track": "temporal",
        "notes": "Bản tin mực nước các trạm chính ngày 04/10/2026"
    },
    {
        "source_id": "SRC_SIWRP_DB_20261003",
        "agency": "Viện Quy hoạch Thủy lợi Miền Nam (SIWRP)",
        "domain": "siwrp.org.vn",
        "source_category": "Tier B — Viện Quy hoạch Thủy lợi",
        "page_url": "https://siwrp.org.vn",
        "document_url": "https://siwrp.org.vn/admin/upload/BantinDBngay-20261003.pdf",
        "document_title": "Bản tin dự báo nguồn nước ĐBSCL ngày 03 tháng 10 năm 2026",
        "document_type": "Bản tin dự báo nguồn nước ngày",
        "publication_date": "2026-10-03",
        "effective_date": "2026-10-03",
        "version_status": "CURRENT",
        "basin": "Đồng bằng Sông Cửu Long",
        "province": "An Giang, Đồng Tháp, Cần Thơ",
        "reservoir": "Hạ lưu sông Mê Công",
        "estimated_pages": 6,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "MEDIUM",
        "track": "temporal",
        "notes": "Bản tin mực nước ngày 03/10/2026"
    },
    {
        "source_id": "SRC_SIWRP_DB_20261001",
        "agency": "Viện Quy hoạch Thủy lợi Miền Nam (SIWRP)",
        "domain": "siwrp.org.vn",
        "source_category": "Tier B — Viện Quy hoạch Thủy lợi",
        "page_url": "https://siwrp.org.vn",
        "document_url": "https://siwrp.org.vn/admin/upload/BantinDBngay-20261001.pdf",
        "document_title": "Bản tin dự báo nguồn nước ĐBSCL ngày 01 tháng 10 năm 2026",
        "document_type": "Bản tin dự báo nguồn nước ngày",
        "publication_date": "2026-10-01",
        "effective_date": "2026-10-01",
        "version_status": "CURRENT",
        "basin": "Đồng bằng Sông Cửu Long",
        "province": "An Giang, Đồng Tháp",
        "reservoir": "Hạ lưu sông Mê Công",
        "estimated_pages": 6,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "MEDIUM",
        "track": "temporal",
        "notes": "Bản tin mực nước đầu tháng 10/2026"
    },
    {
        "source_id": "SRC_SIWRP_DAUTIENG_20261001",
        "agency": "Viện Quy hoạch Thủy lợi Miền Nam (SIWRP)",
        "domain": "siwrp.org.vn",
        "source_category": "Tier B — Viện Quy hoạch Thủy lợi",
        "page_url": "https://siwrp.org.vn",
        "document_url": "https://siwrp.org.vn/admin/upload/10_01_DBL_HoDauTieng_SIWRP.pdf",
        "document_title": "Dự báo lũ hồ Dầu Tiếng: Báo cáo tuần 01 tháng 10 năm 2026",
        "document_type": "Bản tin dự báo lũ và vận hành hồ chứa",
        "publication_date": "2026-10-01",
        "effective_date": "2026-10-01",
        "version_status": "CURRENT",
        "basin": "Sông Sài Gòn (Lưu vực sông Đồng Nai)",
        "province": "Tây Ninh, Bình Dương, TP Hồ Chí Minh",
        "reservoir": "Hồ Dầu Tiếng",
        "estimated_pages": 8,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "temporal",
        "notes": "Dự báo lưu lượng về hồ, mực nước và kiến nghị vận hành xả tràn hồ Dầu Tiếng"
    },
    {
        "source_id": "SRC_SIWRP_TUAN14_20261001",
        "agency": "Viện Quy hoạch Thủy lợi Miền Nam (SIWRP)",
        "domain": "siwrp.org.vn",
        "source_category": "Tier B — Viện Quy hoạch Thủy lợi",
        "page_url": "https://siwrp.org.vn",
        "document_url": "https://siwrp.org.vn/admin/upload/14.BANTIN-TUAN14_DBNN%2020261001.pdf",
        "document_title": "Bản tin tuần 14: Diễn biến nguồn nước vùng ĐBSCL đến ngày 30/9/2026, dự báo nguồn nước từ ngày 01/10 – 10/10/2026",
        "document_type": "Bản tin dự báo nguồn nước tuần",
        "publication_date": "2026-10-01",
        "effective_date": "2026-10-01",
        "version_status": "CURRENT",
        "basin": "Đồng bằng Sông Cửu Long",
        "province": "Toàn vùng ĐBSCL (13 tỉnh thành)",
        "reservoir": "Hạ lưu sông Mê Công, Biển Hồ",
        "estimated_pages": 12,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "temporal",
        "notes": "Bản tin tuần chi tiết về dòng chảy thượng nguồn Kratie, Biển Hồ và xâm nhập mặn"
    },
    {
        "source_id": "SRC_SIWRP_THANG10_20260930",
        "agency": "Viện Quy hoạch Thủy lợi Miền Nam (SIWRP)",
        "domain": "siwrp.org.vn",
        "source_category": "Tier B — Viện Quy hoạch Thủy lợi",
        "page_url": "https://siwrp.org.vn",
        "document_url": "https://siwrp.org.vn/admin/upload/04.BANTIN-DBNN_THANG10%2020260930.pdf",
        "document_title": "Bản tin dự báo tháng 10: Dự báo nguồn nước vùng ĐBSCL năm 2026",
        "document_type": "Bản tin dự báo nguồn nước tháng",
        "publication_date": "2026-09-30",
        "effective_date": "2026-09-30",
        "version_status": "CURRENT",
        "basin": "Đồng bằng Sông Cửu Long",
        "province": "Toàn vùng ĐBSCL",
        "reservoir": "Hạ lưu sông Mê Công",
        "estimated_pages": 15,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "temporal",
        "notes": "Báo cáo tổng kết tháng 9 và dự báo diễn biến thủy văn, đỉnh lũ tháng 10 vùng ĐBSCL"
    },
    {
        "source_id": "SRC_CTL_BT_TUAN_BAC_TRUNG_BO_20250424",
        "agency": "Cục Quản lý và Xây dựng công trình thủy lợi (Cục Thủy lợi)",
        "domain": "cucthuyloi.gov.vn",
        "source_category": "Tier A1 — Cục Thủy lợi",
        "page_url": "https://cucthuyloi.gov.vn/du-bao-nguon-nuoc",
        "document_url": "https://cucthuyloi.gov.vn/Portals/0/2025/D%E1%BB%B1%20b%C3%A1o%20NN/btb-tuan-18-24-4.pdf",
        "document_title": "Bản tin Tuần 18-24.4.2025 DBNN và xây dựng KHSDN Bắc Trung Bộ 2025",
        "document_type": "Bản tin dự báo nguồn nước tuần",
        "publication_date": "2025-04-24",
        "effective_date": "2025-04-24",
        "version_status": "CURRENT",
        "basin": "Sông Mã, Sông Cả, Sông Gianh, Sông Hương",
        "province": "Thanh Hóa, Nghệ An, Hà Tĩnh, Quảng Bình, Quảng Trị, Thừa Thiên Huế",
        "reservoir": "Cửa Đạt, Bản Vẽ, Ngàn Trươi, Tả Trạch",
        "estimated_pages": 8,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "temporal",
        "notes": "Bản tin nguồn nước tuần phục vụ kiểm soát hạn hán và cấp nước tưới Bắc Trung Bộ"
    },
    {
        "source_id": "SRC_CTL_BT_TUAN_TAY_NGUYEN_20250417",
        "agency": "Cục Quản lý và Xây dựng công trình thủy lợi (Cục Thủy lợi)",
        "domain": "cucthuyloi.gov.vn",
        "source_category": "Tier A1 — Cục Thủy lợi",
        "page_url": "https://cucthuyloi.gov.vn/du-bao-nguon-nuoc",
        "document_url": "https://cucthuyloi.gov.vn/Portals/0/2025/D%E1%BB%B1%20b%C3%A1o%20NN/tn_bt-tuan-11-4-2025.pdf",
        "document_title": "Bản tin DB nguồn nước và KHSDN vùng Tây Nguyên - Tuần 11/4/2025 ÷ 17/4/2025",
        "document_type": "Bản tin dự báo nguồn nước tuần",
        "publication_date": "2025-04-17",
        "effective_date": "2025-04-17",
        "version_status": "CURRENT",
        "basin": "Sê San, Srêpôk",
        "province": "Gia Lai, Đắk Lắk, Lâm Đồng, Đắk Nông",
        "reservoir": "Hồ chứa thủy lợi Tây Nguyên",
        "estimated_pages": 8,
        "file_type": "PDF",
        "public_access": True,
        "redistribution_status": "CLEAR",
        "priority": "HIGH",
        "track": "temporal",
        "notes": "Theo dõi dung tích trữ hồ chứa nhỏ và vừa vùng Tây Nguyên trong cao điểm mùa khô"
    }
]

def generate_doc_id(source_agency, pub_year, content_bytes):
    h = hashlib.sha256(content_bytes).hexdigest()[:8]
    agency_code = "CP" if "Chính phủ" in source_agency else ("CTL" if "Thủy lợi" in source_agency else "SIWRP")
    return f"IRR_{agency_code}_{pub_year}_{h}"

def main():
    print("Starting VietIrrDocBench Acquisition & Provenance Pipeline...")
    all_sources = CORE_SOURCES + TEMPORAL_SOURCES
    
    # 1. Write data/manifests/source_catalog.csv
    catalog_path = Path("data/manifests/source_catalog.csv")
    catalog_fields = [
        "source_id", "agency", "domain", "source_category", "page_url", "document_url",
        "document_title", "document_type", "publication_date", "basin", "province",
        "reservoir", "estimated_pages", "file_type", "public_access", "redistribution_status",
        "priority", "notes"
    ]
    with open(catalog_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=catalog_fields)
        writer.writeheader()
        for s in all_sources:
            row = {k: s.get(k, "") for k in catalog_fields}
            writer.writerow(row)
    print(f"Catalog saved to {catalog_path} with {len(all_sources)} records.")

    # 2. Download and verify each document
    download_manifest_path = Path("data/manifests/download_manifest.jsonl")
    manifest_records = []
    
    for item in all_sources:
        track = item["track"]
        target_dir = Path("data/raw/core_long") if track == "core_long" else Path("data/raw/temporal")
        url = item["document_url"]
        orig_fn = Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).name
        dest_file = target_dir / orig_fn
        
        print(f"\nFetching [{item['source_id']}]: {orig_fn} ...")
        http_status = None
        content = None
        
        # Check cache or download
        if dest_file.exists() and dest_file.stat().st_size > 0:
            print(f"  Using local cache: {dest_file}")
            with open(dest_file, "rb") as f:
                content = f.read()
            http_status = 200
        else:
            try:
                r = requests.get(url, headers=HEADERS, verify=False, timeout=25)
                http_status = r.status_code
                if r.status_code == 200:
                    content = r.content
                    with open(dest_file, "wb") as f:
                        f.write(content)
                    print(f"  Downloaded {len(content)} bytes -> {dest_file}")
                else:
                    print(f"  HTTP error: {r.status_code}")
            except Exception as e:
                print(f"  Download exception: {e}")
                http_status = 500

        if content:
            sha256 = hashlib.sha256(content).hexdigest()
            pub_year = item["publication_date"].split("-")[0]
            doc_id = generate_doc_id(item["agency"], pub_year, content)
            
            # Verify actual page count
            try:
                doc = fitz.open(stream=content, filetype="pdf")
                actual_pages = len(doc)
            except Exception:
                actual_pages = 0
            
            rec = {
                "doc_id": doc_id,
                "source_id": item["source_id"],
                "original_filename": orig_fn,
                "local_path": str(dest_file).replace("\\", "/"),
                "source_url": url,
                "landing_page_url": item["page_url"],
                "agency": item["agency"],
                "document_title": item["document_title"],
                "document_type": item["document_type"],
                "basin": item["basin"],
                "province": item["province"],
                "reservoir": item["reservoir"],
                "track": track,
                "download_timestamp": datetime.now().isoformat(),
                "sha256": sha256,
                "bytes": len(content),
                "mime_type": "application/pdf",
                "http_status": http_status,
                "actual_pages": actual_pages,
                "version_status": item.get("version_status", "UNKNOWN")
            }
            manifest_records.append(rec)
    
    with open(download_manifest_path, "w", encoding="utf-8") as f:
        for r in manifest_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nDownload manifest saved to {download_manifest_path} ({len(manifest_records)} records).")

if __name__ == "__main__":
    main()
