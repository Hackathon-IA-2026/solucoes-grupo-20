#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys,yaml
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table
from motor_sin.assets.network import prepare_transmission_lines,compute_hub_scores

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--substations',required=True);p.add_argument('--output',default='data/processed/assets/transmission_lines.parquet');p.add_argument('--hubs-output',default='data/processed/assets/substations_with_hubs.parquet');p.add_argument('--config',default='configs/assets.yaml');a=p.parse_args();sub=read_table(a.substations);lines=prepare_transmission_lines(read_table(a.input),sub);write_table(lines,a.output);cfg=yaml.safe_load(Path(a.config).read_text());hubs=compute_hub_scores(sub,lines,cfg['hub_score']['weights']);write_table(hubs,a.hubs_output);print(f'lines={len(lines)} hubs={len(hubs)}')
if __name__=='__main__':main()
