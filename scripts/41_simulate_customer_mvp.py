#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table, write_table, write_json
from motor_tarifa.pipeline import simulate_dynamic_tariff, load_tariff_config
from motor_tarifa.customer.profiles import synthetic_daily_profile, validate_customer_curve
from motor_tarifa.customer.result import build_customer_result
from contracts.validators.core import validate_dataframe


def main():
    p=argparse.ArgumentParser(description='Customer-facing 24h MVP: ANEEL base tariff versus experimental Predicta dynamic tariff.')
    p.add_argument('--signal',default='outputs/contracts/system_signal_v1.parquet')
    p.add_argument('--base-tariffs',default='data/processed/tariff/base_tariffs.parquet')
    p.add_argument('--distributor',required=True)
    p.add_argument('--profile',required=True,help='Exact tariff_profile_id from outputs/reports/tariff_profiles.csv')
    p.add_argument('--subsystem',default='SE/CO')
    p.add_argument('--monthly-kwh',type=float,help='Used only to synthesize a representative daily curve: monthly/30.4375.')
    p.add_argument('--daily-kwh',type=float)
    p.add_argument('--customer-curve',help='CSV/Parquet with interval_start_utc, consumption_kwh; overrides synthetic shape.')
    p.add_argument('--customer-type',choices=['residential','commercial','industrial_flat'],default='residential')
    p.add_argument('--run-id',default='customer-mvp-v1')
    p.add_argument('--output',default='outputs/contracts/tariff_v1.parquet')
    p.add_argument('--hourly-output',default='outputs/reports/customer_tariff_hourly.csv')
    p.add_argument('--report',default='outputs/reports/customer_mvp_result.json')
    a=p.parse_args()
    signal=read_table(a.signal).sort_values('interval_start_utc');ts=signal[(signal.zone_type.astype(str)=='SUBSYSTEM')&(signal.zone_id.astype(str)==a.subsystem)].interval_start_utc
    if len(ts)!=24: raise SystemExit(f'customer MVP requires exactly 24 signal rows for {a.subsystem}; got {len(ts)}')
    if a.customer_curve:
        consumption=validate_customer_curve(read_table(a.customer_curve),ts)
    else:
        daily=a.daily_kwh if a.daily_kwh is not None else ((a.monthly_kwh/30.4375) if a.monthly_kwh is not None else None)
        if daily is None: raise SystemExit('provide --customer-curve, --daily-kwh or --monthly-kwh')
        consumption=synthetic_daily_profile(daily,a.customer_type,ts)
    out,sim=simulate_dynamic_tariff(system_signal=signal,base_tariffs=read_table(a.base_tariffs),distributor_id=a.distributor,profile_id=a.profile,subsystem_id=a.subsystem,config=load_tariff_config(),run_id=a.run_id,post_rules=None,consumption_ref_kwh=consumption.consumption_kwh.to_numpy(float))
    vr=validate_dataframe(out,'tariff_v1',expected_hours=24);vr.raise_for_errors();write_table(out,a.output)
    meta={'distributor_id':a.distributor,'tariff_profile_id':a.profile,'subsystem_id':a.subsystem,'customer_type':a.customer_type,'profile_source':str(consumption.profile_source.iloc[0]),'daily_consumption_kwh':float(consumption.consumption_kwh.sum())}
    result=build_customer_result(tariff=out,consumption=consumption,simulation_report=sim,customer_meta=meta);write_json(result,a.report)
    hourly=out.merge(consumption[['interval_start_utc','consumption_kwh']],on='interval_start_utc',how='left');write_table(hourly,a.hourly_output)
    print(json.dumps({k:result[k] for k in ['reference_cost_24h_rs','dynamic_cost_24h_rs','difference_rs','difference_pct','best_hours_utc','critical_hours_utc']},indent=2,ensure_ascii=False));print(f'report={Path(a.report).resolve()}')

if __name__=='__main__':main()
