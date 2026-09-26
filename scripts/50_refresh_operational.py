#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
import pandas as pd


def run(cmd,label):
    print(f'\n=== {label} ===\n$ '+' '.join(cmd),flush=True);r=subprocess.run(cmd,text=True)
    if r.returncode:raise RuntimeError(f'{label} failed with code {r.returncode}')

def main():
    p=argparse.ArgumentParser(description='Fast operational refresh after models are trained: refresh ONS history, weather forecast, demand forecast and system_signal_v1.')
    p.add_argument('--start-year',type=int);p.add_argument('--issue-time',default='auto');p.add_argument('--max-staleness-hours',type=float,default=3.0);p.add_argument('--climate-store-root',default='data/climate_store');a=p.parse_args()
    start=a.start_year
    if start is None:
        report=Path('outputs/reports/full_automation.json')
        if report.exists():
            try:start=int(json.loads(report.read_text(encoding='utf-8')).get('config',{}).get('start_year',2021))
            except Exception:start=2021
        else:start=2021
    year=pd.Timestamp.now(tz='America/Sao_Paulo').year
    run([sys.executable,'scripts/45_sync_ons_history.py','--start-year',str(start),'--end-year',str(year),'--source-timezone','America/Sao_Paulo','--refresh-end-year'],'Atualizar ONS até o ano atual')
    run([sys.executable,'scripts/51_prepare_operational_baselines.py','--target-year',str(year),'--store-root',a.climate_store_root,'--history-mode','local-only'],'Carregar baseline climático operacional do Climate Store')
    run([sys.executable,'scripts/48_build_operational_weather.py','--issue-time',a.issue_time],'Atualizar previsão meteorológica H01-H24')
    run([sys.executable,'scripts/49_run_operational_24h.py','--issue-time',a.issue_time,'--max-staleness-hours',str(a.max_staleness_hours)],'Publicar previsão e system_signal_v1 operacionais')
    print(json.dumps({'status':'SUCCESS','year':year,'issue_time':a.issue_time,'system_signal':'outputs/contracts/system_signal_v1.parquet'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
