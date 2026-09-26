#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
from urllib.request import Request, urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.sources.ons_balance import source_url


def main():
    p=argparse.ArgumentParser(description='Download imutável do Balanço de Energia por Subsistema do ONS.')
    p.add_argument('--year',type=int,required=True);p.add_argument('--format',choices=['parquet','csv'],default='parquet');p.add_argument('--output')
    a=p.parse_args();url=source_url(a.year,a.format);out=Path(a.output or f'data/raw/ons/balance/BALANCO_ENERGIA_SUBSISTEMA_{a.year}.{a.format}')
    if out.exists():raise SystemExit(f'raw immutable: {out} already exists')
    out.parent.mkdir(parents=True,exist_ok=True);req=Request(url,headers={'User-Agent':'Predicta-Hackathon/1.1'})
    with urlopen(req,timeout=180) as r:data=r.read()
    out.write_bytes(data);meta={'source':'ONS_BALANCO_ENERGIA_SUBSISTEMA','year':a.year,'url':url,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    out.with_suffix(out.suffix+'.meta.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8');print(json.dumps(meta,indent=2))
if __name__=='__main__':main()
