#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table,write_json
from motor_sin.climate.operational_forecast import build_operational_zone_forecast

REGIONS={'N':'n','NE':'ne','SE/CO':'seco','S':'s'}

def common_issue(load:pd.DataFrame)->pd.Timestamp:
    x=load.copy();x['interval_start_utc']=pd.to_datetime(x.interval_start_utc,utc=True,errors='raise')
    x['subsystem_id']=x.subsystem_id.astype(str).str.upper().replace({'SE':'SE/CO','SECO':'SE/CO'})
    maxima=[]
    for z in REGIONS:
        g=x[x.subsystem_id.eq(z)]
        if g.empty:raise ValueError(f'no load history for {z}')
        maxima.append(g.interval_start_utc.max())
    return min(maxima)

def main():
    p=argparse.ArgumentParser(description='Build current H01-H24 operational E3 climate forecast for all ONS subsystems.')
    p.add_argument('--load',default='data/processed/demand/load_hourly.parquet')
    p.add_argument('--issue-time',default='auto')
    p.add_argument('--output',default='data/processed/climate/operational_zone_climate_24h.parquet')
    p.add_argument('--report',default='outputs/reports/operational_weather_24h.json')
    p.add_argument('--timeout',type=int,default=60)
    a=p.parse_args();load=read_table(a.load)
    issue=common_issue(load) if a.issue_time=='auto' else pd.Timestamp(a.issue_time)
    issue=issue.tz_localize('UTC') if issue.tzinfo is None else issue.tz_convert('UTC')
    parts=[];reports=[]
    template='data/processed/climate/zone_climate_hourly_e3.parquet'
    for region,tag in REGIONS.items():
        points_path=Path(f'data/processed/grid/climate_points_{tag}_01deg.csv');points=str(points_path if points_path.exists() else Path(f'configs/e2_{tag}_points.csv'));op_baseline=Path(f'data/processed/climate/regions/{tag}/e3_temperature_baseline_operational.parquet');train_baseline=Path(f'data/processed/climate/regions/{tag}/e3_temperature_baseline_monthly.parquet');baseline=str(op_baseline if op_baseline.exists() else train_baseline)
        if not Path(baseline).exists():raise FileNotFoundError(f'missing baseline for {region}: {baseline}. Run full automation first.')
        out,rep=build_operational_zone_forecast(points_path=points,subsystem_id=region,baseline_path=baseline,issue_time_utc=issue,historical_template_path=template,timeout_seconds=a.timeout)
        parts.append(out);reports.append(rep)
    combined=pd.concat(parts,ignore_index=True).sort_values(['subsystem_id','interval_start_utc'])
    write_table(combined,a.output);payload={'issue_time_utc':issue.isoformat(),'rows':int(len(combined)),'regions':reports,'weather_mode':'OPERATIONAL_FORECAST','output':str(Path(a.output).resolve())};write_json(payload,a.report);print(json.dumps(payload,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
