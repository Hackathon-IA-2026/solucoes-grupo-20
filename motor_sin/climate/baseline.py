from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from motor_sin.climate.variables import CANONICAL_VARIABLES

BASELINE_OUTPUT_COLUMNS = [
    "baseline_version",
    "target_year",
    "baseline_year_start",
    "baseline_year_end",
    "cell_id",
    "variable",
    "hour_of_day_utc",
    "target_day_of_year",
    "season_day_366",
    "season_month_day",
    "seasonal_window_days",
    "median",
    "p01",
    "p05",
    "p10",
    "p25",
    "p75",
    "p90",
    "p95",
    "p99",
    "iqr",
    "sample_count",
    "expected_sample_count",
    "coverage_ratio",
]

TARGET_SCORE_COLUMNS = [
    "baseline_version",
    "target_year",
    "baseline_year_start",
    "baseline_year_end",
    "interval_start_utc",
    "cell_id",
    "variable",
    "value",
    "baseline_median",
    "baseline_iqr",
    "anomaly",
    "robust_z",
    "percentile",
    "baseline_sample_count",
    "expected_sample_count",
    "coverage_ratio",
]

QUANTILE_LEVELS = np.array([0.01, 0.05, 0.10, 0.25, 0.75, 0.90, 0.95, 0.99], dtype=float)
QUANTILE_NAMES = ("p01", "p05", "p10", "p25", "p75", "p90", "p95", "p99")


@dataclass(frozen=True)
class BaselineBuildResult:
    baseline: pd.DataFrame
    target_scores: pd.DataFrame
    metadata: dict


def baseline_years_for_target(target_year: int, complete_previous_years: int = 10) -> list[int]:
    if complete_previous_years <= 0:
        raise ValueError("complete_previous_years must be positive")
    return list(range(target_year - complete_previous_years, target_year))


def canonical_season_day(value: date | pd.Timestamp) -> int:
    """Map month/day to a stable 366-day seasonal calendar anchored on leap year 2000."""
    if isinstance(value, pd.Timestamp):
        month, day = int(value.month), int(value.day)
    else:
        month, day = value.month, value.day
    return date(2000, month, day).timetuple().tm_yday


def season_day_to_month_day(season_day: int) -> str:
    if not 1 <= int(season_day) <= 366:
        raise ValueError("season_day must be within [1, 366]")
    resolved = date(2000, 1, 1) + timedelta(days=int(season_day) - 1)
    return resolved.strftime("%m-%d")


def circular_season_distance(a: int, b: int, cycle: int = 366) -> int:
    direct = abs(int(a) - int(b))
    return min(direct, cycle - direct)


def _window_days(center: int, radius: int) -> list[int]:
    if radius < 0:
        raise ValueError("seasonal_window_days must be >= 0")
    return [((center - 1 + offset) % 366) + 1 for offset in range(-radius, radius + 1)]


def target_calendar(target_year: int) -> pd.DataFrame:
    start = date(target_year, 1, 1)
    end = date(target_year, 12, 31)
    rows: list[dict] = []
    current = start
    while current <= end:
        rows.append(
            {
                "target_date": current,
                "target_day_of_year": current.timetuple().tm_yday,
                "season_day_366": canonical_season_day(current),
                "season_month_day": current.strftime("%m-%d"),
            }
        )
        current += timedelta(days=1)
    return pd.DataFrame(rows)


def expected_window_counts(baseline_years: Sequence[int], seasonal_window_days: int) -> dict[int, int]:
    per_season_day = {day: 0 for day in range(1, 367)}
    for year in baseline_years:
        current = date(int(year), 1, 1)
        end = date(int(year), 12, 31)
        while current <= end:
            per_season_day[canonical_season_day(current)] += 1
            current += timedelta(days=1)

    expected: dict[int, int] = {}
    for center in range(1, 367):
        expected[center] = sum(per_season_day[day] for day in _window_days(center, seasonal_window_days))
    return expected


def _normalize_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    if "interval_start_utc" not in df.columns:
        raise ValueError("climate dataset missing interval_start_utc")
    result = df.copy()
    result["interval_start_utc"] = pd.to_datetime(result["interval_start_utc"], utc=True, errors="raise")
    if result["interval_start_utc"].isna().any():
        raise ValueError("climate dataset contains null timestamps")
    return result


