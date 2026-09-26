#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table, write_table, write_json
from motor_tarifa.sources.aneel import fetch_tariff_rows
from motor_tarifa.base_tariff.parser import prepare_tariffs


def slug(s): return re.sub(r'[^A-Za-z0-9_-]+','_',str(s).strip()).strip('_').lower() or 'distributor'

def main():
    p=argparse.ArgumentParser(description='Download/normalize ANEEL volumetric TE+TUSD and list profiles valid on the system-signal date.')
    p.add_argument('--distributor',required=True,help='Text filter for SigAgente, e.g. LIGHT')
    p.add_argument('--signal',default='outputs/contracts/system_signal_v1.parquet')
    p.add_argument('--input',help='Optional existing ANEEL raw CSV/Parquet. If omitted, CKAN is queried.')
    p.add_argument('--limit',type=int,default=10000)
    p.add_argument('--base-output',default='data/processed/tariff/base_tariffs.parquet')
    p.add_argument('--profiles-output',default='outputs/reports/tariff_profiles.csv')
    p.add_argument('--report',default='outputs/reports/aneel_tariff_prepare.json')
    a=p.parse_args()
    if a.input:
        raw=read_table(a.input);raw_path=a.input;downloaded=False
    else:
        raw=fetch_tariff_rows(distributor=a.distributor,limit=a.limit)
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');raw_path=f'data/raw/tariff/aneel_{slug(a.distributor)}_{stamp}.csv';write_table(raw,raw_path);downloaded=True
    base,skipped=prepare_tariffs(raw);write_table(base,a.base_output);write_table(skipped,'outputs/reports/tariff_non_volumetric_rows.csv')
    signal=read_table(a.signal);d=pd.to_datetime(signal.interval_start_utc,utc=True).min().date();vf=pd.to_datetime(base.valid_from,errors='coerce').dt.date;vt=pd.to_datetime(base.valid_to,errors='coerce').dt.date
    mask=base.distributor_id.astype(str).str.contains(a.distributor,case=False,regex=False,na=False)&vf.le(d)&vt.ge(d)
    profiles=base.loc[mask].sort_values(['distributor_id','tariff_profile_id','tariff_post']).reset_index(drop=True);write_table(profiles,a.profiles_output)
    report={'distributor_filter':a.distributor,'signal_date':str(d),'downloaded':downloaded,'raw_path':raw_path,'raw_rows':len(raw),'volumetric_rows':len(base),'non_volumetric_rows':len(skipped),'eligible_rows':len(profiles),'unique_profiles':int(profiles.tariff_profile_id.nunique()) if len(profiles) else 0,'base_output':a.base_output,'profiles_output':a.profiles_output};write_json(report,a.report)
    if len(profiles): print(profiles[['distributor_id','tariff_profile_id','tariff_post','base_total_rs_kwh','valid_from','valid_to']].to_string(index=False))
    else: print('No eligible volumetric tariff rows found for the signal date. Try a larger --limit, full raw CSV, or verify distributor spelling/date coverage.')
    print(json.dumps(report,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
