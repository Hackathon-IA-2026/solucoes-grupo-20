#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from predicta_climate.daily import build_daily_from_hourly


def main() -> None:
    p = argparse.ArgumentParser(description="Deriva Climate Store diário a partir do hourly ARCO.")
    p.add_argument("--subsystem", choices=["n", "ne", "seco", "s", "all"], default="all")
    p.add_argument("--start-year", type=int, default=2016)
    p.add_argument("--end-year", type=int, default=2025)
    p.add_argument("--store-root", type=Path, default=ROOT / "data/climate_store")
    args = p.parse_args()

    selected = [args.subsystem] if args.subsystem != "all" else ["n", "ne", "seco", "s"]
    for subsystem in selected:
        for year in range(args.start_year, args.end_year + 1):
            hourly = args.store_root / subsystem / "hourly" / f"{year}.parquet"
            if not hourly.exists():
                print(f"SKIP ausente: {hourly}")
                continue
            daily = args.store_root / subsystem / "daily" / f"{year}.parquet"
            frame = build_daily_from_hourly(hourly, daily)
            print(f"{subsystem.upper()} {year}: {len(frame)} registros diários -> {daily}")


if __name__ == "__main__":
    main()
