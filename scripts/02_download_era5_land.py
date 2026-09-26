from __future__ import annotations

import argparse
import json

from motor_sin.climate.openmeteo import download_and_persist


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Small-scope ERA5-Land hourly download through the Open-Meteo historical endpoint."
    )
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--raw-dir", default="data/raw/climate/openmeteo")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    result = download_and_persist(
        latitude=args.lat,
        longitude=args.lon,
        start_date=args.start_date,
        end_date=args.end_date,
        raw_directory=args.raw_dir,
        timeout_seconds=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
