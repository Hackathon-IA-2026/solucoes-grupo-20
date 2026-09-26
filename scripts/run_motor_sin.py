#!/usr/bin/env python3
from __future__ import annotations

import argparse,sys,subprocess,json
from pathlib import Path
import pandas as pd,yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from motor_sin.common.io import read_table,write_table,write_json
from motor_sin.climate.incidents import detect_incidents,load_incident_config
from motor_sin.assets.generation_assets import geocode_generation_assets,build_generation_centers
from motor_sin.assets.network import prepare_substations,prepare_transmission_lines,compute_hub_scores
from motor_sin.assets.exposure import build_asset_exposure
from motor_sin.signals.grid_state import build_grid_state
from motor_sin.demand.pipeline import train_models,backtest_models,forecast_24h
from motor_sin.signals.system_signal import build_system_signal
from motor_sin.common.manifest import build_manifest
from contracts.validators.core import validate_dataframe


def main():
 p=argparse.ArgumentParser(description='Executa o Motor 1 — SIN, da detecção de incidentes ao system_signal_v1.')
 p.add_argument('--issue-time',default='2026-09-19T00:00:00Z');p.add_argument('--horizon',type=int,default=24);p.add_argument('--run-id',default='demo-motor-sin');p.add_argument('--demo',action='store_true')
 p.add_argument('--data-root',default='data/demo');p.add_argument('--scores');p.add_argument('--generation');p.add_argument('--generation-registry');p.add_argument('--substations');p.add_argument('--lines');p.add_argument('--load');p.add_argument('--zone-climate');p.add_argument('--cell-zone-map')
 a=p.parse_args();root=Path(a.data_root)
 if a.demo:
  subprocess.run([sys.executable,str(Path(__file__).with_name('generate_demo_data.py')),'--issue-time',a.issue_time,'--root',str(root)],check=True)
 def choose(value,name,ext):return Path(value) if value else root/f'{name}.{ext}'
 paths={'scores':choose(a.scores,'target_scores','parquet'),'generation':choose(a.generation,'generation_hourly','parquet'),'registry':choose(a.generation_registry,'generation_registry','csv'),'substations':choose(a.substations,'substations','csv'),'lines':choose(a.lines,'lines','csv'),'load':choose(a.load,'load_hourly','parquet'),'climate':choose(a.zone_climate,'zone_climate','parquet'),'map':choose(a.cell_zone_map,'cell_subsystem_map','csv')}
 for k,v in paths.items():
  if not v.exists():raise SystemExit(f'missing {k}: {v}. Use --demo or provide the input path.')
 scores=read_table(paths['scores']);generation=read_table(paths['generation']);registry=read_table(paths['registry']);load=read_table(paths['load']);zone_climate=read_table(paths['climate']);cellmap=read_table(paths['map'])
 incidents=detect_incidents(scores,load_incident_config());write_table(incidents,'data/processed/climate/incidents_hourly.parquet')
 gen_assets=geocode_generation_assets(generation,registry);write_table(gen_assets,'data/processed/assets/generation_assets.parquet');write_table(build_generation_centers(gen_assets),'data/processed/assets/generation_centers.parquet')
 sub=prepare_substations(read_table(paths['substations']));lines=prepare_transmission_lines(read_table(paths['lines']),sub);cfg=yaml.safe_load(Path('configs/assets.yaml').read_text());sub=compute_hub_scores(sub,lines,cfg['hub_score']['weights']);write_table(sub,'data/processed/assets/substations.parquet');write_table(lines,'data/processed/assets/transmission_lines.parquet')
 exposure=build_asset_exposure(incidents=incidents,generation_assets=gen_assets,substations=sub,lines=lines,run_id=a.run_id);r=validate_dataframe(exposure,'asset_exposure_v1');r.raise_for_errors();write_table(exposure,'outputs/contracts/asset_exposure_v1.parquet')
 grid=build_grid_state(target_scores=scores,incidents=incidents,generation=generation,generation_assets=gen_assets,substations=sub,lines=lines,run_id=a.run_id);r=validate_dataframe(grid,'grid_state_v1');r.raise_for_errors();write_table(grid,'outputs/contracts/grid_state_v1.parquet')
 models=train_models(load,zone_climate,'models/demand','E3');write_table(models,'outputs/metrics/demand_models.csv');metrics=backtest_models(load,zone_climate,experiment='E3',test_hours=min(168,max(24,len(load)//20)));write_table(metrics,'outputs/metrics/demand_metrics.csv')
 forecast=forecast_24h(load_history=load,future_zone_climate=zone_climate,models_index=models,issue_time=pd.Timestamp(a.issue_time),horizon=a.horizon,experiment='E3');write_table(forecast,'data/processed/demand/forecast_24h.parquet')
 signal=build_system_signal(forecast=forecast,load_history=load,grid_state=grid,cell_zone_map=cellmap,future_generation=generation,run_id=a.run_id);r=validate_dataframe(signal,'system_signal_v1',expected_hours=a.horizon);r.raise_for_errors();write_table(signal,'outputs/contracts/system_signal_v1.parquet')
 quality={'run_id':a.run_id,'contracts':{'grid_state_v1':len(grid),'asset_exposure_v1':len(exposure),'system_signal_v1':len(signal)},'demand_metrics':metrics.to_dict(orient='records'),'warnings':['demo generation supply pressure is an adequacy proxy, not power-flow/security analysis']};write_json(quality,'outputs/reports/motor_sin_quality.json')
 manifest=build_manifest(run_id=a.run_id,issue_time=pd.Timestamp(a.issue_time).isoformat(),forecast_horizon=a.horizon,baseline_period='Y-10..Y-1',data_sources=['ERA5/Open-Meteo normalized scores','ONS-compatible generation/load','asset registries'],contract_versions={'grid_state':'grid_state_v1','asset_exposure':'asset_exposure_v1','system_signal':'system_signal_v1','tariff':'tariff_v1'});write_json(manifest,'outputs/reports/run_manifest.json')
 print(f'Motor 1 OK: grid={len(grid)} exposure={len(exposure)} signal={len(signal)}')
 print('outputs/contracts/system_signal_v1.parquet')
if __name__=='__main__':main()
