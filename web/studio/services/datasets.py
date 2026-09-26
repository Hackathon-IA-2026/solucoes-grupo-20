from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import boto3
from django.conf import settings


def _s3_location() -> tuple[str, str] | None:
    configured = os.environ.get('S3_ATANORA', '').strip()
    if not configured:
        return None

    value = configured if '://' in configured else f's3://{configured}'
    parsed = urlparse(value)
    if parsed.scheme != 's3' or not parsed.netloc:
        raise ValueError('S3_ATANORA deve ser um bucket ou uma URI s3://bucket/prefix.')
    return parsed.netloc, parsed.path.strip('/')


def s3_configured() -> bool:
    return _s3_location() is not None


@lru_cache(maxsize=1)
def _s3_client():
    return boto3.client('s3')


def dataset_path(relative_path: str, local_path: Path) -> Path:
    """Return a local dataset path, downloading it from S3 when configured."""
    location = _s3_location()
    if location is None:
        return local_path

    bucket, prefix = location
    relative = relative_path.strip('/')
    key = '/'.join(part for part in (prefix, relative) if part)
    cache_root = Path(getattr(settings, 'PREDICTA_S3_CACHE_ROOT', Path(settings.PREDICTA_PROJECT_ROOT) / 'data' / 'web' / 's3_cache'))
    cached_path = cache_root / relative
    cached_path.parent.mkdir(parents=True, exist_ok=True)
    if not cached_path.exists():
        _s3_client().download_file(bucket, key, str(cached_path))
    return cached_path