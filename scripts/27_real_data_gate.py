#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_json
from motor_sin.demand.real_gate import validate_real_pilot


def main():
 p=argparse.ArgumentParser(description='Gate anti-leakage/qualidade antes do piloto com dados reais.')
 p.add_argument('--load',required=True);p.add_argument('--climate');p.add_argument('--subsystem',default='SE/CO');p.add_argument('--weather-mode',choices=['PERFECT_WEATHER_BACKTEST','OPERATIONAL_FORECAST'],default='PERFECT_WEATHER_BACKTEST');p.add_argument('--start');p.add_argument('--end');p.add_argument('--output',default='outputs/reports/real_data_gate.json')
 a=p.parse_args();report=validate_real_pilot(read_table(a.load),read_table(a.climate) if a.climate else None,subsystem_id=a.subsystem,weather_mode=a.weather_mode,start=a.start,end=a.end);write_json(report,a.output);print(json.dumps(report,indent=2,ensure_ascii=False));raise SystemExit(0 if report['ready'] else 2)
if __name__=='__main__':main()
