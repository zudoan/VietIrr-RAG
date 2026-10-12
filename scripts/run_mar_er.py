from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from viirr_retrieval.mar_er import run_mar_er


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    official_output = root / "outputs/MAR_ER/rankings/m4_dev.jsonl"
    if official_output.exists():
        raise SystemExit("One-shot guard: official M0-M4 outputs already exist; refusing rerun")
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    pytest_result = {
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "summary": completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else "",
        "stdout_tail": completed.stdout.strip().splitlines()[-10:],
    }
    if completed.returncode != 0:
        print(completed.stdout)
        print(completed.stderr, file=sys.stderr)
        raise SystemExit(completed.returncode)
    readiness = run_mar_er(root, pytest_result)
    audit = subprocess.run([sys.executable, "scripts/audit_mar_er.py"], cwd=root, check=False)
    if audit.returncode != 0:
        raise SystemExit(audit.returncode)
    package = subprocess.run([sys.executable, "scripts/package_mar_er.py"], cwd=root, check=False)
    if package.returncode != 0:
        raise SystemExit(package.returncode)
    readiness = json.loads(
        (root / "reports/MAR_ER_EXPERIMENT/READINESS.json").read_text(encoding="utf-8")
    )
    print(json.dumps({key: readiness[key] for key in (
        "status", "EXPERIMENT_VALID", "METHOD_PROMISING", "PAPER_READY",
        "result_class", "blockers",
    )}, indent=2))
