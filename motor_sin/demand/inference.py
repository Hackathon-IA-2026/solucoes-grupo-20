from __future__ import annotations
from datetime import timedelta

import json
from pathlib import Path

import pandas as pd

from motor_sin.demand.direct import build_direct_prediction_row
from motor_sin.demand.model import feature_contributions
from motor_sin.demand.registry import load_frozen_model_family


def _canonical_zone(value: str) -> str:
    raw = str(value).strip().upper()
    return {'SE': 'SE/CO', 'SECO': 'SE/CO'}.get(raw, raw)


def forecast_frozen_direct_family(
    *,
    load_history: pd.DataFrame,
    future_zone_climate: pd.DataFrame | None,
    model_dir: str | Path,
    issue_time: pd.Timestamp,
    horizon: int = 24,
    allow_perfect_weather: bool = False,
) -> pd.DataFrame:
    manifest, models = load_frozen_model_family(model_dir)
    subsystem_id = _canonical_zone(manifest['subsystem_id'])
    calendar_timezone = str(manifest['calendar_timezone'])
    issue = pd.Timestamp(issue_time)
    issue = issue.tz_localize('UTC') if issue.tzinfo is None else issue.tz_convert('UTC')

    l = load_history.copy()
    l['interval_start_utc'] = pd.to_datetime(l['interval_start_utc'], utc=True, errors='raise')
    l['subsystem_id'] = l['subsystem_id'].astype(str).map(_canonical_zone)
    l = l[(l['subsystem_id'].eq(subsystem_id)) & (l['interval_start_utc'].le(issue))].copy()
    if l.empty or issue not in set(l['interval_start_utc']):
        raise ValueError(f'issue_time {issue} must exist in observed load history for {subsystem_id}')
    actual_lookup = {ts: float(v) for ts, v in zip(l['interval_start_utc'], l['load_mw'])}

    experiment = str(manifest.get('experiment','E3')).upper()
    z = None
    climate_lookup = None
    modes = []
    if future_zone_climate is not None and len(future_zone_climate):
        z = future_zone_climate.copy()
        z['interval_start_utc'] = pd.to_datetime(z['interval_start_utc'], utc=True, errors='raise')
        z['subsystem_id'] = z['subsystem_id'].astype(str).map(_canonical_zone)
        z = z[z['subsystem_id'].eq(subsystem_id)].copy()
        modes = sorted(set(z.get('weather_mode', pd.Series(dtype=str)).dropna().astype(str).tolist()))
        if any(m == 'PERFECT_WEATHER_BACKTEST' for m in modes) and not allow_perfect_weather:
            raise ValueError(
                'future_zone_climate is PERFECT_WEATHER_BACKTEST. Pass allow_perfect_weather=True only for historical demo/backtest; '
                'operational inference must use an actual forecast available at issue_time.'
            )
        climate_lookup = z.set_index('interval_start_utc', drop=False)
    elif experiment in {'E2','E3'}:
        raise ValueError(f'{experiment} frozen model requires future climate features')

    rows = []
    for h in range(1, int(horizon) + 1):
        if h not in models:
            raise ValueError(f'frozen model family has no H{h:02d}')
        target = issue + timedelta(hours=int(h))
        if climate_lookup is not None and target not in climate_lookup.index:
            raise ValueError(f'missing climate features for target {target}')
        frame = build_direct_prediction_row(
            issue=issue,
            target=target,
            subsystem_id=subsystem_id,
            actual_lookup=actual_lookup,
            climate_lookup=climate_lookup,
            calendar_timezone=calendar_timezone,
        )
        model = models[h].model
        missing = [c for c in model.features if c not in frame.columns or pd.isna(frame.iloc[0][c])]
        if missing:
            raise ValueError(f'missing E3 features for H{h:02d}: {missing}')
        p10, p50, p90 = model.predict(frame)
        rows.append({
            'issue_time_utc': issue,
            'interval_start_utc': target,
            'horizon_hour': h,
            'subsystem_id': subsystem_id,
            'demand_p10_mw': float(p10[0]),
            'demand_p50_mw': float(p50[0]),
            'demand_p90_mw': float(p90[0]),
            'main_drivers_json': json.dumps(feature_contributions(model, frame.iloc[0]), ensure_ascii=False),
            'model_family_id': manifest['model_family_id'],
            'model_experiment': manifest['experiment'],
            'weather_mode': modes[0] if len(modes) == 1 else ('MIXED' if modes else ('NOT_REQUIRED' if experiment=='E1' else 'UNKNOWN')),
            'calendar_timezone': calendar_timezone,
        })
    out = pd.DataFrame(rows)
    if len(out) != horizon:
        raise AssertionError('forecast output does not match requested horizon')
    return out
