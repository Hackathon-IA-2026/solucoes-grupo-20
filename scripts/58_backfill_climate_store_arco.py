#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from predicta_climate.arco import CORE_GROUPS
from predicta_climate.router import run_arco_historical


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Materializa ERA5-Land ARCO para as células Predicta. "
            "Retomada real ocorre por lote de células."
        )
    )
    p.add_argument("--subsystem", choices=["n", "ne", "seco", "s", "all"], default="all")
    p.add_argument("--start-year", type=int, default=2016)
    p.add_argument("--end-year", type=int, default=2025)
    p.add_argument("--groups", nargs="+", choices=list(CORE_GROUPS), default=list(CORE_GROUPS))
    p.add_argument("--points-dir", type=Path, default=ROOT / "data/processed/grid")
    p.add_argument("--output-root", type=Path, default=ROOT / "data/climate_store")
    p.add_argument("--point-batch-size", type=int, default=32)
    p.add_argument("--max-retries", type=int, default=3)
    p.add_argument("--force", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.end_year < args.start_year:
        raise SystemExit("--end-year deve ser >= --start-year")
    selected = [args.subsystem.upper()] if args.subsystem != "all" else ["N", "NE", "SECO", "S"]
    run_arco_historical(
        points_dir=args.points_dir,
        output_root=args.output_root,
        subsystems=selected,
        start_year=args.start_year,
        end_year=args.end_year,
        groups=args.groups,
        point_batch_size=args.point_batch_size,
        max_retries=args.max_retries,
        force=args.force,
    )


if __name__ == "__main__":
    main()
