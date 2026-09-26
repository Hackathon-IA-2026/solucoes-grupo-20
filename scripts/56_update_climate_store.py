#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
import pandas as pd
REGIONS={'N':'n','NE':'ne','SE/CO':'seco','S':'s'}
def run(cmd,label):
    print(f'\n=== {label} ===\n$ '+' '.join(cmd),flush=True);r=subprocess.run(cmd,text=True)
    if r.returncode:raise SystemExit(r.returncode)
def main():
    p=argparse.ArgumentParser(description='Update only missing/new historical climate ranges in the local Climate Store.')
    p.add_argument('--start-year',type=int);p.add_argument('--end-year',type=int);p.add_argument('--store-root',default='data/climate_store');p.add_argument('--batch-size',type=int,default=6);p.add_argument('--daily-batch-size',type=int,default=24);p.add_argument('--request-delay',type=float,default=2.0);p.add_argument('--max-retries',type=int,default=10);p.add_argument('--backoff',type=float,default=10.0);p.add_argument('--cooldown-after-429',type=int,default=3);p.add_argument('--cooldown-seconds',type=float,default=90.0);p.add_argument('--timeout',type=int,default=120);p.add_argument('--archive-url',default='');p.add_argument('--report',default='outputs/reports/climate_store_update.json');a=p.parse_args()
    current=int(pd.Timestamp.now(tz='America/Sao_Paulo').year);start=a.start_year or current;end=a.end_year or current
    if end<start:raise SystemExit('end-year must be >= start-year')
    subprocess.run([sys.executable,'scripts/55_manage_climate_store.py','seed-existing','--store-root',a.store_root],check=True)
    reports=[]
    for region,tag in REGIONS.items():
        points=Path(f'data/processed/grid/climate_points_{tag}_01deg.csv')
        if not points.exists():raise SystemExit(f'missing {points}; build the climate grid first')
        out=Path('outputs/reports/climate');out.mkdir(parents=True,exist_ok=True)
        cmd=[sys.executable,'scripts/53_download_multiyear_grid_climate.py','--load','data/processed/demand/load_hourly.parquet','--points',str(points),'--subsystem',region,'--start-year',str(start),'--end-year',str(end),'--e2-raw-dir',str(Path(a.store_root)/tag/'hourly'),'--e2-manifest',str(out/f'{tag}_store_update_e2.json'),'--e3-raw-dir',str(Path(a.store_root)/tag/'daily'),'--e3-manifest',str(out/f'{tag}_store_update_e3.json'),'--history-mode','local-first','--batch-size',str(a.batch_size),'--daily-batch-size',str(a.daily_batch_size),'--request-delay',str(a.request_delay),'--max-retries',str(a.max_retries),'--backoff',str(a.backoff),'--cooldown-after-429',str(a.cooldown_after_429),'--cooldown-seconds',str(a.cooldown_seconds),'--timeout',str(a.timeout),'--report',str(out/f'{tag}_store_update.json'),'--checkpoint',str(out/f'{tag}_store_update_checkpoint.json')]
        if a.archive_url:cmd+=['--archive-url',a.archive_url]
        run(cmd,f'{region} · atualizar somente gaps do Climate Store');reports.append(str(out/f'{tag}_store_update.json'))
    payload={'status':'SUCCESS','store_root':a.store_root,'start_year':start,'end_year':end,'policy':'LOCAL_FIRST_INCREMENTAL_GAPS_ONLY','region_reports':reports};Path(a.report).parent.mkdir(parents=True,exist_ok=True);Path(a.report).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(payload,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
