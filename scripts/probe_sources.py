import requests
import urllib3
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

urls = {
    'vbpl': 'https://vbpl.vn',
    'vanban_chinhphu': 'https://vanban.chinhphu.vn',
    'cucthuyloi': 'https://cucthuyloi.gov.vn',
    'nchmf': 'https://nchmf.gov.vn',
    'pctt': 'http://phongchongthientai.mard.gov.vn',
    'siwrp': 'http://www.siwrp.org.vn',
    'iwrp': 'https://iwrp.gov.vn'
}

for name, url in urls.items():
    try:
        r = requests.get(url, headers=headers, timeout=8, verify=False)
        print(f"[{name}] -> {r.status_code}, len={len(r.text)}")
    except Exception as e:
        print(f"[{name}] -> FAIL: {e}")
