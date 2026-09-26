import pandas as pd
from motor_sin.climate.incidents import detect_incidents


def test_heat_and_night_solar_rules():
    ts = pd.Timestamp('2026-01-01T03:00:00Z')
    scores = pd.DataFrame([
        {'interval_start_utc': ts, 'cell_id':'c1','variable':'temperature_2m','value':39,'percentile':0.99,'baseline_year_start':2016,'baseline_year_end':2025},
        {'interval_start_utc': ts, 'cell_id':'c1','variable':'solar_radiation','value':0,'percentile':0.01,'baseline_year_start':2016,'baseline_year_end':2025},
    ])
    cfg = {'rules': {
        'extreme_heat': {'enabled':True,'tail':'upper','percentile_threshold':0.95,'severe_percentile_threshold':0.99},
        'solar_deficit': {'enabled':True,'tail':'lower','percentile_threshold':0.05,'only_solar_hours':True},
    }}
    out = detect_incidents(scores, cfg)
    assert list(out['incident_type']) == ['HEAT']
    assert out.iloc[0]['severity'] == 'SEVERE'
