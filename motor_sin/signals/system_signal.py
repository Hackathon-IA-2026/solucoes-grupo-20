from __future__ import annotations

import json
import numpy as np
import pandas as pd

from .pressure import contextual_demand_percentile


def _empirical_percentile(values: pd.Series, value: float) -> float:
    arr=pd.to_numeric(values,errors='coerce').dropna().to_numpy(float)
    if not len(arr): return 0.5
    return float(np.mean(arr <= float(value)))


def demand_percentiles(forecast:pd.DataFrame,history:pd.DataFrame,timezone_name:str='America/Sao_Paulo')->pd.DataFrame:
    f=forecast.copy();h=history.copy();f['interval_start_utc']=pd.to_datetime(f.interval_start_utc,utc=True);h['interval_start_utc']=pd.to_datetime(h.interval_start_utc,utc=True)
    rows=[]
    for r in f.itertuples(index=False):
        p,method,n=contextual_demand_percentile(h,subsystem_id=r.subsystem_id,target_time_utc=r.interval_start_utc,demand_mw=r.demand_p50_mw,timezone_name=timezone_name)
        rows.append({'interval_start_utc':r.interval_start_utc,'subsystem_id':r.subsystem_id,'demand_percentile':p,'demand_percentile_context':method,'demand_percentile_reference_n':n})
    return pd.DataFrame(rows)


def aggregate_generation_json(generation:pd.DataFrame)->pd.DataFrame:
    if generation is None or generation.empty:
        return pd.DataFrame(columns=['interval_start_utc','subsystem_id','generation_by_type_json','generation_total_mw'])
    g=generation.copy();g['interval_start_utc']=pd.to_datetime(g.interval_start_utc,utc=True)
    agg=g.groupby(['interval_start_utc','subsystem_id','generation_type'],as_index=False)['generation_mw'].sum()
    rows=[]
    for (ts,zone),x in agg.groupby(['interval_start_utc','subsystem_id']):
        values={str(k):float(v) for k,v in zip(x.generation_type,x.generation_mw)}
        rows.append({'interval_start_utc':ts,'subsystem_id':zone,'generation_by_type_json':json.dumps(values,ensure_ascii=False,sort_keys=True),'generation_total_mw':float(x.generation_mw.sum())})
    return pd.DataFrame(rows)


def climate_exposure_from_grid(grid_state:pd.DataFrame,cell_zone_map:pd.DataFrame)->pd.DataFrame:
    if grid_state is None or grid_state.empty:return pd.DataFrame(columns=['interval_start_utc','subsystem_id','climate_exposure'])
    g=grid_state.copy();g['interval_start_utc']=pd.to_datetime(g.interval_start_utc,utc=True)
    score_cols=['heat_incident_score','cold_incident_score','rain_incident_score','wind_incident_score','solar_deficit_score']
    g['_incident_max']=g[score_cols].max(axis=1);g=g.merge(cell_zone_map[['cell_id','subsystem_id']].drop_duplicates(),on='cell_id',how='inner')
    return g.groupby(['interval_start_utc','subsystem_id'],as_index=False)['_incident_max'].mean().rename(columns={'_incident_max':'climate_exposure'})


def _supply_pressure(demand:float,generation:float|None)->float|None:
    if generation is None or not np.isfinite(generation) or generation<=0:return None
    # Transparent adequacy proxy for MVP, not load-flow/security analysis.
    adequacy=float(generation)/max(float(demand),1e-9)
    return float(np.clip(1.0-adequacy,0,1))


