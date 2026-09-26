#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table
from motor_sin.assets.generation_assets import geocode_generation_assets,build_generation_centers

def main():
    p=argparse.ArgumentParser(); p.add_argument('--generation',required=True); p.add_argument('--registry',required=True); p.add_argument('--output',default='data/processed/assets/generation_assets.parquet'); p.add_argument('--centers-output',default='data/processed/assets/generation_centers.parquet'); p.add_argument('--center-percentile',type=float,default=.90); a=p.parse_args()
    out=geocode_generation_assets(read_table(a.generation),read_table(a.registry)); write_table(out,a.output); write_table(build_generation_centers(out,a.center_percentile),a.centers_output); print(f'assets={len(out)} output={Path(a.output).resolve()}')
if __name__=='__main__':main()
