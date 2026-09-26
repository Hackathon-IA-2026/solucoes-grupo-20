#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table,write_json
from motor_tarifa.pipeline import simulate_dynamic_tariff,load_tariff_config
from contracts.validators.core import validate_dataframe

def main():
 p=argparse.ArgumentParser(description='Executa Motor 2 exclusivamente a partir de system_signal_v1 + dados tarifários.');p.add_argument('--signal',default='outputs/contracts/system_signal_v1.parquet');p.add_argument('--base-tariffs',default='data/demo/base_tariffs.csv');p.add_argument('--profile',default='B1_CONVENTIONAL_FIXTURE');p.add_argument('--distributor',default='DIST_EXAMPLE_SECO');p.add_argument('--subsystem',default='SE/CO');p.add_argument('--run-id',default='demo-motor-tarifa');p.add_argument('--consumption-profile',default='data/demo/consumption_profile.csv');p.add_argument('--post-rules');p.add_argument('--output',default='outputs/contracts/tariff_v1.parquet');a=p.parse_args();cons=None
 if a.consumption_profile and Path(a.consumption_profile).exists():cons=read_table(a.consumption_profile)['consumption_kwh'].to_numpy(float)
 rules=read_table(a.post_rules) if a.post_rules else None
 out,report=simulate_dynamic_tariff(system_signal=read_table(a.signal),base_tariffs=read_table(a.base_tariffs),distributor_id=a.distributor,profile_id=a.profile,subsystem_id=a.subsystem,config=load_tariff_config(),run_id=a.run_id,post_rules=rules,consumption_ref_kwh=cons);r=validate_dataframe(out,'tariff_v1',expected_hours=len(out));r.raise_for_errors();write_table(out,a.output);write_json(report,'outputs/reports/tariff_simulation.json');write_json({'run_id':a.run_id,'rows':len(out),'valid':r.valid,'experimental':True},'outputs/reports/tariff_quality.json');print(f'Motor 2 OK: tariff rows={len(out)} output={Path(a.output).resolve()}')
if __name__=='__main__':main()
