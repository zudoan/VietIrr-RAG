import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

test_decisions = [
    ("740", "2019/06/740.signed.pdf", "Sông Hồng (2019)"),
    ("922", "2025/5/922-ttg.signed.pdf", "Sửa đổi Sông Hồng (2025)"),
    ("1605", "2019/11/1605.signed.pdf", "Sông Cả"),
    ("1606", "2019/11/1606.signed.pdf", "Sông Hương"),
    ("1182", "2019/09/1182.signed.pdf", "Sông Sê San"),
    ("1201", "2019/09/1201.signed.pdf", "Sông Srêpôk"),
    ("1865", "2019/12/1865.signed.pdf", "Sông Vu Gia - Thu Bồn"),
    ("1895", "2019/12/1895.signed.pdf", "Sông Đồng Nai"),
    ("214", "2018/02/214.signed.pdf", "Sông Mã"),
    ("878", "2018/07/878.signed.pdf", "Sông Ba"),
    ("1836", "2018/12/1836.signed.pdf", "Sông Trà Khúc"),
    ("1841", "2018/12/1841.signed.pdf", "Sông Kôn - Hà Thanh"),
    ("1500", "2020/10/1500.signed.pdf", "Sửa đổi Sông Mã"),
]

base = "https://datafiles.chinhphu.vn/cpp/files/vbpq/"
for qd, path, desc in test_decisions:
    url = base + path
    try:
        r = requests.head(url, headers=headers, timeout=8)
        print(f"[{qd}] {desc:28s} -> {r.status_code} ({r.headers.get('content-length')} bytes)")
    except Exception as e:
        print(f"[{qd}] {desc:28s} -> ERROR: {e}")
