from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import timedelta
import re

import pandas as pd


def _utc_bound(value: str | None, *, end: bool = False) -> pd.Timestamp | None:
    if not value:
        return None
    ts = pd.Timestamp(value)
    ts = ts.tz_localize('UTC') if ts.tzinfo is None else ts.tz_convert('UTC')
    if end and re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(value).strip()):
        ts = ts + timedelta(days=1) - timedelta(microseconds=1)
    return ts


def clip_requested_period(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    out = df.copy()
    out['interval_start_utc'] = pd.to_datetime(out['interval_start_utc'], utc=True, errors='raise')
    start_ts = _utc_bound(start)
    end_ts = _utc_bound(end, end=True)
    if start_ts is not None:
        out = out[out['interval_start_utc'] >= start_ts]
    if end_ts is not None:
        out = out[out['interval_start_utc'] <= end_ts]
    return out


def _canonical_zone(value: str) -> str:
    raw = str(value).strip().upper()
    return {'SE': 'SE/CO', 'SECO': 'SE/CO'}.get(raw, raw)


def _zone_slice(df: pd.DataFrame, subsystem_id: str) -> pd.DataFrame:
    if 'subsystem_id' not in df.columns:
        return df
    zone = _canonical_zone(subsystem_id)
    ids = df['subsystem_id'].astype(str).str.strip().str.upper().replace({'SE': 'SE/CO', 'SECO': 'SE/CO'})
    return df.loc[ids.eq(zone)].copy()


@dataclass(frozen=True)
class AvailabilityWindow:
    requested_start: str | None
    requested_end: str | None
    load_start: str | None
    load_end: str | None
    climate_start: str | None
    climate_end: str | None
    effective_start: str | None
    effective_end: str | None
    adjusted_to_common_overlap: bool

    def to_dict(self) -> dict:
        return asdict(self)


def align_experiment_period(
    load: pd.DataFrame,
    climate: pd.DataFrame | None,
    *,
    experiment: str,
    subsystem_id: str,
    requested_start: str | None = None,
    requested_end: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame | None, AvailabilityWindow]:
    """Clip requested history and, for E2/E3, align load + climate to their common zone window.

    E1 only needs ONS load. E2/E3 require target-time exogenous climate, therefore the
    evaluation/training window cannot extend beyond the climate coverage. The function makes
    that restriction explicit instead of letting every fixed-origin forecast fail later.
    """
    exp = str(experiment).upper()
    load_c = clip_requested_period(load, requested_start, requested_end)
    climate_c = clip_requested_period(climate, requested_start, requested_end) if climate is not None else None

    lz = _zone_slice(load_c, subsystem_id)
    if lz.empty:
        raise ValueError(f'no load rows for subsystem {subsystem_id} inside requested history window')
    load_start = pd.Timestamp(lz['interval_start_utc'].min())
    load_end = pd.Timestamp(lz['interval_start_utc'].max())

    if exp == 'E1':
        meta = AvailabilityWindow(
            requested_start, requested_end,
            str(load_start), str(load_end), None, None,
            str(load_start), str(load_end), False,
        )
        return load_c, None, meta

    if climate_c is None or climate_c.empty:
        raise ValueError(f'{exp} requires climate features, but no climate dataset is available in the requested window')
    cz = _zone_slice(climate_c, subsystem_id)
    if cz.empty:
        raise ValueError(f'{exp} has no climate rows for subsystem {subsystem_id} inside the requested history window')
    climate_start = pd.Timestamp(cz['interval_start_utc'].min())
    climate_end = pd.Timestamp(cz['interval_start_utc'].max())

    effective_start = max(load_start, climate_start)
    effective_end = min(load_end, climate_end)
    if effective_start > effective_end:
        raise ValueError(
            f'{exp} has no common load/climate period for {subsystem_id}: '
            f'load={load_start}..{load_end}, climate={climate_start}..{climate_end}'
        )

    load_eff = load_c[(load_c['interval_start_utc'] >= effective_start) & (load_c['interval_start_utc'] <= effective_end)].copy()
    climate_eff = climate_c[(climate_c['interval_start_utc'] >= effective_start) & (climate_c['interval_start_utc'] <= effective_end)].copy()
    adjusted = effective_start != load_start or effective_end != load_end
    meta = AvailabilityWindow(
        requested_start, requested_end,
        str(load_start), str(load_end), str(climate_start), str(climate_end),
        str(effective_start), str(effective_end), bool(adjusted),
    )
    return load_eff, climate_eff, meta
