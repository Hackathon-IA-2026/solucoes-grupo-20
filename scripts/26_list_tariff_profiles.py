#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table
from motor_tarifa.base_tariff.parser import prepare_tariffs


def main():
 p=argparse.ArgumentParser(description='Lista perfis tarifários volumétricos elegíveis em uma data.')
 p.add_argument('--input',required=True);p.add_argument('--distributor',required=True);p.add_argument('--date',required=True);p.add_argument('--output',default='outputs/reports/tariff_profiles.csv')
 a=p.parse_args();tariffs,skipped=prepare_tariffs(read_table(a.input));d=pd.Timestamp(a.date).date();vf=pd.to_datetime(tariffs.valid_from,errors='coerce').dt.date;vt=pd.to_datetime(tariffs.valid_to,errors='coerce').dt.date
 mask=tariffs.distributor_id.astype(str).str.contains(a.distributor,case=False,regex=False,na=False)&vf.le(d)&(vt.isna()|vt.ge(d));out=tariffs.loc[mask].sort_values(['tariff_profile_id','tariff_post']).reset_index(drop=True);write_table(out,a.output);print(out[['distributor_id','tariff_profile_id','tariff_post','base_total_rs_kwh','valid_from','valid_to']].to_string(index=False));print(f'eligible={len(out)} skipped_non_volumetric={len(skipped)}')
if __name__=='__main__':main()
