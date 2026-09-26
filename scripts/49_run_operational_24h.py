#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table,write_json
from motor_sin.demand.inference import forecast_frozen_direct_family
from motor_sin.signals.real_signal import build_real_system_signal
from contracts.validators.core import validate_dataframe

REGIONS=('N','NE','SE/CO','S')

def common_issue(load):
    x=load.copy();x['interval_start_utc']=pd.to_datetime(x.interval_start_utc,utc=True,errors='raise');x['subsystem_id']=x.subsystem_id.astype(str).str.upper().replace({'SE':'SE/CO','SECO':'SE/CO'})
    return min(x[x.subsystem_id.eq(z)].interval_start_utc.max() for z in REGIONS)

def main():
    p=argparse.ArgumentParser(description='Run the selected regional models and publish a genuine operational 24h system_signal_v1.')
    p.add_argument('--load',default='data/processed/demand/load_hourly.parquet');p.add_argument('--climate',default='data/processed/climate/operational_zone_climate_24h.parquet')
    p.add_argument('--registry',default='models/demand/operational_registry.json');p.add_argument('--issue-time',default='auto');p.add_argument('--max-staleness-hours',type=float,default=3.0);p.add_argument('--allow-stale',action='store_true')
    p.add_argument('--forecast-output',default='data/processed/demand/operational_forecast_24h.parquet');p.add_argument('--signal-output',default='outputs/contracts/system_signal_v1.parquet');p.add_argument('--report',default='outputs/reports/operational_24h.json');a=p.parse_args()
    registry=json.loads(Path(a.registry).read_text(encoding='utf-8'));load=read_table(a.load);climate=read_table(a.climate)
    issue=common_issue(load) if a.issue_time=='auto' else pd.Timestamp(a.issue_time);issue=issue.tz_localize('UTC') if issue.tzinfo is None else issue.tz_convert('UTC')
    now=pd.Timestamp.now(tz='UTC');staleness=float((now-issue).total_seconds()/3600)
    if staleness>a.max_staleness_hours and not a.allow_stale:raise ValueError(f'latest common ONS load is {staleness:.1f}h old; operational publish blocked (limit={a.max_staleness_hours}h)')
    forecasts=[]
    for z in REGIONS:
        cfg=registry.get('regions',{}).get(z)
        if not cfg:raise ValueError(f'operational registry has no selected model for {z}')
        out=forecast_frozen_direct_family(load_history=load,future_zone_climate=climate,model_dir=cfg['model_dir'],issue_time=issue,horizon=24,allow_perfect_weather=False);forecasts.append(out)
    forecast=pd.concat(forecasts,ignore_index=True);write_table(forecast,a.forecast_output)
    signal=build_real_system_signal(forecast=forecast,load_history=load,climate_context=climate,run_id=f'operational-{issue.strftime("%Y%m%dT%H%MZ")}',calendar_timezone='America/Sao_Paulo',observed_supply_backtest=None)
    report=validate_dataframe(signal,'system_signal_v1',expected_hours=24);report.raise_for_errors();write_table(signal,a.signal_output)
    payload={'ready':True,'issue_time_utc':issue.isoformat(),'issue_time_sao_paulo':issue.tz_convert('America/Sao_Paulo').isoformat(),'load_staleness_hours':staleness,'forecast_rows':int(len(forecast)),'signal_rows':int(len(signal)),'regions':list(REGIONS),'horizon_hours':24,'weather_mode':'OPERATIONAL_FORECAST','forecast_output':str(Path(a.forecast_output).resolve()),'signal_output':str(Path(a.signal_output).resolve())};write_json(payload,a.report);print(json.dumps(payload,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
