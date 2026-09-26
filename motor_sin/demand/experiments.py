from __future__ import annotations
from datetime import timedelta

import json
import numpy as np
import pandas as pd

from motor_sin.demand.direct import (
    DIRECT_ISSUE_LAGS,
    DIRECT_TARGET_LAGS,
    SAME_TARGET_HOUR_WINDOWS_DAYS,
    FEATURE_SET_VERSION,
    build_direct_prediction_row,
    fit_direct_models,
)
from motor_sin.demand.metrics import regression_metrics
from motor_sin.demand.model import feature_contributions


def _canonical_zone(subsystem_id: str) -> str:
    raw = str(subsystem_id).strip().upper()
    return {'SE': 'SE/CO', 'SECO': 'SE/CO'}.get(raw, raw)


def _segment_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    masks = {'ALL': pd.Series(True, index=frame.index)}
    if 'incident_cell_fraction' in frame:
        masks['EXTREME_ANY'] = pd.to_numeric(frame['incident_cell_fraction'], errors='coerce').fillna(0).gt(0)
    for typ in ['heat', 'cold', 'rain', 'wind', 'solar_deficit']:
        c = f'incident_{typ}_fraction'
        if c in frame:
            masks[f'EXTREME_{typ.upper()}'] = pd.to_numeric(frame[c], errors='coerce').fillna(0).gt(0)
    return masks


def _metric_from_predictions(pred: pd.DataFrame, *, subsystem_id: str, experiment: str, segment: str, horizon: str) -> dict:
    y = pred['actual_mw'].astype(float).to_numpy()
    p50 = pred['p50_mw'].astype(float).to_numpy()
    has_interval = {'p10_mw', 'p90_mw'}.issubset(pred.columns) and pred['p10_mw'].notna().all() and pred['p90_mw'].notna().all()
    if has_interval:
        m = regression_metrics(y, p50, pred['p10_mw'].astype(float).to_numpy(), pred['p90_mw'].astype(float).to_numpy())
    else:
        m = regression_metrics(y, p50)
        m['p10_p90_coverage'] = np.nan
    return {'subsystem_id': subsystem_id, 'experiment': experiment, 'segment': segment, 'horizon': horizon, 'n_rows': int(len(pred)), **m}


def _build_origin_schedule(load_zone: pd.DataFrame, *, test_hours: int, forecast_horizon: int, origin_step_hours: int) -> tuple[pd.Timestamp, list[pd.Timestamp]]:
    if forecast_horizon < 1:
        raise ValueError('forecast_horizon must be >= 1')
    if forecast_horizon > 24:
        raise ValueError('real pilot currently limits forecast_horizon to 24h so D-1 remains observable at issue time')
    if origin_step_hours < 1:
        raise ValueError('origin_step_hours must be >= 1')
    if len(load_zone) <= test_hours + max(DIRECT_ISSUE_LAGS):
        raise ValueError(f'not enough rows for pilot: rows={len(load_zone)} test_hours={test_hours}')
    test_hours = int(test_hours)
    test_start = load_zone.iloc[-test_hours]['interval_start_utc']
    first_issue = test_start - timedelta(hours=1)
    last_target = load_zone.iloc[-1]['interval_start_utc']
    last_issue = last_target - timedelta(hours=int(forecast_horizon))
    if last_issue < first_issue:
        raise ValueError('test window is shorter than forecast horizon')
    origins = list(pd.date_range(first_issue, last_issue, freq=f'{int(origin_step_hours)}h'))
    if not origins:
        raise ValueError('no forecast origins available')
    return first_issue, origins


