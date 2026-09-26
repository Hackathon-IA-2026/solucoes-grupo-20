from __future__ import annotations
from datetime import timedelta

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from motor_sin.calendar.br_calendar import calendar_feature_frame
from motor_sin.demand.model import DemandModel, fit_demand_model


# Observed-load features anchored at the forecast issue time.
DIRECT_ISSUE_LAGS = (0, 1, 2, 24, 48, 168)

# Observed-load features anchored at the TARGET hour. Because the MVP horizon is <=24h,
# target-24h, target-48h and target-168h are all known at forecast issue time.
DIRECT_TARGET_LAGS = (24, 48, 168)
SAME_TARGET_HOUR_WINDOWS_DAYS = (3, 7)

# Explicit target-time calendar features used by the direct H01..H24 models.
TARGET_CALENDAR_FEATURES = (
    'target_hour', 'target_day_of_week', 'target_weekend',
    'target_holiday_national', 'target_carnival', 'target_good_friday',
    'target_corpus_christi', 'target_month',
    'target_hour_sin', 'target_hour_cos',
    'target_day_of_week_sin', 'target_day_of_week_cos',
)

# Backward-compatible generic names still materialized in the frame, but not selected for
# the v1.1.4 direct model. Keeping them avoids breaking older inspection notebooks.
CALENDAR_FEATURES = (
    'hour', 'day_of_week', 'weekend', 'holiday_national', 'carnival',
    'good_friday', 'corpus_christi', 'month',
)

FEATURE_SET_VERSION = 'v1.1.4_target_history'


@dataclass(frozen=True)
class DirectModelBundle:
    experiment: str
    horizon_hour: int
    model: DemandModel
    fit_rows: int
    calibration_rows: int
    calibration_start_utc: pd.Timestamp
    calibration_end_utc: pd.Timestamp
    calibration_coverage: float
    calibration_method: str = 'heldout_pretest_asymmetric_residual_quantiles'


def _assert_hourly_contiguous(load_zone: pd.DataFrame) -> None:
    ts = pd.to_datetime(load_zone['interval_start_utc'], utc=True, errors='raise').sort_values()
    if ts.duplicated().any():
        raise ValueError('load has duplicate subsystem-hour rows')
    if len(ts) > 1 and not ts.diff().dropna().eq(timedelta(hours=1)).all():
        raise ValueError('direct multi-horizon training requires a contiguous hourly load series')


def _canonical_climate(climate: pd.DataFrame | None) -> pd.DataFrame | None:
    if climate is None or not len(climate):
        return None
    z = climate.copy()
    z['interval_start_utc'] = pd.to_datetime(z['interval_start_utc'], utc=True, errors='raise')
    if z['interval_start_utc'].duplicated().any():
        raise ValueError('zone climate has duplicate target-hour rows')
    return z.sort_values('interval_start_utc')


def _add_target_calendar(out: pd.DataFrame, *, calendar_timezone: str) -> pd.DataFrame:
    """Materialize local-civil target calendar plus cyclic encodings.

    Generic calendar columns are preserved for backward compatibility; the direct MVP model
    explicitly selects the target_* aliases so the feature semantics are auditable.
    """
    cal = calendar_feature_frame(out['interval_start_utc'], timezone=calendar_timezone)
    for col in cal.columns:
        out[col] = cal[col].to_numpy()

    aliases = {
        'hour': 'target_hour',
        'day_of_week': 'target_day_of_week',
        'weekend': 'target_weekend',
        'holiday_national': 'target_holiday_national',
        'carnival': 'target_carnival',
        'good_friday': 'target_good_friday',
        'corpus_christi': 'target_corpus_christi',
        'month': 'target_month',
    }
    for source, target in aliases.items():
        out[target] = out[source]

    hour = pd.to_numeric(out['target_hour'], errors='coerce').astype(float)
    dow = pd.to_numeric(out['target_day_of_week'], errors='coerce').astype(float)
    out['target_hour_sin'] = np.sin(2 * np.pi * hour / 24.0)
    out['target_hour_cos'] = np.cos(2 * np.pi * hour / 24.0)
    out['target_day_of_week_sin'] = np.sin(2 * np.pi * dow / 7.0)
    out['target_day_of_week_cos'] = np.cos(2 * np.pi * dow / 7.0)
    return out


