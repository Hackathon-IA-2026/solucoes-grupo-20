#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table, write_table, write_json
from motor_sin.demand.inference import forecast_frozen_direct_family


def main():
    p=argparse.ArgumentParser(description='Run H01..H24 inference from a frozen E1/E2/E3 model family. No model training occurs here.')
    p.add_argument('--load',default='data/processed/demand/load_hourly.parquet')
    p.add_argument('--climate',help='Required for E2/E3. Optional for E1.')
    p.add_argument('--model-dir',default='models/demand/e3_seco_v1')
    p.add_argument('--issue-time',required=True)
    p.add_argument('--allow-perfect-weather',action='store_true',help='Historical demo only. Operational inference must use a true forecast available at issue time.')
    p.add_argument('--output',default='data/processed/demand/e3_forecast_24h.parquet')
    p.add_argument('--report',default='outputs/reports/e3_inference.json')
    a=p.parse_args()
    climate=read_table(a.climate) if a.climate else None
    out=forecast_frozen_direct_family(load_history=read_table(a.load),future_zone_climate=climate,model_dir=a.model_dir,issue_time=pd.Timestamp(a.issue_time),horizon=24,allow_perfect_weather=a.allow_perfect_weather)
    write_table(out,a.output)
    report={'issue_time_utc':str(pd.to_datetime(out.issue_time_utc.iloc[0],utc=True)),'rows':len(out),'model_family_id':str(out.model_family_id.iloc[0]),'weather_mode':str(out.weather_mode.iloc[0]),'output':a.output}
    write_json(report,a.report);print(out[['horizon_hour','interval_start_utc','demand_p10_mw','demand_p50_mw','demand_p90_mw']].to_string(index=False));print(json.dumps(report,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
