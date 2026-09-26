#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.climate.grid_sampling import build_active_climate_points, load_generation_asset_cells
from motor_sin.common.io import read_table,write_json

REGIONS={'N':'n','NE':'ne','SE/CO':'seco','S':'s'}

def main():
    p=argparse.ArgumentParser(description='Build 0.1-degree active climate cells: spatial lattice + exact generation-asset cells.')
    p.add_argument('--grid',default='data/processed/grid/brazil_grid_01deg.parquet')
    p.add_argument('--concessions',default='configs/distributor_areas_wgs84.geojson')
    p.add_argument('--generation-assets',default='configs/generation_assets_catalog.json')
    p.add_argument('--mode',choices=['adaptive','full'],default='adaptive')
    p.add_argument('--stride-cells',type=int,default=20,help='adaptive sampling stride on canonical 0.1-degree grid; 20 = 2 degrees between regional sample cells')
    p.add_argument('--output',default='data/processed/grid/climate_points_01deg.csv')
    p.add_argument('--report',default='outputs/reports/climate_grid_points.json')
    a=p.parse_args();grid=read_table(a.grid)
    anchors=[f'configs/e2_{tag}_points.csv' for tag in REGIONS.values()]
    out=build_active_climate_points(grid,concession_geojson=a.concessions,generation_assets_json=a.generation_assets,anchor_files=anchors,mode=a.mode,stride_cells=a.stride_cells)
    Path(a.output).parent.mkdir(parents=True,exist_ok=True);out.to_csv(a.output,index=False)
    asset_map=load_generation_asset_cells(a.generation_assets);asset_out=Path('data/processed/assets/generation_asset_cells.csv');asset_out.parent.mkdir(parents=True,exist_ok=True);asset_map.to_csv(asset_out,index=False)
    per_region={}
    for region,tag in REGIONS.items():
        part=out[out.subsystem_id.eq(region)].copy();path=Path(f'data/processed/grid/climate_points_{tag}_01deg.csv');part.to_csv(path,index=False)
        per_region[region]={'rows':int(len(part)),'asset_cells':int(part.point_role.str.contains('generation_asset').sum()),'path':str(path)}
    report={'mode':a.mode,'stride_cells':a.stride_cells,'grid_resolution_deg':0.1,'crs':'EPSG:4326','rows':int(len(out)),'regions':per_region,'output':a.output,'generation_asset_cells':'data/processed/assets/generation_asset_cells.csv','warning':'adaptive mode materializes exact 0.1-degree cells on a deterministic spatial lattice plus all generation-asset cells; use --mode full to request every mapped Brazil grid cell, which is much more expensive.'}
    write_json(report,a.report);print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
