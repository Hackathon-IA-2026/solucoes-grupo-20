from __future__ import annotations
import json, re
from datetime import date
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd
from django.conf import settings
from motor_sin.common.io import read_table

from .datasets import dataset_path, s3_configured

ROOT=Path(settings.PREDICTA_PROJECT_ROOT)
PROCESSED_GEO=ROOT/'data/processed/tariff/distributor_areas_wgs84.geojson'
BUNDLED_GEO=ROOT/'configs/distributor_areas_wgs84.geojson'
PROCESSED_CATALOG=ROOT/'data/processed/tariff/distributor_catalog.csv'
BUNDLED_CATALOG=ROOT/'configs/distributor_catalog.csv'
TARIFFS=ROOT/'data/processed/tariff/base_tariffs.parquet'
SIGNAL=ROOT/'outputs/contracts/system_signal_v1.parquet'


def _dataset(relative_path: str, local_path: Path) -> Path:
    return dataset_path(relative_path, local_path)


def signal_path() -> Path:
    return _dataset('outputs/contracts/system_signal_v1.parquet', SIGNAL)


def cnpj_digits(v:str)->str:
    d=re.sub(r'\D','',str(v or ''))
    return d.zfill(14) if d else ''


def geojson_path()->Path:
    if s3_configured() or PROCESSED_GEO.exists():
        return _dataset('data/processed/tariff/distributor_areas_wgs84.geojson', PROCESSED_GEO)
    return _dataset('configs/distributor_areas_wgs84.geojson', BUNDLED_GEO)


def geojson_payload()->dict:
    p=geojson_path()
    if not p.exists(): return {'type':'FeatureCollection','features':[],'metadata':{'warning':'distribution areas unavailable'}}
    return json.loads(p.read_text(encoding='utf-8'))


def distributor_catalog()->pd.DataFrame:
    if s3_configured() or PROCESSED_CATALOG.exists():
        p=_dataset('data/processed/tariff/distributor_catalog.csv', PROCESSED_CATALOG)
    else:
        p=_dataset('configs/distributor_catalog.csv', BUNDLED_CATALOG)
    if not p.exists(): return pd.DataFrame()
    df=pd.read_csv(p,dtype={'cnpj_digits':str})
    if 'cnpj_digits' in df: df['cnpj_digits']=df['cnpj_digits'].map(cnpj_digits)
    return df


def distributor_info(cnpj:str)->dict|None:
    df=distributor_catalog();key=cnpj_digits(cnpj)
    if df.empty: return None
    g=df[df.cnpj_digits.eq(key)]
    if g.empty:return None
    r=g.iloc[0]
    return {k:(None if pd.isna(v) else v.item() if hasattr(v,'item') else v) for k,v in r.to_dict().items()}


def signal_date(region:str)->date|None:
    p=signal_path()
    if not p.exists():return None
    s=read_table(p);g=s[(s.zone_type.astype(str)=='SUBSYSTEM')&(s.zone_id.astype(str)==str(region))]
    if g.empty:return None
    ts=pd.to_datetime(g.interval_start_utc,utc=True).min().tz_convert(ZoneInfo('America/Sao_Paulo'))
    return ts.date()


def tariff_profiles_for_cnpj(cnpj:str,region:str|None=None,effective_date:date|None=None)->list[dict]:
    tariffs_path = _dataset('data/processed/tariff/base_tariffs.parquet', TARIFFS)
    if not tariffs_path.exists():return []
    key=cnpj_digits(cnpj);df=read_table(tariffs_path)
    if 'distributor_cnpj' not in df.columns:return []
    df=df.copy();df['distributor_cnpj']=df['distributor_cnpj'].map(cnpj_digits)
    d=effective_date or (signal_date(region) if region else None) or date.today()
    vf=pd.to_datetime(df.valid_from,errors='coerce').dt.date;vt=pd.to_datetime(df.valid_to,errors='coerce').dt.date
    g=df[df.distributor_cnpj.eq(key)&vf.le(d)&vt.ge(d)].copy()
    # Product MVP: use tariff of application and volumetric single-post profiles only.
    if 'tariff_basis' in g.columns:
        b=g.tariff_basis.astype(str).str.casefold()
        app=b.str.contains('aplica',regex=False)
        if app.any():g=g[app]
    if 'customer_class' in g.columns:
        end_customer=~g['customer_class'].astype(str).str.casefold().str.contains('distribui',regex=False)
        if end_customer.any():g=g[end_customer]
    out=[]
    for (pid,dist),grp in g.groupby(['tariff_profile_id','distributor_id']):
        posts=sorted(grp.tariff_post.astype(str).unique().tolist())
        if 'UNIQUE' not in posts:continue
        u=grp[grp.tariff_post.astype(str).eq('UNIQUE')]
        if u.empty:continue
        # Some ANEEL rows differ only in metadata outside the volumetric
        # tariff profile (e.g. accessing agent). Show a profile only when all
        # current UNIQUE rows agree economically; never average conflicts.
        econ_cols=[c for c in ['base_te_rs_kwh','base_tusd_rs_kwh','base_total_rs_kwh','valid_from','valid_to','tariff_post'] if c in u.columns]
        econ=u.drop_duplicates(subset=econ_cols,keep='first')
        if len(econ)!=1:
            continue
        r=econ.iloc[0]
        label=str(r.get('profile_label') or pid)
        out.append({'id':str(pid),'label':label,'distributor_id':str(dist),'cnpj':key,'base_total_rs_kwh':float(r.base_total_rs_kwh),'base_te_rs_kwh':float(r.base_te_rs_kwh),'base_tusd_rs_kwh':float(r.base_tusd_rs_kwh),'posts':posts,'valid_from':str(r.valid_from),'valid_to':str(r.valid_to),'effective_date':str(d),'subgroup':str(r.get('subgroup','')),'modality':str(r.get('modality','')),'customer_class':str(r.get('customer_class',''))})
    return sorted(out,key=lambda x:(x['subgroup'],x['label']))


def available_signal_regions()->dict[str,bool]:
    regions={'N':False,'NE':False,'SE/CO':False,'S':False}
    p=signal_path()
    if p.exists():
        s=read_table(p)
        for z in s[s.zone_type.astype(str).eq('SUBSYSTEM')].zone_id.astype(str).unique():
            if z in regions:regions[z]=True
    return regions