def _add_target_history_training_features(out: pd.DataFrame, values: pd.Series, *, horizon_hour: int) -> pd.DataFrame:
    """Add load history aligned to the target clock hour without peeking past issue time.

    For a row with issue t and target t+h, ``target_lag_24h`` is load(t+h-24h).
    Since h<=24 in the MVP, that timestamp is <=t and is observable when the forecast is issued.
    """
    h = int(horizon_hour)
    for lag in DIRECT_TARGET_LAGS:
        offset_from_issue = lag - h
        if offset_from_issue < 0:
            raise ValueError(f'target_lag_{lag}h would require future load for H{h:02d}')
        out[f'target_lag_{lag}h'] = values.shift(offset_from_issue)

    for days in SAME_TARGET_HOUR_WINDOWS_DAYS:
        parts = []
        for d in range(1, days + 1):
            offset_from_issue = 24 * d - h
            if offset_from_issue < 0:
                raise ValueError(f'same-target-hour mean {days}d would require future load for H{h:02d}')
            parts.append(values.shift(offset_from_issue).rename(f'd{d}'))
        # Require the complete window; do not silently average a partial early-history window.
        hist = pd.concat(parts, axis=1)
        out[f'mean_same_target_hour_{days}d'] = hist.mean(axis=1, skipna=False)
    return out


def build_direct_frame(
    load_zone: pd.DataFrame,
    zone_climate: pd.DataFrame | None,
    *,
    horizon_hour: int,
    calendar_timezone: str,
) -> pd.DataFrame:
    """Build one direct-horizon supervised frame.

    Every row is indexed by an *issue time*. Features combine:
      * issue-time state (issue_lag_*);
      * historical load at the same clock hour as the target (target_lag_* and 3d/7d means);
      * local-civil target calendar and cyclic encodings;
      * optional target-time weather.

    For H01..H24 every observed-load feature is at or before issue time, so no future observed
    load leaks into training or backtesting.
    """
    h = int(horizon_hour)
    if h < 1 or h > 24:
        raise ValueError('horizon_hour must be within 1..24')
    g = load_zone.copy().sort_values('interval_start_utc').reset_index(drop=True)
    g['interval_start_utc'] = pd.to_datetime(g['interval_start_utc'], utc=True, errors='raise')
    _assert_hourly_contiguous(g)

    out = pd.DataFrame({
        'issue_time_utc': g['interval_start_utc'],
        'interval_start_utc': g['interval_start_utc'] + timedelta(hours=int(h)),
        'subsystem_id': g['subsystem_id'].astype(str),
        'load_mw': pd.to_numeric(g['load_mw'], errors='coerce').shift(-h),
        'horizon_hour': h,
    })
    values = pd.to_numeric(g['load_mw'], errors='coerce')
    for lag in DIRECT_ISSUE_LAGS:
        out[f'issue_lag_{lag}h'] = values.shift(lag)

    out = _add_target_history_training_features(out, values, horizon_hour=h)
    out = _add_target_calendar(out, calendar_timezone=calendar_timezone)

    z = _canonical_climate(zone_climate)
    if z is not None:
        exog_cols = [c for c in z.columns if c not in {'subsystem_id', 'weighting_method', 'weather_mode'}]
        # interval_start_utc is target time in both tables.
        z = z[exog_cols].copy()
        out = out.merge(z, on='interval_start_utc', how='left', validate='many_to_one')
    out['feature_set_version'] = FEATURE_SET_VERSION
    return out


def direct_feature_columns(frame: pd.DataFrame, experiment: str) -> list[str]:
    issue_history = [f'issue_lag_{h}h' for h in DIRECT_ISSUE_LAGS if f'issue_lag_{h}h' in frame.columns]
    target_history = [f'target_lag_{h}h' for h in DIRECT_TARGET_LAGS if f'target_lag_{h}h' in frame.columns]
    target_history += [
        f'mean_same_target_hour_{days}d'
        for days in SAME_TARGET_HOUR_WINDOWS_DAYS
        if f'mean_same_target_hour_{days}d' in frame.columns
    ]
    target_calendar = [c for c in TARGET_CALENDAR_FEATURES if c in frame.columns]
    raw = [
        c for c in frame.columns
        if any(c.startswith(v) for v in ['temperature_2m_', 'dewpoint_2m_', 'precipitation_', 'wind_speed_', 'solar_radiation_'])
        and 'percentile' not in c and 'anomaly' not in c
    ]
    enhanced = [c for c in frame.columns if ('anomaly_' in c or 'percentile_' in c or c.startswith('incident_'))]
    base = issue_history + target_history + target_calendar
    if experiment == 'E1':
        return base
    if experiment == 'E2':
        return base + raw
    if experiment == 'E3':
        return base + raw + enhanced
    raise ValueError(f'unsupported model experiment: {experiment}')


