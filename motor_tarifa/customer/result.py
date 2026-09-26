from __future__ import annotations

import json
import pandas as pd


def build_customer_result(*, tariff: pd.DataFrame, consumption: pd.DataFrame, simulation_report: dict, customer_meta: dict) -> dict:
    t = tariff.copy(); c = consumption.copy()
    t['interval_start_utc'] = pd.to_datetime(t['interval_start_utc'], utc=True, errors='raise')
    c['interval_start_utc'] = pd.to_datetime(c['interval_start_utc'], utc=True, errors='raise')
    joined = t.merge(c[['interval_start_utc','consumption_kwh']], on='interval_start_utc', how='left', validate='one_to_one')
    joined['reference_cost_rs'] = joined['consumption_kwh'] * joined['base_total_rs_kwh']
    joined['dynamic_cost_rs'] = joined['consumption_kwh'] * joined['dynamic_tariff_rs_kwh']
    joined['tariff_delta_pct'] = 100 * (joined['dynamic_tariff_rs_kwh'] / joined['base_total_rs_kwh'] - 1.0)
    best = joined.nsmallest(3, 'dynamic_tariff_rs_kwh')['interval_start_utc'].astype(str).tolist()
    critical = joined.nlargest(3, 'dynamic_tariff_rs_kwh')['interval_start_utc'].astype(str).tolist()
    ref = float(joined['reference_cost_rs'].sum()); dyn = float(joined['dynamic_cost_rs'].sum())
    return {
        'customer': customer_meta,
        'simulation_scope': '24h experimental TE+TUSD volumetric comparison; not a regulated bill forecast',
        'reference_cost_24h_rs': ref,
        'dynamic_cost_24h_rs': dyn,
        'difference_rs': dyn - ref,
        'difference_pct': (100 * (dyn - ref) / ref) if ref else None,
        'reference_tariff_mean_rs_kwh': float(joined['base_total_rs_kwh'].mean()),
        'dynamic_tariff_mean_rs_kwh': float(joined['dynamic_tariff_rs_kwh'].mean()),
        'best_hours_utc': best,
        'critical_hours_utc': critical,
        'motor2_report': simulation_report,
        'limitations': [
            'Experimental dynamic tariff; not a current ANEEL regulatory tariff rule.',
            'Comparison includes volumetric TE+TUSD rows only; taxes, public-lighting charges, flags and demand charges may be outside scope.',
            'If a synthetic customer load shape is used, cost comparison is illustrative until an actual hourly consumption curve is supplied.',
        ],
        'hourly': joined[[
            'interval_start_utc','consumption_kwh','base_total_rs_kwh','dynamic_tariff_rs_kwh','tariff_delta_pct',
            'demand_pressure','supply_pressure','final_multiplier','reference_cost_rs','dynamic_cost_rs'
        ]].assign(interval_start_utc=lambda x: x['interval_start_utc'].astype(str)).to_dict(orient='records'),
    }
