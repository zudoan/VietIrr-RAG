import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests, urllib3, urllib.parse, fitz
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0'}
url = 'https://cucthuyloi.gov.vn/DesktopModules/cmsview/api/AdminForm/list'

for cat_id, cat_name in [(125, 'Bắc Bộ'), (126, 'Trung Bộ'), (127, 'Tây Nguyên - Đông Nam Bộ'), (128, 'ĐBSCL')]:
    print(f"\n=== CATEGORY {cat_id}: {cat_name} ===")
    params = {'PortalId': 0, 'AdminFormCatId': cat_id, 'Keyword': '', 'pageindex': 1, 'pagesize': 3}
    r = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
    data = r.json()
    for item in data.get('ListData', []):
        name = item.get('AdminFormName')
        fn = item.get('AdminFormFilename')
        print(f"Title: {name}")
        print(f"Path: {fn}")
        if fn and fn.endswith('.pdf'):
            try:
                furl = 'https://cucthuyloi.gov.vn' + urllib.parse.quote(fn)
                res = requests.get(furl, headers=headers, verify=False, timeout=10)
                if res.status_code == 200:
                    doc = fitz.open(stream=res.content, filetype='pdf')
                    print(f"  -> Downloaded OK, size={len(res.content)} bytes, pages={len(doc)}")
            except Exception as e:
                print(f"  -> Error checking PDF: {e}")
