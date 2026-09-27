#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor_sin.common.io import read_table, write_json, write_table
from motor_sin.sources.ons_dessem import SOURCE, VALUE_COLUMNS, prepare_dessem_schedule, read_dessem_table


def download_day(day: str, url: str, raw_dir: Path, timezone_name: str) -> pd.DataFrame:
    path = raw_dir / url.rsplit('/', 1)[-1]
    metadata_path = path.with_suffix(path.suffix + '.meta.json')
    if path.exists():
        if not metadata_path.exists():
            raise ValueError(f'existing DESSEM snapshot has no metadata: {path}')
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != metadata['sha256'] or metadata['url'] != url:
            raise ValueError(f'DESSEM snapshot identity mismatch: {path}')
    else:
        response = requests.get(url, timeout=60)
        if response.status_code == 404 and url.endswith('.parquet'):
            return download_day(day, url.removesuffix('.parquet') + '.csv', raw_dir, timezone_name)
        response.raise_for_status()
        digest = hashlib.sha256(response.content).hexdigest()
        metadata = {
            'source': SOURCE,
            'reference_date': day,
            'url': url,
            'sha256': digest,
            'bytes': len(response.content),
            'captured_at_utc': pd.Timestamp.now(tz='UTC').isoformat(),
            'http_last_modified': response.headers.get('Last-Modified'),
            'availability_policy': 'CAPTURE_TIME_NOT_HISTORICAL_ISSUE_TIME',
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        write_json(metadata, metadata_path)
    hourly = prepare_dessem_schedule(
        read_dessem_table(path),
        source_timezone=timezone_name,
        captured_at_utc=metadata['captured_at_utc'],
        source_url=url,
        snapshot_sha256=digest,
    )
    local_dates = hourly['interval_start_utc'].dt.tz_convert(timezone_name).dt.strftime('%Y-%m-%d')
    if not local_dates.eq(day).all():
        raise ValueError(f'DESSEM resource does not match its reference date: {day}')
    counts = hourly.groupby('subsystem_id').size()
    if set(counts.index) != {'N', 'NE', 'S', 'SE/CO'} or not counts.eq(24).all():
        raise ValueError(f'DESSEM resource lacks a complete subsystem-day: {day}')
    values = list(VALUE_COLUMNS.values())
    national = hourly.groupby('interval_start_utc', as_index=False)[values].sum()
    national['subsystem_id'] = 'SIN'
    for column in ['source', 'available_at_utc', 'source_url', 'snapshot_sha256']:
        national[column] = hourly[column].iloc[0]
    return pd.concat([hourly, national], ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description='Download official DESSEM schedules aligned to the load training history.')
    parser.add_argument('--load', default='data/processed/demand/load_hourly.parquet')
    parser.add_argument('--start', help='First local date; defaults to the beginning of load history.')
    parser.add_argument('--end', help='Last local date; defaults to the end of load history.')
    parser.add_argument('--source-timezone', default='America/Sao_Paulo')
    parser.add_argument('--raw-dir', default='data/raw/ons/dessem')
    parser.add_argument('--output', default='data/processed/generation/dessem_schedule_hourly.parquet')
    parser.add_argument('--report', default='outputs/reports/dessem_download.json')
    parser.add_argument('--workers', type=int, choices=range(1, 9), default=4)
    args = parser.parse_args()

    load = read_table(args.load)
    local = pd.to_datetime(load['interval_start_utc'], utc=True).dt.tz_convert(args.source_timezone)
    start = pd.Timestamp(args.start).date() if args.start else local.min().date()
    end = pd.Timestamp(args.end).date() if args.end else local.max().date()
    if start > end:
        raise SystemExit('--start must not be after --end')
    days = pd.date_range(start, end, freq='D').strftime('%Y-%m-%d').tolist()
    subsystems = set(load['subsystem_id'].astype(str).replace({'SE': 'SE/CO', 'SECO': 'SE/CO'}))
    if not subsystems.issubset({'N', 'NE', 'S', 'SE/CO', 'SIN'}):
        raise SystemExit('load history contains unknown subsystems')

    response = requests.get('https://dados.ons.org.br/api/3/action/package_show', params={'id': 'balanco_dessem_geral'}, timeout=60)
    response.raise_for_status()
    catalog = response.json()
    if not catalog.get('success'):
        raise SystemExit('ONS DESSEM catalog request failed')
    resources: dict[str, str] = {}
    for resource in catalog['result']['resources']:
        url = resource.get('url', '')
        match = re.fullmatch(
            r'https://ons-aws-prod-opendata\.s3\.amazonaws\.com/dataset/balanco_dessem_geral/'
            r'BALANCO_DESSEM_GERAL_(\d{4})_(\d{2})_(\d{2})\.(parquet|csv)', url,
        )
        if match:
            day = '-'.join(match.groups()[:3])
            if day not in resources or url.endswith('.parquet'):
                resources[day] = url
    selected = {day: resources[day] for day in days if day in resources}
    missing = sorted(set(days) - set(selected))
    failures: dict[str, str] = {}
    unavailable_resources = []
    frames = []
    print(f'DESSEM: {start} to {end}; {len(selected)} published days; {len(missing)} absent from catalog.', flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        pending = {executor.submit(download_day, day, url, Path(args.raw_dir), args.source_timezone): day for day, url in selected.items()}
        for completed, future in enumerate(as_completed(pending), start=1):
            day = pending[future]
            try:
                frames.append(future.result())
            except requests.HTTPError as error:
                if error.response is not None and error.response.status_code == 404:
                    unavailable_resources.append(day)
                else:
                    failures[day] = str(error)
            except (OSError, ValueError, KeyError, requests.RequestException) as error:
                failures[day] = str(error)
            if completed % 50 == 0 or completed == len(pending):
                print(f'DESSEM: {completed}/{len(pending)} files processed; {len(failures)} failures.', flush=True)
    report = {
        'source': SOURCE, 'requested_start': str(start), 'requested_end': str(end),
        'source_resolution': '30min', 'canonical_resolution': '1h',
        'subsystems': sorted(subsystems), 'downloaded_days': len(frames),
        'missing_catalog_dates': missing, 'failed_dates': failures,
        'unavailable_resource_dates': sorted(unavailable_resources),
        'complete_for_requested_range': not (missing or failures or unavailable_resources),
        'historical_availability_verified': False,
        'output': args.output,
    }
    if frames:
        output = pd.concat(frames, ignore_index=True)
        output = output[output['subsystem_id'].isin(subsystems)].sort_values(['subsystem_id', 'interval_start_utc'])
        if output.duplicated(['interval_start_utc', 'subsystem_id']).any():
            raise SystemExit('DESSEM contains conflicting hourly snapshots')
        write_table(output.reset_index(drop=True), args.output)
        report.update(rows=len(output), start_utc=str(output['interval_start_utc'].min()), end_utc=str(output['interval_start_utc'].max()))
    write_json(report, args.report)
    print(json.dumps({key: value for key, value in report.items() if key not in {'missing_catalog_dates', 'failed_dates'}}, indent=2))
    if not frames or failures:
        raise SystemExit(f'DESSEM preparation incomplete; see {args.report}')


if __name__ == '__main__':
    main()