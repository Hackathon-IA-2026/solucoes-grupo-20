from __future__ import annotations

import json
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from motor_sin.sources.ons_dessem import SOURCE as DESSEM_SOURCE

from .pressure import contextual_demand_percentile


def _canonical_zone(value: str) -> str:
    raw = str(value).strip().upper()
    return {'SE': 'SE/CO', 'SECO': 'SE/CO'}.get(raw, raw)


def _local_hour_month(ts: pd.Series, timezone_name: str) -> tuple[pd.Series, pd.Series]:
    local = pd.to_datetime(ts, utc=True, errors='raise').dt.tz_convert(ZoneInfo(timezone_name))
    return local.dt.hour, local.dt.month


def _percentile(arr: pd.Series, value: float) -> float:
    a = pd.to_numeric(arr, errors='coerce').dropna().to_numpy(float)
    if len(a) == 0:
        return 0.5
    return float(np.mean(a <= float(value)))


def _generation_json_from_supply(row: pd.Series) -> str:
    mapping = {
        'HYDRO': 'generation_hydro_mw',
        'THERMAL': 'generation_thermal_mw',
        'WIND': 'generation_wind_mw',
        'SOLAR': 'generation_solar_mw',
    }
    out: dict[str, float] = {}
    for k, c in mapping.items():
        if c in row.index and pd.notna(row[c]):
            out[k] = float(row[c])
    return json.dumps(out, ensure_ascii=False, sort_keys=True)


def enrich_signal_with_dessem(
    signal: pd.DataFrame,
    schedule: pd.DataFrame | None,
    *,
    issue_time_utc: pd.Timestamp | None,
    allow_replay: bool = False,
    required: bool = False,
) -> pd.DataFrame:
    if schedule is None or schedule.empty:
        if required:
            raise ValueError('DESSEM_REQUIRED: prepare the official schedule before simulating the product')
        return signal
    columns = {
        'interval_start_utc', 'subsystem_id', 'programmed_load_mw',
        'source', 'available_at_utc', 'source_url', 'snapshot_sha256',
    }
    missing = sorted(columns - set(schedule.columns))
    if missing:
        raise ValueError(f'DESSEM missing canonical columns: {missing}')
    source = schedule.copy()
    for column in ['interval_start_utc', 'available_at_utc']:
        source[column] = pd.to_datetime(source[column], errors='raise')
        if source[column].dt.tz is None:
            raise ValueError(f'DESSEM {column} must include a timezone')
        source[column] = source[column].dt.tz_convert('UTC')
    source['subsystem_id'] = source['subsystem_id'].map(_canonical_zone)
    if source.duplicated(['interval_start_utc', 'subsystem_id']).any():
        raise ValueError('DESSEM contains duplicate subsystem-hour snapshots')
    issue = pd.Timestamp(issue_time_utc) if issue_time_utc is not None else None
    if issue is not None and (pd.isna(issue) or issue.tzinfo is None):
        raise ValueError('DESSEM requires an explicit timezone-aware forecast issue time')
    output = signal.copy()
    source = source.set_index(['interval_start_utc', 'subsystem_id'])
    for zone, group in output.groupby('zone_id'):
        target_times = pd.to_datetime(group['interval_start_utc'], utc=True)
        index = pd.MultiIndex.from_arrays([target_times, [_canonical_zone(zone)] * len(group)], names=source.index.names)
        selected = source.reindex(index)
        programmed = pd.to_numeric(selected['programmed_load_mw'], errors='coerce').to_numpy(float)
        demand = pd.to_numeric(group['demand_p50_mw'], errors='coerce').to_numpy(float)
        complete = (
            len(group) == 24 and target_times.nunique() == 24
            and target_times.sort_values().diff().dropna().eq(pd.Timedelta(hours=1)).all()
            and target_times.dt.floor('h').eq(target_times).all()
            and np.isfinite(programmed).all() and (programmed > 0).all()
            and np.isfinite(demand).all() and (demand >= 0).all()
            and selected['source'].eq(DESSEM_SOURCE).all()
            and selected['source_url'].fillna('').str.len().gt(0).all()
            and selected['snapshot_sha256'].fillna('').str.fullmatch(r'[0-9a-f]{64}').all()
            and selected['available_at_utc'].notna().all()
        )
        asof = bool(
            complete and issue is not None
            and selected['available_at_utc'].le(issue).all()
            and target_times.gt(issue).all()
        )
        reason = 'DESSEM_INCOMPLETE_OR_INVALID_WINDOW' if not complete else 'DESSEM_NOT_AVAILABLE_AT_ISSUE'
        enabled = bool(complete and (asof or allow_replay))
        if not enabled and required:
            raise ValueError(f'{reason}: {zone} needs 24 complete DESSEM hours for this simulation')
        for position, row_index in enumerate(group.index):
            flags = set(json.loads(output.at[row_index, 'quality_flags']))
            flags = {flag for flag in flags if not flag.startswith('DESSEM_')}
            drivers = json.loads(output.at[row_index, 'main_drivers_json'])
            if not isinstance(drivers, dict):
                drivers = {'forecast_drivers': drivers}
            drivers.pop('dessem', None)
            if enabled:
                record = selected.iloc[position]
                pressure = float(demand[position] / (demand[position] + programmed[position]))
                output.at[row_index, 'supply_pressure'] = pressure
                flags.discard('SUPPLY_PRESSURE_UNAVAILABLE')
                flags.add('DESSEM_SCHEDULE_COMPARISON_PROXY')
                if not asof:
                    flags.add('DESSEM_REPLAY_NOT_ASOF')
                drivers['dessem'] = {
                    'source': DESSEM_SOURCE,
                    'programmed_load_mw': float(programmed[position]),
                    'predicta_load_mw': float(demand[position]),
                    'relative_gap_pct': float(100 * (demand[position] / programmed[position] - 1)),
                    'pressure': pressure,
                    'method': 'D_OVER_D_PLUS_PROGRAMMED_LOAD',
                    'mode': 'ASOF' if asof else 'RETROSPECTIVE_SCENARIO',
                    'available_at_utc': record['available_at_utc'].isoformat(),
                    'forecast_issue_time_utc': issue.isoformat() if issue is not None else None,
                    'source_url': record['source_url'],
                    'snapshot_sha256': record['snapshot_sha256'],
                }
            else:
                output.at[row_index, 'supply_pressure'] = None
                flags.update({'SUPPLY_PRESSURE_UNAVAILABLE', reason})
            output.at[row_index, 'main_drivers_json'] = json.dumps(drivers, ensure_ascii=False, sort_keys=True)
            output.at[row_index, 'quality_flags'] = json.dumps(sorted(flags), ensure_ascii=False)
    return output


