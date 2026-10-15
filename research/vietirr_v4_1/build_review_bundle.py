"""Create a deterministic V4.1 review bundle without PDF or Candidate data."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / "V4_1_REVIEW_BUNDLE.zip"
MANIFEST = HERE / "V4_1_BUNDLE_MANIFEST.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files() -> list[tuple[Path, str]]:
    chosen = []
    for p in HERE.rglob("*"):
        if not p.is_file() or p in {OUT, MANIFEST} or "__pycache__" in p.parts or p.suffix.lower() == ".pdf": continue
        chosen.append((p, p.relative_to(ROOT).as_posix()))
    extra = ROOT / "data/v4_corpus/metadata/v4_corpus_manifest.jsonl"
    if extra.is_file(): chosen.append((extra, extra.relative_to(ROOT).as_posix()))
    return sorted(chosen, key=lambda x: x[1])


def main() -> None:
    selected = files()
    manifest = {"schema_version": "1.0", "candidate_test_included": False, "pdf_binaries_included": False,
                "rights_note": "Acquire source PDFs from canonical URLs; public download is not asserted to be an open licence.",
                "files": [{"path": arc, "size_bytes": p.stat().st_size, "sha256": digest(p)} for p, arc in selected]}
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    selected.append((MANIFEST, MANIFEST.relative_to(ROOT).as_posix()))
    epoch = (2026, 10, 14, 0, 0, 0)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path, arc in sorted(selected, key=lambda x: x[1]):
            info = zipfile.ZipInfo(arc, epoch); info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(info, path.read_bytes())
    print(json.dumps({"bundle": str(OUT), "files": len(selected), "size_bytes": OUT.stat().st_size, "sha256": digest(OUT)}))


if __name__ == "__main__": main()
