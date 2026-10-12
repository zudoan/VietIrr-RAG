import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get('http://www.siwrp.org.vn', headers=headers, timeout=10)
soup = BeautifulSoup(r.text, 'html.parser')
for a in soup.find_all('a', href=True):
    text = a.get_text(strip=True)
    href = a['href']
    if any(k in text.lower() or k in href.lower() for k in ['bản tin', 'dự báo', 'nguồn nước', 'hồ', 'hạn', 'mặn', 'upload', '.pdf', 'bao-cao', 'quy-hoach']):
        print(f"[{text}] -> {href}")
