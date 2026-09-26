from __future__ import annotations

import argparse
import sys

from contracts.registry import REGISTRY
from contracts.validators.core import validate_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a Predicta versioned contract file")
    parser.add_argument("--contract", required=True, choices=sorted(REGISTRY))
    parser.add_argument("--file", required=True)
    parser.add_argument("--expected-hours", type=int, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = validate_file(args.file, args.contract, expected_hours=args.expected_hours)
    print(f"contract={report.contract} rows={report.rows} valid={report.valid}")
    for warning in report.warnings:
        print(f"WARNING: {warning}")
    for error in report.errors:
        print(f"ERROR: {error}")
    if not report.valid:
        sys.exit(1)


if __name__ == "__main__":
    main()
