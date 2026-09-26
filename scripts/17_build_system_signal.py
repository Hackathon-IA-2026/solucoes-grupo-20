#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table
from motor_sin.signals.system_signal import build_system_signal
from contracts.validators.core import validate_dataframe

def main():
 p=argparse.ArgumentParser();p.add_argument('--forecast',required=True);p.add_argument('--load-history',required=True);p.add_argument('--grid-state',required=True);p.add_argument('--cell-zone-map',required=True);p.add_argument('--future-generation');p.add_argument('--run-id',required=True);p.add_argument('--horizon',type=int,default=24);p.add_argument('--output',default='outputs/contracts/system_signal_v1.parquet');a=p.parse_args();gen=read_table(a.future_generation) if a.future_generation else None;out=build_system_signal(forecast=read_table(a.forecast),load_history=read_table(a.load_history),grid_state=read_table(a.grid_state),cell_zone_map=read_table(a.cell_zone_map),future_generation=gen,run_id=a.run_id);r=validate_dataframe(out,'system_signal_v1',expected_hours=a.horizon);r.raise_for_errors();write_table(out,a.output);print(f'rows={len(out)} valid={r.valid} output={Path(a.output).resolve()}')
if __name__=='__main__':main()
