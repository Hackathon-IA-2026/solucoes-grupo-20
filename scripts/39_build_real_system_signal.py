#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table, write_table, write_json
from motor_sin.signals.real_signal import build_real_system_signal
from contracts.validators.core import validate_dataframe


def main():
    p=argparse.ArgumentParser(description='Build real-pilot system_signal_v1 from E3 forecast/backtest prediction, with S=null until a valid future supply source exists.')
    p.add_argument('--forecast',help='Canonical 24h forecast from scripts/38. If omitted, uses --backtest-predictions and selects E3.')
    p.add_argument('--backtest-predictions',default='outputs/metrics/e3_real_pilot_predictions.parquet')
    p.add_argument('--issue-time',help='Issue time to extract from backtest predictions. Default: latest complete E3 issue.')
    p.add_argument('--load',default='data/processed/demand/load_hourly.parquet')
    p.add_argument('--climate',default='data/processed/climate/zone_climate_hourly_e3.parquet')
    p.add_argument('--observed-supply-backtest',default='data/processed/generation/supply_by_subsystem_hourly.parquet')
    p.add_argument('--no-observed-generation-context',action='store_true')
    p.add_argument('--run-id',default='real-pilot-system-signal-v1')
    p.add_argument('--calendar-timezone',default='America/Sao_Paulo')
    p.add_argument('--output',default='outputs/contracts/system_signal_v1.parquet')
    p.add_argument('--report',default='outputs/reports/system_signal_real_pilot.json')
    a=p.parse_args()

    if a.forecast:
        forecast=read_table(a.forecast)
    else:
        pred=read_table(a.backtest_predictions)
        if 'experiment' not in pred.columns: raise SystemExit('backtest predictions do not contain experiment column')
        pred=pred[pred.experiment.astype(str).eq('E3')].copy()
        pred['issue_time_utc']=pd.to_datetime(pred.issue_time_utc,utc=True,errors='raise')
        issue=pd.Timestamp(a.issue_time) if a.issue_time else pred['issue_time_utc'].max()
        issue=issue.tz_localize('UTC') if issue.tzinfo is None else issue.tz_convert('UTC')
        forecast=pred[pred.issue_time_utc.eq(issue)].copy()
        if len(forecast)!=24: raise SystemExit(f'issue {issue} has {len(forecast)} E3 rows; expected 24')
    climate=read_table(a.climate) if Path(a.climate).exists() else None
    supply=None
    if not a.no_observed_generation_context and a.observed_supply_backtest and Path(a.observed_supply_backtest).exists():
        supply=read_table(a.observed_supply_backtest)
    out=build_real_system_signal(forecast=forecast,load_history=read_table(a.load),climate_context=climate,run_id=a.run_id,calendar_timezone=a.calendar_timezone,observed_supply_backtest=supply)
    report=validate_dataframe(out,'system_signal_v1',expected_hours=24);report.raise_for_errors();write_table(out,a.output)
    summary={'run_id':a.run_id,'rows':len(out),'zones':sorted(out.zone_id.unique().tolist()),'valid':report.valid,'supply_pressure_policy':'NULL_UNTIL_VALID_FUTURE_SUPPLY_SOURCE','observed_generation_context':supply is not None,'climate_exposure_mean':float(out.climate_exposure.mean()),'demand_pressure_min':float(out.demand_percentile.min()),'demand_pressure_max':float(out.demand_percentile.max()),'output':a.output}
    write_json(summary,a.report);print(out[['interval_start_utc','zone_id','demand_p50_mw','demand_percentile','supply_pressure','climate_exposure']].to_string(index=False));print(json.dumps(summary,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
