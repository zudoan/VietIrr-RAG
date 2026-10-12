import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests, urllib3
from bs4 import BeautifulSoup
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0'}
url = 'https://vanban.chinhphu.vn/he-thong-van-ban?searchkeyword=quy+tr%C3%ACnh+v%E1%BA%ADn+h%C3%A0nh+li%C3%AAn+h%E1%BB%93+ch%E1%BB%A9a'
r = requests.get(url, headers=headers, verify=False, timeout=10)
soup = BeautifulSoup(r.text, 'html.parser')

print(f"Status: {r.status_code}")
results = []
for a in soup.find_all('a', href=True):
    href = a['href']
    text = a.get_text(strip=True)
    if 'quy trình' in text.lower() or 'liên hồ' in text.lower() or 'hồ chứa' in text.lower() or 'quyết định' in text.lower():
        results.append((text, href))

print(f"Found {len(results)} matching links:")
for t, h in results[:20]:
    print(f"  {t} -> {h}")
