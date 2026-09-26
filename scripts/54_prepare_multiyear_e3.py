#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.climate.e2_pilot import load_pilot_points
from motor_sin.climate.e3_snapshot import parse_manifest_daily_frames,build_e3_daily_context,build_e3_hourly_zone_context,merge_e2_with_e3_context
from motor_sin.climate.openmeteo_snapshot_anomaly import load_snapshot_rules
from motor_sin.common.io import read_table,write_table,write_json


def main():
    p=argparse.ArgumentParser(description='Build rolling no-leakage E3 baselines and events for every target year in a multi-year climate manifest.')
    p.add_argument('--manifest',required=True);p.add_argument('--points',required=True);p.add_argument('--subsystem',required=True);p.add_argument('--e2-climate',required=True)
    p.add_argument('--start-year',type=int,required=True);p.add_argument('--end-year',type=int,required=True);p.add_argument('--rules',default='configs/openmeteo_event_rules_snapshot_2026-08-08.2.json')
    p.add_argument('--baseline-output',required=True);p.add_argument('--daily-output',required=True);p.add_argument('--hourly-output',required=True);p.add_argument('--zone-output',required=True);p.add_argument('--report',required=True);a=p.parse_args()
    manifest=pd.DataFrame(json.loads(Path(a.manifest).read_text(encoding='utf-8')));baseline_daily,target_daily=parse_manifest_daily_frames(manifest);rules=load_snapshot_rules(a.rules);points=load_pilot_points(a.points,subsystem_id=a.subsystem);e2=read_table(a.e2_climate);e2['interval_start_utc']=pd.to_datetime(e2['interval_start_utc'],utc=True,errors='raise')
    baseline_daily['_date']=pd.to_datetime(baseline_daily['date_local'],errors='raise');target_daily['_date']=pd.to_datetime(target_daily['date_local'],errors='raise')
    baselines=[];daily_parts=[];hourly_parts=[];years=[]
    for year in range(a.start_year,a.end_year+1):
        target=target_daily[target_daily['_date'].dt.year.eq(year)].drop(columns=['_date']).copy()
        if target.empty:continue
        base=baseline_daily[baseline_daily['_date'].dt.year.between(year-10,year-1)].drop(columns=['_date']).copy()
        if base.empty:raise ValueError(f'no baseline daily rows for target year {year}')
        available=sorted(pd.to_datetime(base['date_local']).dt.year.unique().tolist())
        expected=list(range(year-10,year))
        missing=sorted(set(expected)-set(available))
        if missing:raise ValueError(f'baseline for target year {year} missing years {missing}')
        b,ctx=build_e3_daily_context(base,target,target_year=year,rules=rules);b['target_year']=year;ctx['target_year']=year;baselines.append(b);daily_parts.append(ctx)
        start=pd.to_datetime(ctx['date_local']).min().date();end=pd.to_datetime(ctx['date_local']).max().date();local_dates=e2['interval_start_utc'].dt.tz_convert('America/Sao_Paulo').dt.date;hours=e2[(local_dates>=start)&(local_dates<=end)][['interval_start_utc']]
        h=build_e3_hourly_zone_context(ctx,points,hours,subsystem_id=a.subsystem);h['target_year']=year;hourly_parts.append(h);years.append(year)
    if not years:raise ValueError('no target years could be prepared from manifest')
    baseline=pd.concat(baselines,ignore_index=True);daily=pd.concat(daily_parts,ignore_index=True);hourly=pd.concat(hourly_parts,ignore_index=True).drop_duplicates(['interval_start_utc','subsystem_id'],keep='last').sort_values('interval_start_utc')
    merged=merge_e2_with_e3_context(e2,hourly)
    write_table(baseline,a.baseline_output);write_table(daily,a.daily_output);write_table(hourly,a.hourly_output);write_table(merged,a.zone_output)
    report={'subsystem_id':a.subsystem,'target_years':years,'rolling_baselines':{str(y):{'start':y-10,'end':y-1} for y in years},'baseline_rows':int(len(baseline)),'daily_rows':int(len(daily)),'hourly_rows':int(len(hourly)),'zone_rows':int(len(merged)),'spatial_method':'GRID_01DEG_ACTIVE_CELLS','no_leakage':True,'outputs':{'baseline':a.baseline_output,'daily':a.daily_output,'hourly':a.hourly_output,'zone':a.zone_output}}
    write_json(report,a.report);print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
