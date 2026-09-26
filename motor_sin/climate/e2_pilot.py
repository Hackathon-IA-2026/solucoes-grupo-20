from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import json

import pandas as pd

from motor_sin.climate.openmeteo import download_and_persist
from motor_sin.demand.features import aggregate_climate_to_zones

REQUIRED_POINT_COLUMNS = {
    'point_id', 'name', 'state', 'subsystem_id', 'latitude', 'longitude', 'timezone', 'weight'
}


def canonical_zone(value: str) -> str:
    raw = str(value).strip().upper()
    return {'SE': 'SE/CO', 'SECO': 'SE/CO'}.get(raw, raw)


def load_pilot_points(path: str | Path, *, subsystem_id: str | None = None) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = REQUIRED_POINT_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f'pilot points missing columns: {sorted(missing)}')
    if df['point_id'].astype(str).duplicated().any():
        raise ValueError('pilot point_id must be unique')
    out = df.copy()
    out['subsystem_id'] = out['subsystem_id'].map(canonical_zone)
    out['latitude'] = pd.to_numeric(out['latitude'], errors='raise')
    out['longitude'] = pd.to_numeric(out['longitude'], errors='raise')
    out['weight'] = pd.to_numeric(out['weight'], errors='raise')
    if not out['latitude'].between(-90, 90, inclusive='neither').all():
        raise ValueError('pilot latitude outside (-90, 90)')
    if not out['longitude'].between(-180, 180, inclusive='neither').all():
        raise ValueError('pilot longitude outside (-180, 180)')
    if out['weight'].le(0).any():
        raise ValueError('pilot weights must be > 0')
    if subsystem_id is not None:
        zone = canonical_zone(subsystem_id)
        out = out[out['subsystem_id'].eq(zone)].copy()
        if out.empty:
            raise ValueError(f'no pilot points for subsystem {zone}')
    return out.reset_index(drop=True)


def infer_date_bounds_from_load(load: pd.DataFrame, *, subsystem_id: str) -> tuple[str, str]:
    required = {'interval_start_utc', 'subsystem_id', 'load_mw'}
    missing = required - set(load.columns)
    if missing:
        raise ValueError(f'load missing columns: {sorted(missing)}')
    zone = canonical_zone(subsystem_id)
    work = load.copy()
    work['subsystem_id'] = work['subsystem_id'].map(canonical_zone)
    work['interval_start_utc'] = pd.to_datetime(work['interval_start_utc'], utc=True, errors='raise')
    work = work[work['subsystem_id'].eq(zone)]
    if work.empty:
        raise ValueError(f'no load rows for subsystem {zone}')
    return work['interval_start_utc'].min().date().isoformat(), work['interval_start_utc'].max().date().isoformat()


def download_points(
    points: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    raw_directory: str | Path,
    timeout_seconds: int = 90,
    model: str = "era5_seamless",
) -> pd.DataFrame:
    rows: list[dict] = []
    for row in points.itertuples(index=False):
        result = download_and_persist(
            latitude=float(row.latitude),
            longitude=float(row.longitude),
            start_date=start_date,
            end_date=end_date,
            raw_directory=raw_directory,
            timeout_seconds=timeout_seconds,
            model=model,
        )
        rows.append({
            'point_id': str(row.point_id),
            'name': str(row.name),
            'state': str(row.state),
            'subsystem_id': canonical_zone(row.subsystem_id),
            'latitude_requested': float(row.latitude),
            'longitude_requested': float(row.longitude),
            'timezone': str(row.timezone),
            'weight': float(row.weight),
            'start_date': start_date,
            'end_date': end_date,
            'requested_model': str(model),
            **result,
        })
    return pd.DataFrame(rows)



E2_REQUIRED_CANONICAL_VARIABLES = (
    'temperature_2m',
    'dewpoint_2m',
    'precipitation',
    'wind_speed_10m',
    'solar_radiation',
)


def validate_e2_climate_coverage(climate: pd.DataFrame) -> dict[str, dict[str, float | int]]:
    """Fail fast if a requested E2 variable family is absent or entirely null.

    Open-Meteo can return a requested variable as all-null when the selected reanalysis
    model does not provide that field. E2 must never silently drop a climate family.
    """
    if climate.empty:
        raise ValueError('climate dataset is empty')
    stats: dict[str, dict[str, float | int]] = {}
    problems: list[str] = []
    n = int(len(climate))
    for name in E2_REQUIRED_CANONICAL_VARIABLES:
        if name not in climate.columns:
            problems.append(f'{name}: column missing')
            stats[name] = {'non_null': 0, 'rows': n, 'coverage': 0.0}
            continue
        vals = pd.to_numeric(climate[name], errors='coerce')
        non_null = int(vals.notna().sum())
        coverage = float(non_null / n) if n else 0.0
        stats[name] = {'non_null': non_null, 'rows': n, 'coverage': coverage}
        if non_null == 0:
            problems.append(f'{name}: all values are null')
    if problems:
        raise ValueError(
            'E2 climate source does not provide all required raw variables. ' +
            '; '.join(problems) +
            '. For the Open-Meteo historical API use model=era5_seamless for this MVP: '
            'temperature/dewpoint retain ERA5-Land support while precipitation, wind and solar '
            'are supplied from ERA5 forcing fields.'
        )
    return stats


def read_partitioned_climate(root: str | Path) -> pd.DataFrame:
    files = sorted(Path(root).rglob('*.parquet'))
    if not files:
        raise FileNotFoundError(f'no parquet files under {root}')
    return pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)


def aggregate_pilot_zone_climate(
    climate: pd.DataFrame,
    *,
    subsystem_id: str,
    spatial_method: str = 'MVP_REPRESENTATIVE_POINTS_UNIFORM',
) -> pd.DataFrame:
    """Aggregate a small, explicit set of ERA5-Land 0.1° cells to one subsystem.

    This is an MVP proxy, not an ONS electrical boundary reconstruction. Every unique
    normalized cell in the input is assigned to the requested subsystem because the
    source point configuration was explicitly curated for that subsystem.
    """
    if climate.empty:
        raise ValueError('climate dataset is empty')
    if 'cell_id' not in climate.columns:
        raise ValueError('climate dataset missing cell_id')
    validate_e2_climate_coverage(climate)
    zone = canonical_zone(subsystem_id)
    mapping = pd.DataFrame({
        'cell_id': sorted(climate['cell_id'].astype(str).unique()),
        'subsystem_id': zone,
    })
    out = aggregate_climate_to_zones(climate, mapping)
    if out.empty:
        raise ValueError('zone climate aggregation produced no rows')
    # aggregate_climate_to_zones materializes zero-valued incident placeholders when no
    # incident table is supplied. The E2 pilot has no baseline-derived incidents yet, so
    # remove those placeholders to avoid falsely advertising E3 readiness.
    placeholder_incidents = [c for c in out.columns if c.startswith('incident_')]
    if placeholder_incidents:
        out = out.drop(columns=placeholder_incidents)
    n_cells = int(climate['cell_id'].astype(str).nunique())
    out['sample_cell_count'] = n_cells
    out['weighting_method'] = 'uniform'
    out['climate_spatial_method'] = spatial_method
    models = sorted(str(x) for x in climate.get('source_model', pd.Series(dtype=str)).dropna().unique())
    out['climate_source_model'] = ','.join(models) if models else 'unknown'
    out['weather_mode'] = 'PERFECT_WEATHER_BACKTEST'
    return out.sort_values(['subsystem_id', 'interval_start_utc']).reset_index(drop=True)


def write_manifest(frame: pd.DataFrame, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(frame.to_dict(orient='records'), ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')
