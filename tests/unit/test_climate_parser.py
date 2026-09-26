import json
from pathlib import Path

import pandas as pd
import pytest

from motor_sin.climate.parser import parse_openmeteo_document, parse_openmeteo_file
from motor_sin.grid.index import coordinate_to_index


FIXTURE = Path(__file__).parents[1] / "fixtures" / "openmeteo_hourly_example.json"


def test_parse_openmeteo_hourly_fixture():
    df = parse_openmeteo_file(FIXTURE)
    assert len(df) == 3
    assert str(df["interval_start_utc"].dtype) == "datetime64[ns, UTC]"
    assert df.loc[1, "wind_speed_10m"] == pytest.approx(10.0)
    assert df.loc[0, "cell_id"] == coordinate_to_index(-22.95, -43.25).cell_id
    assert list(df["solar_radiation"]) == [0.0, 0.0, 0.0]


def test_local_timezone_converted_to_utc():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["timezone"] = "America/Sao_Paulo"
    payload["utc_offset_seconds"] = -10800
    payload["hourly"]["time"] = ["2026-09-18T00:00", "2026-09-18T01:00", "2026-09-18T02:00"]
    df = parse_openmeteo_document(payload)
    assert df.loc[0, "interval_start_utc"] == pd.Timestamp("2026-09-18T03:00:00Z")


def test_missing_required_variable_fails():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    del payload["hourly"]["precipitation"]
    del payload["hourly_units"]["precipitation"]
    with pytest.raises(ValueError, match="missing required hourly variables"):
        parse_openmeteo_document(payload)
