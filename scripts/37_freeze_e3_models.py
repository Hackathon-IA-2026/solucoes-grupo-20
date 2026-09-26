#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table, write_json
from motor_sin.demand.registry import freeze_direct_model_family


def main():
    p=argparse.ArgumentParser(description='Freeze selected E3 H01..H24 models for inference/Django without retraining on every request.')
    p.add_argument('--load',default='data/processed/demand/load_hourly.parquet')
    p.add_argument('--climate',default='data/processed/climate/zone_climate_hourly_e3.parquet')
    p.add_argument('--subsystem',default='SE/CO')
    p.add_argument('--calendar-timezone',default='America/Sao_Paulo')
    p.add_argument('--calibration-hours',type=int,default=720)
    p.add_argument('--alpha',type=float,default=1.0)
    p.add_argument('--model-dir',default='models/demand/e3_seco_v1')
    p.add_argument('--model-family-id',default='E3_SECO_DIRECT_V1_4_0')
    p.add_argument('--report',default='outputs/reports/e3_frozen_model_manifest.json')
    a=p.parse_args()
    manifest=freeze_direct_model_family(read_table(a.load),read_table(a.climate),subsystem_id=a.subsystem,experiment='E3',horizon=24,calendar_timezone=a.calendar_timezone,calibration_hours=a.calibration_hours,alpha=a.alpha,output_dir=a.model_dir,model_family_id=a.model_family_id)
    write_json(manifest,a.report)
    print(json.dumps({'model_family_id':manifest['model_family_id'],'models':len(manifest['models']),'model_dir':str(Path(a.model_dir).resolve()),'report':str(Path(a.report).resolve())},indent=2,ensure_ascii=False))

if __name__=='__main__':main()
