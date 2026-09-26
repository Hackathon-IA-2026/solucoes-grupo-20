#!/usr/bin/env python3
from __future__ import annotations
import os
import argparse, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor_sin.climate.normalize import prepare_climate_dataset
from motor_sin.climate.e2_pilot import read_partitioned_climate, aggregate_pilot_zone_climate, validate_e2_climate_coverage
from motor_sin.common.io import write_table


def main() -> None:
    p = argparse.ArgumentParser(description='Normalize E2 ERA5-Land RAW files and aggregate representative 0.1° cells to an ONS subsystem.')
    p.add_argument('--raw-dir', default='data/raw/climate/e2_openmeteo_seamless')
    p.add_argument('--manifest', help='Optional download manifest; when provided, normalize only RAW files referenced by this run to avoid overlap with older immutable snapshots.')
    p.add_argument('--run-id', default='e2-2025-seamless')
    p.add_argument('--replace-run', action='store_true', help='Remove the derived run partition before rebuilding it. RAW remains immutable.')
    p.add_argument('--subsystem', default='SE/CO')
    p.add_argument('--points', help='Optional point catalog. If point_role exists, zone aggregation uses regional_grid cells only while retaining asset cells in normalized storage.')
    p.add_argument('--output-root', default='data/processed/climate/climate_hourly')
    p.add_argument('--zone-output', default='data/processed/climate/zone_climate_hourly.parquet')
    p.add_argument('--report', default='outputs/reports/e2_climate_prepare.json')
    args = p.parse_args()

    if args.manifest:
        import pandas as pd
        import json as _json
        payload=_json.loads(Path(args.manifest).read_text(encoding='utf-8'))
        manifest_df=pd.DataFrame(payload)
        raw_files=[Path(x) for x in manifest_df.get('raw_file',pd.Series(dtype=str)).dropna().astype(str).tolist()]
    else:
        raw_files = sorted(Path(args.raw_dir).glob('*.json'))
    if not raw_files:
        raise SystemExit(f'no RAW climate JSON files selected from {args.manifest or args.raw_dir}; run the climate download first')
    if args.replace_run:
        import shutil
        safe=''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in args.run_id)
        run_root=Path(args.output_root)/f'run_id={safe}'
        if run_root.exists():shutil.rmtree(run_root)
    # PREDICTA_CANONICAL_POINT_CELL_PATCH_V1
    os.environ['PREDICTA_CLIMATE_POINTS_FILE'] = str(args.points)
    result = prepare_climate_dataset(
        raw_files,
        output_root=args.output_root,
        report_path=args.report,
        run_id=args.run_id,
        strict_duplicates=True,
    )
    dataset_root = result['dataset_root']
    climate = read_partitioned_climate(dataset_root)
    coverage = validate_e2_climate_coverage(climate)
    aggregation_climate = climate
    spatial_method = 'MVP_REPRESENTATIVE_POINTS_UNIFORM'
    if args.points and Path(args.points).exists():
        points = __import__('pandas').read_csv(args.points)
        if 'point_role' in points.columns and 'cell_id' in points.columns:
            regional = points[points['point_role'].astype(str).str.contains('regional_grid', regex=False)]
            allowed = set(regional['cell_id'].astype(str))
            if allowed:
                aggregation_climate = climate[climate['cell_id'].astype(str).isin(allowed)].copy()
                spatial_method = 'GRID_01DEG_ADAPTIVE_REGIONAL_LATTICE'
    zone = aggregate_pilot_zone_climate(aggregation_climate, subsystem_id=args.subsystem, spatial_method=spatial_method)
    write_table(zone, args.zone_output)
    print(json.dumps({
        'normalized_rows': int(len(climate)),
        'sample_cells': int(climate['cell_id'].nunique()),
        'zone_rows': int(len(zone)),
        'zone_output': str(Path(args.zone_output).resolve()),
        'weather_mode': 'PERFECT_WEATHER_BACKTEST',
        'spatial_method': spatial_method,
        'variable_coverage': coverage,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
