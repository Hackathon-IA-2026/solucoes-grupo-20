from __future__ import annotations

from pathlib import Path

import pandas as pd


def build_daily_from_hourly(hourly_path: Path, daily_path: Path) -> pd.DataFrame:
    df = pd.read_parquet(hourly_path)
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df["date_utc"] = df["time_utc"].dt.date

    aggregations = {}
    if "temperature_2m_c" in df:
        aggregations.update(
            temperature_2m_min_c=("temperature_2m_c", "min"),
            temperature_2m_max_c=("temperature_2m_c", "max"),
            temperature_2m_mean_c=("temperature_2m_c", "mean"),
        )
    if "precipitation_mm" in df:
        aggregations["precipitation_sum_mm"] = ("precipitation_mm", "sum")
    if "wind_speed_10m_ms" in df:
        aggregations.update(
            wind_speed_10m_max_ms=("wind_speed_10m_ms", "max"),
            wind_speed_10m_mean_ms=("wind_speed_10m_ms", "mean"),
        )
    if "solar_radiation_j_m2" in df:
        aggregations["solar_radiation_sum_j_m2"] = ("solar_radiation_j_m2", "sum")

    daily = (
        df.groupby(
            ["cell_id", "subsystem", "latitude", "longitude", "date_utc"],
            as_index=False,
        )
        .agg(**aggregations)
        .sort_values(["cell_id", "date_utc"])
    )
    if "solar_radiation_sum_j_m2" in daily:
        daily["solar_radiation_sum_kwh_m2"] = daily["solar_radiation_sum_j_m2"] / 3_600_000.0

    daily_path.parent.mkdir(parents=True, exist_ok=True)
    daily.to_parquet(daily_path, index=False, compression="zstd")
    return daily
