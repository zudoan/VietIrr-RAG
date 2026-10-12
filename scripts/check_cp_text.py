import sys
sys.stdout.reconfigure(encoding='utf-8')
import re
from bs4 import BeautifulSoup

fn = r'C:\Users\AD\.gemini\antigravity-ide\brain\17e2c228-5aa8-4ba7-8956-867a7a229efe\.system_generated\steps\171\content.md'
with open(fn, 'r', encoding='utf-8') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')
# find doc content div
content_div = soup.select_one('.content, #content, .toanvan, .doc-content, .detail-content, .content-doc')
if not content_div:
    # Look for div containing 'QUYẾT ĐỊNH'
    for div in soup.find_all('div'):
        if 'QUYẾT ĐỊNH' in div.get_text() and len(div.get_text()) > 2000:
            content_div = div
            break

if content_div:
    text = content_div.get_text(separator="\n", strip=True)
    print(f"Found content div! Text length: {len(text)} characters.")
    print("First 500 chars:\n", text[:500])
else:
    print("Could not find dedicated div, searching full text...")
    text = soup.get_text(separator="\n", strip=True)
    print(f"Full page text length: {len(text)}")
    for line in text.split("\n"):
        if any(k in line for k in ["Điều 1", "Điều 2", "Hồ Sơn La", "Hòa Bình"]):
            print("  Sample line:", line[:80])
