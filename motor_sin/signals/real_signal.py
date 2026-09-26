from __future__ import annotations

import json
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

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


def build_real_system_signal(
    *,
    forecast: pd.DataFrame,
    load_history: pd.DataFrame,
    climate_context: pd.DataFrame | None,
    run_id: str,
    calendar_timezone: str = 'America/Sao_Paulo',
    observed_supply_backtest: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build a contract-valid pilot system_signal_v1 from the selected demand forecast.

    `supply_pressure` remains null unless a future operational supply model exists. If observed
    historical supply is supplied, its generation mix is exposed only for retrospective context;
    it is NOT converted into a future supply-pressure score and is flagged accordingly.
    """
    f = forecast.copy()
    rename = {'p10_mw': 'demand_p10_mw', 'p50_mw': 'demand_p50_mw', 'p90_mw': 'demand_p90_mw'}
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
        if weather_mode == 'PERFECT_WEATHER_BACKTEST':
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
    return out.sort_values(['zone_id', 'interval_start_utc']).reset_index(drop=True)
