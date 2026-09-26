#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.climate.local_store import climate_store_root,export_store,import_store,seed_store_from_annual_archive,store_inventory
from motor_sin.common.io import write_json

def main():
    p=argparse.ArgumentParser(description='Manage persistent Predicta Climate Store.')
    p.add_argument('action',choices=['status','seed-existing','import','export']);p.add_argument('--store-root',default='data/climate_store');p.add_argument('--annual-archive-root',default='data/raw/climate/annual_archive');p.add_argument('--source');p.add_argument('--output');p.add_argument('--report',default='outputs/reports/climate_store.json');a=p.parse_args();store=climate_store_root(a.store_root)
    if a.action=='seed-existing':payload={'action':a.action,'seed':seed_store_from_annual_archive(annual_archive_root=a.annual_archive_root,store_root=store),'inventory':store_inventory(store)}
    elif a.action=='import':
        if not a.source:raise SystemExit('--source is required for import')
        payload={'action':a.action,'import':import_store(a.source,store),'inventory':store_inventory(store)}
    elif a.action=='export':payload={'action':a.action,'export':export_store(store,a.output or 'Predicta_Climate_Store.zip'),'inventory':store_inventory(store)}
    else:payload={'action':a.action,'inventory':store_inventory(store)}
    write_json(payload,a.report);print(json.dumps(payload,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
