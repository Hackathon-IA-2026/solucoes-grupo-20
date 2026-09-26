import pandas as pd
from motor_sin.demand.availability import align_experiment_period


def _frame(start, end, zone='SE/CO', value_col='load_mw'):
    ts=pd.date_range(start,end,freq='h',tz='UTC')
    return pd.DataFrame({'interval_start_utc':ts,'subsystem_id':zone,value_col:range(len(ts))})


def test_e3_auto_clips_to_common_load_climate_window():
    load=_frame('2023-01-01','2026-09-01')
    climate=_frame('2025-01-01','2025-12-31 23:00',value_col='temperature_2m_mean')
    l,c,m=align_experiment_period(load,climate,experiment='E3',subsystem_id='SE/CO',requested_start='2023-01-01',requested_end='2026-12-31')
    assert l.interval_start_utc.min()==pd.Timestamp('2025-01-01',tz='UTC')
    assert l.interval_start_utc.max()==pd.Timestamp('2025-12-31 23:00',tz='UTC')
    assert c.interval_start_utc.min()==pd.Timestamp('2025-01-01',tz='UTC')
    assert m.adjusted_to_common_overlap is True


def test_e1_keeps_full_requested_load_window_without_climate():
    load=_frame('2023-01-01','2026-09-01')
    l,c,m=align_experiment_period(load,None,experiment='E1',subsystem_id='SE/CO',requested_start='2023-01-01',requested_end='2026-12-31')
    assert c is None
    assert l.interval_start_utc.min()==pd.Timestamp('2023-01-01',tz='UTC')
    assert l.interval_start_utc.max()==pd.Timestamp('2026-09-01',tz='UTC')
    assert m.adjusted_to_common_overlap is False
