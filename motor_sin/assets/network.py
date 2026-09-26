from __future__ import annotations

import json
import numpy as np
import pandas as pd
from motor_sin.grid.index import coordinate_to_index


def prepare_substations(df: pd.DataFrame) -> pd.DataFrame:
    aliases={c.lower():c for c in df.columns}
    def pick(*names):
        for n in names:
            if n.lower() in aliases: return aliases[n.lower()]
        return None
    mapping={
        'substation_id':pick('substation_id','id_subestacao','codigo'),
        'name':pick('name','nome','nom_subestacao'), 'lat':pick('lat','latitude'), 'lon':pick('lon','longitude'),
        'voltage_kv':pick('voltage_kv','tensao_kv','kv'), 'subsystem_id':pick('subsystem_id','subsistema','id_subsistema'),
        'transformer_mva':pick('transformer_mva','mva','capacidade_mva'),
    }
    missing=[k for k,v in mapping.items() if v is None and k not in {'transformer_mva'}]
    if missing: raise ValueError(f'substation source missing fields: {missing}')
    rename={v:k for k,v in mapping.items() if v is not None}
    out=df.rename(columns=rename)[list(rename.values())].copy()
    if 'transformer_mva' not in out: out['transformer_mva']=np.nan
    out['lat']=pd.to_numeric(out['lat'],errors='coerce'); out['lon']=pd.to_numeric(out['lon'],errors='coerce')
    out['voltage_kv']=pd.to_numeric(out['voltage_kv'],errors='coerce'); out['transformer_mva']=pd.to_numeric(out['transformer_mva'],errors='coerce')
    out['subsystem_id']=out['subsystem_id'].astype(str).str.upper().replace({'SE':'SE/CO','SECO':'SE/CO'})
    out['cell_id']=out.apply(lambda r: coordinate_to_index(r.lat,r.lon).cell_id if pd.notna(r.lat) and pd.notna(r.lon) else None,axis=1)
    return out[['substation_id','name','lat','lon','cell_id','voltage_kv','subsystem_id','transformer_mva']]


def _line_cells(row: pd.Series) -> list[str]:
    # MVP: the source may already include traversed grid cells. Otherwise endpoints are used and the line is SCHEMATIC.
    if 'cell_ids_json' in row and pd.notna(row.get('cell_ids_json')):
        try:
            parsed=json.loads(row['cell_ids_json']) if isinstance(row['cell_ids_json'],str) else row['cell_ids_json']
            return [str(x) for x in parsed]
        except Exception: pass
    vals=[]
    for prefix in ('from','to'):
        lat=row.get(f'{prefix}_lat'); lon=row.get(f'{prefix}_lon')
        if pd.notna(lat) and pd.notna(lon): vals.append(coordinate_to_index(float(lat),float(lon)).cell_id)
    return list(dict.fromkeys(vals))


def prepare_transmission_lines(df: pd.DataFrame, substations: pd.DataFrame | None=None) -> pd.DataFrame:
    out=df.copy()
    aliases={c.lower():c for c in out.columns}
    ren={}
    options={
        'line_id':['line_id','id_linha','codigo'], 'from_substation':['from_substation','subestacao_de','de'],
        'to_substation':['to_substation','subestacao_para','para'], 'voltage_kv':['voltage_kv','tensao_kv','kv'],
        'length_km':['length_km','comprimento_km','km'], 'geometry_quality':['geometry_quality','qualidade_geometria'],
        'cell_ids_json':['cell_ids_json','grid_cells_json']}
    for target,names in options.items():
        for name in names:
            if name in aliases: ren[aliases[name]]=target; break
    out=out.rename(columns=ren)
    for req in ['line_id','from_substation','to_substation','voltage_kv']:
        if req not in out: raise ValueError(f'transmission line source missing {req}')
    if substations is not None:
        loc=substations.set_index('substation_id')[['lat','lon']]
        for side in ('from','to'):
            out[f'{side}_lat']=out[f'{side}_substation'].map(loc['lat'])
            out[f'{side}_lon']=out[f'{side}_substation'].map(loc['lon'])
    if 'length_km' not in out: out['length_km']=np.nan
    if 'geometry_quality' not in out: out['geometry_quality']='SCHEMATIC'
    if 'cell_ids_json' not in out: out['cell_ids_json']=None
    out['cell_ids_json']=out.apply(lambda r: json.dumps(_line_cells(r)),axis=1)
    out['voltage_kv']=pd.to_numeric(out['voltage_kv'],errors='coerce'); out['length_km']=pd.to_numeric(out['length_km'],errors='coerce')
    out['geometry_quality']=out['geometry_quality'].fillna('SCHEMATIC').astype(str).str.upper()
    return out[['line_id','from_substation','to_substation','voltage_kv','length_km','cell_ids_json','geometry_quality']]


def compute_hub_scores(substations: pd.DataFrame, lines: pd.DataFrame, weights: dict[str,float]) -> pd.DataFrame:
    sub=substations.copy()
    endpoints=pd.concat([lines[['from_substation']].rename(columns={'from_substation':'substation_id'}),lines[['to_substation']].rename(columns={'to_substation':'substation_id'})])
    degree=endpoints.value_counts('substation_id').rename('degree')
    max_kv=pd.concat([
        lines[['from_substation','voltage_kv']].rename(columns={'from_substation':'substation_id'}),
        lines[['to_substation','voltage_kv']].rename(columns={'to_substation':'substation_id'})]).groupby('substation_id')['voltage_kv'].max().rename('line_max_kv')
    sub=sub.merge(degree,on='substation_id',how='left').merge(max_kv,on='substation_id',how='left')
    sub['degree']=sub['degree'].fillna(0); sub['max_kv']=sub[['voltage_kv','line_max_kv']].max(axis=1)
    components={'transformer_mva':np.log1p(sub['transformer_mva'].fillna(0)), 'degree':sub['degree'].astype(float), 'max_kv':sub['max_kv'].fillna(0).astype(float)}
    score=np.zeros(len(sub)); used=[]; active=[]
    for name,values in components.items():
        w=float(weights.get(name,0))
        if w<=0: continue
        arr=np.asarray(values,dtype=float); lo=np.nanmin(arr); hi=np.nanmax(arr)
        norm=np.zeros_like(arr) if hi<=lo else (arr-lo)/(hi-lo)
        active.append((w,norm)); used.append(name)
    denom=sum(w for w,_ in active) or 1
    for w,norm in active: score += (w/denom)*norm
    sub['hub_score']=np.clip(score,0,1); sub['hub_components_used']=json.dumps(used)
    return sub.drop(columns=['line_max_kv'])
