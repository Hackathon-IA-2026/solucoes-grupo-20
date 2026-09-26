#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor_sin.climate.e2_pilot import load_pilot_points
from motor_sin.climate.batch_openmeteo import download_e3_multiyear_batched
from motor_sin.climate.e3_snapshot import parse_manifest_baseline_daily
from motor_sin.climate.openmeteo_snapshot_anomaly import build_monthly_temperature_baseline, load_snapshot_rules
from motor_sin.common.io import write_table, write_json

REGIONS = {'N': 'n', 'NE': 'ne', 'SE/CO': 'seco', 'S': 's'}


def main() -> None:
    p = argparse.ArgumentParser(
        description='Prepare/reuse the 10-year operational climate baseline from the shared annual Open-Meteo cache.'
    )
    p.add_argument('--target-year', type=int, required=True)
    p.add_argument('--timeout', type=int, default=120)
    p.add_argument('--batch-size', type=int, default=6)
    p.add_argument('--request-delay', type=float, default=2.0)
    p.add_argument('--max-retries', type=int, default=10)
    p.add_argument('--backoff', type=float, default=10.0)
    p.add_argument('--cooldown-after-429', type=int, default=3)
    p.add_argument('--cooldown-seconds', type=float, default=90.0)
    p.add_argument('--store-root', default='data/climate_store')
    p.add_argument('--history-mode', choices=['local-first','local-only'], default='local-only')
    p.add_argument('--report', default='outputs/reports/operational_baselines.json')
    a = p.parse_args()

    rules = load_snapshot_rules()
    years = list(range(a.target_year - 10, a.target_year))
    reports = []
    for region, tag in REGIONS.items():
        out = Path(f'data/processed/climate/regions/{tag}/e3_temperature_baseline_operational.parquet')
        if out.exists():
            try:
                existing = pd.read_parquet(out)
                target_col = existing.get('target_year')
                if len(existing) and target_col is not None and int(target_col.iloc[0]) == a.target_year:
                    reports.append({
                        'region': region, 'target_year': a.target_year,
                        'baseline_year_start': int(existing['baseline_year_start'].min()),
                        'baseline_year_end': int(existing['baseline_year_end'].max()),
                        'rows': int(len(existing)), 'output': str(out), 'reused': True,
                        'source': 'operational_cache',
                    })
                    continue
            except Exception:
                pass

        train = Path(f'data/processed/climate/regions/{tag}/e3_temperature_baseline_monthly.parquet')
        if train.exists():
            try:
                allb = pd.read_parquet(train)
                if 'target_year' in allb.columns:
                    selected = allb[pd.to_numeric(allb['target_year'], errors='coerce').eq(a.target_year)].copy()
                    if not selected.empty:
                        write_table(selected, out)
                        reports.append({
                            'region': region, 'target_year': a.target_year,
                            'baseline_year_start': int(selected['baseline_year_start'].min()),
                            'baseline_year_end': int(selected['baseline_year_end'].max()),
                            'rows': int(len(selected)), 'output': str(out), 'reused': True,
                            'source': 'training_rolling_baseline',
                        })
                        continue
            except Exception:
                pass

        points_path = Path(f'data/processed/grid/climate_points_{tag}_01deg.csv')
        if not points_path.exists():
            points_path = Path(f'configs/e2_{tag}_points.csv')
        points = load_pilot_points(points_path, subsystem_id=region)

        # Shared stable cache: if training already downloaded 2016..2025 for this
        # region, every baseline year is a local cache hit. No dummy target-day
        # request is made anymore.
        raw_dir = str(Path(a.store_root) / tag / 'daily')
        manifest = Path(f'outputs/reports/climate/{tag}_operational_baseline_{a.target_year}.json')
        result = download_e3_multiyear_batched(
            points,
            target_start_date=None,
            target_end_date=None,
            baseline_start_date=f'{years[0]}-01-01',
            baseline_end_date=f'{years[-1]}-12-31',
            raw_directory=raw_dir,
            timeout_seconds=a.timeout,
            batch_size=a.batch_size,
            request_delay_seconds=a.request_delay,
            max_retries=a.max_retries,
            base_backoff_seconds=a.backoff,
            cooldown_after_429=a.cooldown_after_429,
            global_cooldown_seconds=a.cooldown_seconds,
            allow_network=a.history_mode != 'local-only',
        )
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(result.to_dict(orient='records'), ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')

        baseline_daily = parse_manifest_baseline_daily(result)
        baseline = build_monthly_temperature_baseline(
            baseline_daily[['cell_id', 'date_local', 'temperature_2m_max', 'temperature_2m_min']],
            target_year=a.target_year,
            minimum_samples_per_month=int(rules['temperature_baseline']['minimum_samples_per_month']),
        )
        baseline['target_year'] = a.target_year
        write_table(baseline, out)
        reports.append({
            'region': region, 'target_year': a.target_year,
            'baseline_year_start': years[0], 'baseline_year_end': years[-1],
            'rows': int(len(baseline)), 'output': str(out), 'reused': False,
            'source': 'persistent_local_climate_store',
            'cache_hits': int(result.get('cache_hit', pd.Series(dtype=bool)).fillna(False).sum()),
        })

    payload = {
        'target_year': a.target_year,
        'regions': reports,
        'cache_layout': f'{a.store_root}/<region>/daily/<channel>/year=YYYY',
        'history_mode': a.history_mode,
        'rate_limit_policy': {
            'batch_size': a.batch_size,
            'request_delay_seconds': a.request_delay,
            'max_retries': a.max_retries,
            'backoff_seconds': a.backoff,
            'cooldown_after_429': a.cooldown_after_429,
            'cooldown_seconds': a.cooldown_seconds,
        },
    }
    write_json(payload, a.report)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
