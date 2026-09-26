from __future__ import annotations

import json
import math
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


GRID_STEP = 0.1
LAT_ORIGIN = -90.0
LON_ORIGIN = -180.0
CELL_PREFIX = "g01"


@dataclass(frozen=True)
class CellIndex:
    lat_index: int
    lon_index: int

    @property
    def cell_id(self) -> str:
        return f"{CELL_PREFIX}_{self.lat_index:04d}_{self.lon_index:04d}"


def _decimal_index(value: float, origin: float, step: float, *, upper_exclusive: bool = False) -> int:
    ratio = (Decimal(str(value)) - Decimal(str(origin))) / Decimal(str(step))
    if upper_exclusive:
        return int(ratio.to_integral_value(rounding=ROUND_CEILING)) - 1
    return int(ratio.to_integral_value(rounding=ROUND_FLOOR))


def coordinate_to_index(lat: float, lon: float, step: float = GRID_STEP) -> CellIndex:
    if not (-90.0 <= lat < 90.0):
        raise ValueError("latitude must satisfy -90 <= lat < 90")
    if not (-180.0 <= lon < 180.0):
        raise ValueError("longitude must satisfy -180 <= lon < 180")
    lat_index = _decimal_index(lat, LAT_ORIGIN, step)
    lon_index = _decimal_index(lon, LON_ORIGIN, step)
    return CellIndex(lat_index=lat_index, lon_index=lon_index)


def index_to_bounds(index: CellIndex, step: float = GRID_STEP) -> tuple[float, float, float, float]:
    lat_min = LAT_ORIGIN + index.lat_index * step
    lon_min = LON_ORIGIN + index.lon_index * step
    return lat_min, lat_min + step, lon_min, lon_min + step


def index_to_center(index: CellIndex, step: float = GRID_STEP) -> tuple[float, float]:
    lat_min, lat_max, lon_min, lon_max = index_to_bounds(index, step)
    return (lat_min + lat_max) / 2.0, (lon_min + lon_max) / 2.0


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    # Ray casting. GeoJSON coordinates are [lon, lat].
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        intersects = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-30) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _point_in_polygon(lon: float, lat: float, polygon: list[list[list[float]]]) -> bool:
    if not polygon or not _point_in_ring(lon, lat, polygon[0]):
        return False
    # holes
    for hole in polygon[1:]:
        if _point_in_ring(lon, lat, hole):
            return False
    return True


def point_in_geojson_geometry(lon: float, lat: float, geometry: dict) -> bool:
    kind = geometry.get("type")
    coords = geometry.get("coordinates")
    if kind == "Polygon":
        return _point_in_polygon(lon, lat, coords)
    if kind == "MultiPolygon":
        return any(_point_in_polygon(lon, lat, polygon) for polygon in coords)
    raise ValueError(f"unsupported geometry type: {kind!r}")


def load_geojson_geometry(path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("type") == "FeatureCollection":
        features = payload.get("features", [])
        if len(features) != 1:
            raise ValueError("mask FeatureCollection must contain exactly one feature")
        return features[0]["geometry"]
    if payload.get("type") == "Feature":
        return payload["geometry"]
    return payload


def build_grid_dataframe(
    *,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    step: float = GRID_STEP,
    mask_geometry: dict | None = None,
    brazil_only: bool = False,
) -> pd.DataFrame:
    if not (lat_min < lat_max and lon_min < lon_max):
        raise ValueError("invalid bounding box")

    bounded_lat_min = max(lat_min, -90.0)
    bounded_lon_min = max(lon_min, -180.0)
    bounded_lat_max = min(lat_max, 90.0)
    bounded_lon_max = min(lon_max, 180.0)
    first = CellIndex(
        _decimal_index(bounded_lat_min, LAT_ORIGIN, step),
        _decimal_index(bounded_lon_min, LON_ORIGIN, step),
    )
    last = CellIndex(
        _decimal_index(bounded_lat_max, LAT_ORIGIN, step, upper_exclusive=True),
        _decimal_index(bounded_lon_max, LON_ORIGIN, step, upper_exclusive=True),
    )

    records: list[dict] = []
    for lat_index in range(first.lat_index, last.lat_index + 1):
        for lon_index in range(first.lon_index, last.lon_index + 1):
            idx = CellIndex(lat_index, lon_index)
            b_lat_min, b_lat_max, b_lon_min, b_lon_max = index_to_bounds(idx, step)
            lat_center, lon_center = index_to_center(idx, step)
            inside = (
                point_in_geojson_geometry(lon_center, lat_center, mask_geometry)
                if mask_geometry is not None
                else None
            )
            if brazil_only and inside is not True:
                continue
            records.append(
                {
                    "cell_id": idx.cell_id,
                    "lat_min": round(b_lat_min, 10),
                    "lat_max": round(b_lat_max, 10),
                    "lon_min": round(b_lon_min, 10),
                    "lon_max": round(b_lon_max, 10),
                    "lat_center": round(lat_center, 10),
                    "lon_center": round(lon_center, 10),
                    "inside_brazil": inside,
                    "crs": "EPSG:4326",
                    "resolution_deg": step,
                }
            )

    df = pd.DataFrame.from_records(records)
    if not df.empty and df["cell_id"].duplicated().any():
        raise RuntimeError("duplicate cell_id generated")
    return df
