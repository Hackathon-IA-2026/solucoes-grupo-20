#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from predicta_climate.points import build_points_from_generation_join, write_subsystem_point_files


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build canonical ERA5-Land 0.1° climate points from ONS×SIGA assets.")
    p.add_argument(
        "--source",
        type=Path,
        default=ROOT / "data/source/predicta_geracao_siga_join.json",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/processed/grid",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    points = build_points_from_generation_join(args.source)
    written = write_subsystem_point_files(points, args.output_dir)
    print(f"Total de células (subsistema-célula): {len(points)}")
    for subsystem, path in written.items():
        n = int((points["subsystem"] == subsystem).sum())
        print(f"{subsystem}: {n} células -> {path}")


if __name__ == "__main__":
    main()
