"""Seal V4.2 hardening inputs without reading Candidate Test."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]; HERE=Path(__file__).resolve().parent
def sha(p:Path):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

files=[]
for base in [ROOT/"research/vietirr_v4_2",ROOT/"research/vietirr_v4_1"]:
    for p in sorted(base.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            files.append({"path":p.relative_to(ROOT).as_posix(),"size_bytes":p.stat().st_size,"sha256":sha(p)})
candidate=ROOT/"data/v3_2_final_semantic/candidate_test.jsonl"
st=candidate.stat()
out={"schema_version":"1.0","created_at_utc":datetime.now(timezone.utc).isoformat(),
     "purpose":"V4.2 hardening pre-change seal","readable_inputs":files,
     "candidate_test":{"path":candidate.relative_to(ROOT).as_posix(),"policy":"SEALED_NOT_OPENED_NOT_HASHED",
                       "size_bytes_from_stat_only":st.st_size,"mtime_ns_from_stat_only":st.st_mtime_ns,
                       "sha256":"INTENTIONALLY_NOT_COMPUTED"},
     "constraints":{"v4_2_raw_mutated":False,"retrieval_baselines_mutated":False,"candidate_content_accessed":False}}
(HERE/"HARDENING_INPUT_FREEZE.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print({"sealed_files":len(files),"candidate_policy":out["candidate_test"]["policy"]})
