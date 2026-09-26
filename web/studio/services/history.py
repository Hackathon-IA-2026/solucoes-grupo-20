from __future__ import annotations
import re, json
from pathlib import Path
import pandas as pd
from django.conf import settings
from motor_sin.common.io import read_table

ROOT=Path(settings.PREDICTA_PROJECT_ROOT)
RAW=ROOT/'data/raw/ons/balance'
LOAD=ROOT/'data/processed/demand/load_hourly.parquet'
REPORT=ROOT/'outputs/reports/ons_history_manifest.json'
CLIMATE={'E2':ROOT/'data/processed/climate/zone_climate_hourly.parquet','E3':ROOT/'data/processed/climate/zone_climate_hourly_e3.parquet'}


def ons_history_context()->dict:
    years=[]
    if RAW.exists():
        for p in RAW.glob('BALANCO_ENERGIA_SUBSISTEMA_*.parquet'):
            m=re.search(r'_(\d{4})\.parquet$',p.name)
            if m: years.append(int(m.group(1)))
    years=sorted(set(years))
    ctx={'raw_years':years,'raw_year_count':len(years),'consolidated':LOAD.exists(),'subsystems':[]}
    if LOAD.exists():
        try:
            df=read_table(LOAD);df['interval_start_utc']=pd.to_datetime(df.interval_start_utc,utc=True,errors='coerce')
            ctx['rows']=int(len(df));ctx['start']=str(df.interval_start_utc.min());ctx['end']=str(df.interval_start_utc.max())
            for sub,g in df.groupby('subsystem_id'):
                ctx['subsystems'].append({'id':str(sub),'rows':int(len(g)),'start':str(g.interval_start_utc.min()),'end':str(g.interval_start_utc.max()),'years':sorted(g.interval_start_utc.dt.year.dropna().astype(int).unique().tolist())})
        except Exception as e:ctx['error']=str(e)
    ctx['climate_coverage']={}
    for exp,p in CLIMATE.items():
        item={'exists':p.exists()}
        if p.exists():
            try:
                z=read_table(p);z['interval_start_utc']=pd.to_datetime(z.interval_start_utc,utc=True,errors='coerce');z=z.dropna(subset=['interval_start_utc'])
                item.update({'rows':int(len(z)),'start':str(z.interval_start_utc.min()),'end':str(z.interval_start_utc.max()),'subsystems':sorted(z.subsystem_id.dropna().astype(str).unique().tolist()) if 'subsystem_id' in z else []})
            except Exception as e:item['error']=str(e)
        ctx['climate_coverage'][exp]=item
    if REPORT.exists():
        try:ctx['manifest']=json.loads(REPORT.read_text(encoding='utf-8'))
        except Exception:pass
    return ctx
