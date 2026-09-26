#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys,pandas as pd
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table
from motor_sin.demand.pipeline import forecast_24h

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--load',required=True);p.add_argument('--future-climate',required=True);p.add_argument('--models-index',required=True)
 p.add_argument('--issue-time',required=True);p.add_argument('--horizon',type=int,default=24)
 p.add_argument('--calendar-timezone',default='America/Sao_Paulo')
 p.add_argument('--output',default='data/processed/demand/forecast_24h.parquet')
 a=p.parse_args();out=forecast_24h(load_history=read_table(a.load),future_zone_climate=read_table(a.future_climate),models_index=read_table(a.models_index),issue_time=pd.Timestamp(a.issue_time),horizon=a.horizon,calendar_timezone=a.calendar_timezone);write_table(out,a.output);print(f'rows={len(out)} output={Path(a.output).resolve()}')
if __name__=='__main__':main()
