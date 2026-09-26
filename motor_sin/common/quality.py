from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import pandas as pd


def quality_report(*, run_id: str, source: str, input_rows: int, output: pd.DataFrame,
                   timestamp_col: str = 'interval_start_utc', unknown_categories: Iterable[str] = (),
                   warnings: Iterable[str] = (), errors: Iterable[str] = ()) -> dict:
    ts = None
    if timestamp_col in output.columns and len(output):
        ts = pd.to_datetime(output[timestamp_col], utc=True, errors='coerce')
    duplicate_timestamps = 0
    missing_timestamps = 0
    data_start = None
    data_end = None
    if ts is not None:
        missing_timestamps = int(ts.isna().sum())
        duplicate_timestamps = int(ts.duplicated().sum())
        if ts.notna().any():
            data_start = ts.min().isoformat()
            data_end = ts.max().isoformat()
    return {
        'run_id': run_id,
        'source': source,
        'rows_read': int(input_rows),
        'rows_output': int(len(output)),
        'missing_timestamps': missing_timestamps,
        'duplicate_timestamps': duplicate_timestamps,
        'missing_values': {c: int(output[c].isna().sum()) for c in output.columns},
        'unknown_categories': sorted(set(str(x) for x in unknown_categories)),
        'geocoding_quality': output['location_quality'].value_counts(dropna=False).to_dict() if 'location_quality' in output.columns else {},
        'data_start': data_start,
        'data_end': data_end,
        'freshness': None,
        'warnings': list(warnings),
        'errors': list(errors),
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
    }
