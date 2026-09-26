#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.climate.batch_openmeteo import annual_date_windows
from motor_sin.climate.e2_pilot import load_pilot_points,canonical_zone
from motor_sin.climate.e3_snapshot import BASELINE_DAILY_VARIABLES,TARGET_SNAPSHOT_DAILY_VARIABLES,build_daily_archive_parameters
from motor_sin.climate.local_store import find_local_records
from motor_sin.climate.openmeteo import build_archive_parameters
from motor_sin.common.io import read_table,write_json
REGIONS={'N':'n','NE':'ne','SE/CO':'seco','S':'s'}

def bounds(load,sub,start_year,end_year,tz,lag):
    x=load.copy();x['subsystem_id']=x['subsystem_id'].map(canonical_zone);x['interval_start_utc']=pd.to_datetime(x['interval_start_utc'],utc=True,errors='raise');x=x[x.subsystem_id.eq(canonical_zone(sub))]
    if x.empty:raise ValueError(f'no load rows for {sub}')
    local=x.interval_start_utc.dt.tz_convert(ZoneInfo(tz));left=max(local.min().date(),pd.Timestamp(f'{start_year}-01-01').date());cutoff=(pd.Timestamp.now(tz=ZoneInfo(tz)).to_pydatetime()-timedelta(days=int(lag))).date();right=min(local.max().date(),pd.Timestamp(f'{end_year}-12-31').date(),cutoff)
    if right<left:raise ValueError(f'no climate overlap {left}..{right}')
    return left.isoformat(),right.isoformat()

def main():
    p=argparse.ArgumentParser();p.add_argument('--load',default='data/processed/demand/load_hourly.parquet');p.add_argument('--start-year',type=int,required=True);p.add_argument('--end-year',type=int,required=True);p.add_argument('--store-root',default='data/climate_store');p.add_argument('--calendar-timezone',default='America/Sao_Paulo');p.add_argument('--archive-lag-days',type=int,default=5);p.add_argument('--report',default='outputs/reports/climate_store_coverage.json');a=p.parse_args();load=read_table(a.load)
    result={'status':'RUNNING','store_root':a.store_root,'start_year':a.start_year,'end_year':a.end_year,'regions':{},'missing_ranges':0}
    for region,tag in REGIONS.items():
        points_path=Path(f'data/processed/grid/climate_points_{tag}_01deg.csv')
        if not points_path.exists():result['regions'][region]={'ready':False,'error':f'missing {points_path}'};result['missing_ranges']+=1;continue
        points=load_pilot_points(points_path,subsystem_id=region);start,end=bounds(load,region,a.start_year,a.end_year,a.calendar_timezone,a.archive_lag_days);sy=pd.Timestamp(start).year;ey=pd.Timestamp(end).year;gaps=[]
        for year,left,right in annual_date_windows(start,end):
            root=Path(a.store_root)/tag/'hourly'/f'year={year:04d}'
            for _,pt in points.iterrows():
                params=build_archive_parameters(latitude=float(pt.latitude),longitude=float(pt.longitude),start_date=left,end_date=right,model='era5_seamless');_,missing=find_local_records(directory=root,source_service='historical',request_parameters=params,block_name='hourly',start_date=left,end_date=right)
                gaps.extend({'channel':'e2_hourly','point_id':str(pt.point_id),'start_date':ml,'end_date':mr} for ml,mr in missing)
        bstart=f'{sy-10}-01-01';bend=f'{ey-1}-12-31'
        for year,left,right in annual_date_windows(bstart,bend):
            root=Path(a.store_root)/tag/'daily'/'baseline_temperature'/f'year={year:04d}'
            for _,pt in points.iterrows():
                params=build_daily_archive_parameters(latitude=float(pt.latitude),longitude=float(pt.longitude),timezone_name=str(pt.timezone),start_date=left,end_date=right,variables=BASELINE_DAILY_VARIABLES,model='era5_land');_,missing=find_local_records(directory=root,source_service='historical_daily',request_parameters=params,block_name='daily',start_date=left,end_date=right)
                gaps.extend({'channel':'baseline_temperature','point_id':str(pt.point_id),'start_date':ml,'end_date':mr} for ml,mr in missing)
        for year,left,right in annual_date_windows(start,end):
            root=Path(a.store_root)/tag/'daily'/'target_snapshot_daily'/f'year={year:04d}'
            for _,pt in points.iterrows():
                params=build_daily_archive_parameters(latitude=float(pt.latitude),longitude=float(pt.longitude),timezone_name=str(pt.timezone),start_date=left,end_date=right,variables=TARGET_SNAPSHOT_DAILY_VARIABLES,model=None);_,missing=find_local_records(directory=root,source_service='historical_daily',request_parameters=params,block_name='daily',start_date=left,end_date=right)
                gaps.extend({'channel':'target_snapshot_daily','point_id':str(pt.point_id),'start_date':ml,'end_date':mr} for ml,mr in missing)
        result['regions'][region]={'ready':not gaps,'points':len(points),'target_window':{'start':start,'end':end},'baseline_window':{'start':bstart,'end':bend},'missing_ranges':len(gaps),'sample_gaps':gaps[:25]};result['missing_ranges']+=len(gaps)
    result['ready_local_only']=result['missing_ranges']==0 and all(x.get('ready') for x in result['regions'].values());result['status']='READY_LOCAL_ONLY' if result['ready_local_only'] else 'INCOMPLETE';write_json(result,a.report);print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(0 if result['ready_local_only'] else 2)
if __name__=='__main__':main()
