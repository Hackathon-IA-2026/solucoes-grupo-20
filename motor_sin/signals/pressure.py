from __future__ import annotations

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


def empirical_percentile(values: pd.Series, value: float) -> float:
    arr = pd.to_numeric(values, errors='coerce').dropna().to_numpy(float)
    if len(arr) == 0:
        return 0.5
    return float(np.mean(arr <= float(value)))


def _day_type(local_ts: pd.Timestamp) -> str:
    return 'WEEKEND' if int(local_ts.dayofweek) >= 5 else 'WEEKDAY'


def contextual_demand_percentile(
    history: pd.DataFrame,
    *,
    subsystem_id: str,
    target_time_utc: pd.Timestamp,
    demand_mw: float,
    timezone_name: str = 'America/Sao_Paulo',
) -> tuple[float, str, int]:
    """Return a demand pressure percentile against a context-compatible history.

    The comparator is deliberately hierarchical so a short MVP history does not
    produce tiny reference samples:

    1. same local hour + calendar month + weekday/weekend (>=24 observations)
    2. same local hour + calendar month (>=24 observations)
    3. same local hour + a three-month seasonal window (>=60 observations)
    4. same local hour across the available history

    This makes D a *contextual* pressure signal instead of comparing, for example,
    midnight demand with the entire daily load distribution. Timestamps remain UTC
    in storage; only contextual grouping is performed in America/Sao_Paulo by
    default.
    """
    if history.empty:
        return 0.5, 'NO_HISTORY', 0

    h = history.copy()
    h['interval_start_utc'] = pd.to_datetime(h['interval_start_utc'], utc=True, errors='raise')
    h = h[h['subsystem_id'].astype(str).eq(str(subsystem_id))].copy()
    if h.empty:
        return 0.5, 'NO_ZONE_HISTORY', 0

    tz = ZoneInfo(timezone_name)
    local_hist = h['interval_start_utc'].dt.tz_convert(tz)
    h['_hour'] = local_hist.dt.hour
    h['_month'] = local_hist.dt.month
    h['_day_type'] = np.where(local_hist.dt.dayofweek >= 5, 'WEEKEND', 'WEEKDAY')

    target = pd.Timestamp(target_time_utc)
    target = target.tz_localize('UTC') if target.tzinfo is None else target.tz_convert('UTC')
    local = target.tz_convert(tz)
    hour = int(local.hour)
    month = int(local.month)
    day_type = _day_type(local)

    candidates: list[tuple[str, pd.DataFrame, int]] = []
    candidates.append((
        'HOUR_MONTH_DAYTYPE',
        h[(h['_hour'].eq(hour)) & (h['_month'].eq(month)) & (h['_day_type'].eq(day_type))],
        24,
    ))
    candidates.append((
        'HOUR_MONTH',
        h[(h['_hour'].eq(hour)) & (h['_month'].eq(month))],
        24,
    ))
    months = {12 if month == 1 else month - 1, month, 1 if month == 12 else month + 1}
    candidates.append((
        'HOUR_SEASON_3M',
        h[(h['_hour'].eq(hour)) & (h['_month'].isin(months))],
        60,
    ))
    candidates.append(('HOUR_ALL_HISTORY', h[h['_hour'].eq(hour)], 1))

    for method, comp, minimum in candidates:
        valid = pd.to_numeric(comp.get('load_mw'), errors='coerce').dropna()
        if len(valid) >= minimum:
            return empirical_percentile(valid, float(demand_mw)), method, int(len(valid))

    return 0.5, 'INSUFFICIENT_HISTORY', 0
