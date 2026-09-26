#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table
from motor_sin.signals.grid_state import build_grid_state
from contracts.validators.core import validate_dataframe

def main():
 p=argparse.ArgumentParser();p.add_argument('--scores',required=True);p.add_argument('--incidents',required=True);p.add_argument('--generation',required=True);p.add_argument('--generation-assets',required=True);p.add_argument('--substations',required=True);p.add_argument('--lines',required=True);p.add_argument('--run-id',required=True);p.add_argument('--output',default='outputs/contracts/grid_state_v1.parquet');a=p.parse_args();out=build_grid_state(target_scores=read_table(a.scores),incidents=read_table(a.incidents),generation=read_table(a.generation),generation_assets=read_table(a.generation_assets),substations=read_table(a.substations),lines=read_table(a.lines),run_id=a.run_id);r=validate_dataframe(out,'grid_state_v1');r.raise_for_errors();write_table(out,a.output);print(f'rows={len(out)} valid={r.valid} output={Path(a.output).resolve()}')
if __name__=='__main__':main()
