from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == '.csv':
        return pd.read_csv(path)
    if suffix in {'.parquet', '.pq'}:
        return pd.read_parquet(path)
    if suffix == '.json':
        payload = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(payload, list):
            return pd.DataFrame(payload)
        if isinstance(payload, dict) and isinstance(payload.get('records'), list):
            return pd.DataFrame(payload['records'])
        raise ValueError(f'JSON table must be a list or contain records: {path}')
    raise ValueError(f'unsupported table format: {suffix}')


def write_table(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == '.csv':
        df.to_csv(path, index=False)
    else:
        df.to_parquet(path, index=False)
    return path


def write_json(payload: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')
    return path


def canonical_utc_hour(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series, utc=True, errors='raise')
    if ((ts.dt.minute != 0) | (ts.dt.second != 0) | (ts.dt.microsecond != 0)).any():
        raise ValueError('timestamps must be aligned to full UTC hours')
    return ts
