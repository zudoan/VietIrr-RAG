import sys
sys.stdout.reconfigure(encoding='utf-8')
import json
from pathlib import Path

table_files = list(Path('data/tables').glob('*.jsonl'))
print(f'Total table files: {len(table_files)}')

sample_tabs = []
for tf in table_files:
    with open(tf, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                tab = json.loads(line)
                if len(tab.get('header', [])) >= 3 and len(tab.get('rows', [])) >= 2:
                    sample_tabs.append(tab)
                    if len(sample_tabs) >= 8:
                        break
    if len(sample_tabs) >= 8:
        break

for i, tab in enumerate(sample_tabs):
    print(f"\n=== Table {i+1} ({tab['table_id']}, Page {tab['page_number']}) ===")
    print("Header:", tab['header'])
    for r in tab['rows'][:3]:
        print("  Row:", r)
