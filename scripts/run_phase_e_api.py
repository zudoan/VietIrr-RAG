#!/usr/bin/env python
"""Run the local Phase E evidence API."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from viirr_api.app import main  # noqa: E402


if __name__ == "__main__":
    main()
