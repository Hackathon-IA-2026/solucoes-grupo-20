from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd

BALANCE_COLUMNS = (
    'id_subsistema',
    'nom_subsistema',
    'din_instante',
    'val_gerhidraulica',
    'val_gertermica',
    'val_gereolica',
    'val_gersolar',
    'val_carga',
    'val_intercambio',
)

SUBSYSTEM_MAP = {
    'N': 'N', 'NORTE': 'N',
    'NE': 'NE', 'NORDESTE': 'NE',
    'S': 'S', 'SUL': 'S',
    'SIN': 'SIN', 'SISTEMA INTERLIGADO NACIONAL': 'SIN',
    'SE': 'SE/CO', 'SE/CO': 'SE/CO', 'SECO': 'SE/CO', 'SUDESTE/CENTRO-OESTE': 'SE/CO',
    'SUDESTE / CENTRO-OESTE': 'SE/CO', 'SUDESTE/CENTRO OESTE': 'SE/CO',
}

ONS_BALANCE_URL_TEMPLATE = (
    'https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/'
    'balanco_energia_subsistema_ho/BALANCO_ENERGIA_SUBSISTEMA_{year}.{ext}'
)


def source_url(year: int, ext: str = 'parquet') -> str:
    ext = ext.lower().lstrip('.')
    if ext not in {'parquet', 'csv'}:
        raise ValueError('ONS balance extension must be parquet or csv')
    return ONS_BALANCE_URL_TEMPLATE.format(year=int(year), ext=ext)


def read_ons_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in {'.parquet', '.pq'}:
        return pd.read_parquet(path)
    if path.suffix.lower() == '.csv':
        # ONS CSVs are documented as UTF-8; delimiter has changed in some products,
        # so use Python's delimiter inference and keep values as text initially.
        return pd.read_csv(path, sep=None, engine='python', encoding='utf-8', dtype=str)
    raise ValueError(f'unsupported ONS table: {path.suffix}')


def _numeric(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors='coerce')
    s = series.astype(str).str.strip()
    # Supports both 1234.56 and 1.234,56 without altering ordinary decimal-dot values.
    comma = s.str.contains(',', regex=False)
    s.loc[comma] = s.loc[comma].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce')


def _canonical_subsystem(code: pd.Series, name: pd.Series) -> pd.Series:
    c = code.astype(str).str.strip().str.upper()
    n = name.astype(str).str.strip().str.upper()
    out = c.map(SUBSYSTEM_MAP)
    missing = out.isna()
    out.loc[missing] = n.loc[missing].map(SUBSYSTEM_MAP)
    if out.isna().any():
        bad = sorted(set(c.loc[out.isna()].tolist() + n.loc[out.isna()].tolist()))
        raise ValueError(f'unknown ONS subsystem identifiers: {bad}')
    return out


def _to_utc(ts: pd.Series, source_timezone: str | None) -> pd.Series:
    parsed = pd.to_datetime(ts, errors='raise')
    if getattr(parsed.dt, 'tz', None) is not None:
        return parsed.dt.tz_convert('UTC')
    if not source_timezone:
        raise ValueError(
            'ONS din_instante is timezone-naive in this file. Pass source_timezone explicitly; '
            'the adapter refuses to guess the source timezone.'
        )
    # ambiguous/nonexistent raise: historical DST issues must be handled explicitly rather than shifted silently.
    return parsed.dt.tz_localize(ZoneInfo(source_timezone), ambiguous='raise', nonexistent='raise').dt.tz_convert('UTC')


def prepare_ons_balance(df: pd.DataFrame, *, source_timezone: str | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    missing = [c for c in BALANCE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f'ONS balance missing columns: {missing}')
    work = df[list(BALANCE_COLUMNS)].copy()
    work['interval_start_utc'] = _to_utc(work['din_instante'], source_timezone).dt.floor('h')
    work['subsystem_id'] = _canonical_subsystem(work['id_subsistema'], work['nom_subsistema'])
    numeric_cols = ['val_gerhidraulica','val_gertermica','val_gereolica','val_gersolar','val_carga','val_intercambio']
    for c in numeric_cols:
        work[c] = _numeric(work[c])
    if work['val_carga'].isna().any():
        raise ValueError('ONS balance contains missing/non-numeric val_carga')
    key = ['interval_start_utc','subsystem_id']
    if work.duplicated(key).any():
        ex = work.loc[work.duplicated(key, keep=False), key].head(5).astype(str).to_dict('records')
        raise ValueError(f'ONS balance has duplicate subsystem-hour rows, examples={ex}')

    load = work[key + ['val_carga']].rename(columns={'val_carga':'load_mw'}).sort_values(key).reset_index(drop=True)
    supply = work[key + numeric_cols].rename(columns={
        'val_gerhidraulica':'generation_hydro_mw',
        'val_gertermica':'generation_thermal_mw',
        'val_gereolica':'generation_wind_mw',
        'val_gersolar':'generation_solar_mw',
        'val_carga':'load_mw',
        'val_intercambio':'net_interchange_mw',
    }).sort_values(key).reset_index(drop=True)
    gen_cols = ['generation_hydro_mw','generation_thermal_mw','generation_wind_mw','generation_solar_mw']
    supply['generation_total_mw'] = supply[gen_cols].fillna(0).sum(axis=1)
    supply['source'] = 'ONS_BALANCO_ENERGIA_SUBSISTEMA'
    load['source'] = 'ONS_BALANCO_ENERGIA_SUBSISTEMA'
    return load, supply


def quality_summary(load: pd.DataFrame, supply: pd.DataFrame) -> dict:
    return {
        'source': 'ONS_BALANCO_ENERGIA_SUBSISTEMA',
        'load_rows': int(len(load)),
        'supply_rows': int(len(supply)),
        'subsystems': sorted(load['subsystem_id'].unique().tolist()),
        'data_start_utc': str(load['interval_start_utc'].min()),
        'data_end_utc': str(load['interval_start_utc'].max()),
        'missing_load': int(load['load_mw'].isna().sum()),
        'duplicate_subsystem_hours': int(load.duplicated(['interval_start_utc','subsystem_id']).sum()),
        'negative_generation_cells': int((supply[[c for c in supply if c.startswith('generation_') and c.endswith('_mw')]] < 0).sum().sum()),
    }
