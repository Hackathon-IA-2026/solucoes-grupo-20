import pandas as pd

from motor_tarifa.customer.profiles import synthetic_daily_profile


def test_residential_shape_is_aligned_to_sao_paulo_clock_not_utc_order():
    # 03:00 UTC is 00:00 in Sao Paulo. Residential peak coefficient is local 19h,
    # therefore the largest synthetic consumption must occur at 22:00 UTC.
    ts = pd.date_range('2025-12-31T03:00:00Z', periods=24, freq='h')
    profile = synthetic_daily_profile(24, 'residential', ts)
    peak_utc = profile.loc[profile.consumption_kwh.idxmax(), 'interval_start_utc']
    assert pd.Timestamp(peak_utc).hour == 22
    assert pd.Timestamp(peak_utc).tz_convert('America/Sao_Paulo').hour == 19
    assert abs(profile.consumption_kwh.sum() - 24) < 1e-9
