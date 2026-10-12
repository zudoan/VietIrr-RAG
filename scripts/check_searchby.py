import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests, urllib3
urllib3.disable_warnings()

r = requests.get('https://cucthuyloi.gov.vn/du-bao-nguon-nuoc', verify=False)
idx = r.text.find('app.controller("myCntrl1436"')
print(r.text[idx:idx+2500])
