from __future__ import annotations

import json
from pathlib import Path

from motor_sin.grid.index import (
    build_grid_dataframe,
    coordinate_to_index,
    index_to_bounds,
    load_geojson_geometry,
)


ROOT = Path(__file__).resolve().parents[2]
MASK = ROOT / "assets" / "geospatial" / "brazil_naturalearth_lowres.geojson"


def test_same_coordinate_same_cell() -> None:
    a = coordinate_to_index(-22.9068, -43.1729)
    b = coordinate_to_index(-22.9068, -43.1729)
    assert a == b
    assert a.cell_id == b.cell_id


def test_cell_boundary_is_deterministic() -> None:
    # Exact 0.1-degree boundary belongs to the cell beginning at that boundary.
    idx = coordinate_to_index(-22.9, -43.2)
    lat_min, lat_max, lon_min, lon_max = index_to_bounds(idx)
    assert round(lat_min, 10) == -22.9
    assert round(lon_min, 10) == -43.2
    assert round(lat_max - lat_min, 10) == 0.1
    assert round(lon_max - lon_min, 10) == 0.1


def test_small_brazil_mask_grid_has_unique_cells() -> None:
    geom = load_geojson_geometry(MASK)
    df = build_grid_dataframe(
        lat_min=-23.1,
        lat_max=-22.8,
        lon_min=-43.4,
        lon_max=-43.0,
        mask_geometry=geom,
        brazil_only=False,
    )
    assert len(df) == 12
    assert df["cell_id"].is_unique
    assert df["inside_brazil"].isin([True, False]).all()
