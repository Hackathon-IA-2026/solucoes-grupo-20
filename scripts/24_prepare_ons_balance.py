#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import write_table,write_json
from motor_sin.sources.ons_balance import read_ons_table,prepare_ons_balance,quality_summary


def main():
 p=argparse.ArgumentParser(description='Normaliza carga e oferta horária do Balanço ONS para UTC.')
 p.add_argument('--input',required=True);p.add_argument('--source-timezone',required=True,help='Timezone IANA explícito para din_instante quando a fonte não contém offset, ex.: America/Sao_Paulo')
 p.add_argument('--load-output',default='data/processed/demand/load_hourly.parquet');p.add_argument('--supply-output',default='data/processed/generation/supply_by_subsystem_hourly.parquet');p.add_argument('--report',default='outputs/reports/ons_balance_quality.json')
 a=p.parse_args();load,supply=prepare_ons_balance(read_ons_table(a.input),source_timezone=a.source_timezone);write_table(load,a.load_output);write_table(supply,a.supply_output);write_json(quality_summary(load,supply),a.report);print(f'load_rows={len(load)} supply_rows={len(supply)}')
if __name__=='__main__':main()
