from __future__ import annotations

"""OpenMeteo snapshot anomaly semantics preserved for Predicta.

The 2026-09-18 snapshot is partial and does not contain its baseline.py, therefore this
module implements only behavior explicitly supported by config/event_rules.json and the
available detector code:

* ERA5-Land historical source;
* ten complete years before target year;
* daily temperature max/min grouped by calendar month;
* monthly mean, p05, p10, p90, p95 using NumPy linear quantiles;
* anomaly_from_mean_c = observed daily metric - monthly climatological mean;
* temperature event thresholds exactly as rules_version 2026-08-08.2.

E2 intentionally does NOT consume these enhanced features. They are prepared for E3 so
that the incremental E1 -> E2 -> E3 comparison remains identifiable.
"""

from pathlib import Path
import json
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

SNAPSHOT_RULES_VERSION = '2026-08-08.2'
SNAPSHOT_BASELINE_VERSION = '1.1'


def load_snapshot_rules(path: str | Path = 'configs/openmeteo_event_rules_snapshot_2026-08-08.2.json') -> dict:
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if str(payload.get('rules_version')) != SNAPSHOT_RULES_VERSION:
        raise ValueError(f'unexpected snapshot rules_version={payload.get("rules_version")}')
    return payload


def baseline_years_for_target(target_year: int, complete_years: int = 10) -> list[int]:
    if complete_years <= 0:
        raise ValueError('complete_years must be positive')
    return list(range(int(target_year) - int(complete_years), int(target_year)))


def hourly_to_local_daily_temperature(hourly: pd.DataFrame, *, timezone_name: str) -> pd.DataFrame:
    required = {'interval_start_utc', 'cell_id', 'temperature_2m'}
    missing = required - set(hourly.columns)
    if missing:
        raise ValueError(f'hourly climate missing columns: {sorted(missing)}')
    work = hourly.copy()
    work['interval_start_utc'] = pd.to_datetime(work['interval_start_utc'], utc=True, errors='raise')
    # ZoneInfo validation is deliberate; pandas accepts strings but error messages are weaker.
    ZoneInfo(timezone_name)
    local = work['interval_start_utc'].dt.tz_convert(timezone_name)
    work['date_local'] = local.dt.date.astype(str)
    out = work.groupby(['cell_id', 'date_local'], as_index=False).agg(
        temperature_2m_max=('temperature_2m', 'max'),
        temperature_2m_min=('temperature_2m', 'min'),
        hourly_sample_count=('temperature_2m', 'count'),
    )
    return out


def build_monthly_temperature_baseline(
    daily: pd.DataFrame,
    *,
    target_year: int,
    minimum_samples_per_month: int = 250,
) -> pd.DataFrame:
    required = {'cell_id', 'date_local', 'temperature_2m_max', 'temperature_2m_min'}
    missing = required - set(daily.columns)
    if missing:
        raise ValueError(f'daily temperature missing columns: {sorted(missing)}')
    work = daily.copy()
    dates = pd.to_datetime(work['date_local'], errors='raise')
    work['year'] = dates.dt.year
    work['month'] = dates.dt.month
    years = baseline_years_for_target(target_year, 10)
    history = work[work['year'].isin(years)].copy()
    if history.empty:
        raise ValueError(f'no daily temperature rows for baseline years {years[0]}-{years[-1]}')

    records: list[dict] = []
    for (cell_id, month), g in history.groupby(['cell_id', 'month'], sort=True):
        for metric in ['temperature_2m_max', 'temperature_2m_min']:
            vals = pd.to_numeric(g[metric], errors='coerce').dropna().to_numpy(dtype=float)
            if len(vals) < minimum_samples_per_month:
                raise ValueError(
                    f'insufficient snapshot baseline samples cell={cell_id} month={month} metric={metric}: '
                    f'{len(vals)} < {minimum_samples_per_month}'
                )
            q = np.quantile(vals, [0.05, 0.10, 0.90, 0.95], method='linear')
            records.append({
                'baseline_version': SNAPSHOT_BASELINE_VERSION,
                'rules_version': SNAPSHOT_RULES_VERSION,
                'target_year': int(target_year),
                'baseline_year_start': int(years[0]),
                'baseline_year_end': int(years[-1]),
                'cell_id': str(cell_id),
                'month': int(month),
                'metric': metric,
                'mean': float(np.mean(vals)),
                'p05': float(q[0]),
                'p10': float(q[1]),
                'p90': float(q[2]),
                'p95': float(q[3]),
                'sample_count': int(len(vals)),
                'percentile_method': 'linear_interpolation_n_minus_1',
            })
    return pd.DataFrame(records)


