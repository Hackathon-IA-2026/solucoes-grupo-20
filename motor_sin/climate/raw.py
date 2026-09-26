from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from motor_sin.common.provenance import persist_immutable_raw_record, utc_now_iso


def _payloads_from_document(document: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {}
    payload = document
    if isinstance(document, dict) and "payload" in document and isinstance(document.get("payload"), (dict, list)):
        payload = document["payload"]
        meta = document
    if isinstance(payload, dict):
        return [payload], meta
    if isinstance(payload, list) and all(isinstance(x, dict) for x in payload):
        return list(payload), meta
    raise ValueError("input JSON must contain Open-Meteo object/list or a raw wrapper with payload")


def _external_id(payload: dict[str, Any], ordinal: int) -> str:
    hourly = payload.get("hourly") if isinstance(payload.get("hourly"), dict) else {}
    times = hourly.get("time") if isinstance(hourly, dict) else None
    first = times[0] if isinstance(times, list) and times else "unknown"
    last = times[-1] if isinstance(times, list) and times else "unknown"
    lat = payload.get("latitude", "na")
    lon = payload.get("longitude", "na")
    return f"era5_land:{lat}:{lon}:{first}:{last}:{ordinal}"


def ingest_local_openmeteo_json(
    input_path: str | Path,
    *,
    raw_directory: str | Path,
    source_service: str = "historical",
) -> list[dict[str, Any]]:
    input_path = Path(input_path)
    document = json.loads(input_path.read_text(encoding="utf-8"))
    payloads, wrapper = _payloads_from_document(document)
    results: list[dict[str, Any]] = []
    for ordinal, payload in enumerate(payloads, start=1):
        request_parameters = wrapper.get("request_parameters") or {}
        service = str(wrapper.get("source_service") or source_service)
        endpoint = str(wrapper.get("source_endpoint") or wrapper.get("request_url") or "local_import")
        path, created, content_hash = persist_immutable_raw_record(
            directory=Path(raw_directory),
            source=str(wrapper.get("source") or "open-meteo"),
            source_service=service,
            source_endpoint=endpoint,
            external_id=str(wrapper.get("external_id") or _external_id(payload, ordinal)),
            request_parameters=dict(request_parameters),
            payload=payload,
            http_status=int(wrapper.get("http_status") or 200),
            retrieved_at_utc=str(wrapper.get("retrieved_at_utc") or utc_now_iso()),
        )
        results.append({
            "input_file": str(input_path),
            "raw_file": str(path),
            "created": created,
            "content_hash": content_hash,
            "source_service": service,
        })
    return results
