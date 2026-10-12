import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests, urllib3, re
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get('https://cucthuyloi.gov.vn/du-bao-nguon-nuoc', headers=headers, verify=False, timeout=10)
for m in re.finditer(r'(function\s+myCntrl410|myCntrl410\s*=|app\.controller\(["\']myCntrl410[\'"])[\s\S]{0,1500}', r.text):
    print("MATCH 410:")
    print(m.group(0))

for m in re.finditer(r'(function\s+myCntrl1436|myCntrl1436\s*=|app\.controller\(["\']myCntrl1436[\'"])[\s\S]{0,1500}', r.text):
    print("MATCH 1436:")
    print(m.group(0))
