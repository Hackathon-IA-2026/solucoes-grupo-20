from pathlib import Path

import pandas as pd
import pytest

from motor_sin.climate.normalize import prepare_climate_dataset
from motor_sin.climate.raw import ingest_local_openmeteo_json


FIXTURE = Path(__file__).parents[1] / "fixtures" / "openmeteo_hourly_example.json"


def test_prepare_partitioned_parquet(tmp_path):
    pytest.importorskip("pyarrow")
    raw_dir = tmp_path / "raw"
    ingest_local_openmeteo_json(FIXTURE, raw_directory=raw_dir)
    report = prepare_climate_dataset(
        raw_dir.glob("*.json"),
        output_root=tmp_path / "processed",
        report_path=tmp_path / "quality.json",
        run_id="smoke",
    )
    assert report["rows_output"] == 3
    assert report["duplicate_timestamps"] == 0
    assert len(report["artifacts"]) == 1
    artifact = Path(report["artifacts"][0])
    assert "run_id=smoke" in str(artifact)
    assert "year=2026" in str(artifact)
    assert "month=09" in str(artifact)
    df = pd.read_parquet(artifact)
    assert len(df) == 3


def test_overlap_fails_in_strict_mode(tmp_path):
    one = tmp_path / "one.json"
    two = tmp_path / "two.json"
    one.write_bytes(FIXTURE.read_bytes())
    two.write_bytes(FIXTURE.read_bytes())
    with pytest.raises(ValueError, match="duplicate cell/hour"):
        prepare_climate_dataset(
            [one, two],
            output_root=tmp_path / "processed",
            report_path=tmp_path / "quality.json",
            run_id="overlap",
        )
