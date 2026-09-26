#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor_sin.common.io import read_table
from motor_sin.climate.e2_pilot import load_pilot_points, infer_date_bounds_from_load, download_points, write_manifest


def main() -> None:
    p = argparse.ArgumentParser(description='Download ERA5-Land/Open-Meteo hourly climate for the E2 MVP representative-point pilot.')
    p.add_argument('--load', default='data/processed/demand/load_hourly.parquet')
    p.add_argument('--points', default='configs/e2_seco_points.csv')
    p.add_argument('--subsystem', default='SE/CO')
    p.add_argument('--start-date')
    p.add_argument('--end-date')
    p.add_argument('--raw-dir', default='data/raw/climate/e2_openmeteo_seamless')
    p.add_argument('--model', default='era5_seamless', choices=['era5_seamless','era5','era5_land'])
    p.add_argument('--manifest', default='outputs/reports/e2_climate_download_manifest.json')
    p.add_argument('--timeout', type=int, default=90)
    args = p.parse_args()

    points = load_pilot_points(args.points, subsystem_id=args.subsystem)
    if args.start_date and args.end_date:
        start_date, end_date = args.start_date, args.end_date
    elif args.start_date or args.end_date:
        raise SystemExit('--start-date and --end-date must be supplied together')
    else:
        start_date, end_date = infer_date_bounds_from_load(read_table(args.load), subsystem_id=args.subsystem)

    result = download_points(
        points,
        start_date=start_date,
        end_date=end_date,
        raw_directory=args.raw_dir,
        timeout_seconds=args.timeout,
        model=args.model,
    )
    write_manifest(result, args.manifest)
    print(result[['point_id','name','start_date','end_date','created','raw_file']].to_string(index=False))
    print(f'points={len(result)} model={args.model} raw_dir={Path(args.raw_dir).resolve()}')


if __name__ == '__main__':
    main()
