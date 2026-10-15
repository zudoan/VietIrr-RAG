import json
from pathlib import Path
from QA_GENERATOR_V3 import generate
HERE=Path(__file__).resolve().parent
reqs=[json.loads(x) for x in (HERE/"QA_GENERATOR_TESTS/demo_requests.jsonl").read_text(encoding="utf-8").splitlines() if x]
out=[generate(x) for x in reqs]
(HERE/"QA_GENERALIZATION_DEMO.jsonl").write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in out),encoding="utf-8")
print({"requests":len(reqs),"drafts":sum(x["generation_state"]=="DRAFT_CREATED" for x in out),"checksums":[x.get("output_sha256") for x in out]})