def build_real_system_signal(
    *,
    forecast: pd.DataFrame,
    load_history: pd.DataFrame,
    climate_context: pd.DataFrame | None,
    run_id: str,
    calendar_timezone: str = 'America/Sao_Paulo',
    observed_supply_backtest: pd.DataFrame | None = None,
    dessem_schedule: pd.DataFrame | None = None,
    allow_dessem_replay: bool = False,
    require_dessem: bool = False,
) -> pd.DataFrame:
    """Build a contract-valid pilot system_signal_v1 from the selected demand forecast.

    DESSEM optionally supplies an experimental comparison with programmed demand, not a
    capacity or reserve estimate. Observed generation remains retrospective context only.
    """
    f = forecast.copy()
    rename = {'p10_mw': 'demand_p10_mw', 'p50_mw': 'demand_p50_mw', 'p90_mw': 'demand_p90_mw', 'weather_mode': 'forecast_weather_mode'}
    f = f.rename(columns={k: v for k, v in rename.items() if k in f.columns})
    required = {'interval_start_utc', 'subsystem_id', 'demand_p10_mw', 'demand_p50_mw', 'demand_p90_mw'}
    missing = sorted(required - set(f.columns))
    if missing:
        raise ValueError(f'forecast missing columns: {missing}')
    f['interval_start_utc'] = pd.to_datetime(f['interval_start_utc'], utc=True, errors='raise')
    f['subsystem_id'] = f['subsystem_id'].astype(str).map(_canonical_zone)
    if f.duplicated(['interval_start_utc', 'subsystem_id']).any():
        raise ValueError('forecast has duplicate subsystem-hour rows')
    if 'issue_time_utc' in f:
        issues = pd.to_datetime(f['issue_time_utc'], utc=True, errors='raise').drop_duplicates()
        if len(issues) != 1:
            raise ValueError('system signal build requires exactly one forecast issue_time')
        issue_time = issues.iloc[0]
    else:
        issue_time = f['interval_start_utc'].min() - pd.Timedelta(hours=1)

    h = load_history.copy()
    h['interval_start_utc'] = pd.to_datetime(h['interval_start_utc'], utc=True, errors='raise')
    h['subsystem_id'] = h['subsystem_id'].astype(str).map(_canonical_zone)
    h = h[h['interval_start_utc'].le(issue_time)].copy()

    climate = None
    if climate_context is not None and len(climate_context):
        climate = climate_context.copy()
        climate['interval_start_utc'] = pd.to_datetime(climate['interval_start_utc'], utc=True, errors='raise')
        climate['subsystem_id'] = climate['subsystem_id'].astype(str).map(_canonical_zone)
        climate = climate.drop_duplicates(['interval_start_utc', 'subsystem_id'])
        keep = ['interval_start_utc', 'subsystem_id'] + [
            c for c in climate.columns if c.startswith('incident_') or c in {'climate_spatial_method', 'weather_mode'}
        ]
        climate = climate[keep]
        f = f.merge(climate, on=['interval_start_utc', 'subsystem_id'], how='left', validate='one_to_one')

    supply = None
    if observed_supply_backtest is not None and len(observed_supply_backtest):
        supply = observed_supply_backtest.copy()
        supply['interval_start_utc'] = pd.to_datetime(supply['interval_start_utc'], utc=True, errors='raise')
        supply['subsystem_id'] = supply['subsystem_id'].astype(str).map(_canonical_zone)
        cols = ['interval_start_utc', 'subsystem_id', 'generation_hydro_mw', 'generation_thermal_mw', 'generation_wind_mw', 'generation_solar_mw']
        cols = [c for c in cols if c in supply.columns]
        supply = supply[cols].drop_duplicates(['interval_start_utc', 'subsystem_id'])
        f = f.merge(supply, on=['interval_start_utc', 'subsystem_id'], how='left', validate='one_to_one')

    rows = []
    for _, r in f.sort_values(['subsystem_id', 'interval_start_utc']).iterrows():
        zone = str(r['subsystem_id'])
        d_pct, demand_context_method, demand_context_n = contextual_demand_percentile(
            h,
            subsystem_id=zone,
            target_time_utc=r['interval_start_utc'],
            demand_mw=float(r['demand_p50_mw']),
            timezone_name=calendar_timezone,
        )

        exposure_candidates = [
            c for c in ['incident_event_any_fraction', 'incident_cell_fraction', 'incident_heat_event_fraction', 'incident_cold_event_fraction']
            if c in r.index and pd.notna(r[c])
        ]
        climate_exposure = float(max([float(r[c]) for c in exposure_candidates], default=0.0))
        climate_exposure = float(np.clip(climate_exposure, 0.0, 1.0))

        flags = [
            'SUPPLY_PRESSURE_UNAVAILABLE',
            f'DEMAND_PERCENTILE_CONTEXT_{demand_context_method}',
            f'DEMAND_PERCENTILE_REFERENCE_N_{demand_context_n}',
            f'DISPLAY_CONTEXT_TIMEZONE_{calendar_timezone}',
        ]
        weather_mode = str(r.get('weather_mode', '') or '')
        forecast_weather_mode = str(r.get('forecast_weather_mode', '') or '')
        if 'PERFECT_WEATHER_BACKTEST' in {weather_mode, forecast_weather_mode}:
            flags.append('PERFECT_WEATHER_BACKTEST_NOT_OPERATIONAL')
        spatial_method = str(r.get('climate_spatial_method', '') or '')
        if spatial_method:
            flags.append(spatial_method)
        generation_json = '{}'
        if supply is not None:
            generation_json = _generation_json_from_supply(r)
            if generation_json != '{}':
                flags.append('OBSERVED_GENERATION_RETROSPECTIVE_ONLY')

        drivers = r.get('main_drivers_json', '{}')
        if pd.isna(drivers):
            drivers = '{}'
        if not isinstance(drivers, str):
            drivers = json.dumps(drivers, ensure_ascii=False, sort_keys=True)

        rows.append({
            'schema_version': 'system_signal_v1',
            'run_id': run_id,
            'interval_start_utc': r['interval_start_utc'],
            'zone_type': 'SUBSYSTEM',
            'zone_id': zone,
            'demand_p10_mw': float(r['demand_p10_mw']),
            'demand_p50_mw': float(r['demand_p50_mw']),
            'demand_p90_mw': float(r['demand_p90_mw']),
            'demand_percentile': d_pct,
            'supply_pressure': None,
            'climate_exposure': climate_exposure,
            'generation_by_type_json': generation_json,
            'main_drivers_json': drivers,
            'data_freshness_ok': True,
            'quality_flags': json.dumps(sorted(set(flags)), ensure_ascii=False),
        })
    out = pd.DataFrame(rows)
    if (out['demand_p10_mw'] > out['demand_p50_mw']).any() or (out['demand_p50_mw'] > out['demand_p90_mw']).any():
        raise ValueError('forecast quantiles are incoherent')
    out = out.sort_values(['zone_id', 'interval_start_utc']).reset_index(drop=True)
    return enrich_signal_with_dessem(
        out, dessem_schedule,
        issue_time_utc=issue_time if 'issue_time_utc' in f else None,
        allow_replay=allow_dessem_replay, required=require_dessem,
    )
