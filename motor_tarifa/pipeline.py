from __future__ import annotations

import json
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import yaml

from motor_tarifa.signal.calc import calculate_signal
from motor_tarifa.guardrails.core import floor_cap,ramp_limit,neutralize
from motor_tarifa.billing.simulate import bill_kwh
from motor_tarifa.profiles.posts import resolve_tariff_posts


def _select_tariff(base:pd.DataFrame,distributor_id:str,profile_id:str,post:str,ts:pd.Timestamp,timezone_name:str='America/Sao_Paulo')->pd.Series:
    work=base[(base.distributor_id.astype(str)==str(distributor_id))&(base.tariff_profile_id.astype(str)==str(profile_id))].copy()
    if work.empty:raise ValueError(f'no base tariff for distributor={distributor_id} profile={profile_id}')
    work=work[work.tariff_post.astype(str).isin([str(post),'UNIQUE'])]
    stamp=pd.Timestamp(ts);stamp=stamp.tz_localize('UTC') if stamp.tzinfo is None else stamp.tz_convert('UTC');d=stamp.tz_convert(ZoneInfo(timezone_name)).date();vf=pd.to_datetime(work.valid_from,errors='coerce').dt.date;vt=pd.to_datetime(work.valid_to,errors='coerce').dt.date;work=work[(vf<=d)&(vt>=d)]
    # ANEEL can publish duplicate rows for the same economic tariff because of
    # fields that are not part of the Predicta volumetric profile (for example,
    # an accessing agent). Collapse only economically identical duplicates.
    # Conflicting TE/TUSD values remain a hard error: we never average them.
    if len(work)>1:
        economic_cols=[c for c in ['base_te_rs_kwh','base_tusd_rs_kwh','base_total_rs_kwh','valid_from','valid_to','tariff_post'] if c in work.columns]
        unique_economic=work.drop_duplicates(subset=economic_cols,keep='first')
        if len(unique_economic)==1:
            work=unique_economic
    if len(work)!=1:raise ValueError(f'base tariff selection must be unique for {distributor_id}/{profile_id}/{post}/{d}; rows={len(work)}')
    return work.iloc[0]


def simulate_dynamic_tariff(*,system_signal:pd.DataFrame,base_tariffs:pd.DataFrame,distributor_id:str,profile_id:str,
                            subsystem_id:str,config:dict,run_id:str,post_rules:pd.DataFrame|None=None,
                            consumption_ref_kwh:np.ndarray|None=None,economic_signal:float|None=None)->tuple[pd.DataFrame,dict]:
    sig=system_signal[(system_signal.zone_type.astype(str)=='SUBSYSTEM')&(system_signal.zone_id.astype(str)==str(subsystem_id))].copy();sig['interval_start_utc']=pd.to_datetime(sig.interval_start_utc,utc=True);sig=sig.sort_values('interval_start_utc')
    if sig.empty:raise ValueError(f'no system signal for subsystem {subsystem_id}')
    if post_rules is None:posts=pd.DataFrame({'interval_start_utc':sig.interval_start_utc,'tariff_post':'UNIQUE'})
    else:posts=resolve_tariff_posts(sig.interval_start_utc,distributor_id=distributor_id,rules=post_rules)
    sig=sig.merge(posts,on='interval_start_utc',how='left')
    cfg=config['tariff'];weights=config['signal_weights'];fallback_cfg=config.get('fallback',{})
    raws=[];bases=[];reason=[]
    for r in sig.itertuples(index=False):
        t=_select_tariff(base_tariffs,distributor_id,profile_id,r.tariff_post,r.interval_start_utc);base=float(t.base_te_rs_kwh)+float(t.base_tusd_rs_kwh);bases.append((float(t.base_te_rs_kwh),float(t.base_tusd_rs_kwh),base))
        fallback=(bool(fallback_cfg.get('on_stale_data',True)) and not bool(r.data_freshness_ok))
        flags=[]
        if fallback:raw=1.0;flags.append('FALLBACK_STALE_DATA')
        else:
            signal,extra=calculate_signal(demand_pressure=float(r.demand_percentile),supply_pressure=None if pd.isna(r.supply_pressure) else float(r.supply_pressure),economic_signal=economic_signal,weights=weights);flags+=extra;raw=1.0+float(cfg['beta'])*signal
        raws.append(raw);reason.append(flags)
    raw=np.asarray(raws,float);m,floor_flags,cap_flags=floor_cap(raw,float(cfg['multiplier_min']),float(cfg['multiplier_max']));m,ramp_flags=ramp_limit(m,float(cfg['max_hourly_ramp']))
    w=np.asarray(consumption_ref_kwh,float) if consumption_ref_kwh is not None else np.ones(len(m));m_neutral,factor=neutralize(m,w);m2,floor2,cap2=floor_cap(m_neutral,float(cfg['multiplier_min']),float(cfg['multiplier_max']));m2,ramp2=ramp_limit(m2,float(cfg['max_hourly_ramp']))
    bill_cap_applied=False
    if consumption_ref_kwh is not None:
        base_arr=np.array([x[2] for x in bases]);ref=bill_kwh(w,base_arr);dynamic=bill_kwh(w,base_arr*m2);limit=(1+float(cfg.get('bill_cap_fraction',.2)))*ref
        if dynamic>limit and dynamic>0:
            scale=limit/dynamic;m2=np.maximum(float(cfg['multiplier_min']),m2*scale);bill_cap_applied=True
    rows=[]
    for i,r in enumerate(sig.itertuples(index=False)):
        te,tusd,base=bases[i];fallback=any(x.startswith('FALLBACK') for x in reason[i]);flags=list(reason[i]);
        if bill_cap_applied:flags.append('BILL_CAP_APPLIED_GLOBAL')
        rows.append({'schema_version':'tariff_v1','run_id':run_id,'interval_start_utc':r.interval_start_utc,'distributor_id':distributor_id,'tariff_profile_id':profile_id,'zone_type':'SUBSYSTEM','zone_id':subsystem_id,
                     'base_te_rs_kwh':te,'base_tusd_rs_kwh':tusd,'base_total_rs_kwh':base,'demand_pressure':float(r.demand_percentile),'supply_pressure':None if pd.isna(r.supply_pressure) else float(r.supply_pressure),'economic_signal':economic_signal,
                     'raw_multiplier':float(raw[i]),'final_multiplier':float(m2[i]),'dynamic_tariff_rs_kwh':float(base*m2[i]),'floor_applied':bool(floor_flags[i] or floor2[i]),'cap_applied':bool(cap_flags[i] or cap2[i]),'ramp_applied':bool(ramp_flags[i] or ramp2[i]),'neutrality_adjustment':float(factor-1.0),'fallback_applied':fallback,'reason_codes':json.dumps(flags,ensure_ascii=False),'quality_flags':json.dumps(['EXPERIMENTAL_NOT_REGULATORY'])})
    out=pd.DataFrame(rows)
    base_arr=np.array([x[2] for x in bases]);report={'reference_bill_rs':bill_kwh(w,base_arr),'dynamic_bill_rs':bill_kwh(w,base_arr*out.final_multiplier.to_numpy()),'neutrality_factor':factor,'bill_cap_applied':bill_cap_applied,'mean_multiplier':float(np.average(out.final_multiplier,weights=w))}
    return out,report


def load_tariff_config(path:str|Path='configs/tariff.yaml')->dict:return yaml.safe_load(Path(path).read_text(encoding='utf-8'))
