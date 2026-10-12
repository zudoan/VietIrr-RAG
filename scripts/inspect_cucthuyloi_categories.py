import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests, urllib3, json
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0'}
url = 'https://cucthuyloi.gov.vn/DesktopModules/cmsview/api/AdminFormGroup/getbyid?Id=120'
r = requests.get(url, headers=headers, verify=False)
data = r.json()
print("Group name:", data.get('DocumentFieldName'))
for child in data.get('Childrent', []):
    print(f"  Category {child.get('Id')}: {child.get('DocumentFieldName')}")
    for sub in child.get('Childrent', []):
        print(f"    Sub-category {sub.get('Id')}: {sub.get('DocumentFieldName')}")
