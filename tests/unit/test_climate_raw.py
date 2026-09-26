from pathlib import Path

from motor_sin.climate.raw import ingest_local_openmeteo_json


FIXTURE = Path(__file__).parents[1] / "fixtures" / "openmeteo_hourly_example.json"


def test_raw_ingest_is_deduplicated(tmp_path):
    first = ingest_local_openmeteo_json(FIXTURE, raw_directory=tmp_path)
    second = ingest_local_openmeteo_json(FIXTURE, raw_directory=tmp_path)
    assert first[0]["created"] is True
    assert second[0]["created"] is False
    assert first[0]["content_hash"] == second[0]["content_hash"]
    assert len(list(tmp_path.glob("*.json"))) == 1
