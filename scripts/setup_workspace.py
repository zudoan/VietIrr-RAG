import os
from pathlib import Path

DIRS = [
    "configs",
    "configs/prompts",
    "scripts",
    "data/raw/core_long",
    "data/raw/temporal",
    "data/manifests",
    "data/parsed",
    "data/regions",
    "data/tables",
    "data/qa",
    "data/negatives",
    "data/splits",
    "reports",
    "reports/human_review_sample",
    "logs",
    "checksums"
]

def main():
    root = Path(".")
    for d in DIRS:
        p = root / d
        p.mkdir(parents=True, exist_ok=True)
        print(f"Created: {p}")
    print("Workspace directories initialized successfully.")

if __name__ == "__main__":
    main()
