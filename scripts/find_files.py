import sys
sys.stdout.reconfigure(encoding='utf-8')
import re

fn = r'C:\Users\AD\.gemini\antigravity-ide\brain\17e2c228-5aa8-4ba7-8956-867a7a229efe\.system_generated\steps\171\content.md'
with open(fn, 'r', encoding='utf-8') as f:
    text = f.read()

matches = re.findall(r'href=[\'"]([^\'"]+)', text)
for m in matches:
    if any(ext in m.lower() for ext in ['.pdf', '.doc', '.docx', 'download', 'file', 'attach', 'datafile']):
        print("Attachment link:", m)

# Also check table of content / text length
print("Total page text length:", len(text))
idx = text.find('QUY TRÌNH')
if idx != -1:
    print("Found 'QUY TRÌNH' in page text at char", idx)
    print(text[idx:idx+500])
