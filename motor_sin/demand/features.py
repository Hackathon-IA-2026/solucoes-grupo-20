from __future__ import annotations

from typing import Sequence
import pandas as pd

from motor_sin.calendar.br_calendar import calendar_feature_frame

DEFAULT_LAGS=(1,2,24,48,168)


def attach_baseline_scores(climate:pd.DataFrame,scores:pd.DataFrame)->pd.DataFrame:
    """Attach Phase-3 long-form anomaly/percentile scores to the wide cell-hour climate table."""
    c=climate.copy();c['interval_start_utc']=pd.to_datetime(c['interval_start_utc'],utc=True,errors='raise')
    sc=scores.copy();sc['interval_start_utc']=pd.to_datetime(sc['interval_start_utc'],utc=True,errors='raise')
    req={'interval_start_utc','cell_id','variable','anomaly','percentile'}
    miss=req-set(sc.columns)
    if miss:raise ValueError(f'climate scores missing columns {sorted(miss)}')
    key=['interval_start_utc','cell_id']
    if sc.duplicated(key+['variable']).any():raise ValueError('climate scores have duplicate cell-hour-variable rows')
    frames=[]
    mapping={
        'temperature_2m':('temperature_anomaly','temperature_percentile'),
        'precipitation':(None,'precipitation_percentile'),
        'wind_speed_10m':(None,'wind_percentile'),
        'solar_radiation':(None,'solar_percentile'),
    }
    for var,(anom_name,pct_name) in mapping.items():
        g=sc[sc['variable'].eq(var)][key+['anomaly','percentile']].copy()
        if g.empty:continue
        ren={'percentile':pct_name}
        if anom_name:ren['anomaly']=anom_name
        else:g=g.drop(columns=['anomaly'])
        frames.append(g.rename(columns=ren))
    out=c
    for g in frames:out=out.merge(g,on=key,how='left',validate='one_to_one')
    return out


def aggregate_climate_to_zones(climate:pd.DataFrame,cell_zone_map:pd.DataFrame,incidents:pd.DataFrame|None=None)->pd.DataFrame:
    """Aggregate cell-hour climate to ONS subsystems using an explicit cell -> subsystem mapping.

    The mapping is deliberately external: the code never invents an electrical-zone boundary from state borders.
    """
    c=climate.copy(); c['interval_start_utc']=pd.to_datetime(c['interval_start_utc'],utc=True,errors='raise')
    mapping=cell_zone_map[['cell_id','subsystem_id']].drop_duplicates().copy()
    if mapping['cell_id'].duplicated().any():
        raise ValueError('cell_zone_map must assign each cell_id to at most one subsystem')
    mapping['subsystem_id']=mapping['subsystem_id'].astype(str).str.strip().str.upper().replace({'SE':'SE/CO','SECO':'SE/CO'})
    c=c.merge(mapping,on='cell_id',how='inner')
    vars=[x for x in [
        'temperature_2m','dewpoint_2m','precipitation','wind_speed_10m','wind_speed','solar_radiation',
        'temperature_anomaly','temperature_percentile','precipitation_percentile',
        'wind_percentile','solar_percentile'
    ] if x in c.columns]
    rows=[]
    for (ts,zone),g in c.groupby(['interval_start_utc','subsystem_id']):
        row={'interval_start_utc':ts,'subsystem_id':zone,'weighting_method':'uniform'}
        for v in vars:
            vals=pd.to_numeric(g[v],errors='coerce').dropna()
            if len(vals):
                row[f'{v}_mean']=float(vals.mean());row[f'{v}_median']=float(vals.median());row[f'{v}_p90']=float(vals.quantile(.9));row[f'{v}_max']=float(vals.max())
        rows.append(row)
    out=pd.DataFrame(rows)
    if out.empty:
        return out
    out['incident_cell_fraction']=0.0
    for incident_name in ['HEAT','COLD','RAIN','WIND','SOLAR_DEFICIT']:
        out[f'incident_{incident_name.lower()}_fraction']=0.0
    if incidents is not None and len(incidents):
        inc=incidents.copy();inc['interval_start_utc']=pd.to_datetime(inc['interval_start_utc'],utc=True,errors='raise');inc=inc.merge(mapping,on='cell_id',how='inner')
        counts=c.groupby(['interval_start_utc','subsystem_id'])['cell_id'].nunique().rename('n_cells')
        exposed=inc[inc['incident_score'].gt(0)].groupby(['interval_start_utc','subsystem_id'])['cell_id'].nunique().rename('incident_cells')
        frac=pd.concat([counts,exposed],axis=1).fillna(0);frac['incident_cell_fraction']=frac['incident_cells']/frac['n_cells'].clip(lower=1)
        out=out.drop(columns=['incident_cell_fraction']).merge(frac[['incident_cell_fraction']].reset_index(),on=['interval_start_utc','subsystem_id'],how='left')
        out['incident_cell_fraction']=out['incident_cell_fraction'].fillna(0.0)
        for incident_name in ['HEAT','COLD','RAIN','WIND','SOLAR_DEFICIT']:
            exp=inc[(inc['incident_type'].eq(incident_name)) & inc['incident_score'].gt(0)].groupby(['interval_start_utc','subsystem_id'])['cell_id'].nunique().rename('incident_cells')
            f=pd.concat([counts,exp],axis=1).fillna(0);col=f'incident_{incident_name.lower()}_fraction';f[col]=f['incident_cells']/f['n_cells'].clip(lower=1)
            out=out.drop(columns=[col]).merge(f[[col]].reset_index(),on=['interval_start_utc','subsystem_id'],how='left');out[col]=out[col].fillna(0.0)
    return out


def build_supervised_features(load:pd.DataFrame,zone_climate:pd.DataFrame|None=None,*,lags:Sequence[int]=DEFAULT_LAGS,calendar_timezone:str='UTC')->pd.DataFrame:
    x=load.copy();x['interval_start_utc']=pd.to_datetime(x['interval_start_utc'],utc=True,errors='raise');x=x.sort_values(['subsystem_id','interval_start_utc'])
    for lag in lags:x[f'lag_{lag}h']=x.groupby('subsystem_id')['load_mw'].shift(lag)
    cal=calendar_feature_frame(x['interval_start_utc'],timezone=calendar_timezone)
    for col in cal.columns:x[col]=cal[col].to_numpy()
    if zone_climate is not None and len(zone_climate):
        z=zone_climate.copy();z['interval_start_utc']=pd.to_datetime(z['interval_start_utc'],utc=True,errors='raise')
        if z.duplicated(['interval_start_utc','subsystem_id']).any():raise ValueError('zone_climate has duplicate subsystem-hour rows')
        x=x.merge(z,on=['interval_start_utc','subsystem_id'],how='left')
    return x


def feature_columns(df:pd.DataFrame,experiment:str)->list[str]:
    history=[c for c in df if c.startswith('lag_')]
    cal=[c for c in ['hour','day_of_week','weekend','holiday_national','carnival','good_friday','corpus_christi','month'] if c in df]
    raw=[c for c in df if any(c.startswith(v) for v in ['temperature_2m_','dewpoint_2m_','precipitation_','wind_speed_','solar_radiation_']) and 'percentile' not in c and 'anomaly' not in c]
    enhanced=[c for c in df if ('anomaly_' in c or 'percentile_' in c or c.startswith('incident_'))]
    if experiment=='E1':return history+cal
    if experiment=='E2':return history+cal+raw
    if experiment=='E3':return history+cal+raw+enhanced
    raise ValueError(f'unsupported model experiment: {experiment}')
