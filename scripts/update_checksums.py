import os
import hashlib
import glob

def main():
    paths = sorted(
        glob.glob("data/manifests/*.*") +
        glob.glob("data/qa/*.jsonl") +
        glob.glob("data/negatives/*.jsonl") +
        glob.glob("reports/v2_1/*.*") +
        glob.glob("data/raw/*/*.pdf")
    )
    lines = []
    for p in paths:
        if os.path.isfile(p):
            with open(p, "rb") as f:
                h = hashlib.sha256(f.read()).hexdigest()
            lines.append(f"{h}  {p.replace(os.sep, '/')}")
            
    with open("checksums/sha256sums.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
        
    print(f"Updated checksums/sha256sums.txt with {len(lines)} files.")

if __name__ == "__main__":
    main()
