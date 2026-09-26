#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table
from motor_sin.demand.pipeline import train_models

def main():
 p=argparse.ArgumentParser();p.add_argument('--load',required=True);p.add_argument('--climate',required=True);p.add_argument('--experiment',default='E3',choices=['E1','E2','E3']);p.add_argument('--calendar-timezone',default='America/Sao_Paulo');p.add_argument('--model-dir',default='models/demand');p.add_argument('--output',default='outputs/metrics/demand_models.csv');a=p.parse_args();out=train_models(read_table(a.load),read_table(a.climate),a.model_dir,a.experiment,calendar_timezone=a.calendar_timezone);write_table(out,a.output);print(out.to_string(index=False))
if __name__=='__main__':main()
