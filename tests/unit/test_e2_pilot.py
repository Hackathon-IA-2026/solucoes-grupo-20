import json
from pathlib import Path

import numpy as np
import pandas as pd

from motor_sin.climate.e2_pilot import (
    load_pilot_points,
    infer_date_bounds_from_load,
    aggregate_pilot_zone_climate,
    validate_e2_climate_coverage,
)
from motor_sin.climate.openmeteo_snapshot_anomaly import (
    baseline_years_for_target,
    build_monthly_temperature_baseline,
    score_daily_temperature_context,
)
from motor_sin.demand.experiments import compare_experiments


def test_e2_points_config_and_load_bounds():
    points = load_pilot_points('configs/e2_seco_points.csv', subsystem_id='SE/CO')
    assert len(points) == 8
    assert set(points['subsystem_id']) == {'SE/CO'}
    ts = pd.date_range('2025-01-01 03:00', periods=10, freq='h', tz='UTC')
    load = pd.DataFrame({'interval_start_utc': ts, 'subsystem_id': 'SE/CO', 'load_mw': 1.0})
    assert infer_date_bounds_from_load(load, subsystem_id='SE/CO') == ('2025-01-01', '2025-01-01')


def test_e2_zone_aggregation_materializes_raw_feature_families():
    ts = pd.date_range('2025-01-01', periods=4, freq='h', tz='UTC')
    rows = []
    for cell, offset in [('g01_0700_1300', 0.0), ('g01_0710_1310', 2.0)]:
        for i, t in enumerate(ts):
            rows.append({
                'interval_start_utc': t, 'cell_id': cell,
                'temperature_2m': 20+i+offset,
                'dewpoint_2m': 15+i,
                'precipitation': float(i),
                'wind_speed_10m': 3+i,
                'solar_radiation': 100*i,
            })
    climate = pd.DataFrame(rows)
    out = aggregate_pilot_zone_climate(climate, subsystem_id='SE/CO')
    assert len(out) == 4
    assert set(out['subsystem_id']) == {'SE/CO'}
    assert out['sample_cell_count'].eq(2).all()
    for col in ['temperature_2m_mean', 'dewpoint_2m_mean', 'precipitation_mean', 'wind_speed_10m_mean', 'solar_radiation_mean']:
        assert col in out.columns
    assert set(out['climate_spatial_method']) == {'MVP_REPRESENTATIVE_POINTS_UNIFORM'}
    assert not any(c.startswith('incident_') for c in out.columns)


def _make_raw_only_pilot(n=24*80):
    ts = pd.date_range('2025-01-01 03:00:00', periods=n, freq='h', tz='UTC')
    local = ts.tz_convert('America/Sao_Paulo')
    h = local.hour.to_numpy()
    temp = 24 + 7*np.sin(2*np.pi*(h-14)/24)
    rng = np.random.default_rng(3)
    load = pd.DataFrame({
        'interval_start_utc': ts,
        'subsystem_id': 'SE/CO',
        'load_mw': 30000 + 3200*np.sin(2*np.pi*(h-18)/24) + 180*temp + rng.normal(0,100,n),
    })
    climate = pd.DataFrame({
        'interval_start_utc': ts,
        'subsystem_id': 'SE/CO',
        'temperature_2m_mean': temp,
        'temperature_2m_p90': temp+1,
        'temperature_2m_max': temp+2,
        'precipitation_mean': 0.1,
        'precipitation_p90': 0.3,
        'wind_speed_10m_mean': 4.0,
        'wind_speed_10m_p90': 5.0,
        'solar_radiation_mean': np.maximum(0,500*np.sin(np.pi*(h-6)/12)),
        'solar_radiation_p90': np.maximum(0,550*np.sin(np.pi*(h-6)/12)),
        'weather_mode': 'PERFECT_WEATHER_BACKTEST',
    })
    return load, climate


def test_raw_only_climate_runs_e2_but_not_e3():
    load, climate = _make_raw_only_pilot()
    metrics, _ = compare_experiments(
        load, climate, subsystem_id='SE/CO', test_hours=24*5,
        forecast_horizon=24, origin_step_hours=24,
        calendar_timezone='America/Sao_Paulo', calibration_hours=168,
    )
    experiments = set(metrics['experiment'])
    assert 'E1' in experiments
    assert 'E2' in experiments
    assert 'E3' not in experiments


def test_snapshot_baseline_years_and_anomaly_thresholds():
    assert baseline_years_for_target(2025) == list(range(2015, 2025))
    # 10 complete years of January, 31 samples/year -> 310/month, above snapshot minimum 250.
    rows = []
    for year in range(2015, 2025):
        for day in range(1, 32):
            rows.append({
                'cell_id': 'c1', 'date_local': f'{year}-01-{day:02d}',
                'temperature_2m_max': 30.0 + (day % 5),
                'temperature_2m_min': 18.0 + (day % 3),
            })
    daily = pd.DataFrame(rows)
    baseline = build_monthly_temperature_baseline(daily, target_year=2025)
    assert set(baseline['metric']) == {'temperature_2m_max','temperature_2m_min'}
    bmax = baseline[baseline['metric'].eq('temperature_2m_max')].iloc[0]
    target = pd.DataFrame([{
        'cell_id': 'c1','date_local':'2025-01-15',
        'temperature_2m_max': float(bmax['p95']) + 4.0,
        'temperature_2m_min': 20.0,
    }])
    scored = score_daily_temperature_context(target, baseline)
    hot = scored[scored['metric'].eq('temperature_2m_max')].iloc[0]
    assert hot['anomaly_from_mean_c'] > 3.0
    assert bool(hot['extreme_heat_day'])


def test_e2_rejects_all_null_required_variable_instead_of_silently_dropping_family():
    ts = pd.date_range('2025-01-01', periods=2, freq='h', tz='UTC')
    climate = pd.DataFrame({
        'interval_start_utc': ts,
        'cell_id': ['c1','c1'],
        'temperature_2m': [20.0,21.0],
        'dewpoint_2m': [15.0,16.0],
        'precipitation': [np.nan,np.nan],
        'wind_speed_10m': [3.0,4.0],
        'solar_radiation': [0.0,100.0],
    })
    import pytest
    with pytest.raises(ValueError, match='precipitation: all values are null'):
        validate_e2_climate_coverage(climate)
