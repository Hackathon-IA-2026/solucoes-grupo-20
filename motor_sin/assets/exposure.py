from __future__ import annotations

import json
import pandas as pd


def _flags(*items: str) -> str:
    return json.dumps([x for x in items if x], ensure_ascii=False)


def build_asset_exposure(*, incidents: pd.DataFrame, generation_assets: pd.DataFrame,
                         substations: pd.DataFrame, lines: pd.DataFrame, run_id: str) -> pd.DataFrame:
    inc=incidents.copy()
    inc['interval_start_utc']=pd.to_datetime(inc['interval_start_utc'],utc=True,errors='raise')
    rows=[]
    for asset_type,assets,id_col in [('GENERATION',generation_assets,'plant_id'),('SUBSTATION',substations,'substation_id')]:
        if 'cell_id' not in assets: continue
        merged=inc.merge(assets, on='cell_id', how='inner', suffixes=('','_asset'))
        for r in merged.itertuples(index=False):
            rows.append({
                'schema_version':'asset_exposure_v1','run_id':run_id,'interval_start_utc':r.interval_start_utc,
                'asset_id':str(getattr(r,id_col)),'asset_type':asset_type,'cell_id':str(r.cell_id),
                'geometry_quality':str(getattr(r,'location_quality','A')) if asset_type=='GENERATION' else 'A',
                'incident_type':str(r.incident_type),'incident_score':float(r.incident_score),
                'exposure_reason':f'{asset_type.lower()} cell coincides with {r.incident_type} incident',
                'generation_type':str(getattr(r,'generation_type')) if asset_type=='GENERATION' else None,
                'capacity_mw':float(getattr(r,'capacity_mw')) if asset_type=='GENERATION' and pd.notna(getattr(r,'capacity_mw')) else None,
                'hub_score':float(getattr(r,'hub_score')) if asset_type=='SUBSTATION' and pd.notna(getattr(r,'hub_score',None)) else None,
                'voltage_kv':float(getattr(r,'voltage_kv')) if asset_type=='SUBSTATION' and pd.notna(getattr(r,'voltage_kv',None)) else None,
                'transformer_mva':float(getattr(r,'transformer_mva')) if asset_type=='SUBSTATION' and pd.notna(getattr(r,'transformer_mva',None)) else None,
                'quality_flags':_flags('COINCIDENCE_NOT_CAUSALITY'),
            })
    # Lines: cell list may be real or schematic. Exposure is qualitative when schematic.
    inc_key=inc.groupby(['interval_start_utc','cell_id','incident_type'],as_index=False)['incident_score'].max()
    for line in lines.itertuples(index=False):
        try: cells=json.loads(line.cell_ids_json)
        except Exception: cells=[]
        if not cells: continue
        sub=inc_key[inc_key['cell_id'].isin(cells)]
        for (ts,itype),g in sub.groupby(['interval_start_utc','incident_type']):
            rows.append({
                'schema_version':'asset_exposure_v1','run_id':run_id,'interval_start_utc':ts,'asset_id':str(line.line_id),
                'asset_type':'TRANSMISSION_LINE','cell_id':None,'geometry_quality':str(line.geometry_quality),
                'incident_type':str(itype),'incident_score':float(g['incident_score'].max()),
                'exposure_reason':'line intersects incident cells' if str(line.geometry_quality)=='REAL' else 'schematic line endpoints/cells coincide with incident area',
                'generation_type':None,'capacity_mw':None,'hub_score':None,'voltage_kv':float(line.voltage_kv) if pd.notna(line.voltage_kv) else None,
                'transformer_mva':None,'quality_flags':_flags('SCHEMATIC_GEOMETRY' if str(line.geometry_quality)!='REAL' else '', 'COINCIDENCE_NOT_CAUSALITY'),
            })
    out=pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=['schema_version','run_id','interval_start_utc','asset_id','asset_type','cell_id','geometry_quality','incident_type','incident_score','exposure_reason','generation_type','capacity_mw','hub_score','voltage_kv','transformer_mva','quality_flags'])
    return out.sort_values(['interval_start_utc','asset_id','incident_type']).drop_duplicates(['run_id','interval_start_utc','asset_id','incident_type']).reset_index(drop=True)


def line_exposure_by_cell_hour(lines: pd.DataFrame, incidents: pd.DataFrame) -> pd.DataFrame:
    """Return cell/hour transmission exposure proxy in [0,1]. Schematics are still marked through source rows."""
    severe=incidents.groupby(['interval_start_utc','cell_id'],as_index=False)['incident_score'].max()
    records=[]
    for line in lines.itertuples(index=False):
        try: cells=json.loads(line.cell_ids_json)
        except Exception: cells=[]
        n=max(len(cells),1)
        for ts,g in severe[severe['cell_id'].isin(cells)].groupby('interval_start_utc'):
            hit=set(g.loc[g['incident_score'].gt(0),'cell_id'])
            fraction=len(hit)/n
            for cell in cells:
                records.append({'interval_start_utc':ts,'cell_id':cell,'transmission_exposure':fraction,'geometry_quality':line.geometry_quality})
    if not records: return pd.DataFrame(columns=['interval_start_utc','cell_id','transmission_exposure'])
    return pd.DataFrame(records).groupby(['interval_start_utc','cell_id'],as_index=False)['transmission_exposure'].max()
