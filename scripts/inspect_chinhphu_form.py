import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests, urllib3
from bs4 import BeautifulSoup
urllib3.disable_warnings()

headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get('https://vanban.chinhphu.vn/default.aspx?pageid=27160', headers=headers, verify=False, timeout=10)
soup = BeautifulSoup(r.text, 'html.parser')
form = soup.find('form')
if form:
    print("Action:", form.get('action'))
    inputs = form.find_all(['input', 'select'])
    for inp in inputs:
        print(f"  {inp.get('name')} ({inp.get('type')}): {inp.get('value')}")
