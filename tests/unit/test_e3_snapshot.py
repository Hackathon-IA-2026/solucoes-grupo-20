from __future__ import annotations

import numpy as np
import pandas as pd

from motor_sin.climate.e3_snapshot import (
    build_daily_archive_parameters,
    build_e3_daily_context,
    build_e3_hourly_zone_context,
    infer_target_year_from_load,
    merge_e2_with_e3_context,
)
from motor_sin.climate.e2_pilot import load_pilot_points
from motor_sin.demand.direct import direct_feature_columns


def _baseline_one_cell() -> pd.DataFrame:
    dates = pd.date_range('2015-01-01', '2024-12-31', freq='D')
    # deterministic seasonal baseline with enough samples in every month
    doy = dates.dayofyear.to_numpy()
    tmax = 28.0 + 4.0 * np.sin(2 * np.pi * doy / 365.25)
    tmin = 18.0 + 3.0 * np.sin(2 * np.pi * doy / 365.25)
    return pd.DataFrame({
        'point_id': 'p1',
        'cell_id': 'g01_0700_1300',
        'date_local': dates.strftime('%Y-%m-%d'),
        'temperature_2m_max': tmax,
        'temperature_2m_min': tmin,
    })


def test_daily_params_keep_snapshot_baseline_local_day_and_era5_land():
    params = build_daily_archive_parameters(
        latitude=-23.5,
        longitude=-46.6,
        timezone_name='America/Sao_Paulo',
        start_date='2015-01-01',
        end_date='2024-12-31',
        variables=('temperature_2m_max','temperature_2m_min'),
        model='era5_land',
    )
    assert params['models'] == 'era5_land'
    assert params['timezone'] == 'America/Sao_Paulo'
    assert params['daily'] == 'temperature_2m_max,temperature_2m_min'


def test_infer_target_year_from_ons_utc_load_uses_local_civil_year():
    ts = pd.date_range('2025-01-01 03:00', periods=8760, freq='h', tz='UTC')
    load = pd.DataFrame({'interval_start_utc': ts, 'subsystem_id': 'SE/CO', 'load_mw': 1.0})
    assert infer_target_year_from_load(load, subsystem_id='SE/CO') == 2025


def test_e3_snapshot_anomaly_and_event_rules_are_materialized():
    baseline_daily = _baseline_one_cell()
    # Five consecutive very hot days also satisfy rain/wind thresholds on selected days.
    target = pd.DataFrame({
        'point_id': 'p1',
        'cell_id': 'g01_0700_1300',
        'date_local': [f'2025-01-{d:02d}' for d in range(10, 15)],
        'timezone': 'America/Sao_Paulo',
        'name': 'P1',
        'state': 'SP',
        'subsystem_id': 'SE/CO',
        'weight': 1.0,
        'temperature_2m_max': [37.0] * 5,
        'temperature_2m_min': [26.0] * 5,
        'wind_gusts_10m_max': [55.0, 65.0, 85.0, 105.0, 65.0],
        'precipitation_sum': [0.0, 30.0, 55.0, 110.0, 35.0],
    })
    baseline, context = build_e3_daily_context(baseline_daily, target, target_year=2025)
    assert baseline['baseline_year_start'].eq(2015).all()
    assert baseline['baseline_year_end'].eq(2024).all()
    assert context['temperature_max_anomaly_c'].gt(3.0).all()
    assert context['extreme_heat_day'].all()
    assert context['heat_wave_candidate'].all()
    # highest rain/wind daily severity only
    assert bool(context.loc[2, 'heavy_rain_day'])
    assert bool(context.loc[3, 'extreme_rain_day'])
    assert not bool(context.loc[3, 'heavy_rain_day'])
    assert bool(context.loc[1, 'strong_wind_day'])
    assert bool(context.loc[2, 'severe_wind_day'])
    assert bool(context.loc[3, 'extreme_wind_day'])
    assert bool(context.loc[1, 'storm_candidate'])  # >=30 mm and >=60 km/h
    assert context['rules_version'].eq('2026-08-08.2').all()


