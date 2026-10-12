from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from viirr_retrieval.c11 import run_c11


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
    result = run_c11(root, pytest_result)
    print({key: result[key] for key in (
        "C1_1_VALID", "status", "EVIDENCE_SET_SELECTION_PROMISING", "READY_FOR_C2",
        "remaining_blockers",
    )})
