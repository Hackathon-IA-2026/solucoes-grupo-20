#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor_sin.climate.e2_pilot import load_pilot_points, write_manifest
from motor_sin.climate.e3_snapshot import (
    download_e3_context,
    infer_target_year_from_load,
)
from motor_sin.climate.openmeteo_snapshot_anomaly import load_snapshot_rules
from motor_sin.common.io import read_table


def main() -> None:
    p = argparse.ArgumentParser(
        description=(
            'Download the E3 daily climate context required by the supplied OpenMeteo snapshot: '
            '10 complete prior ERA5-Land years for the monthly temperature baseline plus target-year '
            'daily temperature, precipitation and wind-gust context using the same model-selection semantics '
            'as the supplied OpenMeteo snapshot historical collector.'
        )
    )
    p.add_argument('--load', default='data/processed/demand/load_hourly.parquet')
    p.add_argument('--points', default='configs/e2_seco_points.csv')
    p.add_argument('--subsystem', default='SE/CO')
    p.add_argument('--calendar-timezone', default='America/Sao_Paulo')
    p.add_argument('--target-year', type=int)
    p.add_argument('--raw-dir', default='data/raw/climate/e3_openmeteo_daily')
    p.add_argument('--manifest', default='outputs/reports/e3_climate_download_manifest.json')
    p.add_argument('--rules', default='configs/openmeteo_event_rules_snapshot_2026-08-08.2.json')
    p.add_argument('--timeout', type=int, default=90)
    args = p.parse_args()

    load = read_table(args.load)
    target_year = args.target_year or infer_target_year_from_load(
        load,
        subsystem_id=args.subsystem,
        calendar_timezone=args.calendar_timezone,
    )
    points = load_pilot_points(args.points, subsystem_id=args.subsystem)
    rules = load_snapshot_rules(args.rules)
    result = download_e3_context(
        points,
        target_year=target_year,
        raw_directory=args.raw_dir,
        timeout_seconds=args.timeout,
        rules=rules,
    )
    write_manifest(result, args.manifest)
    print(result[['channel','point_id','name','model','start_date','end_date','created','raw_file']].to_string(index=False))
    print(json.dumps({
        'target_year': target_year,
        'baseline_year_start': target_year - int(rules['temperature_baseline']['complete_years']),
        'baseline_year_end': target_year - 1,
        'rules_version': rules['rules_version'],
        'raw_dir': str(Path(args.raw_dir).resolve()),
        'manifest': str(Path(args.manifest).resolve()),
        'records': int(len(result)),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
