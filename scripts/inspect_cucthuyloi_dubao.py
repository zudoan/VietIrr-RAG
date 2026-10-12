import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests, urllib3
from bs4 import BeautifulSoup
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get('https://cucthuyloi.gov.vn/du-bao-nguon-nuoc', headers=headers, verify=False, timeout=10)
soup = BeautifulSoup(r.text, 'html.parser')

print("Title:", soup.title.string if soup.title else "No title")
for a in soup.find_all('a', href=True):
    text = a.get_text(strip=True)
    href = a['href']
    if any(k in text.lower() or k in href.lower() for k in ['bản tin', 'dự báo', 'nguồn nước', 'hồ', 'hạn', 'pdf', 'upload', 'file', 'download']):
        print(f"[{text}] -> {href}")

# Check any ng-controller or ng-init
for elem in soup.find_all(attrs={'ng-controller': True}):
    print("ng-controller:", elem.get('ng-controller'))
for elem in soup.find_all(attrs={'ng-init': True}):
    print("ng-init:", elem.get('ng-init'))
