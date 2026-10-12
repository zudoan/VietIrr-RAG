import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests
from bs4 import BeautifulSoup
import re

headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get('https://cucthuyloi.gov.vn', headers=headers, verify=False, timeout=10)
soup = BeautifulSoup(r.text, 'html.parser')

scripts = soup.find_all('script')
print(f"Total script tags on cucthuyloi: {len(scripts)}")
for s in scripts:
    if s.get('src'):
        print("Script src:", s['src'])
    else:
        text = s.string or ""
        apis = re.findall(r'https?://[^\s"\'<>]+|/[a-zA-Z0-9_\-\./]+', text)
        for api in apis:
            if any(k in api.lower() for k in ['api', 'water', 'du-bao', 'service', 'json']):
                print("Inline api candidate:", api)
