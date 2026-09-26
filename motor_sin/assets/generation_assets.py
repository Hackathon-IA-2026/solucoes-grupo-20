from __future__ import annotations

import re
import unicodedata
import pandas as pd

from motor_sin.grid.index import coordinate_to_index


def _norm_name(value: object) -> str:
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+',' ',text).strip()


def geocode_generation_assets(generation: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    """Join generation plants to a registry (e.g. ANEEL SIGA). CEG > ONS id > treated name.

    Expected registry columns: plant_id/ons_id/ceg, plant_name, latitude, longitude, capacity_mw.
    Missing coordinates are preserved; no fake centroids are created.
    """
    plants = generation[['plant_id','plant_name','generation_type','subsystem_id','state']].drop_duplicates().copy()
    reg = registry.copy()
    aliases = {c.lower(): c for c in reg.columns}
    rename = {}
    for target, opts in {
        'registry_plant_id':('plant_id','ons_id','id_ons','id_usina'),
        'ceg':('ceg','codigo_ceg'),
        'registry_plant_name':('plant_name','nome','nom_usina','empreendimento'),
        'latitude':('latitude','lat'), 'longitude':('longitude','lon','lng'),
        'capacity_mw':('capacity_mw','potencia_mw','potencia_outorgada_mw'),
    }.items():
        for opt in opts:
            if opt in aliases:
                rename[aliases[opt]]=target; break
    reg=reg.rename(columns=rename)
    for c in ['registry_plant_id','ceg','registry_plant_name','latitude','longitude','capacity_mw']:
        if c not in reg.columns: reg[c]=None
    reg['_name_key']=reg['registry_plant_name'].map(_norm_name)
    plants['_name_key']=plants['plant_name'].map(_norm_name)
    reg['_id_key']=reg['registry_plant_id'].astype(str).str.strip()
    plants['_id_key']=plants['plant_id'].astype(str).str.strip()
    # Exact ID first.
    merged=plants.merge(reg.drop_duplicates('_id_key'), on='_id_key', how='left', suffixes=('','_r'))
    unmatched=merged['latitude'].isna() | merged['longitude'].isna()
    if unmatched.any():
        by_name=reg[reg['_name_key'].ne('')].drop_duplicates('_name_key').set_index('_name_key')
        for idx in merged.index[unmatched]:
            key=merged.at[idx,'_name_key']
            if key in by_name.index:
                row=by_name.loc[key]
                for c in ['latitude','longitude','capacity_mw','ceg']:
                    if pd.isna(merged.at[idx,c]): merged.at[idx,c]=row[c]
                merged.at[idx,'match_method']='NAME'
    merged['match_method']=merged.get('match_method', pd.Series(index=merged.index,dtype=object)).fillna('ID')
    merged['latitude']=pd.to_numeric(merged['latitude'],errors='coerce')
    merged['longitude']=pd.to_numeric(merged['longitude'],errors='coerce')
    merged['capacity_mw']=pd.to_numeric(merged['capacity_mw'],errors='coerce')
    def locate(row):
        if pd.notna(row.latitude) and pd.notna(row.longitude):
            try: return coordinate_to_index(float(row.latitude),float(row.longitude)).cell_id
            except ValueError: return None
        return None
    merged['cell_id']=merged.apply(locate,axis=1)
    merged['location_quality']=merged.apply(lambda r: 'A' if pd.notna(r.latitude) and pd.notna(r.longitude) and r.match_method=='ID' else ('B' if pd.notna(r.latitude) and pd.notna(r.longitude) else 'D'),axis=1)
    merged['outside_sin_scope']=~merged['subsystem_id'].isin(['N','NE','S','SE/CO'])
    return merged[['plant_id','plant_name','generation_type','subsystem_id','state','ceg','latitude','longitude','cell_id','capacity_mw','location_quality','match_method','outside_sin_scope']].reset_index(drop=True)


def build_generation_centers(assets: pd.DataFrame, percentile_threshold: float=0.90) -> pd.DataFrame:
    valid=assets.dropna(subset=['cell_id','capacity_mw']).copy()
    if valid.empty:
        return pd.DataFrame(columns=['cell_id','generation_type','capacity_mw','generation_center_score','is_generation_center'])
    grouped=valid.groupby(['cell_id','generation_type'],as_index=False)['capacity_mw'].sum()
    grouped['generation_center_score']=grouped.groupby('generation_type')['capacity_mw'].rank(method='average',pct=True)
    grouped['is_generation_center']=grouped['generation_center_score'].ge(float(percentile_threshold))
    return grouped
