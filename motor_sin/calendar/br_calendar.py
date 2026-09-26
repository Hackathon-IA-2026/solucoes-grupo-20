from __future__ import annotations

from datetime import date, timedelta
import pandas as pd

# Fixed federal holidays from Brazilian national calendar. Movable dates below are separate features
# because Carnival/Corpus Christi are not represented here as if they were fixed federal holidays.
FIXED_NATIONAL = {
    (1, 1): 'Confraternizacao Universal',
    (4, 21): 'Tiradentes',
    (5, 1): 'Dia do Trabalho',
    (9, 7): 'Independencia do Brasil',
    (10, 12): 'Nossa Senhora Aparecida',
    (11, 2): 'Finados',
    (11, 15): 'Proclamacao da Republica',
    (11, 20): 'Dia Nacional de Zumbi e da Consciencia Negra',
    (12, 25): 'Natal',
}


def easter_date(year: int) -> date:
    # Anonymous Gregorian algorithm.
    a = year % 19; b = year // 100; c = year % 100; d = b // 4; e = b % 4
    f = (b + 8) // 25; g = (b - f + 1) // 3; h = (19*a + b - d - g + 15) % 30
    i = c // 4; k = c % 4; l = (32 + 2*e + 2*i - h - k) % 7; m = (a + 11*h + 22*l) // 451
    month = (h + l - 7*m + 114) // 31; day = ((h + l - 7*m + 114) % 31) + 1
    return date(year, month, day)


def to_local_time(ts: pd.Series | pd.DatetimeIndex, *, timezone: str = 'UTC'):
    """Convert canonical UTC timestamps to the calendar timezone without changing stored UTC values."""
    utc = pd.to_datetime(ts, utc=True, errors='raise')
    try:
        return utc.tz_convert(timezone) if isinstance(utc, pd.DatetimeIndex) else utc.dt.tz_convert(timezone)
    except Exception as exc:  # pandas/zoneinfo raises different concrete errors depending on platform
        raise ValueError(f'invalid calendar timezone: {timezone!r}') from exc


def calendar_flags(ts: pd.Series, *, timezone: str = 'UTC') -> pd.DataFrame:
    """Calendar flags evaluated on local civil dates.

    The project stores timestamps in UTC. Behavioural/calendar features, however, must be derived from
    the local civil time relevant to the load series. ``timezone`` makes that conversion explicit.
    """
    local = to_local_time(ts, timezone=timezone)
    rows=[]
    for x in local:
        d=x.date(); easter=easter_date(d.year)
        fixed=(d.month,d.day) in FIXED_NATIONAL
        carnival=d in {easter-timedelta(days=48), easter-timedelta(days=47)}
        good_friday=d == easter-timedelta(days=2)
        corpus=d == easter+timedelta(days=60)
        rows.append({
            'holiday_national': int(fixed),
            'carnival': int(carnival),
            'good_friday': int(good_friday),
            'corpus_christi': int(corpus),
            'major_calendar_event': int(fixed or carnival or good_friday or corpus),
        })
    return pd.DataFrame(rows, index=ts.index)


def calendar_feature_frame(ts: pd.Series, *, timezone: str = 'UTC') -> pd.DataFrame:
    """Return all model calendar features using local civil time.

    This helper is shared by training, backtesting and operational forecasting to prevent train/serve skew.
    """
    local = to_local_time(ts, timezone=timezone)
    out = pd.DataFrame(index=ts.index)
    out['hour'] = local.dt.hour.to_numpy()
    out['day_of_week'] = local.dt.dayofweek.to_numpy()
    out['weekend'] = local.dt.dayofweek.ge(5).astype(int).to_numpy()
    out['month'] = local.dt.month.to_numpy()
    flags = calendar_flags(ts, timezone=timezone)
    for col in flags.columns:
        out[col] = flags[col].to_numpy()
    # Backward-compatible alias used by v1.0 models/fixtures.
    out['holiday'] = out['holiday_national']
    return out
