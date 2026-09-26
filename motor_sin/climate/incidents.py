from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

INCIDENT_MAP = {
    'extreme_heat': ('HEAT', 'temperature_2m'),
    'extreme_cold': ('COLD', 'temperature_2m'),
    'intense_rain': ('RAIN', 'precipitation'),
    'strong_wind': ('WIND', 'wind_speed_10m'),
    'solar_deficit': ('SOLAR_DEFICIT', 'solar_radiation'),
}


def load_incident_config(path: str | Path = 'configs/incidents.yaml') -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding='utf-8'))


def _score(percentile: float, threshold: float, tail: str) -> float:
    if not np.isfinite(percentile):
        return 0.0
    if tail == 'upper':
        return float(np.clip((percentile - threshold) / max(1.0 - threshold, 1e-12), 0, 1))
    return float(np.clip((threshold - percentile) / max(threshold, 1e-12), 0, 1))


def detect_incidents(scores: pd.DataFrame, config: dict[str, Any], *, solar_radiation_min: float = 1.0) -> pd.DataFrame:
    required = {'interval_start_utc', 'cell_id', 'variable', 'value', 'percentile'}
    missing = required - set(scores.columns)
    if missing:
        raise ValueError(f'target score dataset missing columns: {sorted(missing)}')
    work = scores.copy()
    work['interval_start_utc'] = pd.to_datetime(work['interval_start_utc'], utc=True, errors='raise')
    rows: list[dict] = []
    for rule_name, rule in config.get('rules', {}).items():
        if rule_name not in INCIDENT_MAP or not bool(rule.get('enabled', False)):
            continue
        incident_type, metric = INCIDENT_MAP[rule_name]
        subset = work[work['variable'].eq(metric)]
        threshold = float(rule['percentile_threshold'])
        tail = str(rule.get('tail', 'upper'))
        abs_min = rule.get('absolute_minimum_mm_h')
        for row in subset.itertuples(index=False):
            p = float(row.percentile) if pd.notna(row.percentile) else np.nan
            value = float(row.value) if pd.notna(row.value) else np.nan
            score = _score(p, threshold, tail)
            if incident_type == 'RAIN' and abs_min is not None and (not np.isfinite(value) or value <= float(abs_min)):
                score = 0.0
            if incident_type == 'SOLAR_DEFICIT' and bool(rule.get('only_solar_hours', False)):
                # A near-zero radiation value is normally night, not a solar deficit event.
                if not np.isfinite(value) or value < solar_radiation_min:
                    score = 0.0
            if score <= 0:
                continue
            severe = rule.get('severe_percentile_threshold')
            severity = 'MODERATE'
            if severe is not None:
                severe = float(severe)
                if (tail == 'upper' and p >= severe) or (tail == 'lower' and p <= severe):
                    severity = 'SEVERE'
            rows.append({
                'interval_start_utc': row.interval_start_utc,
                'cell_id': str(row.cell_id),
                'incident_type': incident_type,
                'incident_score': score,
                'severity': severity,
                'baseline_year_start': getattr(row, 'baseline_year_start', None),
                'baseline_year_end': getattr(row, 'baseline_year_end', None),
                'variable': metric,
                'percentile': p,
                'value': value,
            })
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=['interval_start_utc','cell_id','incident_type','incident_score','severity','baseline_year_start','baseline_year_end','variable','percentile','value'])
    key = ['interval_start_utc','cell_id','incident_type']
    out = out.sort_values('incident_score', ascending=False).drop_duplicates(key).sort_values(key).reset_index(drop=True)
    return out
