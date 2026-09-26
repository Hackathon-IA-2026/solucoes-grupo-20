from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from motor_sin.grid.index import coordinate_to_index
from motor_sin.climate.variables import CANONICAL_VARIABLES, convert_value, resolve_source_field


OUTPUT_COLUMNS = [
    "interval_start_utc",
    "cell_id",
    "temperature_2m",
    "dewpoint_2m",
    "precipitation",
    "wind_speed_10m",
    "solar_radiation",
    "source",
    "source_service",
    "source_model",
    "source_grid_latitude",
    "source_grid_longitude",
    "source_elevation",
    "raw_record_id",
    "raw_payload_hash",
    "raw_file",
]


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_hourly_block(hourly: dict[str, Any]) -> int:
    times = hourly.get("time")
    if not isinstance(times, list) or not times:
        raise ValueError("Open-Meteo payload must contain non-empty hourly.time list")
    n = len(times)
    for key, values in hourly.items():
        if key == "time":
            continue
        if not isinstance(values, list):
            raise ValueError(f"hourly.{key} must be a list")
        if len(values) != n:
            raise ValueError(f"hourly.{key} has {len(values)} values but hourly.time has {n}")
    return n


def _parse_timestamp_to_utc(value: Any, *, timezone_name: str | None, utc_offset_seconds: Any) -> pd.Timestamp:
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"invalid Open-Meteo timestamp: {value!r}") from exc

    if dt.tzinfo is None:
        tz = None
        if timezone_name:
            if timezone_name.upper() in {"UTC", "GMT", "ETC/UTC"}:
                tz = timezone.utc
            else:
                try:
                    tz = ZoneInfo(timezone_name)
                except ZoneInfoNotFoundError:
                    tz = None
        if tz is None:
            if utc_offset_seconds is None:
                raise ValueError("naive timestamps require timezone or utc_offset_seconds")
            tz = timezone(timedelta(seconds=int(utc_offset_seconds)))
        dt = dt.replace(tzinfo=tz)

    return pd.Timestamp(dt.astimezone(timezone.utc))


def _unwrap_raw_record(document: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {}
    payload = document
    if isinstance(document, dict) and "payload" in document and isinstance(document.get("payload"), (dict, list)):
        payload = document["payload"]
        meta = {
            "source": document.get("source", "open-meteo"),
            "source_service": document.get("source_service", "historical"),
            "raw_record_id": document.get("raw_record_id"),
            "raw_payload_hash": document.get("payload_hash"),
            "request_parameters": document.get("request_parameters") or {},
        }

    if isinstance(payload, dict):
        return [payload], meta
    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        return list(payload), meta
    raise ValueError("JSON does not contain an Open-Meteo object or list of objects")


def parse_openmeteo_document(document: Any, *, raw_file: str = "") -> pd.DataFrame:
    payloads, meta = _unwrap_raw_record(document)
    frames = [_parse_openmeteo_payload(payload, meta=meta, raw_file=raw_file) for payload in payloads]
    if not frames:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    result = pd.concat(frames, ignore_index=True)
    return result[OUTPUT_COLUMNS]


def parse_openmeteo_file(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    return parse_openmeteo_document(load_json(path), raw_file=str(path))


def _parse_openmeteo_payload(payload: dict[str, Any], *, meta: dict[str, Any], raw_file: str) -> pd.DataFrame:
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise ValueError("Open-Meteo payload does not contain hourly object")
    validate_hourly_block(hourly)

    units = payload.get("hourly_units") or {}
    if not isinstance(units, dict):
        raise ValueError("hourly_units must be an object when present")

    try:
        lat = float(payload["latitude"])
        lon = float(payload["longitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Open-Meteo payload requires numeric latitude and longitude") from exc

    cell_id = coordinate_to_index(lat, lon).cell_id
    tz_name = payload.get("timezone")
    offset_seconds = payload.get("utc_offset_seconds")
    request_params = meta.get("request_parameters") or {}
    source_model = request_params.get("models") or payload.get("model") or payload.get("models")
    source = meta.get("source", "open-meteo")
    source_service = meta.get("source_service", "historical")
    elevation = payload.get("elevation")

    source_fields = {name: resolve_source_field(hourly, name) for name in CANONICAL_VARIABLES}
    missing = [name for name, field in source_fields.items() if field is None]
    if missing:
        raise ValueError(f"missing required hourly variables: {missing}")

    records: list[dict[str, Any]] = []
    for idx, time_value in enumerate(hourly["time"]):
        record: dict[str, Any] = {
            "interval_start_utc": _parse_timestamp_to_utc(
                time_value,
                timezone_name=str(tz_name) if tz_name else None,
                utc_offset_seconds=offset_seconds,
            ),
            "cell_id": cell_id,
            "source": source,
            "source_service": source_service,
            "source_model": str(source_model) if source_model is not None else None,
            "source_grid_latitude": lat,
            "source_grid_longitude": lon,
            "source_elevation": float(elevation) if elevation is not None else None,
            "raw_record_id": meta.get("raw_record_id"),
            "raw_payload_hash": meta.get("raw_payload_hash"),
            "raw_file": raw_file,
        }
        for canonical_name, source_field in source_fields.items():
            assert source_field is not None
            record[canonical_name] = convert_value(
                canonical_name,
                hourly[source_field][idx],
                units.get(source_field),
            )
        records.append(record)

    df = pd.DataFrame.from_records(records, columns=OUTPUT_COLUMNS)
    if df["interval_start_utc"].duplicated().any():
        raise ValueError("duplicate timestamps inside Open-Meteo payload")
    return df
