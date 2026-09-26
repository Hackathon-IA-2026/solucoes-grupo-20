#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table
from motor_sin.demand.pipeline import backtest_models

def main():
 p=argparse.ArgumentParser();p.add_argument('--load',required=True);p.add_argument('--climate',required=True);p.add_argument('--experiment',default='E3');p.add_argument('--test-hours',type=int,default=168);p.add_argument('--forecast-horizon',type=int,default=24);p.add_argument('--origin-step-hours',type=int,default=24);p.add_argument('--calendar-timezone',default='America/Sao_Paulo');p.add_argument('--output',default='outputs/metrics/demand_metrics.csv');a=p.parse_args();out=backtest_models(read_table(a.load),read_table(a.climate),experiment=a.experiment,test_hours=a.test_hours,forecast_horizon=a.forecast_horizon,origin_step_hours=a.origin_step_hours,calendar_timezone=a.calendar_timezone);write_table(out,a.output);print(out.to_string(index=False))
if __name__=='__main__':main()
