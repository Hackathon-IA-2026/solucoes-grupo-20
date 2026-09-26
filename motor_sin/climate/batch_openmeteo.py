from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlencode

import pandas as pd

from motor_sin.climate.http_client import fetch_json_with_retry
from motor_sin.climate.local_store import LocalClimateStoreGap, find_local_records, raw_record_row_common
from motor_sin.climate.openmeteo import build_archive_parameters, get_openmeteo_archive_url, get_openmeteo_api_key
from motor_sin.climate.e3_snapshot import (
    BASELINE_DAILY_VARIABLES,
    TARGET_SNAPSHOT_DAILY_VARIABLES,
    build_daily_archive_parameters,
)
from motor_sin.common.provenance import find_cached_raw_record, persist_immutable_raw_record, utc_now_iso

ProgressCallback = Callable[[dict[str, Any]], None] | None


def _chunks(frame: pd.DataFrame, size: int):
    size = max(1, int(size))
    for start in range(0, len(frame), size):
        yield frame.iloc[start:start + size].copy()


def annual_date_windows(start_date: str, end_date: str) -> list[tuple[int, str, str]]:
    """Split an inclusive date interval into non-overlapping calendar-year windows."""
    start = date.fromisoformat(str(start_date))
    end = date.fromisoformat(str(end_date))
    if end < start:
        raise ValueError(f'end_date {end} precedes start_date {start}')
    windows: list[tuple[int, str, str]] = []
    for year in range(start.year, end.year + 1):
        left = max(start, date(year, 1, 1))
        right = min(end, date(year, 12, 31))
        if left <= right:
            windows.append((year, left.isoformat(), right.isoformat()))
    return windows


def _as_payload_list(payload: Any, expected: int) -> list[dict[str, Any]]:
    if expected == 1 and isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list) and len(payload) == expected and all(isinstance(x, dict) for x in payload):
        return payload
    raise ValueError(f'Open-Meteo multi-location response shape mismatch: expected={expected}, type={type(payload).__name__}')


def _notify(callback: ProgressCallback, **payload: Any) -> None:
    if callback:
        callback(dict(payload))


