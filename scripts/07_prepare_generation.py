#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table, write_table, write_json
from motor_sin.common.quality import quality_report
from motor_sin.generation.prepare import normalize_generation


def main() -> None:
    p=argparse.ArgumentParser(description='Normaliza geração por usina ONS para o contrato interno horário.')
    p.add_argument('--input', required=True)
    p.add_argument('--output', default='data/processed/generation/generation_hourly.parquet')
    p.add_argument('--run-id', default='generation-run')
    p.add_argument('--quality', default='outputs/reports/generation_quality.json')
    args=p.parse_args()
    raw=read_table(args.input)
    out, unknown=normalize_generation(raw)
    write_table(out,args.output)
    write_json(quality_report(run_id=args.run_id,source='ONS_GENERATION',input_rows=len(raw),output=out,unknown_categories=unknown),args.quality)
    print(f'rows={len(out)} unknown_types={unknown} output={Path(args.output).resolve()}')

if __name__=='__main__': main()
