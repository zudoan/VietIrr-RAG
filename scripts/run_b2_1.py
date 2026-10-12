from pathlib import Path

from viirr_retrieval.b21 import run_b21


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    result = run_b21(root)
    print({key: result[key] for key in ("B2_VERIFIED", "B2_1_VALID", "remaining_blockers")})
