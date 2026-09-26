import numpy as np
import pandas as pd

from motor_sin.signals.pressure import contextual_demand_percentile


def test_contextual_percentile_uses_sao_paulo_hour_and_month_not_global_day():
    # 40 January midnights in Sao Paulo are around 100 MW; other hours are much higher.
    midnight_local = pd.date_range('2024-01-01 00:00', periods=40, freq='24h', tz='America/Sao_Paulo')
    noon_local = pd.date_range('2024-01-01 12:00', periods=40, freq='24h', tz='America/Sao_Paulo')
    h = pd.DataFrame({
        'interval_start_utc': list(midnight_local.tz_convert('UTC')) + list(noon_local.tz_convert('UTC')),
        'subsystem_id': ['SE/CO'] * 80,
        'load_mw': list(np.linspace(90, 110, 40)) + list(np.linspace(900, 1100, 40)),
    })
    target = pd.Timestamp('2024-01-20 00:00', tz='America/Sao_Paulo').tz_convert('UTC')
    p, method, n = contextual_demand_percentile(
        h,
        subsystem_id='SE/CO',
        target_time_utc=target,
        demand_mw=105,
    )
    assert method in {'HOUR_MONTH_DAYTYPE', 'HOUR_MONTH'}
    assert n >= 24
    assert 0.5 < p <= 1.0


def test_contextual_percentile_falls_back_safely_with_short_history():
    ts = pd.date_range('2025-01-01T03:00:00Z', periods=10, freq='24h')
    h = pd.DataFrame({'interval_start_utc': ts, 'subsystem_id': 'SE/CO', 'load_mw': np.arange(10) + 100})
    p, method, n = contextual_demand_percentile(h, subsystem_id='SE/CO', target_time_utc=ts[-1], demand_mw=105)
    assert method == 'HOUR_ALL_HISTORY'
    assert n == 10
    assert 0 <= p <= 1
