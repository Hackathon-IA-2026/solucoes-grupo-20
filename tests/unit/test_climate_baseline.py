from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from motor_sin.climate.baseline import (
    baseline_years_for_target,
    build_climate_baseline,
    canonical_season_day,
    circular_season_distance,
    empirical_percentile,
    robust_z_score,
)


def _row(ts: str, value: float, cell: str = "g01_test") -> dict:
    return {
        "interval_start_utc": pd.Timestamp(ts),
        "cell_id": cell,
        "temperature_2m": value,
        "dewpoint_2m": value - 5,
        "precipitation": 0.0,
        "wind_speed_10m": 2.0,
        "solar_radiation": 100.0,
    }


def _ten_year_minimal_history(*, target_year: int = 2026, target_value: float = 999.0) -> pd.DataFrame:
    rows = []
    for year in range(target_year - 10, target_year):
        rows.append(_row(f"{year}-06-15T12:00:00Z", float(year - (target_year - 10))))
    rows.append(_row(f"{target_year}-06-15T12:00:00Z", target_value))
    return pd.DataFrame(rows)


def test_baseline_years_are_previous_ten_only():
    assert baseline_years_for_target(2026, 10) == list(range(2016, 2026))


def test_canonical_season_calendar_keeps_march_aligned_across_leap_years():
    assert canonical_season_day(date(2024, 3, 1)) == 61
    assert canonical_season_day(date(2025, 3, 1)) == 61
    assert canonical_season_day(date(2024, 2, 29)) == 60


def test_circular_window_wraps_december_to_january():
    assert circular_season_distance(366, 1) == 1
    assert circular_season_distance(365, 2) == 3


def test_target_year_is_excluded_from_baseline_statistics():
    df = _ten_year_minimal_history(target_value=999.0)
    result = build_climate_baseline(
        df,
        target_year=2026,
        variables=["temperature_2m"],
        seasonal_window_days=0,
        max_cells=1,
    )
    row = result.baseline.query("season_month_day == '06-15' and hour_of_day_utc == 12").iloc[0]
    assert row["sample_count"] == 10
    assert row["median"] == pytest.approx(4.5)
    assert row["p99"] < 999.0
    assert result.metadata["target_year_excluded_from_baseline"] is True


def test_target_scoring_uses_historical_sample_only():
    df = _ten_year_minimal_history(target_value=9.5)
    result = build_climate_baseline(
        df,
        target_year=2026,
        variables=["temperature_2m"],
        seasonal_window_days=0,
        max_cells=1,
    )
    score = result.target_scores.iloc[0]
    assert score["baseline_sample_count"] == 10
    assert score["baseline_median"] == pytest.approx(4.5)
    assert score["anomaly"] == pytest.approx(5.0)
    assert score["percentile"] == pytest.approx(1.0)
    assert 0.0 <= score["percentile"] <= 1.0


def test_empirical_percentile_is_weak_ecdf():
    samples = np.array([1.0, 2.0, 2.0, 4.0])
    assert empirical_percentile(samples, 2.0) == pytest.approx(0.75)
    assert empirical_percentile(samples, 0.0) == 0.0
    assert empirical_percentile(samples, 5.0) == 1.0


def test_robust_z_uses_epsilon_when_iqr_zero():
    score = robust_z_score(11.0, 10.0, 0.0, epsilon=0.5)
    assert score == pytest.approx(2.0)


def test_missing_required_baseline_year_fails_by_default():
    df = _ten_year_minimal_history()
    df = df[df["interval_start_utc"] != pd.Timestamp("2020-06-15T12:00:00Z")]
    with pytest.raises(ValueError, match="all required years"):
        build_climate_baseline(
            df,
            target_year=2026,
            variables=["temperature_2m"],
            seasonal_window_days=0,
            max_cells=1,
        )


def test_small_scope_guard_blocks_accidental_large_cell_selection():
    rows = []
    for cell_idx in range(3):
        cell = f"cell_{cell_idx}"
        for year in range(2016, 2026):
            rows.append(_row(f"{year}-06-15T12:00:00Z", 20.0, cell=cell))
    df = pd.DataFrame(rows)
    with pytest.raises(ValueError, match="small-scope guard"):
        build_climate_baseline(
            df,
            target_year=2026,
            variables=["temperature_2m"],
            seasonal_window_days=0,
            max_cells=2,
        )