def download_hourly_points_batched(
    points: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    raw_directory: str | Path,
    model: str = 'era5_seamless',
    timeout_seconds: int = 90,
    batch_size: int = 6,
    request_delay_seconds: float = 2.0,
    max_retries: int = 10,
    base_backoff_seconds: float = 10.0,
    cooldown_after_429: int = 3,
    global_cooldown_seconds: float = 90.0,
    allow_network: bool = True,
    progress_callback: ProgressCallback = None,
) -> pd.DataFrame:
    """Resolve hourly history LOCAL-FIRST and download only uncovered date deltas."""
    raw_directory = Path(raw_directory)
    rows: list[dict[str, Any]] = []
    pending_by_window: dict[tuple[str, str], list[pd.Series]] = {}
    gaps: list[dict[str, Any]] = []

    for _, point in points.iterrows():
        scalar = build_archive_parameters(
            latitude=float(point.latitude), longitude=float(point.longitude),
            start_date=start_date, end_date=end_date, model=model,
        )
        local_records, missing_ranges = find_local_records(
            directory=raw_directory, source_service='historical', request_parameters=scalar,
            block_name='hourly', start_date=start_date, end_date=end_date,
        )
        for path, record in local_records:
            params = record.get('request_parameters') or {}
            rows.append({
                'point_id': str(point.point_id), 'name': str(point.name), 'state': str(point.state),
                'subsystem_id': str(point.subsystem_id), 'latitude_requested': float(point.latitude),
                'longitude_requested': float(point.longitude), 'timezone': str(point.timezone), 'weight': float(point.weight),
                'start_date': str(params.get('start_date') or start_date), 'end_date': str(params.get('end_date') or end_date),
                'requested_model': model, 'status': 'local_store',
                'http_status': int(record.get('http_status') or 200), 'created': False, 'model': model,
                **raw_record_row_common(path, record),
            })
        for left, right in missing_ranges:
            pending_by_window.setdefault((left, right), []).append(point)
            gaps.append({'point_id': str(point.point_id), 'start_date': left, 'end_date': right, 'channel': 'e2_hourly'})

    pending_count = sum(len(x) for x in pending_by_window.values())
    _notify(progress_callback, phase='cache_scan', channel='e2_hourly', start_date=start_date, end_date=end_date,
            cached_records=len(rows), pending_ranges=len(gaps), pending_points=pending_count, local_only=not allow_network)
    if gaps and not allow_network:
        sample = gaps[:12]
        raise LocalClimateStoreGap(
            f'LOCAL_ONLY climate store is missing {len(gaps)} point/date ranges for hourly history; sample={sample}',
            gaps=gaps,
        )

    for (left, right), pending in sorted(pending_by_window.items()):
        pending_df = pd.DataFrame(pending)
        batch_total = (len(pending_df) + max(1, int(batch_size)) - 1) // max(1, int(batch_size))
        for batch_index, batch in enumerate(_chunks(pending_df, batch_size), start=1):
            params = build_archive_parameters(
                latitude=float(batch.iloc[0].latitude), longitude=float(batch.iloc[0].longitude),
                start_date=left, end_date=right, model=model,
            )
            params['latitude'] = ','.join(f'{float(x):.5f}' for x in batch.latitude)
            params['longitude'] = ','.join(f'{float(x):.5f}' for x in batch.longitude)
            endpoint = get_openmeteo_archive_url()
            apikey = get_openmeteo_api_key()
            if apikey: params['apikey'] = apikey
            url = f'{endpoint}?{urlencode(params)}'
            status, payload = fetch_json_with_retry(
                url, timeout_seconds=timeout_seconds, max_retries=max_retries,
                base_backoff_seconds=base_backoff_seconds, cooldown_after_429=cooldown_after_429,
                global_cooldown_seconds=global_cooldown_seconds,
            )
            payloads = _as_payload_list(payload, len(batch))
            retrieved_at = utc_now_iso()
            downloaded = 0
            for (_, point), item in zip(batch.iterrows(), payloads):
                scalar = build_archive_parameters(
                    latitude=float(point.latitude), longitude=float(point.longitude),
                    start_date=left, end_date=right, model=model,
                )
                external_id = f'{model}:{float(point.latitude):.4f}:{float(point.longitude):.4f}:{left}:{right}'
                path, created, content_hash = persist_immutable_raw_record(
                    directory=raw_directory, source='open-meteo', source_service='historical',
                    source_endpoint=endpoint, external_id=external_id, request_parameters=scalar,
                    payload=item, http_status=status, retrieved_at_utc=retrieved_at,
                )
                rows.append({
                    'point_id': str(point.point_id), 'name': str(point.name), 'state': str(point.state),
                    'subsystem_id': str(point.subsystem_id), 'latitude_requested': float(point.latitude),
                    'longitude_requested': float(point.longitude), 'timezone': str(point.timezone), 'weight': float(point.weight),
                    'start_date': left, 'end_date': right, 'requested_model': model, 'status': 'downloaded_gap',
                    'http_status': status, 'request_url': url, 'raw_file': str(path), 'created': bool(created),
                    'content_hash': content_hash, 'retrieved_at_utc': retrieved_at, 'model': model,
                })
                downloaded += int(bool(created))
            _notify(progress_callback, phase='batch_complete', channel='e2_hourly', start_date=left, end_date=right,
                    batch_index=batch_index, batch_total=batch_total, points_in_batch=len(batch), downloaded=downloaded,
                    records_persisted=len(rows), incremental_gap=True)
            if request_delay_seconds > 0:
                time.sleep(float(request_delay_seconds))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(['point_id', 'start_date', 'end_date']).reset_index(drop=True)

