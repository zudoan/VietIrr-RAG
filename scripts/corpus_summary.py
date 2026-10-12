import sys
sys.stdout.reconfigure(encoding='utf-8')
import json
from pathlib import Path
from collections import Counter

manifest_file = Path("data/manifests/download_manifest.jsonl")
records = []
with open(manifest_file, "r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            records.append(json.loads(line))

print(f"Total downloaded records: {len(records)}")
qualities = Counter(r.get("quality_label", "UNKNOWN") for r in records)
acceptance = Counter(r.get("acceptance_status", "UNKNOWN") for r in records)
tracks = Counter(r.get("track", "UNKNOWN") for r in records)
agencies = Counter(r.get("agency", "UNKNOWN") for r in records)
basins = Counter(r.get("basin", "UNKNOWN") for r in records)

print("Quality distribution:", dict(qualities))
print("Acceptance distribution:", dict(acceptance))
print("Track distribution:", dict(tracks))
print("Agency distribution:", dict(agencies))

# Count pages, characters, table candidates among ACCEPTED documents
accepted_docs = [r for r in records if r.get("acceptance_status") == "ACCEPTED"]
total_pages = sum(r.get("page_count", 0) for r in accepted_docs)
total_chars = sum(r.get("character_count", 0) for r in accepted_docs)
total_tabs = sum(r.get("table_candidate_count", 0) for r in accepted_docs)

print(f"\nACCEPTED Benchmark Corpus:")
print(f"  Count: {len(accepted_docs)} documents")
print(f"  Pages: {total_pages}")
print(f"  Characters: {total_chars:,}")
print(f"  Table Candidates: {total_tabs}")
