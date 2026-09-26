#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import socket
import subprocess
import time
import urllib.request
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor_sin.climate.e2_pilot import load_pilot_points, canonical_zone, write_manifest
from motor_sin.climate.batch_openmeteo import download_hourly_points_annual, download_e3_multiyear_batched
from motor_sin.climate.http_client import OpenMeteoRateLimitDeferred, rate_limit_stats, reset_rate_limit_state
from motor_sin.climate.local_store import LocalClimateStoreGap
from motor_sin.climate.annual_cache import seed_annual_cache_from_legacy
from motor_sin.climate.openmeteo import get_openmeteo_archive_url
from motor_sin.common.io import read_table, write_json
from motor_sin.common.provenance import utc_now_iso


def _load_bounds(
    load: pd.DataFrame,
    subsystem: str,
    start_year: int,
    end_year: int,
    timezone: str,
    archive_lag_days: int = 5,
) -> tuple[str, str]:
    zone = canonical_zone(subsystem)
    x = load.copy()
    x['subsystem_id'] = x['subsystem_id'].map(canonical_zone)
    x['interval_start_utc'] = pd.to_datetime(x['interval_start_utc'], utc=True, errors='raise')
    x = x[x.subsystem_id.eq(zone)]
    if x.empty:
        raise ValueError(f'no load rows for {zone}')
    local = x['interval_start_utc'].dt.tz_convert(ZoneInfo(timezone))
    min_d = max(local.min().date(), pd.Timestamp(f'{start_year}-01-01').date())
    # Standard-library timedelta avoids NumPy/Pandas generic-unit deprecation warnings.
    archive_cutoff = (pd.Timestamp.now(tz=ZoneInfo(timezone)).to_pydatetime() - timedelta(days=int(archive_lag_days))).date()
    max_d = min(local.max().date(), pd.Timestamp(f'{end_year}-12-31').date(), archive_cutoff)
    if max_d < min_d:
        raise ValueError(f'no load/climate overlap for {zone}: {min_d}..{max_d}')
    return min_d.isoformat(), max_d.isoformat()


def _atomic_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')
    tmp.replace(path)


def _reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def _start_arco_proxy(startup_timeout: float = 90.0) -> tuple[subprocess.Popen, str]:
    script = Path(__file__).with_name('62_arco_openmeteo_proxy.py')
    if not script.exists():
        raise FileNotFoundError(
            f'ARCO compatibility proxy ausente: {script}. '
            'Copie scripts/62_arco_openmeteo_proxy.py para o projeto.'
        )
    port = _reserve_local_port()
    cmd = [sys.executable, str(script), '--host', '127.0.0.1', '--port', str(port)]
    print('PREDICTA_ARCO_START: ' + ' '.join(cmd), flush=True)
    proc = subprocess.Popen(cmd, text=True)
    health = f'http://127.0.0.1:{port}/healthz'
    deadline = time.time() + float(startup_timeout)
    last_error = None
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f'ARCO proxy encerrou durante startup (exit={proc.returncode})')
        try:
            with urllib.request.urlopen(health, timeout=2.0) as response:
                if int(response.status) == 200:
                    url = f'http://127.0.0.1:{port}/v1/archive'
                    print(f'PREDICTA_ARCO_READY: {url}', flush=True)
                    return proc, url
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    raise RuntimeError(f'ARCO proxy não ficou pronto em {startup_timeout}s: {last_error}')


