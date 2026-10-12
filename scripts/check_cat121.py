import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests, urllib3, json
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0'}
url = 'https://cucthuyloi.gov.vn/DesktopModules/cmsview/api/AdminForm/list'

# Check Cat 121 (Forecast and water use plan) across all pages
params = {
    'PortalId': 0,
    'AdminFormCatId': 121,
    'Keyword': '',
    'pageindex': 1,
    'pagesize': 20
}
r = requests.get(url, params=params, headers=headers, verify=False)
data = r.json()
print("Cat 121 total count:", data.get('TotalCount'))
for item in data.get('ListData', []):
    print(f"[{item.get('Id')}] ({item.get('PublishDate')}) {item.get('AdminFormName')} -> {item.get('AdminFormFilename')}")
