#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from predicta_climate.points import SUBSYSTEM_FILE_NAMES, load_points_file
from predicta_climate.quality import validate_year_file, write_quality_report


def main() -> None:
    p = argparse.ArgumentParser(description="Valida completude anual do Climate Store ARCO.")
    p.add_argument("--subsystem", choices=["n", "ne", "seco", "s", "all"], default="all")
    p.add_argument("--start-year", type=int, default=2016)
    p.add_argument("--end-year", type=int, default=2025)
    p.add_argument("--points-dir", type=Path, default=ROOT / "data/processed/grid")
    p.add_argument("--store-root", type=Path, default=ROOT / "data/climate_store")
    args = p.parse_args()

    selected = [args.subsystem.upper()] if args.subsystem != "all" else ["N", "NE", "SECO", "S"]
    summary = []
    for subsystem in selected:
        points_path = args.points_dir / SUBSYSTEM_FILE_NAMES[subsystem]
        expected_cells = len(load_points_file(points_path, subsystem=subsystem))
        for year in range(args.start_year, args.end_year + 1):
            path = args.store_root / subsystem.lower() / "hourly" / f"{year}.parquet"
            if not path.exists():
                report = {"status": "missing", "subsystem": subsystem, "year": year, "path": str(path)}
            else:
                report = validate_year_file(path, year, expected_cells=expected_cells)
                report["subsystem"] = subsystem
                write_quality_report(report, path.with_suffix(".quality.json"))
            summary.append(report)
            print(f"{subsystem} {year}: {report['status']}")

    out = ROOT / "outputs/reports/climate_store_validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Relatório: {out}")


if __name__ == "__main__":
    main()
