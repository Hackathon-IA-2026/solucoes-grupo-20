from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from motor_sin.common.provenance import find_cached_raw_record, persist_immutable_raw_record, utc_now_iso
from motor_sin.climate.http_client import fetch_json_with_retry


DEFAULT_OPENMETEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

def get_openmeteo_archive_url() -> str:
    """Resolve the historical endpoint at runtime.

    Set PREDICTA_OPENMETEO_ARCHIVE_URL to a local/self-hosted endpoint such as
    http://127.0.0.1:8080/v1/archive or to the customer archive endpoint.
    """
    return os.getenv("PREDICTA_OPENMETEO_ARCHIVE_URL", DEFAULT_OPENMETEO_ARCHIVE_URL).rstrip("?")

def get_openmeteo_api_key() -> str | None:
    value=os.getenv("PREDICTA_OPENMETEO_API_KEY", "").strip()
    return value or None

OPENMETEO_ARCHIVE_URL = DEFAULT_OPENMETEO_ARCHIVE_URL
OPENMETEO_HOURLY_VARIABLES = (
    "temperature_2m",
    "dew_point_2m",
    "precipitation",
    "wind_speed_10m",
    "shortwave_radiation",
)


def build_archive_parameters(
    *,
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
    model: str = "era5_land",
) -> dict[str, Any]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end_date must be >= start_date")
    return {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": ",".join(OPENMETEO_HOURLY_VARIABLES),
        "models": str(model),
        "timezone": "GMT",
        "temperature_unit": "celsius",
        "wind_speed_unit": "ms",
        "precipitation_unit": "mm",
        "timeformat": "iso8601",
    }


def fetch_archive_payload(params: dict[str, Any], *, timeout_seconds: int = 60) -> tuple[int, dict[str, Any], str]:
    endpoint=get_openmeteo_archive_url()
    params=dict(params)
    apikey=get_openmeteo_api_key()
    if apikey: params["apikey"]=apikey
    url = f"{endpoint}?{urlencode(params)}"
    status, payload = fetch_json_with_retry(
        url, timeout_seconds=timeout_seconds, user_agent="predicta-hackathon/1.11.1",
        max_retries=10, base_backoff_seconds=10.0,
    )
    if not isinstance(payload, dict):
        raise ValueError("Open-Meteo archive response must be a JSON object")
    if payload.get("error") is True:
        raise RuntimeError(f"Open-Meteo archive request failed: status={status} payload={payload}")
    return status, payload, url


def download_and_persist(
    *,
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
    raw_directory: str | Path,
    timeout_seconds: int = 60,
    model: str = "era5_land",
) -> dict[str, Any]:
    params = build_archive_parameters(
        latitude=latitude, longitude=longitude, start_date=start_date, end_date=end_date, model=model
    )
    external_id = f"{model}:{latitude:.4f}:{longitude:.4f}:{start_date}:{end_date}"
    cached = find_cached_raw_record(directory=Path(raw_directory), source_service="historical", external_id=external_id, request_parameters=params)
    if cached:
        path, record = cached
        return {"status":"cached","http_status":int(record.get("http_status") or 200),"request_url":record.get("source_endpoint"),"raw_file":str(path),"created":False,"content_hash":str(record.get("payload_hash") or ""),"retrieved_at_utc":record.get("retrieved_at_utc"),"model":str(model)}
    retrieved_at = utc_now_iso()
    endpoint=get_openmeteo_archive_url()
    status, payload, request_url = fetch_archive_payload(params, timeout_seconds=timeout_seconds)
    path, created, content_hash = persist_immutable_raw_record(
        directory=Path(raw_directory),
        source="open-meteo",
        source_service="historical",
        source_endpoint=endpoint,
        external_id=external_id,
        request_parameters=params,
        payload=payload,
        http_status=status,
        retrieved_at_utc=retrieved_at,
    )
    return {
        "status": "ok",
        "http_status": status,
        "request_url": request_url,
        "raw_file": str(path),
        "created": created,
        "content_hash": content_hash,
        "retrieved_at_utc": retrieved_at,
        "model": str(model),
    }
