from __future__ import annotations
from datetime import timedelta

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from motor_sin.demand.direct import build_direct_frame, direct_feature_columns
from motor_sin.demand.model import DemandModel, fit_demand_model, load_model, save_model


@dataclass(frozen=True)
class FrozenDirectModel:
    horizon_hour: int
    path: Path
    model: DemandModel
    fit_rows: int
    calibration_rows: int
    calibration_coverage: float


def _canonical_zone(value: str) -> str:
    raw = str(value).strip().upper()
    return {'SE': 'SE/CO', 'SECO': 'SE/CO'}.get(raw, raw)


def _calibrate(model: DemandModel, frame: pd.DataFrame, features: list[str]) -> tuple[DemandModel, float]:
    work = frame.dropna(subset=[*features, 'load_mw']).copy()
    if len(work) < 48:
        raise ValueError(f'calibration block requires >=48 rows, got {len(work)}')
    p50 = model.predict_p50(work)
    y = work['load_mw'].astype(float).to_numpy()
    residual = y - p50
    model.residual_p10 = min(float(np.quantile(residual, 0.10)), 0.0)
    model.residual_p90 = max(float(np.quantile(residual, 0.90)), 0.0)
    model.calibration_rows = int(len(work))
    model.calibration_method = 'final_model_tail_asymmetric_residual_quantiles'
    model.target_interval_coverage = 0.80
    p10, _, p90 = model.predict(work)
    coverage = float(np.mean((y >= p10) & (y <= p90)))
    model.calibration_empirical_coverage = coverage
    return model, coverage


def freeze_direct_model_family(
    load: pd.DataFrame,
    climate: pd.DataFrame | None,
    *,
    subsystem_id: str,
    experiment: str = 'E3',
    horizon: int = 24,
    calendar_timezone: str = 'America/Sao_Paulo',
    calibration_hours: int = 720,
    alpha: float = 1.0,
    algorithm: str = 'ridge',
    xgb_params: dict[str, Any] | None = None,
    output_dir: str | Path = 'models/demand/e3_seco_v1',
    model_family_id: str = 'E3_SECO_DIRECT_V1',
) -> dict[str, Any]:
    """Freeze a deployment-ready H01..H24 model family after experiment selection.

    The point model is fit on all eligible history except the final chronological calibration
    block. The calibration block is reserved for p10/p90 residual quantiles. This is a deployment
    packaging step, not a new model-selection experiment.
    """
    subsystem_id = _canonical_zone(subsystem_id)
    l = load.copy()
    l['interval_start_utc'] = pd.to_datetime(l['interval_start_utc'], utc=True, errors='raise')
    l['subsystem_id'] = l['subsystem_id'].astype(str).map(_canonical_zone)
    l = l[l['subsystem_id'].eq(subsystem_id)].sort_values('interval_start_utc').reset_index(drop=True)
    if l.empty:
        raise ValueError(f'no load rows for subsystem={subsystem_id}')
    if l['interval_start_utc'].duplicated().any():
        raise ValueError('load contains duplicate hours')
    if len(l) > 1 and not l['interval_start_utc'].diff().dropna().eq(timedelta(hours=1)).all():
        raise ValueError('load must be hourly and contiguous')

    z = None
    if climate is not None and len(climate):
        z = climate.copy()
        z['interval_start_utc'] = pd.to_datetime(z['interval_start_utc'], utc=True, errors='raise')
        z['subsystem_id'] = z['subsystem_id'].astype(str).map(_canonical_zone)
        z = z[z['subsystem_id'].eq(subsystem_id)].sort_values('interval_start_utc').reset_index(drop=True)
        if z.empty:
            raise ValueError(f'no climate rows for subsystem={subsystem_id}')
        if z['interval_start_utc'].duplicated().any():
            raise ValueError('climate contains duplicate hours')
    elif str(experiment).upper() != 'E1':
        raise ValueError(f'{experiment} requires a climate dataset')

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []

    for h in range(1, int(horizon) + 1):
        frame = build_direct_frame(l, z, horizon_hour=h, calendar_timezone=calendar_timezone)
        features = direct_feature_columns(frame, experiment)
        valid = frame.dropna(subset=[*features, 'load_mw']).copy()
        min_fit = max(30, len(features) + 5)
        if len(valid) < min_fit + max(48, calibration_hours):
            raise ValueError(
                f'not enough rows to freeze {experiment} H{h:02d}: '
                f'valid={len(valid)} min_fit={min_fit} calibration={calibration_hours}'
            )
        fit = valid.iloc[:-calibration_hours].copy()
        cal = valid.iloc[-calibration_hours:].copy()
        model = fit_demand_model(fit, features, algorithm=algorithm, alpha=alpha, xgb_params=xgb_params)
        model, coverage = _calibrate(model, cal, features)
        model_path = output_dir / f'{subsystem_id.replace("/", "_")}_{experiment}_H{h:02d}.json'
        save_model(model, model_path)
        records.append({
            'horizon_hour': h,
            'model_file': model_path.name,
            'fit_rows': int(len(fit)),
            'calibration_rows': int(len(cal)),
            'calibration_coverage': coverage,
            'fit_target_start_utc': str(fit['interval_start_utc'].min()),
            'fit_target_end_utc': str(fit['interval_start_utc'].max()),
            'calibration_target_start_utc': str(cal['interval_start_utc'].min()),
            'calibration_target_end_utc': str(cal['interval_start_utc'].max()),
            'feature_count': len(features),
            'features': features,
        })

    weather_modes = sorted(set(z.get('weather_mode', pd.Series(dtype=str)).dropna().astype(str).tolist())) if z is not None else []
    manifest = {
        'model_family_id': model_family_id,
        'experiment': experiment,
        'subsystem_id': subsystem_id,
        'forecast_horizon_hours': int(horizon),
        'calendar_timezone': calendar_timezone,
        'algorithm': 'XGBoostResidualModel' if str(algorithm).lower() in {'xgb','xgboost'} else 'RidgeQuantileModel',
        'algorithm_key': str(algorithm).lower(),
        'algorithm_params': (xgb_params or {}) if str(algorithm).lower() in {'xgb','xgboost'} else {'alpha': float(alpha)},
        'feature_set_version': 'v1.1.4_target_history',
        'ridge_alpha': float(alpha),
        'interval_target_coverage': 0.80,
        'calibration_hours': int(calibration_hours),
        'load_history_start_utc': str(l['interval_start_utc'].min()),
        'load_history_end_utc': str(l['interval_start_utc'].max()),
        'climate_history_start_utc': str(z['interval_start_utc'].min()) if z is not None else None,
        'climate_history_end_utc': str(z['interval_start_utc'].max()) if z is not None else None,
        'weather_modes_seen': weather_modes,
        'deployment_status': 'MVP_FROZEN_AFTER_HELDOUT_SELECTION',
        'models': records,
    }
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def load_frozen_model_family(model_dir: str | Path) -> tuple[dict[str, Any], dict[int, FrozenDirectModel]]:
    model_dir = Path(model_dir)
    manifest_path = model_dir / 'manifest.json'
    if not manifest_path.exists():
        raise FileNotFoundError(f'model manifest not found: {manifest_path}')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    models: dict[int, FrozenDirectModel] = {}
    for rec in manifest['models']:
        h = int(rec['horizon_hour'])
        path = model_dir / rec['model_file']
        models[h] = FrozenDirectModel(
            horizon_hour=h,
            path=path,
            model=load_model(path),
            fit_rows=int(rec['fit_rows']),
            calibration_rows=int(rec['calibration_rows']),
            calibration_coverage=float(rec['calibration_coverage']),
        )
    return manifest, models
