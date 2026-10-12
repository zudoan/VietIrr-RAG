import sys
sys.stdout.reconfigure(encoding='utf-8')
import hashlib
from pathlib import Path

def get_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def main():
    checksum_file = Path("checksums/sha256sums.txt")
    targets = [
        "data/manifests/source_catalog.csv",
        "data/manifests/download_manifest.jsonl",
        "data/qa/pilot_qa.jsonl",
        "data/qa/page_localization_gold.jsonl",
        "data/negatives/hard_negatives.jsonl",
        "data/splits/pilot_dev.jsonl"
    ]
    
    # Also add sample of raw files, regions, and tables
    for d in ["data/raw/core_long", "data/raw/temporal", "data/parsed", "data/regions", "data/tables"]:
        p = Path(d)
        if p.exists():
            for f in sorted(p.glob("*"))[:5]:
                targets.append(str(f).replace("\\", "/"))
                
    print(f"Calculating SHA-256 for {len(targets)} artifacts...")
    entries = []
    for t in sorted(set(targets)):
        p = Path(t)
        if p.exists() and p.is_file():
            h = get_sha256(p)
            entries.append(f"{h}  {t}")
            
    with open(checksum_file, "w", encoding="utf-8") as f:
        f.write("\n".join(entries) + "\n")
        
    print(f"Checksums saved to {checksum_file} ({len(entries)} verified files).")

if __name__ == "__main__":
    main()
