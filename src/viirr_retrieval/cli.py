from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adapter import build_indexable_view
from .validate import validate_b1


def main() -> None:
    parser = argparse.ArgumentParser(prog="viirr_retrieval")
    sub = parser.add_subparsers(dest="command", required=True)
    all_cmd = sub.add_parser("all")
    all_cmd.add_argument("--root", default=".")
    b2_cmd = sub.add_parser("b2")
    b2_cmd.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.command == "all":
        manifest = build_indexable_view(root)
        report = validate_b1(root)
        print(json.dumps({"manifest_counts": manifest["counts"], **report}, ensure_ascii=False, indent=2))
        if report["B1_INTEGRITY"] != "PASS":
            raise SystemExit(1)
    else:
        from .experiment import run_b2
        print(json.dumps(run_b2(root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
