from __future__ import annotations

from pathlib import Path

import pandas as pd

from contracts.validators.core import validate_dataframe, validate_file


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "contracts" / "fixtures"


def test_system_signal_fixture_is_valid_24h_per_zone() -> None:
    report = validate_file(
        FIXTURES / "system_signal_v1_example.csv",
        "system_signal_v1",
        expected_hours=24,
    )
    assert report.valid, report.errors
    assert report.rows == 120


def test_tariff_fixture_is_valid_24h() -> None:
    report = validate_file(
        FIXTURES / "tariff_v1_example.csv",
        "tariff_v1",
        expected_hours=24,
    )
    assert report.valid, report.errors


def test_grid_and_asset_fixtures_are_valid() -> None:
    assert validate_file(FIXTURES / "grid_state_v1_example.csv", "grid_state_v1").valid
    assert validate_file(FIXTURES / "asset_exposure_v1_example.csv", "asset_exposure_v1").valid


def test_missing_column_is_detected() -> None:
    df = pd.read_csv(FIXTURES / "system_signal_v1_example.csv")
    df = df.drop(columns=["quality_flags"])
    report = validate_dataframe(df, "system_signal_v1")
    assert not report.valid
    assert any("missing columns" in error for error in report.errors)


def test_duplicate_timestamp_zone_is_detected() -> None:
    df = pd.read_csv(FIXTURES / "system_signal_v1_example.csv")
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    report = validate_dataframe(df, "system_signal_v1")
    assert not report.valid
    assert any("duplicate contract key" in error for error in report.errors)


def test_out_of_range_signal_is_detected() -> None:
    df = pd.read_csv(FIXTURES / "system_signal_v1_example.csv")
    df.loc[0, "demand_percentile"] = 1.2
    report = validate_dataframe(df, "system_signal_v1")
    assert not report.valid
    assert any("demand_percentile" in error for error in report.errors)


def test_quantile_order_is_detected() -> None:
    df = pd.read_csv(FIXTURES / "system_signal_v1_example.csv")
    df.loc[0, "demand_p10_mw"] = df.loc[0, "demand_p90_mw"] + 100
    report = validate_dataframe(df, "system_signal_v1")
    assert not report.valid
    assert any("quantiles" in error for error in report.errors)


def test_non_utc_timestamp_is_rejected() -> None:
    df = pd.read_csv(FIXTURES / "system_signal_v1_example.csv")
    df.loc[0, "interval_start_utc"] = "2026-09-19T00:00:00-03:00"
    report = validate_dataframe(df, "system_signal_v1")
    assert not report.valid
    assert any("UTC" in error for error in report.errors)
