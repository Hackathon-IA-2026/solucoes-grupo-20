from __future__ import annotations

import pandas as pd
import pytest

pyarrow = pytest.importorskip("pyarrow")

from motor_sin.climate.baseline import build_climate_baseline, write_phase3_artifacts


def test_phase3_artifacts_are_partitioned_and_reported(tmp_path):
    rows = []
    for year in range(2016, 2026):
        rows.append(
            {
                "interval_start_utc": pd.Timestamp(f"{year}-06-15T12:00:00Z"),
                "cell_id": "cell_a",
                "temperature_2m": float(year - 2016),
            }
        )
    rows.append(
        {
            "interval_start_utc": pd.Timestamp("2026-06-15T12:00:00Z"),
            "cell_id": "cell_a",
            "temperature_2m": 10.0,
        }
    )
    result = build_climate_baseline(
        pd.DataFrame(rows),
        target_year=2026,
        variables=["temperature_2m"],
        seasonal_window_days=0,
        max_cells=1,
    )
    report = write_phase3_artifacts(
        result,
        baseline_output_root=tmp_path / "baseline",
        score_output_root=tmp_path / "scores",
        report_path=tmp_path / "report.json",
        run_id="test",
        source_files=["fixture.parquet"],
    )
    assert report["status"] == "ok"
    assert len(report["artifacts"]["baseline"]) == 1
    assert len(report["artifacts"]["target_scores"]) == 1
    assert (tmp_path / "report.json").exists()
