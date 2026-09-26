#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
from urllib.request import Request, urlopen
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import write_table, write_json
from motor_sin.sources.ons_balance import source_url, read_ons_table, prepare_ons_balance


def download_if_missing(year:int, raw_dir:Path, *, force:bool=False)->tuple[Path,bool]:
    out=raw_dir/f'BALANCO_ENERGIA_SUBSISTEMA_{year}.parquet'
    if out.exists() and not force: return out,False
    raw_dir.mkdir(parents=True,exist_ok=True);url=source_url(year,'parquet')
    req=Request(url,headers={'User-Agent':'Predicta-Hackathon/1.6'})
    with urlopen(req,timeout=240) as r:data=r.read()
    out.write_bytes(data)
    meta={'source':'ONS_BALANCO_ENERGIA_SUBSISTEMA','year':year,'url':url,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    out.with_suffix(out.suffix+'.meta.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8')
    return out,True


def _merge(parts:list[pd.DataFrame],key:list[str])->pd.DataFrame:
    out=pd.concat(parts,ignore_index=True).sort_values(key).reset_index(drop=True)
    dup=out.duplicated(key,keep=False)
    if dup.any():
        # Repeated year files may overlap by timestamp only if source corrections exist. Refuse conflicts.
        sample=out.loc[dup].sort_values(key)
        nonkey=[c for c in out.columns if c not in key]
        bad=[]
        for kval,g in sample.groupby(key,dropna=False):
            if any(g[c].astype(str).nunique(dropna=False)>1 for c in nonkey): bad.append(kval)
        if bad: raise ValueError(f'conflicting duplicate ONS hours across years, examples={bad[:5]}')
        out=out.drop_duplicates(key,keep='last').sort_values(key).reset_index(drop=True)
    return out


def main():
    p=argparse.ArgumentParser(description='Baixa/reutiliza múltiplos anos do ONS e consolida um histórico horário único para treino.')
    p.add_argument('--start-year',type=int,default=2021)
    p.add_argument('--end-year',type=int,default=2025)
    p.add_argument('--source-timezone',default='America/Sao_Paulo')
    p.add_argument('--raw-dir',default='data/raw/ons/balance')
    p.add_argument('--load-output',default='data/processed/demand/load_hourly.parquet')
    p.add_argument('--supply-output',default='data/processed/generation/supply_by_subsystem_hourly.parquet')
    p.add_argument('--report',default='outputs/reports/ons_history_manifest.json')
    p.add_argument('--refresh-end-year',action='store_true',help='Redownload the end-year source even if RAW already exists. Use this for operational refreshes of the current year.')
    a=p.parse_args()
    if a.end_year<a.start_year: raise SystemExit('end-year must be >= start-year')
    raw_dir=Path(a.raw_dir);load_parts=[];supply_parts=[];years=[]
    for year in range(a.start_year,a.end_year+1):
        path,downloaded=download_if_missing(year,raw_dir,force=bool(a.refresh_end_year and year==a.end_year))
        raw=read_ons_table(path)
        load,supply=prepare_ons_balance(raw,source_timezone=a.source_timezone)
        load['source_year']=year;supply['source_year']=year
        load_parts.append(load);supply_parts.append(supply)
        years.append({'year':year,'raw_path':str(path),'downloaded':downloaded,'load_rows':int(len(load)),'start_utc':str(load.interval_start_utc.min()),'end_utc':str(load.interval_start_utc.max())})
        print(f'year={year} rows={len(load)} downloaded={downloaded}')
    load=_merge(load_parts,['interval_start_utc','subsystem_id']);supply=_merge(supply_parts,['interval_start_utc','subsystem_id'])
    # Keep the consolidated dataset canonical; source_year remains useful for data explorer.
    write_table(load,a.load_output);write_table(supply,a.supply_output)
    coverage=[]
    for sub,g in load.groupby('subsystem_id'):
        ts=g.interval_start_utc.sort_values();diff=ts.diff().dropna();missing=int((diff.dt.total_seconds()/3600-1).clip(lower=0).sum()) if len(diff) else 0
        coverage.append({'subsystem_id':sub,'rows':int(len(g)),'start_utc':str(ts.min()),'end_utc':str(ts.max()),'missing_hours_between_rows':missing})
    report={'start_year':a.start_year,'end_year':a.end_year,'source_timezone':a.source_timezone,'years':years,'load_rows':int(len(load)),'supply_rows':int(len(supply)),'coverage':coverage,'load_output':a.load_output,'supply_output':a.supply_output}
    write_json(report,a.report);print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
