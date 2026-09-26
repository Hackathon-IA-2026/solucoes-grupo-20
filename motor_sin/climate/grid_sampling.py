from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from motor_sin.grid.index import CellIndex, coordinate_to_index, point_in_geojson_geometry


def _geometry_bbox(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    def walk(value):
        if isinstance(value, list) and len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
            xs.append(float(value[0])); ys.append(float(value[1])); return
        if isinstance(value, list):
            for item in value: walk(item)
    walk(geometry.get('coordinates'))
    return min(xs), min(ys), max(xs), max(ys)


def _canonical_zone(value: str | None) -> str:
    raw = str(value or '').strip().upper()
    return {'SE': 'SE/CO', 'SECO': 'SE/CO'}.get(raw, raw)


def load_generation_asset_cells(path: str | Path) -> pd.DataFrame:
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    rows = []
    for item in payload.get('usinas', []):
        lat = item.get('latitude'); lon = item.get('longitude')
        if lat is None or lon is None: continue
        idx = coordinate_to_index(float(lat), float(lon))
        rows.append({
            'cell_id': idx.cell_id,
            'subsystem_id': _canonical_zone(item.get('subsistema')),
            'plant_name': item.get('nome_siga') or item.get('nome_ons'),
            'generation_type': item.get('fonte_nome') or item.get('fonte'),
            'capacity_mw': item.get('capacidade_instalada_mw'),
        })
    return pd.DataFrame(rows)


def assign_grid_subsystems(grid: pd.DataFrame, concession_geojson: str | Path) -> pd.DataFrame:
    payload = json.loads(Path(concession_geojson).read_text(encoding='utf-8'))
    features = []
    for feat in payload.get('features', []):
        props = feat.get('properties') or {}
        zone = _canonical_zone(props.get('subsystem_id'))
        if zone not in {'N', 'NE', 'SE/CO', 'S'}: continue
        geom = feat.get('geometry') or {}
        try: bbox = _geometry_bbox(geom)
        except Exception: continue
        features.append((zone, geom, bbox))
    out = grid.copy()
    zones = []
    for row in out.itertuples(index=False):
        lon = float(row.lon_center); lat = float(row.lat_center); match = None
        for zone, geom, (xmin, ymin, xmax, ymax) in features:
            if lon < xmin or lon > xmax or lat < ymin or lat > ymax: continue
            try:
                if point_in_geojson_geometry(lon, lat, geom):
                    match = zone; break
            except Exception:
                continue
        zones.append(match)
    out['subsystem_id'] = zones
    return out


def _nearest_anchor_timezone(lat: float, lon: float, anchors: pd.DataFrame) -> tuple[str, str]:
    if anchors.empty:
        return 'America/Sao_Paulo', 'GRID'
    d = (anchors['latitude'].astype(float) - lat) ** 2 + ((anchors['longitude'].astype(float) - lon) * np.cos(np.radians(lat))) ** 2
    r = anchors.loc[d.idxmin()]
    return str(r['timezone']), str(r.get('state') or 'GRID')


def build_active_climate_points(
    grid: pd.DataFrame,
    *,
    concession_geojson: str | Path,
    generation_assets_json: str | Path,
    anchor_files: list[str | Path],
    mode: str = 'adaptive',
    stride_cells: int = 20,
) -> pd.DataFrame:
    """Build exact 0.1° climate cells for training/asset exposure.

    adaptive: deterministic spatial lattice + every generation-asset cell.
    full: every Brazil grid cell assigned to an MVP subsystem polygon.
    """
    if mode not in {'adaptive', 'full'}:
        raise ValueError('mode must be adaptive or full')
    g = assign_grid_subsystems(grid, concession_geojson)
    g = g[g['subsystem_id'].isin(['N', 'NE', 'SE/CO', 'S'])].copy()
    # derive canonical grid indices from cell id so sampling is stable across runs
    parts = g['cell_id'].astype(str).str.split('_', expand=True)
    g['_lat_i'] = pd.to_numeric(parts[1], errors='coerce')
    g['_lon_i'] = pd.to_numeric(parts[2], errors='coerce')
    if mode == 'full':
        sample = g.copy(); sample['point_role'] = 'regional_grid'; sample['weight'] = 1.0
    else:
        stride = max(1, int(stride_cells))
        sample = g[(g['_lat_i'] % stride == 0) & (g['_lon_i'] % stride == 0)].copy()
        sample['point_role'] = 'regional_grid'; sample['weight'] = 1.0

    assets = load_generation_asset_cells(generation_assets_json)
    asset_cells = g.merge(assets[['cell_id', 'subsystem_id']].drop_duplicates(), on=['cell_id', 'subsystem_id'], how='inner')
    asset_cells['point_role'] = 'generation_asset'; asset_cells['weight'] = 0.001
    combined = pd.concat([sample, asset_cells], ignore_index=True)
    role = combined.groupby(['cell_id', 'subsystem_id'])['point_role'].agg(lambda s: 'regional_grid+generation_asset' if set(s) == {'regional_grid', 'generation_asset'} else list(s)[0]).rename('point_role')
    weight = combined.groupby(['cell_id', 'subsystem_id'])['weight'].max().rename('weight')
    base = combined.drop_duplicates(['cell_id', 'subsystem_id']).drop(columns=['point_role', 'weight']).set_index(['cell_id', 'subsystem_id'])
    combined = base.join(role).join(weight).reset_index()

    anchor_parts=[]
    for path in anchor_files:
        p=Path(path)
        if p.exists():
            x=pd.read_csv(p);x['subsystem_id']=x['subsystem_id'].map(_canonical_zone);anchor_parts.append(x)
    anchors=pd.concat(anchor_parts,ignore_index=True) if anchor_parts else pd.DataFrame()
    tz=[];state=[]
    for r in combined.itertuples(index=False):
        a=anchors[anchors['subsystem_id'].eq(r.subsystem_id)] if not anchors.empty else anchors
        t,s=_nearest_anchor_timezone(float(r.lat_center),float(r.lon_center),a);tz.append(t);state.append(s)
    combined['point_id']='grid_'+combined['cell_id'].astype(str)
    combined['name']=combined['cell_id'].astype(str)
    combined['state']=state
    combined['latitude']=combined['lat_center'].astype(float)
    combined['longitude']=combined['lon_center'].astype(float)
    combined['timezone']=tz
    combined['grid_resolution_deg']=0.1
    combined['crs']='EPSG:4326'
    cols=['point_id','name','state','subsystem_id','latitude','longitude','timezone','weight','cell_id','point_role','grid_resolution_deg','crs']
    return combined[cols].sort_values(['subsystem_id','point_role','cell_id']).reset_index(drop=True)
