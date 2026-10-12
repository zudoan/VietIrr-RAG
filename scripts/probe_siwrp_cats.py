import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests
from bs4 import BeautifulSoup
import re

headers = {'User-Agent': 'Mozilla/5.0'}

# Let's inspect news pages or category pages on siwrp
# We saw news links like: /news/csdl-quy-hoach_832.html, /tin-tuc/...
# Let's see category pages
category_urls = [
    'https://siwrp.org.vn/tin-tuc/tin-chuyen-nganh_21.html',
    'https://siwrp.org.vn/tin-tuc/thong-tin-du-bao_22.html',
    'https://siwrp.org.vn/tin-tuc/du-bao-nguon-nuoc_18.html',
    'https://siwrp.org.vn/tin-tuc/du-an-nhiem-vu_23.html',
]

for curl in category_urls:
    try:
        r = requests.get(curl, headers=headers, timeout=10)
        print(f"{curl} -> {r.status_code}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            pdfs = [a['href'] for a in soup.find_all('a', href=True) if '.pdf' in a['href'].lower()]
            print(f"  PDFs: {len(pdfs)}")
    except Exception as e:
        print(f"{curl} -> err: {e}")