def build_system_signal(*,forecast:pd.DataFrame,load_history:pd.DataFrame,grid_state:pd.DataFrame,
                        cell_zone_map:pd.DataFrame,future_generation:pd.DataFrame|None,run_id:str,
                        data_freshness_ok:bool=True)->pd.DataFrame:
    f=forecast.copy();f['interval_start_utc']=pd.to_datetime(f.interval_start_utc,utc=True)
    dp=demand_percentiles(f,load_history);cx=climate_exposure_from_grid(grid_state,cell_zone_map);gj=aggregate_generation_json(future_generation if future_generation is not None else pd.DataFrame())
    merged=f.merge(dp,on=['interval_start_utc','subsystem_id']).merge(cx,on=['interval_start_utc','subsystem_id'],how='left').merge(gj,on=['interval_start_utc','subsystem_id'],how='left')
    merged['climate_exposure']=merged['climate_exposure'].fillna(0.0);merged['generation_by_type_json']=merged['generation_by_type_json'].fillna('{}')
    rows=[]
    for r in merged.itertuples(index=False):
        gen=float(r.generation_total_mw) if hasattr(r,'generation_total_mw') and pd.notna(r.generation_total_mw) else None
        drivers=r.main_drivers_json
        if not isinstance(drivers,str):drivers=json.dumps(drivers,ensure_ascii=False,sort_keys=True)
        rows.append({'schema_version':'system_signal_v1','run_id':run_id,'interval_start_utc':r.interval_start_utc,'zone_type':'SUBSYSTEM','zone_id':str(r.subsystem_id),
                     'demand_p10_mw':float(r.demand_p10_mw),'demand_p50_mw':float(r.demand_p50_mw),'demand_p90_mw':float(r.demand_p90_mw),'demand_percentile':float(r.demand_percentile),
                     'supply_pressure':_supply_pressure(r.demand_p50_mw,gen),'climate_exposure':float(r.climate_exposure),'generation_by_type_json':r.generation_by_type_json,
                     'main_drivers_json':drivers,'data_freshness_ok':bool(data_freshness_ok),'quality_flags':json.dumps(['SUPPLY_PROXY_NOT_POWER_FLOW'] if gen is not None else ['SUPPLY_PRESSURE_UNAVAILABLE'])})
    # SIN aggregation. Quantiles summed as an operational approximation; dependence between subsystems is not modeled in MVP.
    for ts,g in merged.groupby('interval_start_utc'):
        gen_total=float(g['generation_total_mw'].sum()) if 'generation_total_mw' in g and g['generation_total_mw'].notna().any() else None
        by_type={}
        for raw in g['generation_by_type_json']:
            try:
                for k,v in json.loads(raw).items():by_type[k]=by_type.get(k,0.0)+float(v)
            except Exception:pass
        d50=float(g.demand_p50_mw.sum())
        hist=load_history.copy();hist['interval_start_utc']=pd.to_datetime(hist.interval_start_utc,utc=True);sin_hist=hist.groupby('interval_start_utc',as_index=False).load_mw.sum();comp=sin_hist[sin_hist.interval_start_utc.dt.hour==ts.hour]
        rows.append({'schema_version':'system_signal_v1','run_id':run_id,'interval_start_utc':ts,'zone_type':'SIN','zone_id':'SIN','demand_p10_mw':float(g.demand_p10_mw.sum()),'demand_p50_mw':d50,'demand_p90_mw':float(g.demand_p90_mw.sum()),
                     'demand_percentile':_empirical_percentile(comp.load_mw,d50),'supply_pressure':_supply_pressure(d50,gen_total),'climate_exposure':float(g.climate_exposure.mean()),
                     'generation_by_type_json':json.dumps(by_type,ensure_ascii=False,sort_keys=True),'main_drivers_json':json.dumps({'aggregation':'subsystem_sum','subsystems':sorted(g.subsystem_id.astype(str).tolist())},ensure_ascii=False,sort_keys=True),
                     'data_freshness_ok':bool(data_freshness_ok),'quality_flags':json.dumps(['QUANTILE_SUM_APPROXIMATION','SUPPLY_PROXY_NOT_POWER_FLOW'] if gen_total is not None else ['QUANTILE_SUM_APPROXIMATION','SUPPLY_PRESSURE_UNAVAILABLE'])})
    return pd.DataFrame(rows).sort_values(['interval_start_utc','zone_type','zone_id']).reset_index(drop=True)
