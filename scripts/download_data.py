#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from urllib.request import Request,urlopen

def main():
 p=argparse.ArgumentParser(description='Downloader genérico imutável para recursos oficiais informados pelo usuário.');p.add_argument('--url',required=True);p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output)
 if out.exists():raise SystemExit(f'raw immutable: {out} already exists')
 out.parent.mkdir(parents=True,exist_ok=True);req=Request(a.url,headers={'User-Agent':'Predicta-Hackathon/1.0'});data=urlopen(req,timeout=120).read();out.write_bytes(data);meta={'url':a.url,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()};out.with_suffix(out.suffix+'.meta.json').write_text(json.dumps(meta,indent=2)+'\n');print(meta)
if __name__=='__main__':main()
