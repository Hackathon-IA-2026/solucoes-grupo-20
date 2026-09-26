from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from motor_sin.grid.index import build_grid_dataframe, load_geojson_geometry


DEFAULT_MASK = ROOT / "assets" / "geospatial" / "brazil_naturalearth_lowres.geojson"

# Natural Earth bounding box rounded outwards to the 0.1-degree grid.
DEFAULT_BBOX = (-33.8, 5.3, -74.0, -34.7)  # lat_min, lat_max, lon_min, lon_max


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Predicta canonical 0.1-degree grid")
    parser.add_argument("--lat-min", type=float, default=DEFAULT_BBOX[0])
    parser.add_argument("--lat-max", type=float, default=DEFAULT_BBOX[1])
    parser.add_argument("--lon-min", type=float, default=DEFAULT_BBOX[2])
    parser.add_argument("--lon-max", type=float, default=DEFAULT_BBOX[3])
    parser.add_argument("--mask", default=str(DEFAULT_MASK))
    parser.add_argument("--brazil-only", action="store_true")
    parser.add_argument("--format", choices=["parquet", "csv"], default="parquet")
    parser.add_argument("--output", default="data/processed/grid/brazil_grid_01deg.parquet")
    args = parser.parse_args()

    mask = load_geojson_geometry(args.mask) if args.mask else None
    df = build_grid_dataframe(
        lat_min=args.lat_min,
        lat_max=args.lat_max,
        lon_min=args.lon_min,
        lon_max=args.lon_max,
        mask_geometry=mask,
        brazil_only=args.brazil_only,
    )

    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)

    if args.format == "csv":
        df.to_csv(output, index=False)
    else:
        try:
            df.to_parquet(output, index=False)
        except ImportError as exc:
            raise RuntimeError(
                "Parquet requires pyarrow. Install with `pip install -e \".[dev]\"` "
                "or rerun with --format csv."
            ) from exc

    print(f"rows={len(df)} output={output}")
    if not df.empty:
        print(f"cell_id_min={df['cell_id'].min()} cell_id_max={df['cell_id'].max()}")


if __name__ == "__main__":
    main()