def score_daily_temperature_context(
    daily_target: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    rules: dict | None = None,
) -> pd.DataFrame:
    rules = rules or load_snapshot_rules()
    work = daily_target.copy()
    dates = pd.to_datetime(work['date_local'], errors='raise')
    work['month'] = dates.dt.month
    long = work.melt(
        id_vars=['cell_id', 'date_local', 'month'],
        value_vars=['temperature_2m_max', 'temperature_2m_min'],
        var_name='metric', value_name='value'
    )
    base = baseline[['cell_id', 'month', 'metric', 'mean', 'p05', 'p10', 'p90', 'p95']].copy()
    scored = long.merge(base, on=['cell_id', 'month', 'metric'], how='left', validate='many_to_one')
    if scored[['mean', 'p05', 'p10', 'p90', 'p95']].isna().any().any():
        raise ValueError('snapshot temperature baseline missing cell/month/metric thresholds')
    scored['anomaly_from_mean_c'] = scored['value'].astype(float) - scored['mean'].astype(float)

    # Event flags exactly from event_rules.json. Consecutive-day wave logic is intentionally
    # not inferred here; this function only materializes the per-day predicates required by it.
    te = rules['temperature_events']
    scored['unusually_hot_day'] = False
    scored['extreme_heat_day'] = False
    scored['heat_wave_day_predicate'] = False
    scored['unusually_cold_day'] = False
    scored['extreme_cold_day'] = False
    scored['cold_wave_day_predicate'] = False

    hot = scored['metric'].eq('temperature_2m_max')
    cold = scored['metric'].eq('temperature_2m_min')
    scored.loc[hot, 'unusually_hot_day'] = scored.loc[hot, 'value'].ge(scored.loc[hot, 'p90'])
    scored.loc[hot, 'extreme_heat_day'] = (
        scored.loc[hot, 'value'].ge(scored.loc[hot, 'p95'])
        & scored.loc[hot, 'anomaly_from_mean_c'].ge(float(te['extreme_heat_day']['anomaly_threshold_c']))
    )
    scored.loc[hot, 'heat_wave_day_predicate'] = (
        scored.loc[hot, 'value'].ge(scored.loc[hot, 'p90'])
        & scored.loc[hot, 'anomaly_from_mean_c'].ge(float(te['heat_wave_candidate']['anomaly_threshold_c']))
    )
    scored.loc[cold, 'unusually_cold_day'] = scored.loc[cold, 'value'].le(scored.loc[cold, 'p10'])
    scored.loc[cold, 'extreme_cold_day'] = (
        scored.loc[cold, 'value'].le(scored.loc[cold, 'p05'])
        & scored.loc[cold, 'anomaly_from_mean_c'].le(float(te['extreme_cold_day']['anomaly_threshold_c']))
    )
    scored.loc[cold, 'cold_wave_day_predicate'] = (
        scored.loc[cold, 'value'].le(scored.loc[cold, 'p10'])
        & scored.loc[cold, 'anomaly_from_mean_c'].le(float(te['cold_wave_candidate']['anomaly_threshold_c']))
    )
    return scored.sort_values(['cell_id', 'date_local', 'metric']).reset_index(drop=True)