def download_hourly_points_annual(
    points: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    raw_directory: str | Path,
    **kwargs: Any,
) -> pd.DataFrame:
    """Download hourly history as immutable per-year cache partitions."""
    root = Path(raw_directory)
    parts: list[pd.DataFrame] = []
    user_callback: ProgressCallback = kwargs.pop('progress_callback', None)
    for year, left, right in annual_date_windows(start_date, end_date):
        print(f'Open-Meteo E2 hourly year={year} window={left}..{right}', flush=True)

        def cb(event: dict[str, Any], *, _year: int = year) -> None:
            event = {**event, 'archive_year': _year}
            _notify(user_callback, **event)

        part = download_hourly_points_batched(
            points,
            start_date=left,
            end_date=right,
            raw_directory=root / f'year={year:04d}',
            progress_callback=cb,
            **kwargs,
        )
        part['archive_year'] = int(year)
        parts.append(part)
        _notify(user_callback, phase='year_complete', channel='e2_hourly', archive_year=year, start_date=left, end_date=right,
                records=int(len(part)), cache_hits=int(part['status'].astype(str).isin(['local_store','cached','cached_after_request']).sum()) if not part.empty else 0)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True).sort_values(['archive_year', 'point_id']).reset_index(drop=True)


def _daily_external_id(channel: str, point: pd.Series, model_label: str, start_date: str, end_date: str) -> str:
    return f'e3:{channel}:{point.point_id}:{model_label}:{start_date}:{end_date}'