def _origin_is_complete(
    issue: pd.Timestamp,
    *,
    forecast_horizon: int,
    actual_lookup: dict[pd.Timestamp, float],
    climate_lookup: pd.DataFrame | None,
    required_exog: set[str],
) -> bool:
    # All issue-state load inputs are anchored at or before issue time.
    for lag in DIRECT_ISSUE_LAGS:
        if issue - timedelta(hours=int(lag)) not in actual_lookup:
            return False
    for step in range(1, forecast_horizon + 1):
        ts = issue + timedelta(hours=int(step))
        if ts not in actual_lookup:
            return False
        # E0 and v1.1.4 target-history features must be genuinely observable at issue time.
        target_history_lags = set(DIRECT_TARGET_LAGS) | {24 * d for days in SAME_TARGET_HOUR_WINDOWS_DAYS for d in range(1, days + 1)}
        for lag in target_history_lags:
            lag_ts = ts - timedelta(hours=int(lag))
            if lag_ts > issue or lag_ts not in actual_lookup:
                return False
        if required_exog:
            if climate_lookup is None or ts not in climate_lookup.index:
                return False
            row = climate_lookup.loc[ts]
            if isinstance(row, pd.DataFrame):
                return False
            for c in required_exog:
                if c not in row.index or pd.isna(row[c]):
                    return False
    return True


