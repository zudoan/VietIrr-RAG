import sys
sys.stdout.reconfigure(encoding='utf-8')
import re

fn = r'C:\Users\AD\.gemini\antigravity-ide\brain\17e2c228-5aa8-4ba7-8956-867a7a229efe\.system_generated\steps\183\content.md'
with open(fn, 'r', encoding='utf-8') as f:
    text = f.read()

for m in re.finditer(r'https://datafiles\.chinhphu\.vn/cpp/files/vbpq/[^\s"\'<>]+', text):
    print("PDF:", m.group(0))
