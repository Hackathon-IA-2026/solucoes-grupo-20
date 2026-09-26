#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys,pandas as pd
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table
from motor_tarifa.profiles.posts import resolve_tariff_posts

def main():
 p=argparse.ArgumentParser();p.add_argument('--timestamps',required=True);p.add_argument('--timestamp-column',default='interval_start_utc');p.add_argument('--rules',required=True);p.add_argument('--distributor',required=True);p.add_argument('--timezone',default='America/Sao_Paulo');p.add_argument('--output',default='data/processed/tariff/resolved_posts.parquet');a=p.parse_args();src=read_table(a.timestamps);out=resolve_tariff_posts(src[a.timestamp_column],distributor_id=a.distributor,rules=read_table(a.rules),timezone_name=a.timezone);write_table(out,a.output);print(f'rows={len(out)}')
if __name__=='__main__':main()
