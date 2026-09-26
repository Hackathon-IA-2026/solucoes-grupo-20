#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys,numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table,write_json
from motor_tarifa.pipeline import simulate_dynamic_tariff,load_tariff_config
from contracts.validators.core import validate_dataframe

def main():
 p=argparse.ArgumentParser();p.add_argument('--signal',required=True);p.add_argument('--base-tariffs',required=True);p.add_argument('--distributor',required=True);p.add_argument('--profile',required=True);p.add_argument('--subsystem',required=True);p.add_argument('--run-id',required=True);p.add_argument('--post-rules');p.add_argument('--consumption-profile');p.add_argument('--output',default='outputs/contracts/tariff_v1.parquet');p.add_argument('--report',default='outputs/reports/tariff_simulation.json');a=p.parse_args();cons=None
 if a.consumption_profile:
  c=read_table(a.consumption_profile);cons=c['consumption_kwh'].to_numpy(float)
 rules=read_table(a.post_rules) if a.post_rules else None
 out,report=simulate_dynamic_tariff(system_signal=read_table(a.signal),base_tariffs=read_table(a.base_tariffs),distributor_id=a.distributor,profile_id=a.profile,subsystem_id=a.subsystem,config=load_tariff_config(),run_id=a.run_id,post_rules=rules,consumption_ref_kwh=cons);r=validate_dataframe(out,'tariff_v1',expected_hours=len(out));r.raise_for_errors();write_table(out,a.output);write_json(report,a.report);print(f'rows={len(out)} valid={r.valid} output={Path(a.output).resolve()}')
if __name__=='__main__':main()
