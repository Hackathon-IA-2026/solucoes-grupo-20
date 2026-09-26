from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd

from motor_sin.grid.index import coordinate_to_index
from motor_sin.climate.parser import OUTPUT_COLUMNS


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic normalized climate data for Phase 3 smoke tests.")
    parser.add_argument("--output-root", default="data/processed/climate/climate_hourly")
    parser.add_argument("--run-id", default="baseline-fixture")
    parser.add_argument("--start-year", type=int, default=2016)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--lat", type=float, default=-22.90)
    parser.add_argument("--lon", type=float, default=-43.20)
    args = parser.parse_args()

    if args.end_year < args.start_year:
        raise SystemExit("end-year must be >= start-year")
    cell_id = coordinate_to_index(args.lat, args.lon).cell_id
    run_root = Path(args.output_root) / f"run_id={args.run_id}"
    rows_total = 0

    for year in range(args.start_year, args.end_year + 1):
        for month in range(1, 13):
            start = pd.Timestamp(year=year, month=month, day=1, tz="UTC")
            end = start + pd.offsets.MonthBegin(1)
            times = pd.date_range(start, end, freq="1h", inclusive="left")
            doy = times.dayofyear.to_numpy(dtype=float)
            hour = times.hour.to_numpy(dtype=float)
            seasonal = np.sin(2.0 * math.pi * (doy - 30.0) / 365.25)
            diurnal = np.sin(2.0 * math.pi * (hour - 8.0) / 24.0)
            trend = (year - args.start_year) * 0.03
            temperature = 24.0 + 5.0 * seasonal + 2.0 * diurnal + trend
            dewpoint = temperature - 4.0 - 0.5 * np.cos(2.0 * math.pi * hour / 24.0)
            precipitation = np.maximum(0.0, 1.5 * np.sin(2.0 * math.pi * (doy + hour / 24.0) / 17.0))
            wind = 3.5 + 1.2 * np.cos(2.0 * math.pi * (hour - 14.0) / 24.0)
            solar = np.maximum(0.0, 850.0 * np.sin(math.pi * (hour - 6.0) / 12.0))

            df = pd.DataFrame(
                {
                    "interval_start_utc": times,
                    "cell_id": cell_id,
                    "temperature_2m": temperature,
                    "dewpoint_2m": dewpoint,
                    "precipitation": precipitation,
                    "wind_speed_10m": wind,
                    "solar_radiation": solar,
                    "source": "synthetic_phase3_smoke",
                    "source_service": "synthetic",
                    "source_model": "synthetic",
                    "source_grid_latitude": float(args.lat),
                    "source_grid_longitude": float(args.lon),
                    "source_elevation": np.nan,
                    "raw_record_id": None,
                    "raw_payload_hash": None,
                    "raw_file": "synthetic://phase3-smoke",
                },
                columns=OUTPUT_COLUMNS,
            )
            partition = run_root / f"year={year:04d}" / f"month={month:02d}"
            partition.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()[:16]
            path = partition / f"part-{digest}.parquet"
            df.to_parquet(path, index=False)
            rows_total += len(df)

    print(f"rows={rows_total} cell_id={cell_id} output={run_root}")
    print("NOTE: synthetic data are only for pipeline validation; do not use them as scientific evidence.")


if __name__ == "__main__":
    main()
