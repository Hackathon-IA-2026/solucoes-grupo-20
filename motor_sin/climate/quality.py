from __future__ import annotations

from typing import Any
import pandas as pd

from motor_sin.climate.variables import CANONICAL_VARIABLES


def build_climate_quality_report(
    df: pd.DataFrame,
    *,
    run_id: str,
    source_files: list[str],
    rows_read: int | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    warnings = list(warnings or [])
    errors = list(errors or [])
    if df.empty:
        data_start = None
        data_end = None
        duplicates = 0
        missing_timestamps = 0
    else:
        data_start = df["interval_start_utc"].min().isoformat()
        data_end = df["interval_start_utc"].max().isoformat()
        duplicates = int(df.duplicated(["interval_start_utc", "cell_id"]).sum())
        missing_timestamps = int(df["interval_start_utc"].isna().sum())

    missing_values = {
        name: int(df[name].isna().sum()) if name in df.columns else int(len(df))
        for name in CANONICAL_VARIABLES
    }
    unknown_models = []
    if "source_model" in df.columns:
        unknown_models = sorted(
            str(x) for x in df["source_model"].dropna().unique() if str(x) not in {"era5_land", "era5_seamless", "era5"}
        )
        if unknown_models:
            warnings.append(f"unexpected source models: {unknown_models}")

    return {
        "run_id": run_id,
        "source": "open-meteo/era5_land",
        "source_files": source_files,
        "rows_read": int(rows_read if rows_read is not None else len(df)),
        "rows_output": int(len(df)),
        "missing_timestamps": missing_timestamps,
        "duplicate_timestamps": duplicates,
        "missing_values": missing_values,
        "unknown_categories": {"source_model": unknown_models},
        "geocoding_quality": "source_grid_coordinate",
        "data_start": data_start,
        "data_end": data_end,
        "freshness": {"status": "not_assessed", "reason": "historical_reanalysis_ingestion"},
        "warnings": warnings,
        "errors": errors,
    }
