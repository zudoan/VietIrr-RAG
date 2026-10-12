import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests, urllib3
from bs4 import BeautifulSoup
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

# Search on vanban.chinhphu.vn
# URL pattern for vanban.chinhphu.vn search:
# https://vanban.chinhphu.vn/default.aspx?pageid=27160
# Let's search by so_ky_hieu or keyword
search_url = "https://vanban.chinhphu.vn/default.aspx?pageid=27160"
data = {
    'searchKeyword': 'quy trình vận hành liên hồ chứa',
    'searchType': 1
}

r = requests.post(search_url, data=data, headers=headers, verify=False, timeout=10)
print(f"Status: {r.status_code}, len={len(r.text)}")
soup = BeautifulSoup(r.text, 'html.parser')
links = [a for a in soup.find_all('a', href=True) if 'pageid=27160' in a['href'] or 'docid' in a['href'].lower() or 'van-ban' in a['href']]
print(f"Found {len(links)} links")
for a in links[:10]:
    print(" ", a.get_text(strip=True)[:50], "->", a['href'])
