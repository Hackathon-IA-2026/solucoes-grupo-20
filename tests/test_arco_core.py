from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from predicta_climate.arco import ArcoClient, expected_hours_for_year
from predicta_climate.points import make_cell_id, round_to_era5_land_grid
from predicta_climate.quality import validate_year_file


def test_expected_hours_leap_and_regular():
    assert expected_hours_for_year(2016) == 8784
    assert expected_hours_for_year(2017) == 8760
    assert expected_hours_for_year(2018) == 8760


def test_grid_rounding_and_cell_id_are_deterministic():
    assert round_to_era5_land_grid(-25.40831282) == -25.4
    assert round_to_era5_land_grid(-54.58741668) == -54.6
    assert make_cell_id(-25.4, -54.6) == make_cell_id(-25.40001, -54.59999)


def test_fetch_batch_converts_units(monkeypatch):
    year = 2017
    times = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    points = pd.DataFrame(
        {
            "cell_id": ["a", "b"],
            "subsystem": ["SECO", "SECO"],
            "latitude": [-15.8, -15.9],
            "longitude": [-47.9, -48.0],
        }
    )

    values = {
        "temperature_2m": 300.0,
        "dewpoint_2m": 290.0,
        "precipitation": 0.001,
        "wind_u_10m": 3.0,
        "wind_v_10m": 4.0,
        "solar_radiation": 3600.0,
    }

    def fake_select(self, *, logical_name, **kwargs):
        data = np.full((len(times), len(points)), values[logical_name], dtype=np.float32)
        return xr.DataArray(
            data,
            dims=("time", "point"),
            coords={"time": times, "point": range(len(points))},
        )

    monkeypatch.setattr(ArcoClient, "_select", fake_select)
    client = ArcoClient(api_key="not-used")
    frame = client.fetch_batch(points=points, year=year)

    assert len(frame) == 8760 * 2
    assert np.isclose(frame["temperature_2m_c"].iloc[0], 26.85, atol=0.01)
    assert np.isclose(frame["precipitation_mm"].iloc[0], 1.0, atol=1e-6)
    assert np.isclose(frame["wind_speed_10m_ms"].iloc[0], 5.0, atol=1e-6)
    assert np.isclose(frame["solar_radiation_w_m2_avg"].iloc[0], 1.0, atol=1e-6)


def test_quality_marks_full_year_complete(tmp_path: Path):
    import pytest
    pytest.importorskip("pyarrow")
    year = 2018
    times = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    frame = pd.DataFrame(
        {
            "time_utc": times,
            "cell_id": "g0001_0001",
            "subsystem": "S",
            "latitude": -30.0,
            "longitude": -52.0,
            "temperature_2m_c": np.float32(20.0),
        }
    )
    path = tmp_path / "2018.parquet"
    frame.to_parquet(path, index=False)
    report = validate_year_file(path, year, expected_cells=1)
    assert report["status"] == "complete"
    assert report["hours_per_cell_expected"] == 8760


def test_quality_can_require_requested_group_columns(tmp_path: Path):
    import pytest
    pytest.importorskip("pyarrow")
    year = 2018
    times = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    frame = pd.DataFrame(
        {
            "time_utc": times,
            "cell_id": "g0001_0001",
            "subsystem": "S",
            "latitude": -30.0,
            "longitude": -52.0,
            "temperature_2m_c": np.float32(20.0),
        }
    )
    path = tmp_path / "2018.parquet"
    frame.to_parquet(path, index=False)
    report = validate_year_file(
        path,
        year,
        expected_cells=1,
        required_columns=["temperature_2m_c", "dewpoint_2m_c"],
    )
    assert report["status"] == "invalid"
    assert "dewpoint_2m_c" in report["reason"]