def test_e3_hourly_context_merges_with_e2_and_becomes_model_feature():
    baseline_daily = _baseline_one_cell()
    target = pd.DataFrame({
        'point_id': 'p1', 'cell_id': 'g01_0700_1300',
        'date_local': ['2025-01-10'], 'timezone': 'America/Sao_Paulo',
        'name': 'P1', 'state': 'SP', 'subsystem_id': 'SE/CO', 'weight': 1.0,
        'temperature_2m_max': [37.0], 'temperature_2m_min': [26.0],
        'wind_gusts_10m_max': [85.0], 'precipitation_sum': [55.0],
    })
    _, daily = build_e3_daily_context(baseline_daily, target, target_year=2025)
    points = pd.DataFrame([{
        'point_id':'p1','name':'P1','state':'SP','subsystem_id':'SE/CO',
        'latitude':-23.5,'longitude':-46.6,'timezone':'America/Sao_Paulo','weight':1.0,
    }])
    ts = pd.date_range('2025-01-10 03:00', periods=24, freq='h', tz='UTC')
    e2 = pd.DataFrame({
        'interval_start_utc': ts,
        'subsystem_id': 'SE/CO',
        'temperature_2m_mean': 30.0,
        'precipitation_mean': 0.0,
        'wind_speed_10m_mean': 3.0,
        'solar_radiation_mean': 100.0,
        'weather_mode': 'PERFECT_WEATHER_BACKTEST',
    })
    hourly = build_e3_hourly_zone_context(daily, points, e2[['interval_start_utc']], subsystem_id='SE/CO')
    merged = merge_e2_with_e3_context(e2, hourly)
    assert merged['incident_heat_fraction'].eq(1.0).all()
    assert merged['incident_rain_fraction'].eq(1.0).all()
    assert 'temperature_max_anomaly_c_mean' in merged.columns
    features = direct_feature_columns(merged, 'E3')
    assert 'temperature_max_anomaly_c_mean' in features
    assert 'incident_heat_fraction' in features


def test_target_snapshot_daily_params_omit_models_like_supplied_historical_collector():
    params = build_daily_archive_parameters(
        latitude=-23.5,
        longitude=-46.6,
        timezone_name='America/Sao_Paulo',
        start_date='2025-01-01',
        end_date='2025-12-31',
        variables=('temperature_2m_max','temperature_2m_min','precipitation_sum','wind_gusts_10m_max'),
        model=None,
    )
    assert 'models' not in params
    assert params['daily'] == 'temperature_2m_max,temperature_2m_min,precipitation_sum,wind_gusts_10m_max'


def test_e3_download_specs_keep_era5_land_only_for_baseline(monkeypatch, tmp_path):
    import motor_sin.climate.e3_snapshot as mod
    calls = []
    def fake_download_daily_record(*, point, spec, raw_directory, timeout_seconds=90):
        calls.append(spec)
        return {
            'channel': spec.channel, 'point_id': point.point_id, 'name': point.name,
            'state': point.state, 'subsystem_id': point.subsystem_id,
            'latitude_requested': point.latitude, 'longitude_requested': point.longitude,
            'timezone': point.timezone, 'weight': point.weight,
            'model': spec.model or 'best_match', 'variables': list(spec.variables),
            'start_date': spec.start_date, 'end_date': spec.end_date,
            'raw_file': str(tmp_path/'x.json'), 'created': True, 'content_hash': 'x',
            'retrieved_at_utc': '2025-01-01T00:00:00Z', 'request_url': 'x',
        }
    monkeypatch.setattr(mod, 'download_daily_record', fake_download_daily_record)
    points = pd.DataFrame([{
        'point_id':'p1','name':'P1','state':'SP','subsystem_id':'SE/CO',
        'latitude':-23.5,'longitude':-46.6,'timezone':'America/Sao_Paulo','weight':1.0,
    }])
    out = mod.download_e3_context(points, target_year=2025, raw_directory=tmp_path)
    assert len(out) == 2
    baseline = next(x for x in calls if x.channel == 'baseline_temperature')
    target = next(x for x in calls if x.channel == 'target_snapshot_daily')
    assert baseline.model == 'era5_land'
    assert target.model is None
    assert 'wind_gusts_10m_max' in target.variables
    assert 'precipitation_sum' in target.variables
