import requests
from bs4 import BeautifulSoup
import re
import json

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# Let's inspect siwrp.org.vn upload directory or listing pages
url = 'https://siwrp.org.vn/du-bao-nguon-nuoc_c18.html'
try:
    r = requests.get(url, headers=headers, timeout=10)
    print("siwrp c18 status:", r.status_code)
    soup = BeautifulSoup(r.text, 'html.parser')
    news_items = soup.find_all('a', href=True)
    article_links = [a['href'] for a in news_items if '_18.' in a['href'] or 'du-bao' in a['href']]
    print("siwrp articles found:", len(article_links))
    for a in article_links[:10]:
        print(" ", a)
except Exception as e:
    print("siwrp err:", e)
