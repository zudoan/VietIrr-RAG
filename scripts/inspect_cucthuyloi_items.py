import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests, urllib3, json
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0'}
url = 'https://cucthuyloi.gov.vn/DesktopModules/cmsview/api/AdminForm/list'
params = {
    'PortalId': 0,
    'AdminFormCatId': 120,
    'Keyword': '',
    'pageindex': 1,
    'pagesize': 5
}
r = requests.get(url, params=params, headers=headers, verify=False)
data = r.json()
print(f"TotalCount: {data.get('TotalCount')}")
for i, item in enumerate(data.get('ListData', [])):
    print(f"\n--- Item {i+1} ---")
    for k, v in item.items():
        if v:
            print(f"  {k}: {str(v)[:100]}")
