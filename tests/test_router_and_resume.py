from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from predicta_climate.router import HistoricalMode, RouterConfig, run_historical_router
from predicta_climate.store import materialize_year


def _points(n: int = 2) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cell_id": [f"c{i}" for i in range(n)],
            "subsystem": ["SECO"] * n,
            "latitude": [-15.8 - i * 0.1 for i in range(n)],
            "longitude": [-47.9 - i * 0.1 for i in range(n)],
        }
    )


def _frame_for(points: pd.DataFrame, year: int) -> pd.DataFrame:
    times = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    n_time = len(times)
    n_points = len(points)
    return pd.DataFrame(
        {
            "time_utc": np.repeat(times.values, n_points),
            "cell_id": np.tile(points["cell_id"].astype(str).to_numpy(), n_time),
            "subsystem": np.tile(points["subsystem"].astype(str).to_numpy(), n_time),
            "latitude": np.tile(points["latitude"].to_numpy(dtype=np.float32), n_time),
            "longitude": np.tile(points["longitude"].to_numpy(dtype=np.float32), n_time),
            "temperature_2m_c": np.float32(20.0),
            "dewpoint_2m_c": np.float32(15.0),
        }
    )


class InterruptingClient:
    def __init__(self):
        self.calls = 0

    def fetch_batch(self, *, points, year, groups):
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("simulated interruption")
        return _frame_for(points, year)


class RecordingClient:
    def __init__(self):
        self.cell_batches: list[list[str]] = []

    def fetch_batch(self, *, points, year, groups):
        self.cell_batches.append(points["cell_id"].astype(str).tolist())
        return _frame_for(points, year)


def test_materialize_year_resumes_completed_batch(tmp_path: Path):
    pytest.importorskip("pyarrow")
    points = _points(2)
    with pytest.raises(RuntimeError):
        materialize_year(
            client=InterruptingClient(),
            points=points,
            subsystem="SECO",
            year=2018,
            groups=["temperature"],
            output_root=tmp_path,
            batch_size=1,
            max_retries=1,
        )

    partial = tmp_path / "seco/hourly/.2018.partial"
    assert (partial / "part-00000.parquet").exists()
    assert not (partial / "part-00001.parquet").exists()

    client = RecordingClient()
    manifest = materialize_year(
        client=client,
        points=points,
        subsystem="SECO",
        year=2018,
        groups=["temperature"],
        output_root=tmp_path,
        batch_size=1,
        max_retries=1,
    )
    assert client.cell_batches == [["c1"]]
    assert manifest["status"] == "complete"
    assert (tmp_path / "seco/hourly/2018.parquet").exists()
    assert not partial.exists()


def test_auto_routes_directly_to_arco(monkeypatch, tmp_path: Path):
    calls = {"arco": 0, "openmeteo": 0}

    def fake_arco(**kwargs):
        calls["arco"] += 1
        return [{"status": "complete"}]

    def fake_openmeteo(command):
        calls["openmeteo"] += 1
        return 0, "ok"

    monkeypatch.setattr("predicta_climate.router.run_arco_historical", fake_arco)
    monkeypatch.setattr("predicta_climate.router.run_openmeteo_command", fake_openmeteo)

    result = run_historical_router(
        config=RouterConfig(mode=HistoricalMode.AUTO),
        points_dir=tmp_path,
        output_root=tmp_path,
        subsystems=["SECO"],
        start_year=2018,
        end_year=2018,
        openmeteo_command=["fake"],
    )
    assert result["backend"] == "arco"
    assert calls == {"arco": 1, "openmeteo": 0}


def test_429_falls_back_to_arco(monkeypatch, tmp_path: Path):
    calls = {"arco": 0}

    def fake_arco(**kwargs):
        calls["arco"] += 1
        return [{"status": "complete"}]

    monkeypatch.setattr("predicta_climate.router.run_arco_historical", fake_arco)
    monkeypatch.setattr(
        "predicta_climate.router.run_openmeteo_command",
        lambda command: (1, "ERROR HTTP 429 Too Many Requests"),
    )

    result = run_historical_router(
        config=RouterConfig(mode=HistoricalMode.OPENMETEO_WITH_ARCO_FALLBACK),
        points_dir=tmp_path,
        output_root=tmp_path,
        subsystems=["SECO"],
        start_year=2018,
        end_year=2018,
        openmeteo_command=["fake"],
    )
    assert result["backend"] == "arco"
    assert result["fallback_used"] is True
    assert result["reason"] == "HTTP 429"
    assert calls["arco"] == 1


def test_non_429_error_is_not_hidden(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "predicta_climate.router.run_openmeteo_command",
        lambda command: (2, "schema validation failed"),
    )
    with pytest.raises(RuntimeError):
        run_historical_router(
            config=RouterConfig(mode=HistoricalMode.OPENMETEO_WITH_ARCO_FALLBACK),
            points_dir=tmp_path,
            output_root=tmp_path,
            subsystems=["SECO"],
            start_year=2018,
            end_year=2018,
            openmeteo_command=["fake"],
        )
