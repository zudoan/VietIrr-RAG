import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests

headers = {'User-Agent': 'Mozilla/5.0'}
base = "https://datafiles.chinhphu.vn/cpp/files/vbpq/"

for qd in ["1182", "1836", "1841"]:
    found = False
    for y in [2018, 2019, 2020]:
        for m in range(1, 13):
            for variant in [f"{y}/{m:02d}/{qd}.signed.pdf", f"{y}/{m}/{qd}.signed.pdf", f"{y}/{m:02d}/{qd}-ttg.signed.pdf", f"{y}/{m}/{qd}-ttg.signed.pdf"]:
                url = base + variant
                try:
                    r = requests.head(url, headers=headers, timeout=2)
                    if r.status_code == 200:
                        print(f"FOUND {qd}: {url} ({r.headers.get('content-length')} bytes)")
                        found = True
                        break
                except:
                    pass
            if found:
                break
        if found:
            break