def _stop_arco_proxy(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def main() -> None:
    p = argparse.ArgumentParser(
        description='Download multi-year 0.1-degree climate year-by-year with point cache, batch checkpoints and shared 429 cooldown.'
    )
    p.add_argument('--load', default='data/processed/demand/load_hourly.parquet')
    p.add_argument('--points', required=True)
    p.add_argument('--subsystem', required=True)
    p.add_argument('--start-year', type=int, required=True)
    p.add_argument('--end-year', type=int, required=True)
    p.add_argument('--calendar-timezone', default='America/Sao_Paulo')
    p.add_argument('--e2-raw-dir', required=True)
    p.add_argument('--e2-manifest', required=True)
    p.add_argument('--e3-raw-dir', required=True)
    p.add_argument('--e3-manifest', required=True)
    p.add_argument('--legacy-e2-raw-dir', help='Optional v1.10 multi-year RAW directory to split locally into annual cache before downloading.')
    p.add_argument('--legacy-e3-raw-dir', help='Optional v1.10 multi-year E3 RAW directory to split locally into annual cache before downloading.')
    p.add_argument('--archive-lag-days', type=int, default=5, help='Historical feed capped this many days behind now.')
    p.add_argument('--archive-url', help='Override historical endpoint, e.g. http://127.0.0.1:8080/v1/archive for a self-hosted Open-Meteo archive.')
    p.add_argument('--history-mode', choices=['local-first','local-only'], default='local-first', help='local-first uses local Climate Store and downloads only gaps; local-only forbids historical network access.')
    p.add_argument('--history-backend', choices=['auto','arco','openmeteo','openmeteo-fallback-arco'], default='auto', help='Historical provider. auto/arco route missing cache through local ARCO adapter; openmeteo keeps legacy Archive API; openmeteo-fallback-arco switches to ARCO after rate-limit defer.')
    p.add_argument('--arco-proxy-startup-timeout', type=float, default=90.0)
    p.add_argument('--batch-size', type=int, default=6, help='Coordinates per request for hourly history.')
    p.add_argument('--daily-batch-size', type=int, default=24, help='Coordinates per request for daily E3/baseline. Larger than hourly to cut request count.')
    p.add_argument('--request-delay', type=float, default=2.0, help='Pause after every successful spatial batch.')
    p.add_argument('--max-retries', type=int, default=10)
    p.add_argument('--backoff', type=float, default=10.0)
    p.add_argument('--cooldown-after-429', type=int, default=3, help='Consecutive 429s before a process-wide cooldown.')
    p.add_argument('--cooldown-seconds', type=float, default=90.0)
    p.add_argument('--timeout', type=int, default=120)
    p.add_argument('--checkpoint', help='Progress JSON. Defaults next to --report.')
    p.add_argument('--report', required=True)
    a = p.parse_args()
    if a.archive_url:
        os.environ['PREDICTA_OPENMETEO_ARCHIVE_URL']=str(a.archive_url).strip()

    if a.end_year < a.start_year:
        raise SystemExit('end-year must be >= start-year')
    if a.batch_size < 1:
        raise SystemExit('batch-size must be >= 1')
    if a.daily_batch_size < 1:
        raise SystemExit('daily-batch-size must be >= 1')

    report_path = Path(a.report)
    checkpoint_path = Path(a.checkpoint) if a.checkpoint else report_path.with_name(report_path.stem + '_checkpoint.json')
    load = read_table(a.load)
    start_date, end_date = _load_bounds(load, a.subsystem, a.start_year, a.end_year, a.calendar_timezone, a.archive_lag_days)
    points = load_pilot_points(a.points, subsystem_id=a.subsystem)
    target_start_year = int(pd.Timestamp(start_date).year)
    target_end_year = int(pd.Timestamp(end_date).year)
    baseline_start = f'{target_start_year - 10}-01-01'
    baseline_end = f'{target_end_year - 1}-12-31'


    # PREDICTA_CLIMATE_FAST_RESUME_V1
    # If the exact requested climate slice was already materialized and its
    # manifests still exist, do not start ARCO/Open-Meteo or re-scan thousands
    # of annual point RAW files. A changed load bound / date / point count
    # automatically invalidates this shortcut.
    _fast_report = Path(a.report)
    _fast_e2_manifest = Path(a.e2_manifest)
    _fast_e3_manifest = Path(a.e3_manifest)
    if _fast_report.exists() and _fast_e2_manifest.exists() and _fast_e3_manifest.exists():
        try:
            _prev = json.loads(_fast_report.read_text(encoding='utf-8'))
            _expected_target_years = list(range(target_start_year, target_end_year + 1))
            _expected_baseline_years = list(range(target_start_year - 10, target_end_year))
            _same = (
                str(_prev.get('subsystem_id')) == str(canonical_zone(a.subsystem))
                and int(_prev.get('points', -1)) == int(len(points))
                and str(_prev.get('start_date')) == str(start_date)
                and str(_prev.get('end_date')) == str(end_date)
                and list(_prev.get('target_years', [])) == _expected_target_years
                and list(_prev.get('baseline_years', [])) == _expected_baseline_years
                and int(_prev.get('e2_records', 0)) > 0
                and int(_prev.get('e3_records', 0)) > 0
                and _fast_e2_manifest.stat().st_size > 2
                and _fast_e3_manifest.stat().st_size > 2
            )
            _points_mtime = Path(a.points).stat().st_mtime if Path(a.points).exists() else 0.0
            _report_mtime = _fast_report.stat().st_mtime
            if _points_mtime > _report_mtime:
                _same = False

            if _same:
                print(
                    f'PREDICTA_CLIMATE_FAST_REUSE: '
                    f'{canonical_zone(a.subsystem)} {start_date}..{end_date}; '
                    f'points={len(points)}; existing E2/E3 manifests accepted; '
                    f'network/proxy/cache-rescan skipped',
                    flush=True,
                )
                return
        except Exception as _fast_exc:
            print(
                f'PREDICTA_CLIMATE_FAST_REUSE_MISS: '
                f'{type(_fast_exc).__name__}: {_fast_exc}; doing normal validation',
                flush=True,
            )

    checkpoint: dict = {
        'schema_version': 'openmeteo_annual_checkpoint_v1',
        'status': 'RUNNING',
        'subsystem_id': canonical_zone(a.subsystem),
        'started_at_utc': utc_now_iso(),
        'updated_at_utc': utc_now_iso(),
        'target_window': {'start': start_date, 'end': end_date},
        'baseline_window': {'start': baseline_start, 'end': baseline_end},
        'points': int(len(points)),
        'policy': {
            'cache_partition': 'channel/year/point',
            'checkpoint_granularity': 'batch',
            'batch_size_hourly': a.batch_size,
            'batch_size_daily': a.daily_batch_size,
            'archive_endpoint': get_openmeteo_archive_url(),
            'history_mode': a.history_mode,
            'history_backend_requested': a.history_backend,
            'request_delay_seconds': a.request_delay,
            'max_retries': a.max_retries,
            'base_backoff_seconds': a.backoff,
            'cooldown_after_429': a.cooldown_after_429,
            'cooldown_seconds': a.cooldown_seconds,
        },
        'years': {},
        'last_events': [],
    }
    _atomic_json(checkpoint, checkpoint_path)

    def progress(event: dict) -> None:
        channel = str(event.get('channel', 'unknown'))
        year = str(event.get('archive_year', 'unknown'))
        timezone_name = str(event.get('timezone', 'all'))
        key = f'{channel}:{year}:{timezone_name}'
        checkpoint['years'].setdefault(key, {})
        checkpoint['years'][key].update({k: v for k, v in event.items() if k not in {'channel', 'archive_year'}})
        checkpoint['years'][key]['channel'] = channel
        checkpoint['years'][key]['archive_year'] = event.get('archive_year')
        checkpoint['updated_at_utc'] = utc_now_iso()
        checkpoint['rate_limit'] = rate_limit_stats()
        checkpoint['last_events'] = (checkpoint.get('last_events', []) + [{**event, 'at_utc': utc_now_iso()}])[-40:]
        _atomic_json(checkpoint, checkpoint_path)
        phase = event.get('phase')
        if phase == 'batch_complete':
            print(
                f"checkpoint {channel} {year}: batch {event.get('batch_index')}/{event.get('batch_total')} complete; "
                f"points={event.get('points_in_batch')} downloaded={event.get('downloaded')}",
                flush=True,
            )
        elif phase == 'year_complete':
            print(
                f"checkpoint {channel} {year}: YEAR COMPLETE records={event.get('records')} cache_hits={event.get('cache_hits')}",
                flush=True,
            )

    reset_rate_limit_state()
    try:
        migration = seed_annual_cache_from_legacy(
            legacy_e2_directory=a.legacy_e2_raw_dir, legacy_e3_directory=a.legacy_e3_raw_dir,
            annual_e2_directory=a.e2_raw_dir, annual_e3_directory=a.e3_raw_dir,
        )
        checkpoint['legacy_cache_migration'] = migration
        _atomic_json(checkpoint, checkpoint_path)
        if migration['e2']['created'] or migration['e3']['created']:
            print(f"Legacy v1.10 RAW converted locally to annual cache: {migration}", flush=True)
        print(
            f'[{canonical_zone(a.subsystem)}] annual climate cache: target={start_date}..{end_date}; '
            f'baseline={baseline_start}..{baseline_end}; points={len(points)}',
            flush=True,
        )
        proxy_proc: subprocess.Popen | None = None
        original_archive_env = os.environ.get('PREDICTA_OPENMETEO_ARCHIVE_URL')
        effective_backend = 'local-only' if a.history_mode == 'local-only' else a.history_backend
        effective_archive_endpoint = get_openmeteo_archive_url()
        fallback_used = False

        def run_download_pass() -> tuple[pd.DataFrame, pd.DataFrame]:
            reset_rate_limit_state()
            e2_pass = download_hourly_points_annual(
                points,
                start_date=start_date,
                end_date=end_date,
                raw_directory=a.e2_raw_dir,
                model='era5_seamless',
                timeout_seconds=a.timeout,
                batch_size=a.batch_size,
                request_delay_seconds=a.request_delay,
                max_retries=a.max_retries,
                base_backoff_seconds=a.backoff,
                cooldown_after_429=a.cooldown_after_429,
                global_cooldown_seconds=a.cooldown_seconds,
                allow_network=a.history_mode != 'local-only',
                progress_callback=progress,
            )
            write_manifest(e2_pass, a.e2_manifest)
            e3_pass = download_e3_multiyear_batched(
                points,
                target_start_date=start_date,
                target_end_date=end_date,
                baseline_start_date=baseline_start,
                baseline_end_date=baseline_end,
                raw_directory=a.e3_raw_dir,
                timeout_seconds=a.timeout,
                batch_size=a.batch_size,
                daily_batch_size=a.daily_batch_size,
                request_delay_seconds=a.request_delay,
                max_retries=a.max_retries,
                base_backoff_seconds=a.backoff,
                cooldown_after_429=a.cooldown_after_429,
                global_cooldown_seconds=a.cooldown_seconds,
                allow_network=a.history_mode != 'local-only',
                progress_callback=progress,
            )
            write_manifest(e3_pass, a.e3_manifest)
            return e2_pass, e3_pass

        try:
            if a.history_mode == 'local-only':
                print('PREDICTA_CLIMATE_BACKEND: LOCAL ONLY; nenhuma rede histórica permitida', flush=True)
                e2, e3 = run_download_pass()
            elif a.history_backend in {'auto', 'arco'}:
                # ARCO-first is the default for historical materialization. Existing
                # point/year cache is still reused before any network request by the
                # existing batch_openmeteo layer. Only cache gaps hit this local proxy.
                proxy_proc, proxy_url = _start_arco_proxy(a.arco_proxy_startup_timeout)
                os.environ['PREDICTA_OPENMETEO_ARCHIVE_URL'] = proxy_url
                effective_backend = 'arco'
                effective_archive_endpoint = proxy_url
                checkpoint['policy']['archive_endpoint'] = proxy_url
                checkpoint['policy']['history_backend_effective'] = 'arco'
                _atomic_json(checkpoint, checkpoint_path)
                print('PREDICTA_CLIMATE_BACKEND: histórico faltante -> ERA5-Land/ERA5 ARCO', flush=True)
                e2, e3 = run_download_pass()
            elif a.history_backend == 'openmeteo':
                effective_backend = 'openmeteo'
                print('PREDICTA_CLIMATE_BACKEND: Open-Meteo Archive (modo legado explícito)', flush=True)
                e2, e3 = run_download_pass()
            elif a.history_backend == 'openmeteo-fallback-arco':
                effective_backend = 'openmeteo'
                print('PREDICTA_CLIMATE_BACKEND: Open-Meteo com fallback ARCO', flush=True)
                try:
                    e2, e3 = run_download_pass()
                except OpenMeteoRateLimitDeferred as rate_exc:
                    fallback_used = True
                    checkpoint['last_events'] = (checkpoint.get('last_events', []) + [{
                        'phase': 'backend_fallback',
                        'from': 'openmeteo',
                        'to': 'arco',
                        'reason': f'{type(rate_exc).__name__}: {rate_exc}',
                        'at_utc': utc_now_iso(),
                    }])[-40:]
                    _atomic_json(checkpoint, checkpoint_path)
                    print('PREDICTA_ARCO_FALLBACK: Open-Meteo rate limit -> ARCO; caches concluídos serão reaproveitados', flush=True)
                    proxy_proc, proxy_url = _start_arco_proxy(a.arco_proxy_startup_timeout)
                    os.environ['PREDICTA_OPENMETEO_ARCHIVE_URL'] = proxy_url
                    effective_backend = 'arco'
                    effective_archive_endpoint = proxy_url
                    checkpoint['policy']['archive_endpoint'] = proxy_url
                    checkpoint['policy']['history_backend_effective'] = 'arco'
                    checkpoint['policy']['fallback_used'] = True
                    _atomic_json(checkpoint, checkpoint_path)
                    e2, e3 = run_download_pass()
            else:
                raise ValueError(f'history-backend inválido: {a.history_backend}')
        finally:
            _stop_arco_proxy(proxy_proc)
            if original_archive_env is None:
                os.environ.pop('PREDICTA_OPENMETEO_ARCHIVE_URL', None)
            else:
                os.environ['PREDICTA_OPENMETEO_ARCHIVE_URL'] = original_archive_env

        e2_cache_hits = int(e2['status'].astype(str).isin(['local_store','cached','cached_after_request']).sum()) if not e2.empty and 'status' in e2 else 0
        e3_cache_hits = int(e3.get('cache_hit', pd.Series(dtype=bool)).fillna(False).sum()) if not e3.empty else 0
        payload = {
            'subsystem_id': canonical_zone(a.subsystem),
            'points': int(len(points)),
            'start_date': start_date,
            'end_date': end_date,
            'target_years': list(range(target_start_year, target_end_year + 1)),
            'baseline_years': list(range(target_start_year - 10, target_end_year)),
            'e2_records': int(len(e2)),
            'e3_records': int(len(e3)),
            'e2_annual_partitions': sorted(int(x) for x in e2.get('archive_year', pd.Series(dtype=int)).dropna().unique()),
            'e3_annual_partitions': sorted(int(x) for x in e3.get('archive_year', pd.Series(dtype=int)).dropna().unique()),
            'batch_size_hourly': a.batch_size,
            'batch_size_daily': a.daily_batch_size,
            'archive_endpoint': effective_archive_endpoint,
            'history_mode': a.history_mode,
            'history_backend_requested': a.history_backend,
            'history_backend_effective': effective_backend,
            'arco_fallback_used': fallback_used,
            'arco_provenance': {
                'core': 'ERA5-Land ARCO 0.1°',
                'wind_gust': 'ERA5 single-level ARCO 0.25° nearest-neighbour when requested',
                'adapter_contract': 'Open-Meteo-compatible local HTTP response; existing annual point cache/manifests unchanged',
            } if effective_backend == 'arco' else None,
            'request_delay_seconds': a.request_delay,
            'max_retries': a.max_retries,
            'cooldown_after_429': a.cooldown_after_429,
            'cooldown_seconds': a.cooldown_seconds,
            'archive_lag_days': a.archive_lag_days,
            'cache_hits_e2': e2_cache_hits,
            'cache_hits_e3': e3_cache_hits,
            'rate_limit': rate_limit_stats(),
            'spatial_resolution_deg': 0.1,
            'cache_layout': 'persistent local Climate Store / annual/channel/point + incremental current-year deltas',
            'resume_policy': 'LOCAL_FIRST; cache hits are reused; only uncovered point/date ranges access the selected historical backend',
            'points_file': a.points,
            'e2_manifest': a.e2_manifest,
            'e3_manifest': a.e3_manifest,
            'checkpoint': str(checkpoint_path),
            'legacy_cache_migration': checkpoint.get('legacy_cache_migration', {}),
        }
        write_json(payload, a.report)
        checkpoint['status'] = 'SUCCESS'
        checkpoint['finished_at_utc'] = utc_now_iso()
        checkpoint['updated_at_utc'] = checkpoint['finished_at_utc']
        checkpoint['rate_limit'] = rate_limit_stats()
        _atomic_json(checkpoint, checkpoint_path)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    except LocalClimateStoreGap as exc:
        checkpoint['status'] = 'MISSING_LOCAL_HISTORY'
        checkpoint['error'] = f'{type(exc).__name__}: {exc}'
        checkpoint['updated_at_utc'] = utc_now_iso()
        checkpoint['local_store_gaps'] = exc.gaps[:200]
        _atomic_json(checkpoint, checkpoint_path)
        missing_report = {'status':'MISSING_LOCAL_HISTORY','subsystem_id':canonical_zone(a.subsystem),'checkpoint':str(checkpoint_path),'history_mode':a.history_mode,'missing_ranges':len(exc.gaps),'sample_gaps':exc.gaps[:20],'message':str(exc)}
        write_json(missing_report, a.report)
        print('PREDICTA_LOCAL_HISTORY_MISSING ' + json.dumps(missing_report, ensure_ascii=False), flush=True)
        raise SystemExit(76)
    except OpenMeteoRateLimitDeferred as exc:
        checkpoint['status'] = 'WAITING_RATE_LIMIT'
        checkpoint['error'] = f'{type(exc).__name__}: {exc}'
        checkpoint['resume_after_seconds'] = float(exc.retry_after_seconds or 900.0)
        checkpoint['updated_at_utc'] = utc_now_iso()
        checkpoint['rate_limit'] = rate_limit_stats()
        _atomic_json(checkpoint, checkpoint_path)
        waiting_report = {
            'status': 'WAITING_RATE_LIMIT',
            'subsystem_id': canonical_zone(a.subsystem),
            'checkpoint': str(checkpoint_path),
            'resume_after_seconds': checkpoint['resume_after_seconds'],
            'rate_limit': checkpoint['rate_limit'],
            'archive_endpoint': get_openmeteo_archive_url(),
            'message': str(exc),
        }
        write_json(waiting_report, a.report)
        print('PREDICTA_RATE_LIMIT_DEFERRED ' + json.dumps(waiting_report, ensure_ascii=False), flush=True)
        raise SystemExit(75)
    except Exception as exc:
        checkpoint['status'] = 'FAILED'
        checkpoint['error'] = f'{type(exc).__name__}: {exc}'
        checkpoint['updated_at_utc'] = utc_now_iso()
        checkpoint['rate_limit'] = rate_limit_stats()
        _atomic_json(checkpoint, checkpoint_path)
        raise


if __name__ == '__main__':
    main()