def _daily_download_group(
    points: pd.DataFrame,
    *,
    channel: str,
    model: str | None,
    variables: tuple[str, ...],
    start_date: str,
    end_date: str,
    raw_directory: Path,
    timeout_seconds: int,
    batch_size: int,
    request_delay_seconds: float,
    max_retries: int,
    base_backoff_seconds: float,
    cooldown_after_429: int,
    global_cooldown_seconds: float,
    allow_network: bool = True,
    progress_callback: ProgressCallback = None,
) -> list[dict[str, Any]]:
    """Resolve daily E3 inputs LOCAL-FIRST, requesting only uncovered date deltas."""
    rows: list[dict[str, Any]] = []
    model_label = model or 'best_match'
    pending_by_window: dict[tuple[str, str], list[pd.Series]] = {}
    gaps: list[dict[str, Any]] = []
    for _, point in points.iterrows():
        scalar = build_daily_archive_parameters(
            latitude=float(point.latitude), longitude=float(point.longitude), timezone_name=str(point.timezone),
            start_date=start_date, end_date=end_date, variables=variables, model=model,
        )
        local_records, missing_ranges = find_local_records(
            directory=raw_directory, source_service='historical_daily', request_parameters=scalar,
            block_name='daily', start_date=start_date, end_date=end_date,
        )
        for path, record in local_records:
            params = record.get('request_parameters') or {}
            rows.append({
                'channel': channel, 'point_id': str(point.point_id), 'name': str(point.name), 'state': str(point.state),
                'subsystem_id': str(point.subsystem_id), 'latitude_requested': float(point.latitude), 'longitude_requested': float(point.longitude),
                'timezone': str(point.timezone), 'weight': float(point.weight), 'model': model_label, 'variables': list(variables),
                'start_date': str(params.get('start_date') or start_date), 'end_date': str(params.get('end_date') or end_date),
                'created': False, 'cache_hit': True, 'status': 'local_store',
                **raw_record_row_common(path, record),
            })
        for left, right in missing_ranges:
            pending_by_window.setdefault((left, right), []).append(point)
            gaps.append({'point_id': str(point.point_id), 'start_date': left, 'end_date': right, 'channel': channel})

    _notify(progress_callback, phase='cache_scan', channel=channel, timezone='mixed', start_date=start_date, end_date=end_date,
            cached_records=len(rows), pending_ranges=len(gaps), pending_points=sum(len(v) for v in pending_by_window.values()), local_only=not allow_network)
    if gaps and not allow_network:
        sample = gaps[:12]
        raise LocalClimateStoreGap(
            f'LOCAL_ONLY climate store is missing {len(gaps)} point/date ranges for {channel}; sample={sample}',
            gaps=gaps,
        )

    for (left, right), pending in sorted(pending_by_window.items()):
        pending_df = pd.DataFrame(pending)
        batch_total = (len(pending_df) + max(1, int(batch_size)) - 1) // max(1, int(batch_size))
        for batch_index, batch in enumerate(_chunks(pending_df, batch_size), start=1):
            first = batch.iloc[0]
            params = build_daily_archive_parameters(
                latitude=float(first.latitude), longitude=float(first.longitude), timezone_name=str(first.timezone),
                start_date=left, end_date=right, variables=variables, model=model,
            )
            params['latitude'] = ','.join(f'{float(x):.5f}' for x in batch.latitude)
            params['longitude'] = ','.join(f'{float(x):.5f}' for x in batch.longitude)
            params['timezone'] = ','.join(str(x) for x in batch.timezone)
            endpoint = get_openmeteo_archive_url()
            apikey = get_openmeteo_api_key()
            if apikey: params['apikey'] = apikey
            url = f'{endpoint}?{urlencode(params)}'
            status, payload = fetch_json_with_retry(
                url, timeout_seconds=timeout_seconds, max_retries=max_retries,
                base_backoff_seconds=base_backoff_seconds, cooldown_after_429=cooldown_after_429,
                global_cooldown_seconds=global_cooldown_seconds,
            )
            payloads = _as_payload_list(payload, len(batch))
            retrieved_at = utc_now_iso()
            downloaded = 0
            for (_, point), item in zip(batch.iterrows(), payloads):
                scalar = build_daily_archive_parameters(
                    latitude=float(point.latitude), longitude=float(point.longitude), timezone_name=str(point.timezone),
                    start_date=left, end_date=right, variables=variables, model=model,
                )
                external_id = _daily_external_id(channel, point, model_label, left, right)
                path, created, content_hash = persist_immutable_raw_record(
                    directory=raw_directory, source='open-meteo', source_service='historical_daily', source_endpoint=endpoint,
                    external_id=external_id, request_parameters=scalar, payload=item, http_status=status, retrieved_at_utc=retrieved_at,
                )
                rows.append({
                    'channel': channel, 'point_id': str(point.point_id), 'name': str(point.name), 'state': str(point.state),
                    'subsystem_id': str(point.subsystem_id), 'latitude_requested': float(point.latitude), 'longitude_requested': float(point.longitude),
                    'timezone': str(point.timezone), 'weight': float(point.weight), 'model': model_label, 'variables': list(variables),
                    'start_date': left, 'end_date': right, 'raw_file': str(path), 'created': bool(created),
                    'content_hash': content_hash, 'retrieved_at_utc': retrieved_at, 'request_url': url,
                    'cache_hit': not bool(created), 'status': 'downloaded_gap',
                })
                downloaded += int(bool(created))
            _notify(progress_callback, phase='batch_complete', channel=channel, timezone='mixed', start_date=left, end_date=right,
                    batch_index=batch_index, batch_total=batch_total, points_in_batch=len(batch), downloaded=downloaded,
                    records_persisted=len(rows), incremental_gap=True)
            if request_delay_seconds > 0:
                time.sleep(float(request_delay_seconds))
    return rows

