from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from viirr_retrieval.r1 import run_r1


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
    readiness = run_r1(root, pytest_result)
    audit = subprocess.run([sys.executable, "scripts/audit_r1.py"], cwd=root, check=False)
    if audit.returncode != 0:
        raise SystemExit(audit.returncode)
    print({key: readiness[key] for key in (
        "status", "R1_VALID", "READY_FOR_R2", "candidate_test_sealed", "blockers",
    )})

