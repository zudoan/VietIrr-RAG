import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests, fitz, urllib.parse, urllib3
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0'}
url = 'https://cucthuyloi.gov.vn/DesktopModules/cmsview/api/AdminForm/list'

# Check a sample across recent items
params = {'PortalId': 0, 'AdminFormCatId': 120, 'Keyword': '', 'pageindex': 1, 'pagesize': 25}
r = requests.get(url, params=params, headers=headers, verify=False)
data = r.json()

print(f"{'Title':<45} | {'Pages':<5} | {'Chars':<6} | {'Status'}")
print("-" * 75)
for item in data.get('ListData', []):
    name = item.get('AdminFormName', '')[:42]
    fn = item.get('AdminFormFilename', '')
    if not fn or not fn.endswith('.pdf'):
        continue
    try:
        furl = 'https://cucthuyloi.gov.vn' + urllib.parse.quote(fn)
        res = requests.get(furl, headers=headers, verify=False, timeout=8)
        if res.status_code == 200:
            doc = fitz.open(stream=res.content, filetype='pdf')
            total_chars = sum(len(p.get_text().strip()) for p in doc)
            pages = len(doc)
            ext_ratio = sum(1 for p in doc if len(p.get_text().strip()) > 50) / max(1, pages)
            status = "A (Digital)" if ext_ratio > 0.8 else ("B (Usable)" if ext_ratio > 0.3 else "C (Scanned)")
            print(f"{name:<45} | {pages:<5} | {total_chars:<6} | {status}")
    except Exception as e:
        print(f"{name:<45} | ERR: {e}")
