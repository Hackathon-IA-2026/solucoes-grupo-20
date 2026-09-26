from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def payload_for_hash(payload: dict[str, Any], volatile_keys: tuple[str, ...] = ("generationtime_ms",)) -> dict[str, Any]:
    clean = dict(payload)
    for key in volatile_keys:
        clean.pop(key, None)
    return clean


def persist_immutable_raw_record(
    *,
    directory: Path,
    source: str,
    source_service: str,
    source_endpoint: str,
    external_id: str,
    request_parameters: dict[str, Any],
    payload: dict[str, Any],
    http_status: int,
    retrieved_at_utc: str | None = None,
) -> tuple[Path, bool, str]:
    """Persist one immutable RAW snapshot, deduplicated by canonical content hash.

    Adapted from the OpenMeteo snapshot storage contract. Unlike the old
    location-specific naming, the deduplication key here is provider/service/
    external_id + request + payload, so the helper can also be used by ONS,
    ANEEL and future providers.
    """
    directory.mkdir(parents=True, exist_ok=True)
    retrieved_at_utc = retrieved_at_utc or utc_now_iso()
    hash_payload = {
        "request_parameters": request_parameters,
        "payload": payload_for_hash(payload),
    }
    content_hash = sha256_json(hash_payload)

    safe_external = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in external_id)[:80]
    pattern = f"{source_service}__{safe_external}__*__{content_hash}.json"
    existing = sorted(directory.glob(pattern))
    if existing:
        return existing[-1], False, content_hash

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{source_service}__{safe_external}__{timestamp}__{content_hash}.json"
    record = {
        "schema_version": "raw_external_record_v1",
        "raw_record_id": f"{source_service}:{safe_external}:{content_hash[:16]}",
        "source": source,
        "source_service": source_service,
        "source_endpoint": source_endpoint,
        "external_id": external_id,
        "request_parameters": request_parameters,
        "payload_hash": content_hash,
        "retrieved_at_utc": retrieved_at_utc,
        "http_status": http_status,
        "processing_status": "pending",
        "processing_error": None,
        "payload": payload,
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path, True, content_hash


def find_cached_raw_record(
    *,
    directory: Path,
    source_service: str,
    external_id: str,
    request_parameters: dict[str, Any],
) -> tuple[Path, dict[str, Any]] | None:
    """Return a previously persisted RAW record with the same logical request.

    This avoids calling external APIs again merely to rediscover an immutable payload.
    """
    if not directory.exists():
        return None
    safe_external = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in external_id)[:80]
    candidates = sorted(directory.glob(f"{source_service}__{safe_external}__*.json"), reverse=True)
    for path in candidates:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if record.get("external_id") != external_id:
            continue
        if record.get("request_parameters") != request_parameters:
            continue
        payload = record.get("payload")
        if isinstance(payload, dict):
            return path, record
    return None
