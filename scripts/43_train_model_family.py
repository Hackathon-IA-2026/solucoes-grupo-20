#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table, write_json
from motor_sin.demand.registry import freeze_direct_model_family
from motor_sin.demand.availability import align_experiment_period



def main():
    p=argparse.ArgumentParser(description='Train/freeze a deployment-ready direct H01..H24 model family for E1, E2 or E3 with Ridge or XGBoost.')
    p.add_argument('--experiment',choices=['E1','E2','E3'],default='E3')
    p.add_argument('--algorithm',choices=['ridge','xgboost'],default='ridge')
    p.add_argument('--load',default='data/processed/demand/load_hourly.parquet')
    p.add_argument('--climate')
    p.add_argument('--subsystem',default='SE/CO')
    p.add_argument('--calendar-timezone',default='America/Sao_Paulo')
    p.add_argument('--train-start',help='Optional inclusive UTC/date start for model history.')
    p.add_argument('--train-end',help='Optional inclusive UTC/date end for model history.')
    p.add_argument('--calibration-hours',type=int,default=720)
    p.add_argument('--alpha',type=float,default=1.0)
    p.add_argument('--n-estimators',type=int,default=350)
    p.add_argument('--max-depth',type=int,default=6)
    p.add_argument('--learning-rate',type=float,default=0.05)
    p.add_argument('--subsample',type=float,default=0.9)
    p.add_argument('--colsample-bytree',type=float,default=0.9)
    p.add_argument('--model-dir',required=True)
    p.add_argument('--model-family-id',required=True)
    p.add_argument('--report',default='outputs/reports/trained_model_manifest.json')
    a=p.parse_args()
    climate_path=a.climate
    if not climate_path:
        if a.experiment=='E2': climate_path='data/processed/climate/zone_climate_hourly.parquet'
        elif a.experiment=='E3': climate_path='data/processed/climate/zone_climate_hourly_e3.parquet'
    raw_load=read_table(a.load)
    raw_climate=read_table(climate_path) if climate_path else None
    load,climate,availability=align_experiment_period(
        raw_load,raw_climate,experiment=a.experiment,subsystem_id=a.subsystem,
        requested_start=a.train_start,requested_end=a.train_end,
    )
    print(json.dumps({'availability_window':availability.to_dict()},ensure_ascii=False,indent=2))
    if availability.adjusted_to_common_overlap:
        print('INFO: E2/E3 training was automatically clipped to the common ONS + climate coverage window.')
    xgb_params={
        'n_estimators':a.n_estimators,'max_depth':a.max_depth,'learning_rate':a.learning_rate,
        'subsample':a.subsample,'colsample_bytree':a.colsample_bytree,
    }
    manifest=freeze_direct_model_family(
        load,climate,subsystem_id=a.subsystem,experiment=a.experiment,horizon=24,
        calendar_timezone=a.calendar_timezone,calibration_hours=a.calibration_hours,alpha=a.alpha,
        algorithm=a.algorithm,xgb_params=xgb_params if a.algorithm=='xgboost' else None,
        output_dir=a.model_dir,model_family_id=a.model_family_id,
    )
    manifest['requested_train_start']=a.train_start;manifest['requested_train_end']=a.train_end;manifest['availability_window']=availability.to_dict()
    write_json(manifest,a.report)
    print(json.dumps({'model_family_id':manifest['model_family_id'],'experiment':manifest['experiment'],'algorithm':manifest['algorithm'],'models':len(manifest['models']),'model_dir':str(Path(a.model_dir).resolve()),'report':str(Path(a.report).resolve())},indent=2,ensure_ascii=False))

if __name__=='__main__': main()
