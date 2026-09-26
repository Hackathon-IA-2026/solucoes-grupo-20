#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table
from motor_tarifa.base_tariff.parser import prepare_tariffs

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',default='data/processed/tariff/base_tariffs.parquet');p.add_argument('--skipped-output',default='outputs/reports/tariff_non_volumetric_rows.csv');a=p.parse_args();out,skipped=prepare_tariffs(read_table(a.input));write_table(out,a.output);write_table(skipped,a.skipped_output);print(f'volumetric_rows={len(out)} skipped_non_volumetric={len(skipped)}')
if __name__=='__main__':main()
