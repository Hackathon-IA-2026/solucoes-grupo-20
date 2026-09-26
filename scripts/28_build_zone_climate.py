#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table
from motor_sin.demand.features import aggregate_climate_to_zones,attach_baseline_scores


def main():
 p=argparse.ArgumentParser(description='Agrega clima por célula para subsistemas usando mapa cell_id -> subsystem_id explícito.')
 p.add_argument('--climate',required=True,help='climate_hourly wide da Fase 2');p.add_argument('--scores',help='anomalies_hourly long da Fase 3');p.add_argument('--cell-zone-map',required=True);p.add_argument('--incidents',help='incidents_hourly da Fase 4');p.add_argument('--weather-mode',choices=['PERFECT_WEATHER_BACKTEST','OPERATIONAL_FORECAST'],default='PERFECT_WEATHER_BACKTEST');p.add_argument('--output',default='data/processed/climate/zone_climate_hourly.parquet')
 a=p.parse_args();climate=read_table(a.climate)
 if a.scores:climate=attach_baseline_scores(climate,read_table(a.scores))
 out=aggregate_climate_to_zones(climate,read_table(a.cell_zone_map),read_table(a.incidents) if a.incidents else None);out['weather_mode']=a.weather_mode;write_table(out,a.output);print(f'rows={len(out)} output={Path(a.output).resolve()}')
if __name__=='__main__':main()
