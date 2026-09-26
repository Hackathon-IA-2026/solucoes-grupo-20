#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import sys


def main() -> None:
    p = argparse.ArgumentParser(description='Run the held-out E1 vs E2 real-data pilot with raw target-hour climate.')
    p.add_argument('--load', default='data/processed/demand/load_hourly.parquet')
    p.add_argument('--climate', default='data/processed/climate/zone_climate_hourly.parquet')
    p.add_argument('--subsystem', default='SE/CO')
    p.add_argument('--test-hours', type=int, default=720)
    p.add_argument('--forecast-horizon', type=int, default=24)
    p.add_argument('--origin-step-hours', type=int, default=24)
    p.add_argument('--calendar-timezone', default='America/Sao_Paulo')
    p.add_argument('--calibration-hours', type=int, default=720)
    args = p.parse_args()
    cmd = [
        sys.executable, 'scripts/29_run_real_pilot.py',
        '--load', args.load,
        '--climate', args.climate,
        '--subsystem', args.subsystem,
        '--weather-mode', 'PERFECT_WEATHER_BACKTEST',
        '--test-hours', str(args.test_hours),
        '--forecast-horizon', str(args.forecast_horizon),
        '--origin-step-hours', str(args.origin_step_hours),
        '--calendar-timezone', args.calendar_timezone,
        '--calibration-hours', str(args.calibration_hours),
    ]
    raise SystemExit(subprocess.call(cmd, cwd=Path(__file__).resolve().parents[1]))


if __name__ == '__main__':
    main()
