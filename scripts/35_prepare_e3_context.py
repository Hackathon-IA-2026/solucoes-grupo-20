#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from motor_sin.climate.e2_pilot import load_pilot_points
from motor_sin.climate.e3_snapshot import (
    build_e3_daily_context,
    build_e3_hourly_zone_context,
    e3_quality_summary,
    merge_e2_with_e3_context,
    parse_manifest_daily_frames,
)
from motor_sin.climate.openmeteo_snapshot_anomaly import load_snapshot_rules
from motor_sin.common.io import read_table, write_json, write_table


def main() -> None:
    p = argparse.ArgumentParser(
        description=(
            'Build the E3 10-year monthly temperature baseline, score target-year daily anomalies/events '
            'using the supplied OpenMeteo snapshot rules, propagate them to target hours and merge with E2.'
        )
    )
    p.add_argument('--manifest', default='outputs/reports/e3_climate_download_manifest.json')
    p.add_argument('--points', default='configs/e2_seco_points.csv')
    p.add_argument('--subsystem', default='SE/CO')
    p.add_argument('--target-year', type=int, default=2025)
    p.add_argument('--rules', default='configs/openmeteo_event_rules_snapshot_2026-08-08.2.json')
    p.add_argument('--e2-climate', default='data/processed/climate/zone_climate_hourly.parquet')
    p.add_argument('--baseline-output', default='data/processed/climate/e3_temperature_baseline_monthly.parquet')
    p.add_argument('--daily-output', default='data/processed/climate/e3_daily_context.parquet')
    p.add_argument('--hourly-output', default='data/processed/climate/e3_zone_context_hourly.parquet')
    p.add_argument('--zone-output', default='data/processed/climate/zone_climate_hourly_e3.parquet')
    p.add_argument('--report', default='outputs/reports/e3_climate_prepare.json')
    args = p.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        raise SystemExit(
            f"E3 manifest not found: {manifest_path}. Run scripts/34_download_e3_context.py successfully first."
        )
    manifest_payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest = pd.DataFrame(manifest_payload)
    baseline_daily, target_daily = parse_manifest_daily_frames(manifest)
    rules = load_snapshot_rules(args.rules)
    baseline, daily_context = build_e3_daily_context(
        baseline_daily,
        target_daily,
        target_year=args.target_year,
        rules=rules,
    )
    points = load_pilot_points(args.points, subsystem_id=args.subsystem)
    e2_zone = read_table(args.e2_climate)
    hourly_context = build_e3_hourly_zone_context(
        daily_context,
        points,
        e2_zone[['interval_start_utc']],
        subsystem_id=args.subsystem,
    )
    merged = merge_e2_with_e3_context(e2_zone, hourly_context)

    write_table(baseline, args.baseline_output)
    write_table(daily_context, args.daily_output)
    write_table(hourly_context, args.hourly_output)
    write_table(merged, args.zone_output)
    report = e3_quality_summary(baseline, daily_context, hourly_context, merged)
    report.update({
        'baseline_output': str(Path(args.baseline_output).resolve()),
        'daily_output': str(Path(args.daily_output).resolve()),
        'hourly_output': str(Path(args.hourly_output).resolve()),
        'zone_output': str(Path(args.zone_output).resolve()),
    })
    write_json(report, args.report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
