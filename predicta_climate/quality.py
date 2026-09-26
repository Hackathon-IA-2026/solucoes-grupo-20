from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .arco import expected_hours_for_year


CORE_COLUMNS = (
    "temperature_2m_c",
    "dewpoint_2m_c",
    "precipitation_mm",
    "wind_u_10m_ms",
    "wind_v_10m_ms",
    "wind_speed_10m_ms",
    "solar_radiation_j_m2",
    "solar_radiation_w_m2_avg",
)


def validate_year_file(
    path: Path,
    year: int,
    expected_cells: int | None = None,
    required_columns: list[str] | tuple[str, ...] | None = None,
) -> dict:
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(path)
    row_count = pf.metadata.num_rows
    schema_names = set(pf.schema_arrow.names)

    needed = ["time_utc", "cell_id", "subsystem", "latitude", "longitude"]
    missing_base_columns = [c for c in needed if c not in schema_names]
    missing_required_columns = [
        c for c in (required_columns or []) if c not in schema_names
    ]
    if missing_base_columns or missing_required_columns:
        reasons = []
        if missing_base_columns:
            reasons.append(f"missing base columns: {missing_base_columns}")
        if missing_required_columns:
            reasons.append(f"missing required climate columns: {missing_required_columns}")
        return {
            "status": "invalid",
            "reason": "; ".join(reasons),
            "reasons": reasons,
            "path": str(path),
            "year": year,
        }

    base = pd.read_parquet(path, columns=["time_utc", "cell_id"])
    base["time_utc"] = pd.to_datetime(base["time_utc"], utc=True)
    unique_cells = int(base["cell_id"].nunique())
    expected_hours = expected_hours_for_year(year)
    expected_rows = unique_cells * expected_hours

    per_cell = base.groupby("cell_id")["time_utc"].agg(["count", "nunique", "min", "max"])
    incomplete_cells = per_cell.loc[
        (per_cell["count"] != expected_hours) | (per_cell["nunique"] != expected_hours)
    ]
    duplicate_rows = int(base.duplicated(["cell_id", "time_utc"]).sum())

    null_counts = {}
    numeric_columns = [c for c in CORE_COLUMNS if c in schema_names]
    if numeric_columns:
        numeric = pd.read_parquet(path, columns=numeric_columns)
        null_counts = {c: int(v) for c, v in numeric.isna().sum().items()}

    negative_counts = {}
    for c in ("precipitation_mm", "solar_radiation_j_m2"):
        if c in schema_names:
            series = pd.read_parquet(path, columns=[c])[c]
            negative_counts[c] = int((series < -1e-6).sum())

    status = "complete"
    reasons = []
    if row_count != expected_rows:
        status = "incomplete"
        reasons.append(f"rows={row_count}, expected={expected_rows}")
    if expected_cells is not None and unique_cells != expected_cells:
        status = "incomplete"
        reasons.append(f"cells={unique_cells}, expected_cells={expected_cells}")
    if len(incomplete_cells):
        status = "incomplete"
        reasons.append(f"incomplete_cells={len(incomplete_cells)}")
    if duplicate_rows:
        status = "incomplete"
        reasons.append(f"duplicate_rows={duplicate_rows}")
    if any(v > 0 for v in null_counts.values()):
        status = "incomplete"
        reasons.append("nulls_in_climate_variables")

    return {
        "status": status,
        "year": year,
        "path": str(path),
        "rows": int(row_count),
        "expected_rows": int(expected_rows),
        "cells": unique_cells,
        "expected_cells": expected_cells,
        "hours_per_cell_expected": expected_hours,
        "duplicate_rows": duplicate_rows,
        "incomplete_cells": int(len(incomplete_cells)),
        "null_counts": null_counts,
        "negative_counts_warning": negative_counts,
        "time_min": str(base["time_utc"].min()),
        "time_max": str(base["time_utc"].max()),
        "reasons": reasons,
    }


def write_quality_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
