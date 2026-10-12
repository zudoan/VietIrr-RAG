import requests
import re
import urllib3
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0'}
for s in ['AdminWaterResource/AdminWaterService.js', 'Document/DocumentService.js', 'News/ContentService.js']:
    url = f'https://cucthuyloi.gov.vn/DesktopModules/CmsView/scripts/{s}'
    r = requests.get(url, headers=headers, verify=False, timeout=10)
    print(f"=== {s} ({len(r.text)} bytes) ===")
    matches = set(re.findall(r'/[A-Za-z0-9_/\.-]+', r.text))
    for m in sorted(matches):
        if any(k in m.lower() for k in ['api', 'desktopmodules', 'service', 'get']):
            print("  ", m)
