import requests
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# 1. Probe vbpl search
print("--- PROBING VBPL ---")
vbpl_url = "https://vbpl.vn/pages/vbpq-timkiem.aspx?Keyword=quy+tr%C3%ACnh+v%E1%BA%ADn+h%C3%A0nh+li%C3%AAn+h%E1%BB%93+ch%E1%BB%A9a"
try:
    r = requests.get(vbpl_url, headers=headers, verify=False, timeout=10)
    print("VBPL status:", r.status_code)
    soup = BeautifulSoup(r.text, 'html.parser')
    items = soup.select('.item, .vbpq-item, ul.listLaw li, .results li')
    print("VBPL items found:", len(items))
    if not items:
        # check links
        doc_links = [a['href'] for a in soup.find_all('a', href=True) if 'vanban' in a['href'] or 'vbpq' in a['href']]
        print("VBPL doc links:", len(doc_links), doc_links[:5])
except Exception as e:
    print("VBPL error:", e)

# 2. Probe vanban.chinhphu.vn search
print("--- PROBING CHINHPHU ---")
cp_url = "https://vanban.chinhphu.vn/default.aspx?pageid=27160&dataid=0"
try:
    r = requests.get(cp_url, headers=headers, verify=False, timeout=10)
    print("Chinhphu status:", r.status_code)
    soup = BeautifulSoup(r.text, 'html.parser')
    forms = soup.find_all('form')
    print("Chinhphu forms:", len(forms))
except Exception as e:
    print("Chinhphu error:", e)

# 3. Probe cucthuyloi.gov.vn
print("--- PROBING CUCTHUYLOI ---")
try:
    r = requests.get("https://cucthuyloi.gov.vn/du-bao-nguon-nuoc", headers=headers, verify=False, timeout=10)
    print("cucthuyloi du-bao-nguon-nuoc status:", r.status_code)
    # let's see any API or ajax call in page content
    import re
    matches = re.findall(r'/api/[^\s"\'<>]+', r.text)
    print("cucthuyloi APIs:", set(matches))
except Exception as e:
    print("Cucthuyloi error:", e)
