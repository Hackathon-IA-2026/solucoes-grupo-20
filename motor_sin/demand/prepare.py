from __future__ import annotations

import pandas as pd

LOAD_ALIASES={
    'interval_start_utc':('interval_start_utc','din_referenciautc','din_instante','data_hora','timestamp'),
    'subsystem_id':('subsystem_id','id_subsistema','nom_subsistema','subsistema','cod_subsistema'),
    'load_mw':('load_mw','val_cargaenergiahomwmed','val_cargaglobal','val_carga','carga_mw'),
}


def _pick(df,names):
    lower={c.lower():c for c in df.columns}
    for n in names:
        if n.lower() in lower:return lower[n.lower()]
    return None


def prepare_load(df:pd.DataFrame)->pd.DataFrame:
    rename={}
    for target,aliases in LOAD_ALIASES.items():
        c=_pick(df,aliases)
        if c is None: raise ValueError(f'load source missing {target}; accepted={aliases}')
        rename[c]=target
    out=df.rename(columns=rename)[list(LOAD_ALIASES)].copy()
    out['interval_start_utc']=pd.to_datetime(out['interval_start_utc'],utc=True,errors='raise')
    out['subsystem_id']=out['subsystem_id'].astype(str).str.strip().str.upper().replace({'SE':'SE/CO','SECO':'SE/CO','SUDESTE/CENTRO-OESTE':'SE/CO'})
    out['load_mw']=pd.to_numeric(out['load_mw'],errors='coerce')
    if out['load_mw'].isna().any(): raise ValueError('load source has non-numeric load values')
    # MWmed sampled at sub-hourly resolution -> hourly mean.
    out['interval_start_utc']=out['interval_start_utc'].dt.floor('h')
    out=out.groupby(['interval_start_utc','subsystem_id'],as_index=False)['load_mw'].mean().sort_values(['subsystem_id','interval_start_utc'])
    return out
