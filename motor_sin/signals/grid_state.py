from __future__ import annotations

import json
import numpy as np
import pandas as pd
from motor_sin.assets.exposure import line_exposure_by_cell_hour

INCIDENT_SCORE_COLUMNS={'HEAT':'heat_incident_score','COLD':'cold_incident_score','RAIN':'rain_incident_score','WIND':'wind_incident_score','SOLAR_DEFICIT':'solar_deficit_score'}
PERCENTILE_COLUMNS={'temperature_2m':'temperature_percentile','precipitation':'precipitation_percentile','wind_speed_10m':'wind_percentile','solar_radiation':'solar_percentile'}
VALUE_COLUMNS={'temperature_2m':'temperature_2m','precipitation':'precipitation','wind_speed_10m':'wind_speed','solar_radiation':'solar_radiation'}


def build_grid_state(*, target_scores: pd.DataFrame, incidents: pd.DataFrame, generation: pd.DataFrame,
                     generation_assets: pd.DataFrame, substations: pd.DataFrame, lines: pd.DataFrame, run_id: str) -> pd.DataFrame:
    s=target_scores.copy(); s['interval_start_utc']=pd.to_datetime(s['interval_start_utc'],utc=True,errors='raise')
    base=s[['interval_start_utc','cell_id']].drop_duplicates().copy()
    # values, percentiles and temperature anomaly
    for var,col in VALUE_COLUMNS.items():
        tmp=s[s['variable'].eq(var)][['interval_start_utc','cell_id','value','percentile']].rename(columns={'value':col,'percentile':PERCENTILE_COLUMNS[var]})
        base=base.merge(tmp,on=['interval_start_utc','cell_id'],how='left')
    temp_an=s[s['variable'].eq('temperature_2m')][['interval_start_utc','cell_id','anomaly']].rename(columns={'anomaly':'temperature_anomaly'}) if 'anomaly' in s else pd.DataFrame(columns=['interval_start_utc','cell_id','temperature_anomaly'])
    base=base.merge(temp_an,on=['interval_start_utc','cell_id'],how='left')
    inc=incidents.copy(); inc['interval_start_utc']=pd.to_datetime(inc['interval_start_utc'],utc=True,errors='raise')
    if len(inc):
        pivot=inc.pivot_table(index=['interval_start_utc','cell_id'],columns='incident_type',values='incident_score',aggfunc='max',fill_value=0).reset_index()
        pivot=pivot.rename(columns=INCIDENT_SCORE_COLUMNS)
        base=base.merge(pivot,on=['interval_start_utc','cell_id'],how='left')
    for col in INCIDENT_SCORE_COLUMNS.values():
        if col not in base: base[col]=0.0
        base[col]=base[col].fillna(0.0)
    # capacity by cell/type
    cap=generation_assets.dropna(subset=['cell_id']).groupby(['cell_id','generation_type'])['capacity_mw'].sum(min_count=1).unstack(fill_value=0) if len(generation_assets) else pd.DataFrame()
    cap_json={idx:json.dumps({str(k):float(v) for k,v in row.items() if pd.notna(v) and float(v)!=0},ensure_ascii=False,sort_keys=True) for idx,row in cap.iterrows()}
    base['capacity_by_type_json']=base['cell_id'].map(cap_json).fillna('{}')
    # generation by mapped plant cell
    gen=generation.merge(generation_assets[['plant_id','cell_id']],on='plant_id',how='left').dropna(subset=['cell_id']) if len(generation) else pd.DataFrame()
    if len(gen):
        gg=gen.groupby(['interval_start_utc','cell_id','generation_type'])['generation_mw'].sum().unstack(fill_value=0)
        gj={(ts,cell):json.dumps({str(k):float(v) for k,v in row.items() if float(v)!=0},ensure_ascii=False,sort_keys=True) for (ts,cell),row in gg.iterrows()}
        base['generation_by_type_json']=[gj.get((ts,cell),'{}') for ts,cell in zip(base.interval_start_utc,base.cell_id)]
    else: base['generation_by_type_json']='{}'
    # substations/hubs
    if len(substations):
        sc=substations.groupby('cell_id').size().rename('substation_count'); hm=substations.groupby('cell_id')['hub_score'].max().rename('hub_max') if 'hub_score' in substations else pd.Series(dtype=float,name='hub_max')
        base=base.merge(sc,on='cell_id',how='left').merge(hm,on='cell_id',how='left')
    else:
        base['substation_count']=0;base['hub_max']=np.nan
    base['substation_count']=base['substation_count'].fillna(0).astype(int)
    tx=line_exposure_by_cell_hour(lines,incidents)
    base=base.merge(tx,on=['interval_start_utc','cell_id'],how='left'); base['transmission_exposure']=base['transmission_exposure'].fillna(0.0)
    # Coordinates are resolved from deterministic cell id using existing grid helpers.
    from motor_sin.grid.index import CellIndex,index_to_center
    coords=[]
    for cell in base.cell_id:
        _,la,lo=str(cell).split('_'); coords.append(index_to_center(CellIndex(int(la),int(lo))))
    base['lat_center']=[x[0] for x in coords]; base['lon_center']=[x[1] for x in coords]
    core=['temperature_2m','temperature_percentile','precipitation','precipitation_percentile','wind_speed','wind_percentile','solar_radiation','solar_percentile']
    base['data_quality']=1.0-base[core].isna().mean(axis=1)
    base.insert(0,'run_id',run_id);base.insert(0,'schema_version','grid_state_v1')
    cols=['schema_version','run_id','interval_start_utc','cell_id','lat_center','lon_center','temperature_2m','temperature_anomaly','temperature_percentile','precipitation','precipitation_percentile','wind_speed','wind_percentile','solar_radiation','solar_percentile','heat_incident_score','cold_incident_score','rain_incident_score','wind_incident_score','solar_deficit_score','capacity_by_type_json','generation_by_type_json','substation_count','hub_max','transmission_exposure','data_quality']
    return base[cols].sort_values(['interval_start_utc','cell_id']).reset_index(drop=True)
