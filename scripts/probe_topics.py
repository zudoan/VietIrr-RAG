import requests
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

sites = {
    'siwrp': 'http://www.siwrp.org.vn',
    'nchmf': 'https://nchmf.gov.vn',
    'pctt': 'http://phongchongthientai.mard.gov.vn',
    'iwrp': 'https://iwrp.gov.vn'
}

for name, url in sites.items():
    try:
        r = requests.get(url, headers=headers, verify=False, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        # find pdf links
        pdf_links = [a['href'] for a in soup.find_all('a', href=True) if '.pdf' in a['href'].lower()]
        # find sub-category links
        nav_links = [a['href'] for a in soup.find_all('a', href=True) if any(k in a['href'].lower() for k in ['du-bao', 'nguon-nuoc', 'bao-cao', 'tin-tuc', 'van-hanh', 'thuy-van', 'tai-nguyen-nuoc'])]
        print(f"[{name}] Total links: {len(soup.find_all('a'))}, PDF links: {len(pdf_links)}, Topic links: {len(nav_links)}")
        if pdf_links:
            print(f"  Sample PDFs: {pdf_links[:3]}")
        if nav_links:
            print(f"  Sample Topic links: {nav_links[:3]}")
    except Exception as e:
        print(f"[{name}] error: {e}")
