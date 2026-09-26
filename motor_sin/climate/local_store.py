from __future__ import annotations

import json
import os
import shutil
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

DATE_KEYS = {'start_date', 'end_date'}


class LocalClimateStoreGap(RuntimeError):
    """Raised when LOCAL_ONLY mode cannot satisfy a requested historical window."""

    def __init__(self, message: str, *, gaps: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.gaps = gaps or []


def climate_store_root(value: str | Path | None = None) -> Path:
    raw = value or os.getenv('PREDICTA_CLIMATE_STORE_ROOT') or 'data/climate_store'
    return Path(raw)


def region_store_paths(root: str | Path, tag: str) -> tuple[Path, Path]:
    base = Path(root) / str(tag)
    return base / 'hourly', base / 'daily'


def _identity_params(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if k not in DATE_KEYS}


def _record_dates(record: dict[str, Any], block_name: str) -> set[date]:
    payload = record.get('payload')
    if not isinstance(payload, dict):
        return set()
    block = payload.get(block_name)
    if not isinstance(block, dict):
        return set()
    times = block.get('time')
    if not isinstance(times, list):
        return set()
    out: set[date] = set()
    for value in times:
        try:
            out.add(date.fromisoformat(str(value)[:10]))
        except Exception:
            continue
    return out


def _desired_dates(start_date: str, end_date: str) -> set[date]:
    start = date.fromisoformat(str(start_date))
    end = date.fromisoformat(str(end_date))
    if end < start:
        raise ValueError('end_date precedes start_date')
    return {start + timedelta(days=i) for i in range((end - start).days + 1)}


def contiguous_ranges(dates: Iterable[date]) -> list[tuple[str, str]]:
    values = sorted(set(dates))
    if not values:
        return []
    ranges: list[tuple[date, date]] = []
    left = right = values[0]
    for value in values[1:]:
        if value == right + timedelta(days=1):
            right = value
            continue
        ranges.append((left, right))
        left = right = value
    ranges.append((left, right))
    return [(a.isoformat(), b.isoformat()) for a, b in ranges]


def find_local_records(
    *,
    directory: str | Path,
    source_service: str,
    request_parameters: dict[str, Any],
    block_name: str,
    start_date: str,
    end_date: str,
) -> tuple[list[tuple[Path, dict[str, Any]]], list[tuple[str, str]]]:
    """Return non-overlapping local RAW records plus uncovered date ranges.

    Identity is every request parameter except start/end dates. A partial current-year
    record can therefore satisfy part of a later request and only the new dates become
    gaps. Overlapping candidate records are not combined to avoid duplicates downstream.
    """
    root = Path(directory)
    desired = _desired_dates(start_date, end_date)
    identity = _identity_params(dict(request_parameters))
    candidates: list[tuple[int, Path, dict[str, Any], set[date]]] = []
    if root.exists():
        for path in sorted(root.glob('*.json')):
            try:
                record = json.loads(path.read_text(encoding='utf-8'))
            except Exception:
                continue
            if str(record.get('source_service')) != str(source_service):
                continue
            params = record.get('request_parameters')
            if not isinstance(params, dict) or _identity_params(params) != identity:
                continue
            dates = _record_dates(record, block_name) & desired
            if dates:
                candidates.append((len(dates), path, record, dates))

    selected: list[tuple[Path, dict[str, Any]]] = []
    covered: set[date] = set()
    for _, path, record, dates in sorted(candidates, key=lambda x: (x[0], str(x[1])), reverse=True):
        if dates & covered:
            continue
        selected.append((path, record))
        covered |= dates
    missing = desired - covered
    return selected, contiguous_ranges(missing)


def raw_record_row_common(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    return {
        'raw_file': str(path),
        'content_hash': str(record.get('payload_hash') or ''),
        'retrieved_at_utc': record.get('retrieved_at_utc'),
        'request_url': record.get('source_endpoint'),
    }


def link_or_copy_file(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return 'existing'
    try:
        os.link(source, destination)
        return 'hardlink'
    except OSError:
        shutil.copy2(source, destination)
        return 'copy'


def seed_store_from_annual_archive(
    *,
    annual_archive_root: str | Path,
    store_root: str | Path,
    regions: Iterable[str] = ('n', 'ne', 'seco', 's'),
) -> dict[str, Any]:
    """Seed the canonical local store from v1.11 annual caches without network IO."""
    source_root = Path(annual_archive_root)
    target_root = Path(store_root)
    report: dict[str, Any] = {'source': str(source_root), 'destination': str(target_root), 'regions': {}, 'files': 0, 'created': 0}
    for tag in regions:
        item = {'files': 0, 'created': 0, 'hardlinks': 0, 'copies': 0, 'existing': 0}
        for branch in ('hourly', 'daily'):
            src = source_root / tag / branch
            dst = target_root / tag / branch
            if not src.exists():
                continue
            for path in sorted(src.rglob('*.json')):
                rel = path.relative_to(src)
                mode = link_or_copy_file(path, dst / rel)
                item['files'] += 1
                item['existing' if mode == 'existing' else 'created'] += 1
                if mode == 'hardlink':
                    item['hardlinks'] += 1
                elif mode == 'copy':
                    item['copies'] += 1
        report['regions'][tag] = item
        report['files'] += item['files']
        report['created'] += item['created']
    return report


def copy_store_tree(source_root: str | Path, target_root: str | Path) -> dict[str, int]:
    source = Path(source_root)
    target = Path(target_root)
    if not source.exists():
        raise FileNotFoundError(source)
    stats = {'files': 0, 'created': 0, 'hardlinks': 0, 'copies': 0, 'existing': 0}
    for path in sorted(source.rglob('*.json')):
        rel = path.relative_to(source)
        mode = link_or_copy_file(path, target / rel)
        stats['files'] += 1
        stats['existing' if mode == 'existing' else 'created'] += 1
        if mode == 'hardlink':
            stats['hardlinks'] += 1
        elif mode == 'copy':
            stats['copies'] += 1
    return stats


def export_store(store_root: str | Path, output_zip: str | Path) -> dict[str, Any]:
    root = Path(store_root)
    if not root.exists():
        raise FileNotFoundError(root)
    output = Path(output_zip)
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(root.rglob('*')):
            if not path.is_file():
                continue
            zf.write(path, arcname=str(path.relative_to(root)))
            count += 1
    return {'output': str(output), 'files': count, 'bytes': output.stat().st_size}


def import_store(source: str | Path, store_root: str | Path) -> dict[str, Any]:
    src = Path(source)
    dst = Path(store_root)
    if src.is_dir():
        return {'mode': 'directory', **copy_store_tree(src, dst)}
    if src.suffix.lower() != '.zip':
        raise ValueError('source must be a Climate Store directory or .zip')
    import tempfile
    with tempfile.TemporaryDirectory(prefix='predicta-climate-store-') as tmp:
        with zipfile.ZipFile(src, 'r') as zf:
            zf.extractall(tmp)
        stats = copy_store_tree(tmp, dst)
    return {'mode': 'zip', **stats}


def store_inventory(store_root: str | Path) -> dict[str, Any]:
    root = Path(store_root)
    payload: dict[str, Any] = {'root': str(root), 'exists': root.exists(), 'regions': {}, 'total_files': 0, 'total_bytes': 0}
    for tag in ('n', 'ne', 'seco', 's'):
        region: dict[str, Any] = {}
        for branch in ('hourly', 'daily'):
            base = root / tag / branch
            files = sorted(base.rglob('*.json')) if base.exists() else []
            years = sorted({int(p.name.split('=', 1)[1]) for p in base.rglob('year=*') if p.is_dir() and p.name.split('=', 1)[1].isdigit()}) if base.exists() else []
            size = sum(p.stat().st_size for p in files)
            region[branch] = {'files': len(files), 'years': years, 'bytes': size}
            payload['total_files'] += len(files)
            payload['total_bytes'] += size
        payload['regions'][tag] = region
    return payload