def _calibrate_model(
    model: DemandModel,
    calibration: pd.DataFrame,
    features: list[str],
) -> tuple[DemandModel, float]:
    work = calibration.dropna(subset=[*features, 'load_mw']).copy()
    if len(work) < 48:
        raise ValueError(f'not enough calibration rows for horizon-specific intervals: {len(work)}')
    p50 = model.predict_p50(work)
    y = work['load_mw'].astype(float).to_numpy()
    residual = y - p50
    q10 = float(np.quantile(residual, 0.10))
    q90 = float(np.quantile(residual, 0.90))
    # Keep p50 as the point forecast and guarantee a coherent p10 <= p50 <= p90 interval.
    model.residual_p10 = min(q10, 0.0)
    model.residual_p90 = max(q90, 0.0)
    p10, _, p90 = model.predict(work)
    coverage = float(np.mean((y >= p10) & (y <= p90)))
    model.calibration_rows = int(len(work))
    model.calibration_method = 'heldout_pretest_asymmetric_residual_quantiles'
    model.target_interval_coverage = 0.80
    model.calibration_empirical_coverage = coverage
    return model, coverage


def fit_direct_models(
    load_zone: pd.DataFrame,
    zone_climate: pd.DataFrame | None,
    *,
    experiments: Iterable[str],
    first_issue: pd.Timestamp,
    forecast_horizon: int,
    calendar_timezone: str,
    alpha: float = 1.0,
    calibration_hours: int = 720,
    algorithm: str = 'ridge',
    xgb_params: dict | None = None,
) -> tuple[dict[tuple[str, int], DirectModelBundle], set[str]]:
    """Fit one model per (experiment, horizon) and calibrate its 10–90 interval.

    ``algorithm`` may be ``ridge`` or ``xgboost``. Both use the same supervised frames,
    chronological split and residual-quantile calibration so validation remains comparable.

    Interval calibration uses a chronological block immediately before the held-out test.
    All calibration targets are <= ``first_issue``; the test window is never used for fitting
    the point model or calibrating residual quantiles.
    """
    first_issue = pd.Timestamp(first_issue)
    if first_issue.tzinfo is None:
        first_issue = first_issue.tz_localize('UTC')
    else:
        first_issue = first_issue.tz_convert('UTC')
    calibration_hours = int(calibration_hours)
    if calibration_hours < 48:
        raise ValueError('calibration_hours must be >= 48')

    canonical_climate = _canonical_climate(zone_climate)
    climate_feature_names = set(canonical_climate.columns) if canonical_climate is not None else set()

    bundles: dict[tuple[str, int], DirectModelBundle] = {}
    required_exog: set[str] = set()
    for h in range(1, int(forecast_horizon) + 1):
        frame = build_direct_frame(load_zone, canonical_climate, horizon_hour=h, calendar_timezone=calendar_timezone)
        eligible = frame[frame['interval_start_utc'].le(first_issue)].copy()
        if eligible.empty:
            raise ValueError(f'no direct training rows available for H{h:02d}')
        for experiment in experiments:
            cols = direct_feature_columns(frame, experiment)
            # Only climate-origin columns are exogenous availability requirements. Target-history
            # and target-calendar features are computed locally and must never trigger a climate gate.
            required_exog.update(c for c in cols if c in climate_feature_names)
            valid_all = eligible.dropna(subset=[*cols, 'load_mw']).copy()
            min_fit = max(30, len(cols) + 5)
            if len(valid_all) < min_fit + 48:
                raise ValueError(
                    f'not enough pre-test rows for fit + calibration in {experiment} H{h:02d}: {len(valid_all)}'
                )
            # Use the requested chronological calibration block when history allows it.
            # On small smoke datasets shrink it automatically, but never below 48 rows and
            # never at the cost of the minimum point-model fit sample.
            max_cal = len(valid_all) - min_fit
            preferred_small_sample = max(48, len(valid_all) // 4)
            n_cal = min(calibration_hours, max_cal)
            if calibration_hours > preferred_small_sample and len(valid_all) < 4 * calibration_hours:
                n_cal = min(preferred_small_sample, max_cal)
            if n_cal < 48:
                raise ValueError(f'not enough calibration rows for {experiment} H{h:02d}: {n_cal}')
            valid_fit = valid_all.iloc[:-n_cal].copy()
            valid_cal = valid_all.iloc[-n_cal:].copy()
            model = fit_demand_model(valid_fit, cols, algorithm=algorithm, alpha=alpha, xgb_params=xgb_params)
            model, coverage = _calibrate_model(model, valid_cal, cols)
            bundles[(experiment, h)] = DirectModelBundle(
                experiment=experiment,
                horizon_hour=h,
                model=model,
                fit_rows=int(len(valid_fit)),
                calibration_rows=int(len(valid_cal)),
                calibration_start_utc=pd.Timestamp(valid_cal['interval_start_utc'].min()),
                calibration_end_utc=pd.Timestamp(valid_cal['interval_start_utc'].max()),
                calibration_coverage=coverage,
            )
    return bundles, required_exog


def build_direct_prediction_row(
    *,
    issue: pd.Timestamp,
    target: pd.Timestamp,
    subsystem_id: str,
    actual_lookup: dict[pd.Timestamp, float],
    climate_lookup: pd.DataFrame | None,
    calendar_timezone: str,
) -> pd.DataFrame:
    issue = pd.Timestamp(issue)
    target = pd.Timestamp(target)
    row = {'issue_time_utc': issue, 'interval_start_utc': target, 'subsystem_id': subsystem_id}

    for lag in DIRECT_ISSUE_LAGS:
        row[f'issue_lag_{lag}h'] = actual_lookup.get(issue - timedelta(hours=int(lag)))

    for lag in DIRECT_TARGET_LAGS:
        lag_ts = target - timedelta(hours=int(lag))
        if lag_ts > issue:
            raise ValueError(f'target_lag_{lag}h would read future observed load at {lag_ts} for issue {issue}')
        row[f'target_lag_{lag}h'] = actual_lookup.get(lag_ts)

    for days in SAME_TARGET_HOUR_WINDOWS_DAYS:
        vals = []
        for d in range(1, days + 1):
            lag_ts = target - timedelta(hours=24 * int(d))
            if lag_ts > issue:
                raise ValueError(f'same-target-hour {days}d mean would read future load at {lag_ts}')
            vals.append(actual_lookup.get(lag_ts))
        row[f'mean_same_target_hour_{days}d'] = float(np.mean(vals)) if all(v is not None for v in vals) else np.nan

    cal = calendar_feature_frame(pd.Series([target]), timezone=calendar_timezone).iloc[0]
    row.update(cal.to_dict())
    row.update({
        'target_hour': row['hour'],
        'target_day_of_week': row['day_of_week'],
        'target_weekend': row['weekend'],
        'target_holiday_national': row['holiday_national'],
        'target_carnival': row['carnival'],
        'target_good_friday': row['good_friday'],
        'target_corpus_christi': row['corpus_christi'],
        'target_month': row['month'],
    })
    row['target_hour_sin'] = float(np.sin(2 * np.pi * float(row['target_hour']) / 24.0))
    row['target_hour_cos'] = float(np.cos(2 * np.pi * float(row['target_hour']) / 24.0))
    row['target_day_of_week_sin'] = float(np.sin(2 * np.pi * float(row['target_day_of_week']) / 7.0))
    row['target_day_of_week_cos'] = float(np.cos(2 * np.pi * float(row['target_day_of_week']) / 7.0))

    if climate_lookup is not None and target in climate_lookup.index:
        cr = climate_lookup.loc[target]
        if isinstance(cr, pd.DataFrame):
            raise ValueError(f'duplicate climate rows for {subsystem_id} {target}')
        for c, v in cr.items():
            if c not in {'interval_start_utc', 'subsystem_id', 'weighting_method', 'weather_mode'}:
                row[c] = v
    row['feature_set_version'] = FEATURE_SET_VERSION
    return pd.DataFrame([row])