def _download_daily_annual_channel(
    points: pd.DataFrame,
    *,
    channel: str,
    model: str | None,
    variables: tuple[str, ...],
    start_date: str,
    end_date: str,
    raw_directory: Path,
    timeout_seconds: int,
    batch_size: int,
    request_delay_seconds: float,
    max_retries: int,
    base_backoff_seconds: float,
    cooldown_after_429: int,
    global_cooldown_seconds: float,
    allow_network: bool = True,
    progress_callback: ProgressCallback = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for year, left, right in annual_date_windows(start_date, end_date):
        print(f'Open-Meteo E3 {channel} year={year} window={left}..{right}', flush=True)

        def cb(event: dict[str, Any], *, _year: int = year) -> None:
            event = {**event, 'archive_year': _year}
            _notify(progress_callback, **event)

        part = _daily_download_group(
            points, channel=channel, model=model, variables=variables,
            start_date=left, end_date=right,
            raw_directory=raw_directory / channel / f'year={year:04d}',
            timeout_seconds=timeout_seconds, batch_size=batch_size,
            request_delay_seconds=request_delay_seconds, max_retries=max_retries,
            base_backoff_seconds=base_backoff_seconds,
            cooldown_after_429=cooldown_after_429,
            global_cooldown_seconds=global_cooldown_seconds,
            allow_network=allow_network,
            progress_callback=cb,
        )
        for row in part:
            row['archive_year'] = int(year)
        rows.extend(part)
        _notify(progress_callback, phase='year_complete', channel=channel, archive_year=year, start_date=left, end_date=right,
                records=len(part), cache_hits=sum(bool(x.get('cache_hit')) for x in part))
    return rows


def download_e3_multiyear_batched(
    points: pd.DataFrame,
    *,
    target_start_date: str | None,
    target_end_date: str | None,
    baseline_start_date: str,
    baseline_end_date: str,
    raw_directory: str | Path,
    timeout_seconds: int = 90,
    batch_size: int = 6,
    daily_batch_size: int | None = None,
    request_delay_seconds: float = 2.0,
    max_retries: int = 10,
    base_backoff_seconds: float = 10.0,
    cooldown_after_429: int = 3,
    global_cooldown_seconds: float = 90.0,
    allow_network: bool = True,
    progress_callback: ProgressCallback = None,
) -> pd.DataFrame:
    """Download E3 daily inputs year by year.

    Baseline and target channels are stored separately under ``year=YYYY``. The
    resulting manifest can span many years; downstream E3 preparation concatenates
    these non-overlapping annual records locally to build rolling baselines.
    """
    raw_directory = Path(raw_directory)
    rows: list[dict[str, Any]] = []
    rows.extend(_download_daily_annual_channel(
        points, channel='baseline_temperature', model='era5_land', variables=BASELINE_DAILY_VARIABLES,
        start_date=baseline_start_date, end_date=baseline_end_date, raw_directory=raw_directory,
        timeout_seconds=timeout_seconds, batch_size=int(daily_batch_size or batch_size), request_delay_seconds=request_delay_seconds,
        max_retries=max_retries, base_backoff_seconds=base_backoff_seconds,
        cooldown_after_429=cooldown_after_429, global_cooldown_seconds=global_cooldown_seconds,
        allow_network=allow_network, progress_callback=progress_callback,
    ))
    if (target_start_date is None) != (target_end_date is None):
        raise ValueError('target_start_date and target_end_date must both be provided or both omitted')
    if target_start_date is not None and target_end_date is not None:
        rows.extend(_download_daily_annual_channel(
            points, channel='target_snapshot_daily', model=None, variables=TARGET_SNAPSHOT_DAILY_VARIABLES,
            start_date=target_start_date, end_date=target_end_date, raw_directory=raw_directory,
            timeout_seconds=timeout_seconds, batch_size=int(daily_batch_size or batch_size), request_delay_seconds=request_delay_seconds,
            max_retries=max_retries, base_backoff_seconds=base_backoff_seconds,
            cooldown_after_429=cooldown_after_429, global_cooldown_seconds=global_cooldown_seconds,
            allow_network=allow_network, progress_callback=progress_callback,
        ))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(['channel', 'archive_year', 'point_id']).reset_index(drop=True)
