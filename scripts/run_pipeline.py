#!/usr/bin/env python3
from __future__ import annotations
import argparse,subprocess,sys
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description='Pipeline Predicta ponta a ponta (Motor 1 -> contrato -> Motor 2).');p.add_argument('--issue-time',default='2026-09-19T00:00:00Z');p.add_argument('--horizon',type=int,default=24);p.add_argument('--profile',default='B1_CONVENTIONAL_FIXTURE');p.add_argument('--distributor',default='DIST_EXAMPLE_SECO');p.add_argument('--subsystem',default='SE/CO');p.add_argument('--demo',action='store_true');a=p.parse_args();here=Path(__file__).resolve().parent
 cmd=[sys.executable,str(here/'run_motor_sin.py'),'--issue-time',a.issue_time,'--horizon',str(a.horizon),'--run-id','pipeline-motor-sin'];
 if a.demo:cmd.append('--demo')
 subprocess.run(cmd,check=True)
 subprocess.run([sys.executable,str(here/'run_motor_tarifa.py'),'--signal','outputs/contracts/system_signal_v1.parquet','--base-tariffs','data/demo/base_tariffs.csv','--profile',a.profile,'--distributor',a.distributor,'--subsystem',a.subsystem,'--run-id','pipeline-motor-tarifa'],check=True)
 print('Predicta pipeline OK')
if __name__=='__main__':main()
