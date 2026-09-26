from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd


SUBSYSTEM_FILE_NAMES = {
    "N": "climate_points_n_01deg.csv",
    "NE": "climate_points_ne_01deg.csv",
    "SECO": "climate_points_seco_01deg.csv",
    "S": "climate_points_s_01deg.csv",
}


def round_to_era5_land_grid(value: float) -> float:
    return round(float(value), 1)


def make_cell_id(latitude: float, longitude: float) -> str:
    # Integer indices avoid using floating-point text as the primary identity.
    lat_idx = int(round((round_to_era5_land_grid(latitude) + 90.0) * 10))
    lon_idx = int(round((round_to_era5_land_grid(longitude) + 180.0) * 10))
    return f"g{lat_idx:04d}_{lon_idx:04d}"


def build_points_from_generation_join(source_json: Path) -> pd.DataFrame:
    payload = json.loads(source_json.read_text(encoding="utf-8"))
    rows: list[dict] = []

    layer_specs = (
        ("usinas", "A"),
        ("conjuntos_nomeados", "B"),
        ("agregados_por_estado", "D"),
    )
    for layer_name, location_quality in layer_specs:
        for record in payload.get(layer_name, []):
            lat = record.get("latitude")
            lon = record.get("longitude")
            subsystem = record.get("subsistema")
            if lat is None or lon is None or not subsystem:
                continue
            lat_grid = round_to_era5_land_grid(float(lat))
            lon_grid = round_to_era5_land_grid(float(lon))
            capacity = record.get("capacidade_instalada_mw")
            rows.append(
                {
                    "cell_id": make_cell_id(lat_grid, lon_grid),
                    "subsystem": str(subsystem).upper(),
                    "latitude": lat_grid,
                    "longitude": lon_grid,
                    "capacity_mw_known": float(capacity) if capacity is not None else 0.0,
                    "asset_count": 1,
                    "source_layer": layer_name,
                    "location_quality": location_quality,
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("Nenhum ponto georreferenciado encontrado no JSON ONS×SIGA.")

    # Aggregate assets that map to the same canonical 0.1° cell.
    grouped = (
        df.groupby(["cell_id", "subsystem", "latitude", "longitude"], as_index=False)
        .agg(
            capacity_mw_known=("capacity_mw_known", "sum"),
            asset_count=("asset_count", "sum"),
            source_layers=("source_layer", lambda s: ",".join(sorted(set(s)))),
            location_qualities=("location_quality", lambda s: ",".join(sorted(set(s)))),
        )
        .sort_values(["subsystem", "cell_id"])
        .reset_index(drop=True)
    )
    return grouped


def write_subsystem_point_files(points: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for subsystem, filename in SUBSYSTEM_FILE_NAMES.items():
        subset = points.loc[points["subsystem"] == subsystem].copy()
        path = output_dir / filename
        subset.to_csv(path, index=False)
        written[subsystem] = path
    return written


def load_points_file(path: Path, subsystem: str | None = None) -> pd.DataFrame:
    df = pd.read_csv(path)
    rename = {}
    for target, candidates in {
        "latitude": ("latitude", "lat", "lat_center", "grid_lat"),
        "longitude": ("longitude", "lon", "lng", "lon_center", "grid_lon"),
        "cell_id": ("cell_id", "grid_cell_id"),
        "subsystem": ("subsystem", "subsistema", "subsystem_id"),
    }.items():
        for candidate in candidates:
            if candidate in df.columns:
                rename[candidate] = target
                break
    df = df.rename(columns=rename)

    for required in ("latitude", "longitude"):
        if required not in df.columns:
            raise ValueError(f"{path}: coluna de {required} não encontrada.")

    if "cell_id" not in df.columns:
        df["cell_id"] = [make_cell_id(a, b) for a, b in zip(df["latitude"], df["longitude"])]
    if "subsystem" not in df.columns:
        if not subsystem:
            raise ValueError(f"{path}: subsystem ausente e não informado pela CLI.")
        df["subsystem"] = subsystem.upper()

    df["subsystem"] = df["subsystem"].astype(str).str.upper()
    df["latitude"] = df["latitude"].astype(float).map(round_to_era5_land_grid)
    df["longitude"] = df["longitude"].astype(float).map(round_to_era5_land_grid)
    df = df.drop_duplicates(subset=["cell_id"]).sort_values("cell_id").reset_index(drop=True)
    return df
