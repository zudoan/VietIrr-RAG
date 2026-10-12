import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests, urllib3
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0'}
for gid in range(1, 150):
    url = f'https://cucthuyloi.gov.vn/DesktopModules/cmsview/api/AdminFormGroup/getbyid?Id={gid}'
    try:
        r = requests.get(url, headers=headers, verify=False, timeout=3)
        if r.status_code == 200 and r.text and r.text != 'null':
            data = r.json()
            if data and data.get('DocumentFieldName'):
                print(f"Group {gid}: {data.get('DocumentFieldName')}")
    except:
        pass
