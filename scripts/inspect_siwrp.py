import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests
from bs4 import BeautifulSoup
import re

headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get('https://siwrp.org.vn/tin-tuc/thong-tin-du-bao_22.html', headers=headers, timeout=10)
soup = BeautifulSoup(r.text, 'html.parser')
links = []
for a in soup.find_all('a', href=True):
    if '/tin-tuc/' in a['href'] and '_22.html' not in a['href']:
        links.append((a.get_text(strip=True), a['href']))

print(f"Found {len(links)} article links in thong-tin-du-bao_22.html:")
for t, h in links[:15]:
    print(f"  {t} -> {h}")
