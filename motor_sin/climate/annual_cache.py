from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from motor_sin.climate.batch_openmeteo import annual_date_windows
from motor_sin.common.provenance import persist_immutable_raw_record


def _slice_payload(payload: dict[str, Any], block_name: str, start_date: str, end_date: str) -> dict[str, Any] | None:
    block = payload.get(block_name)
    if not isinstance(block, dict):
        return None
    times = block.get('time')
    if not isinstance(times, list) or not times:
        return None
    indexes = [i for i, raw in enumerate(times) if start_date <= str(raw)[:10] <= end_date]
    if not indexes:
        return None
    out = deepcopy(payload)
    sliced = {}
    n = len(times)
    for key, value in block.items():
        if isinstance(value, list) and len(value) == n:
            sliced[key] = [value[i] for i in indexes]
        else:
            sliced[key] = deepcopy(value)
    out[block_name] = sliced
    return out


def _annual_external_id(external_id: str, start_date: str, end_date: str) -> str:
    parts = str(external_id).rsplit(':', 2)
    if len(parts) != 3:
        raise ValueError(f'cannot convert external_id to annual cache key: {external_id}')
    return f'{parts[0]}:{start_date}:{end_date}'


def _migrate_file(path: Path, *, destination_root: Path, expected_service: str) -> dict[str, int]:
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {'examined': 1, 'migrated': 0, 'created': 0}
    if str(record.get('source_service')) != expected_service:
        return {'examined': 1, 'migrated': 0, 'created': 0}
    params = record.get('request_parameters')
    payload = record.get('payload')
    external_id = record.get('external_id')
    if not isinstance(params, dict) or not isinstance(payload, dict) or not external_id:
        return {'examined': 1, 'migrated': 0, 'created': 0}
    start_date = str(params.get('start_date') or '')
    end_date = str(params.get('end_date') or '')
    if not start_date or not end_date:
        return {'examined': 1, 'migrated': 0, 'created': 0}
    block_name = 'hourly' if expected_service == 'historical' else 'daily'
    migrated = 0
    created_count = 0
    for year, left, right in annual_date_windows(start_date, end_date):
        annual_payload = _slice_payload(payload, block_name, left, right)
        if annual_payload is None:
            continue
        annual_params = dict(params)
        annual_params['start_date'] = left
        annual_params['end_date'] = right
        annual_external = _annual_external_id(str(external_id), left, right)
        if expected_service == 'historical':
            dest = destination_root / f'year={year:04d}'
        else:
            channel = str(external_id).split(':', 2)[1] if str(external_id).startswith('e3:') else 'unknown'
            dest = destination_root / channel / f'year={year:04d}'
        _, created, _ = persist_immutable_raw_record(
            directory=dest,
            source=str(record.get('source') or 'open-meteo'),
            source_service=expected_service,
            source_endpoint=str(record.get('source_endpoint') or ''),
            external_id=annual_external,
            request_parameters=annual_params,
            payload=annual_payload,
            http_status=int(record.get('http_status') or 200),
            retrieved_at_utc=record.get('retrieved_at_utc'),
        )
        migrated += 1
        created_count += int(bool(created))
    return {'examined': 1, 'migrated': migrated, 'created': created_count}


def seed_annual_cache_from_legacy(
    *,
    legacy_e2_directory: str | Path | None,
    legacy_e3_directory: str | Path | None,
    annual_e2_directory: str | Path,
    annual_e3_directory: str | Path,
) -> dict[str, Any]:
    """Split previous multi-year RAW snapshots into the new annual cache locally.

    No external request is made. This allows users upgrading from v1.10 to retain
    successful batches from an interrupted multi-year run instead of downloading
    those years again.
    """
    report: dict[str, Any] = {
        'e2': {'examined': 0, 'migrated': 0, 'created': 0},
        'e3': {'examined': 0, 'migrated': 0, 'created': 0},
    }
    specs = [
        ('e2', legacy_e2_directory, Path(annual_e2_directory), 'historical'),
        ('e3', legacy_e3_directory, Path(annual_e3_directory), 'historical_daily'),
    ]
    for key, legacy, destination, service in specs:
        if not legacy:
            continue
        root = Path(legacy)
        if not root.exists():
            continue
        for path in sorted(root.glob('*.json')):
            item = _migrate_file(path, destination_root=destination, expected_service=service)
            for metric in ('examined', 'migrated', 'created'):
                report[key][metric] += int(item[metric])
    return report
