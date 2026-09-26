#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
from urllib.request import Request,urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_tarifa.sources.aneel import ANEEL_TARIFF_CSV_URL,fetch_tariff_rows


def main():
 p=argparse.ArgumentParser(description='Baixa tarifas homologadas ANEEL: CSV completo ou amostra via CKAN DataStore.')
 p.add_argument('--output',required=True);p.add_argument('--distributor',help='Filtro textual de SigAgente para modo DataStore');p.add_argument('--limit',type=int,default=5000);p.add_argument('--full-csv',action='store_true')
 a=p.parse_args();out=Path(a.output)
 if out.exists():raise SystemExit(f'raw immutable: {out} already exists')
 out.parent.mkdir(parents=True,exist_ok=True)
 if a.full_csv:
  req=Request(ANEEL_TARIFF_CSV_URL,headers={'User-Agent':'Predicta-Hackathon/1.1'});data=urlopen(req,timeout=300).read();out.write_bytes(data);meta={'mode':'full_csv','url':ANEEL_TARIFF_CSV_URL,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
 else:
  df=fetch_tariff_rows(distributor=a.distributor,limit=a.limit);df.to_csv(out,index=False);meta={'mode':'ckan_datastore','distributor_filter':a.distributor,'rows':len(df)}
 out.with_suffix(out.suffix+'.meta.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');print(json.dumps(meta,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
