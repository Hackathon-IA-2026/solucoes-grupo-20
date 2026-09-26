from __future__ import annotations

import json
from pathlib import Path

from motor_sin.common.provenance import persist_immutable_raw_record, sha256_json


def test_hash_is_order_independent_for_dicts() -> None:
    assert sha256_json({"a": 1, "b": 2}) == sha256_json({"b": 2, "a": 1})


def test_raw_persistence_deduplicates_identical_content(tmp_path: Path) -> None:
    kwargs = dict(
        directory=tmp_path,
        source="fixture",
        source_service="historical",
        source_endpoint="https://example.invalid",
        external_id="cell:1:2026-09-19",
        request_parameters={"x": 1},
        payload={"value": 42, "generationtime_ms": 1.23},
        http_status=200,
    )
    first, created_first, hash_first = persist_immutable_raw_record(**kwargs)
    kwargs["payload"] = {"value": 42, "generationtime_ms": 9.99}
    second, created_second, hash_second = persist_immutable_raw_record(**kwargs)
    assert created_first is True
    assert created_second is False
    assert first == second
    assert hash_first == hash_second
