#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table
from motor_sin.assets.network import prepare_substations

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',default='data/processed/assets/substations.parquet');a=p.parse_args();out=prepare_substations(read_table(a.input));write_table(out,a.output);print(f'rows={len(out)} output={Path(a.output).resolve()}')
if __name__=='__main__':main()