def _validate_columns(df: pd.DataFrame, variables: Sequence[str]) -> None:
    required = {"interval_start_utc", "cell_id", *variables}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"climate dataset missing required columns: {missing}")
    unknown_variables = [name for name in variables if name not in CANONICAL_VARIABLES]
    if unknown_variables:
        raise ValueError(f"unknown canonical climate variables: {unknown_variables}")


def _validate_unique_cell_hour(df: pd.DataFrame) -> None:
    duplicate_mask = df.duplicated(["interval_start_utc", "cell_id"], keep=False)
    if duplicate_mask.any():
        sample = df.loc[duplicate_mask, ["interval_start_utc", "cell_id"]].head(10)
        raise ValueError(
            "duplicate cell/hour observations in selected climate data; select a single non-overlapping run or fix input. "
            f"sample={sample.to_dict(orient='records')}"
        )


def validate_baseline_year_coverage(
    df: pd.DataFrame,
    *,
    baseline_years: Sequence[int],
    cells: Sequence[str],
    require_all_years: bool,
) -> dict[str, list[int]]:
    years = df["interval_start_utc"].dt.year
    missing_by_cell: dict[str, list[int]] = {}
    expected = set(int(y) for y in baseline_years)
    for cell_id in cells:
        present = set(int(y) for y in years[df["cell_id"] == cell_id].unique())
        missing = sorted(expected - present)
        if missing:
            missing_by_cell[str(cell_id)] = missing
    if require_all_years and missing_by_cell:
        raise ValueError(f"baseline does not contain all required years for selected cells: {missing_by_cell}")
    return missing_by_cell


