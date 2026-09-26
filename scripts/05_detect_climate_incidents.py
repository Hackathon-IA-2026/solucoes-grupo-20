#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor_sin.climate.incidents import detect_incidents, load_incident_config
from motor_sin.common.io import read_table, write_table


def main() -> None:
    p = argparse.ArgumentParser(description='Detecta incidentes climáticos por célula/hora a partir dos scores do baseline.')
    p.add_argument('--scores', required=True, help='Parquet/CSV anomalies_hourly produzido na Fase 3.')
    p.add_argument('--config', default='configs/incidents.yaml')
    p.add_argument('--output', default='data/processed/climate/incidents_hourly.parquet')
    args = p.parse_args()
    scores = read_table(args.scores)
    out = detect_incidents(scores, load_incident_config(args.config))
    write_table(out, args.output)
    print(f'rows={len(out)} output={Path(args.output).resolve()}')

if __name__ == '__main__':
    main()
