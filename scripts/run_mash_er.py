from __future__ import annotations

import subprocess
import sys
import json
from pathlib import Path

from viirr_retrieval.mash_er import run_mash_er


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    pytest_result = {
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "summary": completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else "",
    }
    if completed.returncode != 0:
        print(completed.stdout)
        print(completed.stderr, file=sys.stderr)
        raise SystemExit(completed.returncode)
    readiness = run_mash_er(root, pytest_result)
    audit = subprocess.run([sys.executable, "scripts/audit_mash_er.py"], cwd=root, check=False)
    if audit.returncode != 0:
        raise SystemExit(audit.returncode)
    readiness = json.loads((root / "reports/MASH_ER/READINESS.json").read_text(encoding="utf-8"))
    print({key: readiness[key] for key in (
        "status", "EXPERIMENT_VALID", "METHOD_PROMISING", "PAPER_READY",
        "NOVELTY_STATUS", "blockers",
    )})
