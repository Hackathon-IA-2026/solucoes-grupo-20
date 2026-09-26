from __future__ import annotations

import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo


# Relative 24h shapes only. They are demonstrative defaults when the customer has no hourly curve.
_SHAPES = {
    'residential': np.array([0.45,0.38,0.34,0.32,0.34,0.45,0.70,0.92,0.78,0.63,0.58,0.56,0.58,0.60,0.62,0.66,0.78,1.00,1.25,1.35,1.20,0.98,0.75,0.58]),
    'commercial': np.array([0.15,0.12,0.10,0.10,0.10,0.12,0.25,0.55,0.90,1.10,1.20,1.25,1.25,1.22,1.18,1.15,1.05,0.85,0.55,0.35,0.25,0.20,0.18,0.16]),
    'industrial_flat': np.ones(24),
}


def synthetic_daily_profile(
    total_kwh: float,
    profile_type: str,
    timestamps: pd.Series,
    timezone_name: str = 'America/Sao_Paulo',
) -> pd.DataFrame:
    profile_type = str(profile_type).strip().lower()
    if profile_type not in _SHAPES:
        raise ValueError(f'unsupported synthetic profile_type={profile_type}; choose {sorted(_SHAPES)}')
    ts = pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True, errors='raise'))
    if len(ts) != 24:
        raise ValueError('synthetic customer MVP currently requires exactly 24 hourly timestamps')
    if total_kwh <= 0:
        raise ValueError('total_kwh must be positive')
    # Storage and joins stay in UTC, but the consumer load shape is a civil-time
    # concept. Align each shape coefficient to the local Sao Paulo clock hour.
    local_hours = ts.tz_convert(ZoneInfo(timezone_name)).hour
    shape = _SHAPES[profile_type].astype(float)[np.asarray(local_hours, dtype=int)]
    values = float(total_kwh) * shape / shape.sum()
    return pd.DataFrame({'interval_start_utc': ts, 'consumption_kwh': values, 'profile_source': f'SYNTHETIC_{profile_type.upper()}'})


def validate_customer_curve(curve: pd.DataFrame, timestamps: pd.Series) -> pd.DataFrame:
    required = {'interval_start_utc', 'consumption_kwh'}
    if not required.issubset(curve.columns):
        raise ValueError(f'customer curve must contain {sorted(required)}')
    c = curve.copy()
    c['interval_start_utc'] = pd.to_datetime(c['interval_start_utc'], utc=True, errors='raise')
    c['consumption_kwh'] = pd.to_numeric(c['consumption_kwh'], errors='raise')
    if (c['consumption_kwh'] < 0).any():
        raise ValueError('customer consumption cannot be negative')
    target = pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True, errors='raise'))
    c = c[c['interval_start_utc'].isin(target)].drop_duplicates('interval_start_utc')
    c = pd.DataFrame({'interval_start_utc': target}).merge(c, on='interval_start_utc', how='left')
    if c['consumption_kwh'].isna().any():
        raise ValueError('customer curve does not cover all 24 signal hours')
    c['profile_source'] = c.get('profile_source', 'CUSTOMER_HOURLY_CURVE')
    return c
