from __future__ import annotations
import hashlib,json,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;RESEARCH=HERE.parent

hardening=[p for p in HERE.rglob("*") if p.is_file() and p.name not in {"V4_2_HARDENING_REVIEW_BUNDLE.zip","HARDENING_BUNDLE_MANIFEST.json","V4_2_HARDENING_INDEPENDENT_AUDIT.json"} and "__pycache__" not in p.parts]
base=[]
for folder in [RESEARCH/"vietirr_v4_2",RESEARCH/"vietirr_v4_1"]:
    base.extend(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
files=sorted(set(hardening+base),key=lambda p:p.relative_to(RESEARCH.parent).as_posix())
checks={p.relative_to(RESEARCH.parent).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
manifest={"bundle":"V4_2_HARDENING_REVIEW_BUNDLE.zip","payload_file_count":len(files),"source_pdfs_included":False,
          "candidate_test_included":False,"files":checks}
(HERE/"HARDENING_BUNDLE_MANIFEST.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
with zipfile.ZipFile(HERE/manifest["bundle"],"w",zipfile.ZIP_DEFLATED) as z:
    for p in files:z.write(p,p.relative_to(RESEARCH.parent).as_posix())
    z.write(HERE/"HARDENING_BUNDLE_MANIFEST.json","HARDENING_BUNDLE_MANIFEST.json")
print({"payload_files":len(files)+1,"source_pdfs":0,"candidate_test":0})
