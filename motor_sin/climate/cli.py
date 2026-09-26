from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from motor_sin.climate.normalize import prepare_climate_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare Predicta hourly climate Parquet from immutable RAW files.")
    parser.add_argument("--raw-dir", default="data/raw/climate/openmeteo")
    parser.add_argument("--output-root", default="data/processed/climate/climate_hourly")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--report", default=None)
    args = parser.parse_args()
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = args.report or f"outputs/reports/climate_prepare_{run_id}.json"
    files = sorted(Path(args.raw_dir).glob("*.json"))
    result = prepare_climate_dataset(
        files,
        output_root=args.output_root,
        report_path=report,
        run_id=run_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
