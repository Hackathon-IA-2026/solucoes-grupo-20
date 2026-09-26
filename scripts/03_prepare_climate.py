from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from motor_sin.climate.normalize import prepare_climate_dataset


def _default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize Open-Meteo/ERA5-Land RAW files to Predicta hourly climate dataset."
    )
    parser.add_argument("--raw-dir", default="data/raw/climate/openmeteo")
    parser.add_argument("--input", action="append", default=[], help="Explicit RAW JSON; may be repeated")
    parser.add_argument("--output-root", default="data/processed/climate/climate_hourly")
    parser.add_argument("--report", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--allow-overlap", action="store_true", help="Allow duplicate cell/hour rows")
    args = parser.parse_args()

    files = [Path(x) for x in args.input]
    if not files:
        files = sorted(Path(args.raw_dir).glob("*.json"))
    run_id = args.run_id or _default_run_id()
    report = args.report or f"outputs/reports/climate_prepare_{run_id}.json"
    result = prepare_climate_dataset(
        files,
        output_root=args.output_root,
        report_path=report,
        run_id=run_id,
        strict_duplicates=not args.allow_overlap,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