def _long_frame(df: pd.DataFrame, variables: Sequence[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["interval_start_utc", "cell_id", "variable", "value", "year", "hour_of_day_utc", "season_day_366"])
    long_df = df[["interval_start_utc", "cell_id", *variables]].melt(
        id_vars=["interval_start_utc", "cell_id"],
        value_vars=list(variables),
        var_name="variable",
        value_name="value",
    )
    long_df = long_df.dropna(subset=["value"]).copy()
    long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce")
    long_df = long_df.dropna(subset=["value"])
    long_df["year"] = long_df["interval_start_utc"].dt.year.astype(int)
    long_df["hour_of_day_utc"] = long_df["interval_start_utc"].dt.hour.astype(int)
    # Vectorized mapping keeps Mar-Dec aligned between leap and non-leap years.
    month = long_df["interval_start_utc"].dt.month
    day = long_df["interval_start_utc"].dt.day
    non_leap_doy = long_df["interval_start_utc"].dt.dayofyear
    is_after_feb = month.gt(2)
    is_non_leap = ~long_df["interval_start_utc"].dt.is_leap_year
    season_day = non_leap_doy + (is_after_feb & is_non_leap).astype(int)
    # Feb 29 remains canonical day 60; Jan/Feb and leap-year dates already align.
    long_df["season_day_366"] = season_day.astype(int)
    return long_df


def _sample_buckets(group: pd.DataFrame) -> dict[int, np.ndarray]:
    buckets: dict[int, np.ndarray] = {}
    for season_day, day_group in group.groupby("season_day_366", sort=False):
        buckets[int(season_day)] = day_group["value"].to_numpy(dtype=float)
    return buckets


def _samples_for_center(buckets: dict[int, np.ndarray], center: int, radius: int) -> np.ndarray:
    arrays = [buckets[day] for day in _window_days(center, radius) if day in buckets and len(buckets[day])]
    if not arrays:
        return np.array([], dtype=float)
    return np.concatenate(arrays)


def _summary(samples: np.ndarray) -> dict[str, float | int | None]:
    finite = samples[np.isfinite(samples)]
    if finite.size == 0:
        return {
            "median": None,
            **{name: None for name in QUANTILE_NAMES},
            "iqr": None,
            "sample_count": 0,
        }
    quantiles = np.quantile(finite, QUANTILE_LEVELS, method="linear")
    values = dict(zip(QUANTILE_NAMES, (float(x) for x in quantiles), strict=True))
    return {
        "median": float(np.median(finite)),
        **values,
        "iqr": float(values["p75"] - values["p25"]),
        "sample_count": int(finite.size),
    }


def empirical_percentile(samples: np.ndarray, value: float) -> float | None:
    finite = samples[np.isfinite(samples)]
    if finite.size == 0 or not np.isfinite(value):
        return None
    # Weak empirical CDF: fraction of baseline observations <= current value.
    return float(np.count_nonzero(finite <= value) / finite.size)


def robust_z_score(value: float, median: float | None, iqr: float | None, *, epsilon: float = 1e-6) -> float | None:
    if median is None or iqr is None or not np.isfinite(value):
        return None
    denominator = max(float(iqr) / 1.349, float(epsilon))
    return float((float(value) - float(median)) / denominator)


def build_climate_baseline(
    df: pd.DataFrame,
    *,
    target_year: int,
    variables: Sequence[str] | None = None,
    complete_previous_years: int = 10,
    seasonal_window_days: int = 15,
    baseline_version: str = "1.0",
    require_all_baseline_years: bool = True,
    cell_ids: Sequence[str] | None = None,
    max_cells: int | None = 25,
    robust_epsilon: float = 1e-6,
) -> BaselineBuildResult:
    variables = tuple(variables or CANONICAL_VARIABLES)
    if not variables:
        raise ValueError("at least one climate variable must be selected")
    data = _normalize_timestamps(df)
    _validate_columns(data, variables)

    if cell_ids:
        selected = {str(x) for x in cell_ids}
        data = data[data["cell_id"].astype(str).isin(selected)].copy()
        missing_cells = sorted(selected - set(data["cell_id"].astype(str).unique()))
        if missing_cells:
            raise ValueError(f"requested cell_ids not found in input: {missing_cells}")

    if data.empty:
        raise ValueError("no climate observations remain after filters")

    _validate_unique_cell_hour(data)
    cells = sorted(str(x) for x in data["cell_id"].astype(str).unique())
    if max_cells is not None and max_cells > 0 and len(cells) > max_cells:
        raise ValueError(
            f"Phase 3 small-scope guard: selected {len(cells)} cells, limit is {max_cells}. "
            "Filter --cell-id or explicitly raise/disable --max-cells after validating the pipeline."
        )

    baseline_years = baseline_years_for_target(target_year, complete_previous_years)
    baseline_start, baseline_end = baseline_years[0], baseline_years[-1]
    years = data["interval_start_utc"].dt.year
    history = data[years.isin(baseline_years)].copy()
    target = data[years.eq(int(target_year))].copy()

    if history.empty:
        raise ValueError(f"no observations found for baseline years {baseline_start}-{baseline_end}")

    missing_by_cell = validate_baseline_year_coverage(
        history,
        baseline_years=baseline_years,
        cells=cells,
        require_all_years=require_all_baseline_years,
    )

    history_long = _long_frame(history, variables)
    target_long = _long_frame(target, variables)
    calendar = target_calendar(target_year)
    expected_counts = expected_window_counts(baseline_years, seasonal_window_days)

    baseline_records: list[dict] = []
    score_records: list[dict] = []

    target_grouped: dict[tuple[str, str, int], pd.DataFrame] = {}
    if not target_long.empty:
        for key, group in target_long.groupby(["cell_id", "variable", "hour_of_day_utc"], sort=False):
            target_grouped[(str(key[0]), str(key[1]), int(key[2]))] = group

    for (cell_id, variable, hour), group in history_long.groupby(
        ["cell_id", "variable", "hour_of_day_utc"], sort=True
    ):
        cell_id = str(cell_id)
        variable = str(variable)
        hour = int(hour)
        buckets = _sample_buckets(group)

        summary_by_season: dict[int, tuple[dict, np.ndarray]] = {}
        for cal_row in calendar.itertuples(index=False):
            season_day = int(cal_row.season_day_366)
            samples = _samples_for_center(buckets, season_day, seasonal_window_days)
            summary = _summary(samples)
            expected = int(expected_counts[season_day])
            sample_count = int(summary["sample_count"])
            coverage = float(sample_count / expected) if expected > 0 else 0.0
            baseline_records.append(
                {
                    "baseline_version": baseline_version,
                    "target_year": int(target_year),
                    "baseline_year_start": int(baseline_start),
                    "baseline_year_end": int(baseline_end),
                    "cell_id": cell_id,
                    "variable": variable,
                    "hour_of_day_utc": hour,
                    "target_day_of_year": int(cal_row.target_day_of_year),
                    "season_day_366": season_day,
                    "season_month_day": str(cal_row.season_month_day),
                    "seasonal_window_days": int(seasonal_window_days),
                    **summary,
                    "expected_sample_count": expected,
                    "coverage_ratio": coverage,
                }
            )
            summary_by_season[season_day] = (summary, samples)

        target_group = target_grouped.get((cell_id, variable, hour))
        if target_group is None:
            continue
        for row in target_group.itertuples(index=False):
            season_day = int(row.season_day_366)
            summary, samples = summary_by_season[season_day]
            expected = int(expected_counts[season_day])
            sample_count = int(summary["sample_count"])
            coverage = float(sample_count / expected) if expected > 0 else 0.0
            value = float(row.value)
            median = summary["median"]
            iqr = summary["iqr"]
            anomaly = float(value - median) if median is not None else None
            score_records.append(
                {
                    "baseline_version": baseline_version,
                    "target_year": int(target_year),
                    "baseline_year_start": int(baseline_start),
                    "baseline_year_end": int(baseline_end),
                    "interval_start_utc": row.interval_start_utc,
                    "cell_id": cell_id,
                    "variable": variable,
                    "value": value,
                    "baseline_median": median,
                    "baseline_iqr": iqr,
                    "anomaly": anomaly,
                    "robust_z": robust_z_score(value, median, iqr, epsilon=robust_epsilon),
                    "percentile": empirical_percentile(samples, value),
                    "baseline_sample_count": sample_count,
                    "expected_sample_count": expected,
                    "coverage_ratio": coverage,
                }
            )

    baseline_df = pd.DataFrame.from_records(baseline_records, columns=BASELINE_OUTPUT_COLUMNS)
    scores_df = pd.DataFrame.from_records(score_records, columns=TARGET_SCORE_COLUMNS)
    if not scores_df.empty:
        scores_df = scores_df.sort_values(["interval_start_utc", "cell_id", "variable"], kind="stable").reset_index(drop=True)
    if not baseline_df.empty:
        baseline_df = baseline_df.sort_values(
            ["cell_id", "variable", "hour_of_day_utc", "target_day_of_year"], kind="stable"
        ).reset_index(drop=True)

    metadata = {
        "target_year": int(target_year),
        "baseline_year_start": int(baseline_start),
        "baseline_year_end": int(baseline_end),
        "baseline_years_expected": baseline_years,
        "target_year_excluded_from_baseline": True,
        "variables": list(variables),
        "cells": cells,
        "missing_baseline_years_by_cell": missing_by_cell,
        "seasonal_window_days": int(seasonal_window_days),
        "season_calendar": "canonical_leap_366_month_day_aligned",
        "quantile_method": "numpy_linear",
        "percentile_method": "weak_empirical_cdf_leq",
        "robust_z_scale": "IQR/1.349",
        "robust_z_epsilon": float(robust_epsilon),
        "rows_history": int(len(history)),
        "rows_target": int(len(target)),
        "rows_baseline": int(len(baseline_df)),
        "rows_target_scores": int(len(scores_df)),
    }
    return BaselineBuildResult(baseline=baseline_df, target_scores=scores_df, metadata=metadata)


def discover_climate_parquets(
    input_root: str | Path,
    *,
    years: Sequence[int],
    run_ids: Sequence[str] | None = None,
) -> list[Path]:
    root = Path(input_root)
    if not root.exists():
        raise FileNotFoundError(root)
    files: list[Path] = []
    run_ids = list(run_ids or [])
    for year in years:
        if run_ids:
            for run_id in run_ids:
                files.extend(sorted((root / f"run_id={run_id}" / f"year={int(year):04d}").glob("**/*.parquet")))
        else:
            files.extend(sorted(root.glob(f"run_id=*/year={int(year):04d}/**/*.parquet")))
            files.extend(sorted((root / f"year={int(year):04d}").glob("**/*.parquet")))
    # Deduplicate paths while preserving deterministic order.
    return list(dict.fromkeys(files))


def read_climate_parquets(
    paths: Iterable[str | Path],
    *,
    columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    files = [Path(path) for path in paths]
    if not files:
        raise ValueError("no normalized climate parquet files found for requested years/runs")
    frames = [pd.read_parquet(path, columns=list(columns) if columns else None) for path in files]
    return pd.concat(frames, ignore_index=True)


def _safe_run_id(run_id: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in run_id)
    if not cleaned:
        raise ValueError("run_id must contain at least one safe character")
    return cleaned


def write_phase3_artifacts(
    result: BaselineBuildResult,
    *,
    baseline_output_root: str | Path,
    score_output_root: str | Path,
    report_path: str | Path,
    run_id: str,
    source_files: Sequence[str | Path],
    scientific_status: str = "operational_baseline_not_official_climatological_normal",
    coverage_warning_threshold: float = 0.80,
) -> dict:
    run_id_safe = _safe_run_id(run_id)
    target_year = int(result.metadata["target_year"])
    baseline_root = Path(baseline_output_root) / f"run_id={run_id_safe}" / f"target_year={target_year:04d}"
    score_root = Path(score_output_root) / f"run_id={run_id_safe}" / f"target_year={target_year:04d}"
    artifacts: list[str] = []
    score_artifacts: list[str] = []

    for variable, group in result.baseline.groupby("variable", sort=True):
        partition = baseline_root / f"variable={variable}"
        partition.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(pd.util.hash_pandas_object(group, index=False).values.tobytes()).hexdigest()[:16]
        path = partition / f"part-{digest}.parquet"
        group.to_parquet(path, index=False)
        artifacts.append(str(path))

    if not result.target_scores.empty:
        for variable, group in result.target_scores.groupby("variable", sort=True):
            partition = score_root / f"variable={variable}"
            partition.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256(pd.util.hash_pandas_object(group, index=False).values.tobytes()).hexdigest()[:16]
            path = partition / f"part-{digest}.parquet"
            group.to_parquet(path, index=False)
            score_artifacts.append(str(path))

    sample_counts = result.baseline["sample_count"] if not result.baseline.empty else pd.Series(dtype=float)
    coverage = result.baseline["coverage_ratio"] if not result.baseline.empty else pd.Series(dtype=float)
    warnings: list[str] = []
    low_coverage = int((coverage < float(coverage_warning_threshold)).sum()) if not coverage.empty else 0
    if low_coverage:
        warnings.append(
            f"{low_coverage} baseline groups have coverage_ratio < {coverage_warning_threshold:.2f}; inspect before incident detection"
        )
    if result.metadata.get("missing_baseline_years_by_cell"):
        warnings.append("some selected cells are missing one or more baseline years")
    if result.metadata.get("rows_target", 0) == 0:
        warnings.append("target year has no observations in input; baseline built but anomaly/percentile artifact is empty")

    report = {
        "phase": "phase3_climate_baseline",
        "status": "ok",
        "run_id": run_id_safe,
        "scientific_status": scientific_status,
        **result.metadata,
        "source_files": [str(p) for p in source_files],
        "coverage_warning_threshold": float(coverage_warning_threshold),
        "low_coverage_groups": low_coverage,
        "sample_count": {
            "min": int(sample_counts.min()) if not sample_counts.empty else None,
            "median": float(sample_counts.median()) if not sample_counts.empty else None,
            "max": int(sample_counts.max()) if not sample_counts.empty else None,
        },
        "coverage_ratio": {
            "min": float(coverage.min()) if not coverage.empty else None,
            "median": float(coverage.median()) if not coverage.empty else None,
            "max": float(coverage.max()) if not coverage.empty else None,
        },
        "artifacts": {
            "baseline": artifacts,
            "target_scores": score_artifacts,
        },
        "warnings": warnings,
        "errors": [],
    }
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
