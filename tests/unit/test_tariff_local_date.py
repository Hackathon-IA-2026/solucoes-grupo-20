import pandas as pd

from motor_tarifa.pipeline import _select_tariff


def test_tariff_validity_uses_sao_paulo_civil_date_not_utc_date():
    base = pd.DataFrame([
        {'distributor_id':'D','tariff_profile_id':'P','tariff_post':'UNIQUE','valid_from':'2025-01-01','valid_to':'2025-12-31','base_te_rs_kwh':0.2,'base_tusd_rs_kwh':0.3,'base_total_rs_kwh':0.5},
        {'distributor_id':'D','tariff_profile_id':'P','tariff_post':'UNIQUE','valid_from':'2026-01-01','valid_to':'2026-12-31','base_te_rs_kwh':0.4,'base_tusd_rs_kwh':0.4,'base_total_rs_kwh':0.8},
    ])
    # 2026-01-01 01:00 UTC is still 2025-12-31 22:00 in Sao Paulo.
    row = _select_tariff(base,'D','P','UNIQUE',pd.Timestamp('2026-01-01T01:00:00Z'))
    assert row.base_total_rs_kwh == 0.5
    row2 = _select_tariff(base,'D','P','UNIQUE',pd.Timestamp('2026-01-01T03:00:00Z'))
    assert row2.base_total_rs_kwh == 0.8
