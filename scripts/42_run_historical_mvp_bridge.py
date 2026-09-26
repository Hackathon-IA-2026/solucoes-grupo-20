#!/usr/bin/env python3
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path


def run(cmd):
    print('+',' '.join(str(x) for x in cmd));subprocess.run(cmd,check=True,cwd=Path(__file__).resolve().parents[1])

def main():
    p=argparse.ArgumentParser(description='Bridge validated E3 backtest -> system_signal_v1 -> optional customer tariff simulation.')
    p.add_argument('--issue-time')
    p.add_argument('--distributor')
    p.add_argument('--profile')
    p.add_argument('--monthly-kwh',type=float,default=300.0)
    p.add_argument('--customer-type',choices=['residential','commercial','industrial_flat'],default='residential')
    a=p.parse_args();py=sys.executable
    cmd=[py,'scripts/39_build_real_system_signal.py']
    if a.issue_time:cmd+=['--issue-time',a.issue_time]
    run(cmd)
    if a.distributor and not a.profile:
        run([py,'scripts/40_prepare_aneel_mvp.py','--distributor',a.distributor])
        print('Select an exact tariff_profile_id from outputs/reports/tariff_profiles.csv, then rerun with --profile.');return
    if a.distributor and a.profile:
        if not Path('data/processed/tariff/base_tariffs.parquet').exists():run([py,'scripts/40_prepare_aneel_mvp.py','--distributor',a.distributor])
        run([py,'scripts/41_simulate_customer_mvp.py','--distributor',a.distributor,'--profile',a.profile,'--monthly-kwh',str(a.monthly_kwh),'--customer-type',a.customer_type])
    else:
        print('system_signal_v1 generated. To continue: scripts/40_prepare_aneel_mvp.py --distributor <SIGAGENTE>')

if __name__=='__main__':main()