def compare_experiments(
    load: pd.DataFrame,
    zone_climate: pd.DataFrame | None,
    *,
    subsystem_id: str,
    test_hours: int = 720,
    alpha: float = 1.0,
    forecast_horizon: int = 24,
    origin_step_hours: int = 24,
    calendar_timezone: str = 'America/Sao_Paulo',
    calibration_hours: int = 720,
    algorithm: str = 'ridge',
    xgb_params: dict | None = None,
    experiments_override: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fixed-origin direct multi-horizon E0/E1/E2/E3 backtest.

    One independent point model is fit for each horizon H01..H24 and experiment. Every model
    uses issue-time state plus observed history aligned to the target clock hour, target-time
    calendar/cyclic features, and optional target-time weather. No H01 prediction is fed into H02, etc., so forecast errors do
    not propagate recursively.

    P10/P90 are calibrated separately for every horizon on a chronological pre-test calibration
    block. The test window is never used either for point-model fitting or interval calibration.
    """
    subsystem_id = _canonical_zone(subsystem_id)
    l = load.copy()
    l['interval_start_utc'] = pd.to_datetime(l['interval_start_utc'], utc=True, errors='raise')
    l['subsystem_id'] = l['subsystem_id'].astype(str).str.strip().str.upper().replace({'SE': 'SE/CO', 'SECO': 'SE/CO'})
    g_load = l[l['subsystem_id'].eq(subsystem_id)].sort_values('interval_start_utc').copy()
    if g_load.empty:
        raise ValueError(f'no load rows for subsystem {subsystem_id}')
    if g_load['interval_start_utc'].duplicated().any():
        raise ValueError('load has duplicate subsystem-hour rows')
    diffs = g_load['interval_start_utc'].diff().dropna()
    if len(diffs) and not diffs.eq(timedelta(hours=1)).all():
        raise ValueError('load must be hourly and contiguous for direct multi-horizon evaluation')

    first_issue, origins = _build_origin_schedule(
        g_load,
        test_hours=test_hours,
        forecast_horizon=forecast_horizon,
        origin_step_hours=origin_step_hours,
    )

    z = None
    climate_lookup = None
    if zone_climate is not None and len(zone_climate):
        z = zone_climate.copy()
        z['interval_start_utc'] = pd.to_datetime(z['interval_start_utc'], utc=True, errors='raise')
        z['subsystem_id'] = z['subsystem_id'].astype(str).str.strip().str.upper().replace({'SE': 'SE/CO', 'SECO': 'SE/CO'})
        z = z[z['subsystem_id'].eq(subsystem_id)].sort_values('interval_start_utc').copy()
        if z.duplicated(['interval_start_utc', 'subsystem_id']).any():
            raise ValueError('zone_climate has duplicate subsystem-hour rows')
        climate_lookup = z.set_index('interval_start_utc', drop=False)

    experiments = ['E1']
    if z is not None and len(z):
        raw_prefixes = ('temperature_2m_', 'precipitation_', 'wind_speed_', 'solar_radiation_')
        has_raw = all(any(c.startswith(prefix) and 'percentile' not in c and 'anomaly' not in c for c in z.columns) for prefix in raw_prefixes)
        anomaly_or_percentile = any(('anomaly_' in c or 'percentile_' in c) for c in z.columns)
        incident_cols = [c for c in z.columns if c.startswith('incident_')]
        nonzero_incident = any(pd.to_numeric(z[c], errors='coerce').fillna(0).abs().gt(0).any() for c in incident_cols)
        has_enhanced = bool(anomaly_or_percentile or nonzero_incident)
        if has_raw:
            experiments.append('E2')
        if has_raw and has_enhanced:
            experiments.append('E3')
    if experiments_override is not None:
        requested=[str(e).upper() for e in experiments_override]
        unavailable=[e for e in requested if e not in experiments]
        if unavailable:
            raise ValueError(f'requested experiment(s) unavailable for supplied datasets: {unavailable}')
        experiments=requested
    bundles, required_exog = fit_direct_models(
        g_load,
        z,
        experiments=experiments,
        first_issue=first_issue,
        forecast_horizon=forecast_horizon,
        calendar_timezone=calendar_timezone,
        alpha=alpha,
        calibration_hours=calibration_hours,
        algorithm=algorithm,
        xgb_params=xgb_params,
    )

    actual_lookup = {ts: float(v) for ts, v in zip(g_load['interval_start_utc'], g_load['load_mw'])}
    valid_origins = [
        o for o in origins
        if _origin_is_complete(
            o,
            forecast_horizon=forecast_horizon,
            actual_lookup=actual_lookup,
            climate_lookup=climate_lookup,
            required_exog=required_exog,
        )
    ]
    if not valid_origins:
        raise ValueError('no complete fixed forecast origins after target/exogenous availability checks')

    pred_rows = []
    for issue in valid_origins:
        for step in range(1, forecast_horizon + 1):
            ts = issue + timedelta(hours=int(step))
            actual = float(actual_lookup[ts])
            d1 = float(actual_lookup[ts - timedelta(hours=24)])
            d7 = float(actual_lookup[ts - timedelta(hours=168)])
            for name, p in [('E0_D1', d1), ('E0_D7', d7), ('E0_BLEND', (d1 + d7) / 2)]:
                pred_rows.append({
                    'issue_time_utc': issue,
                    'interval_start_utc': ts,
                    'horizon_hour': step,
                    'subsystem_id': subsystem_id,
                    'experiment': name,
                    'actual_mw': actual,
                    'p10_mw': np.nan,
                    'p50_mw': p,
                    'p90_mw': np.nan,
                    'main_drivers_json': None,
                    'model_strategy': 'observed_lag_baseline',
                    'algorithm': 'baseline',
                    'interval_calibration_method': None,
                    'interval_calibration_rows': 0,
                    'interval_calibration_coverage': np.nan,
                })

            frame = build_direct_prediction_row(
                issue=issue,
                target=ts,
                subsystem_id=subsystem_id,
                actual_lookup=actual_lookup,
                climate_lookup=climate_lookup,
                calendar_timezone=calendar_timezone,
            )
            for experiment in experiments:
                bundle = bundles[(experiment, step)]
                model = bundle.model
                missing = [c for c in model.features if c not in frame.columns or pd.isna(frame.iloc[0][c])]
                if missing:
                    raise ValueError(f'missing feature(s) at direct origin {issue} H{step:02d} target {ts}: {missing}')
                p10, p50, p90 = model.predict(frame)
                pred_rows.append({
                    'issue_time_utc': issue,
                    'interval_start_utc': ts,
                    'horizon_hour': step,
                    'subsystem_id': subsystem_id,
                    'experiment': experiment,
                    'actual_mw': actual,
                    'p10_mw': float(p10[0]),
                    'p50_mw': float(p50[0]),
                    'p90_mw': float(p90[0]),
                    'main_drivers_json': json.dumps(feature_contributions(model, frame.iloc[0]), ensure_ascii=False),
                    'model_strategy': 'direct_multi_horizon_target_history',
                    'algorithm': str(algorithm).lower(),
                    'feature_set_version': FEATURE_SET_VERSION,
                    'interval_calibration_method': bundle.calibration_method,
                    'interval_calibration_rows': bundle.calibration_rows,
                    'interval_calibration_coverage': bundle.calibration_coverage,
                })

    preds = pd.DataFrame(pred_rows)
    # Incident columns are attached only for evaluation segmentation, never as implicit E1 inputs.
    if z is not None:
        incident_cols = [c for c in z.columns if c.startswith('incident_')]
        if incident_cols:
            seg = z[['interval_start_utc', *incident_cols]].drop_duplicates('interval_start_utc')
            preds = preds.merge(seg, on='interval_start_utc', how='left', validate='many_to_one')

    metrics = []
    for e, ep in preds.groupby('experiment', sort=True):
        masks = _segment_masks(ep)
        for seg_name, mask in masks.items():
            sub = ep.loc[mask].copy()
            if len(sub):
                metrics.append(_metric_from_predictions(sub, subsystem_id=subsystem_id, experiment=e, segment=seg_name, horizon='ALL'))
        for h in range(1, forecast_horizon + 1):
            sub = ep[ep['horizon_hour'].eq(h)]
            if len(sub):
                metrics.append(_metric_from_predictions(sub, subsystem_id=subsystem_id, experiment=e, segment='ALL', horizon=f'H{h:02d}'))

    metrics_df = pd.DataFrame(metrics).sort_values(['segment', 'horizon', 'experiment']).reset_index(drop=True)
    metrics_df['algorithm'] = metrics_df['experiment'].map(lambda e: 'baseline' if str(e).startswith('E0_') else str(algorithm).lower())
    preds_df = preds.sort_values(['issue_time_utc', 'horizon_hour', 'experiment']).reset_index(drop=True)
    preds_df['calendar_timezone'] = calendar_timezone
    preds_df['forecast_horizon'] = forecast_horizon
    preds_df['backtest_method'] = 'fixed_origin_direct_multi_horizon_target_history'
    preds_df['feature_set_version'] = preds_df.get('feature_set_version', pd.Series(index=preds_df.index, dtype=object)).fillna('baseline_observed_lags')
    return metrics_df, preds_df


def incremental_summary(metrics: pd.DataFrame) -> dict:
    base = metrics[(metrics.segment.eq('ALL')) & (metrics.horizon.eq('ALL'))].set_index('experiment')
    out = {'baseline_reference': 'E1' if 'E1' in base.index else None}
    for e in ['E2', 'E3']:
        if e in base.index and 'E1' in base.index:
            e1 = float(base.loc['E1', 'WAPE'])
            v = float(base.loc[e, 'WAPE'])
            out[f'{e}_wape_change_vs_E1_pct'] = 100 * (v - e1) / e1 if e1 else None
    if 'E3' in base.index and 'E2' in base.index:
        e2 = float(base.loc['E2', 'WAPE'])
        e3 = float(base.loc['E3', 'WAPE'])
        out['E3_wape_change_vs_E2_pct'] = 100 * (e3 - e2) / e2 if e2 else None
    ext = metrics[(metrics.segment.eq('EXTREME_ANY')) & (metrics.horizon.eq('ALL'))].set_index('experiment')
    if 'E3' in ext.index and 'E1' in ext.index:
        e1 = float(ext.loc['E1', 'WAPE'])
        v = float(ext.loc['E3', 'WAPE'])
        out['E3_extreme_wape_change_vs_E1_pct'] = 100 * (v - e1) / e1 if e1 else None
    if 'E3' in ext.index and 'E2' in ext.index:
        e2 = float(ext.loc['E2', 'WAPE'])
        e3 = float(ext.loc['E3', 'WAPE'])
        out['E3_extreme_wape_change_vs_E2_pct'] = 100 * (e3 - e2) / e2 if e2 else None
    for h in [1, 6, 12, 24]:
        tag = f'H{h:02d}'
        hm = metrics[(metrics.segment.eq('ALL')) & (metrics.horizon.eq(tag))].set_index('experiment')
        if 'E1' in hm.index:
            out[f'E1_wape_{tag}'] = float(hm.loc['E1', 'WAPE'])
        for e in ['E2', 'E3']:
            if e in hm.index and 'E1' in hm.index:
                e1 = float(hm.loc['E1', 'WAPE'])
                v = float(hm.loc[e, 'WAPE'])
                out[f'{e}_wape_change_vs_E1_pct_{tag}'] = 100 * (v - e1) / e1 if e1 else None
        if 'E3' in hm.index and 'E2' in hm.index:
            e2 = float(hm.loc['E2', 'WAPE'])
            e3 = float(hm.loc['E3', 'WAPE'])
            out[f'E3_wape_change_vs_E2_pct_{tag}'] = 100 * (e3 - e2) / e2 if e2 else None
    return out
