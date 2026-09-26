from pathlib import Path
import pandas as pd

from motor_sin.climate.operational_forecast import _score_daily_forecast
from motor_sin.climate.openmeteo_snapshot_anomaly import load_snapshot_rules


def test_all_regional_representative_point_configs_exist():
    root=Path(__file__).resolve().parents[2]
    for tag in ['n','ne','seco','s']:
        p=root/f'configs/e2_{tag}_points.csv'
        assert p.exists(), tag
        df=pd.read_csv(p)
        assert len(df)>=3
        assert {'point_id','subsystem_id','latitude','longitude','timezone','weight'}<=set(df.columns)


def test_operational_daily_scoring_reuses_frozen_event_semantics():
    baseline=pd.DataFrame([
        {'cell_id':'x','month':9,'metric':'temperature_2m_max','mean':30,'p05':25,'p10':27,'p90':33,'p95':35,'baseline_year_start':2016,'baseline_year_end':2025},
        {'cell_id':'x','month':9,'metric':'temperature_2m_min','mean':20,'p05':15,'p10':17,'p90':23,'p95':25,'baseline_year_start':2016,'baseline_year_end':2025},
    ])
    daily=pd.DataFrame({
        'point_id':['p'],'cell_id':['x'],'date_local':['2026-09-20'],'temperature_2m_max':[36.0],'temperature_2m_min':[24.0],
        'precipitation_sum':[60.0],'wind_gusts_10m_max':[70.0],'weather_code':[95],
        'timezone':['America/Sao_Paulo'],'name':['X'],'state':['SP'],'subsystem_id':['SE/CO'],'weight':[1.0],
    })
    scored=_score_daily_forecast(daily,baseline,load_snapshot_rules())
    row=scored.iloc[0]
    assert bool(row['extreme_heat_day'])
    assert bool(row['heavy_rain_day'])
    assert bool(row['storm_candidate'])
    assert bool(row['event_any'])
