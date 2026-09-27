from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .ons_balance import SUBSYSTEM_MAP


SOURCE = 'ONS_DESSEM_BALANCO_GERAL'
URL_TEMPLATE = (
    'https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/'
    'balanco_dessem_geral/BALANCO_DESSEM_GERAL_{date}.parquet'
)
VALUE_COLUMNS = {
    'val_demanda': 'programmed_load_mw',
    'val_geracao_renovavel': 'generation_renewable_mw',
    'val_geracao_hidraulica': 'generation_hydro_mw',
    'val_geracao_termica': 'generation_thermal_mw',
    'val_cons_elevatoria': 'pumping_load_mw',
}


def read_dessem_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in {'.parquet', '.pq'}:
        return pd.read_parquet(path)
    if path.suffix.lower() == '.csv':
        return pd.read_csv(path, sep=';', decimal='.', thousands=',', encoding='utf-8-sig')
    raise ValueError(f'unsupported DESSEM table: {path.suffix}')


def prepare_dessem_schedule(
    raw: pd.DataFrame,
    *,
    source_timezone: str,
    captured_at_utc: str | pd.Timestamp,
    source_url: str,
    snapshot_sha256: str,
) -> pd.DataFrame:
    required = {'din_programacaodia', 'num_patamar', 'cod_subsistema', *VALUE_COLUMNS}
    missing = sorted(required - set(raw.columns))
    if missing or raw.empty:
        raise ValueError(f'DESSEM requires nonempty data and columns: {missing}')
    if not source_timezone:
        raise ValueError('DESSEM requires an explicit source timezone')
    captured = pd.Timestamp(captured_at_utc)
    if pd.isna(captured) or captured.tzinfo is None:
        raise ValueError('DESSEM captured_at_utc must include a timezone')
    if not source_url or len(snapshot_sha256) != 64:
        raise ValueError('DESSEM requires a source URL and SHA256 snapshot identity')

    work = raw[list(required)].copy()
    reference_day = pd.to_datetime(work['din_programacaodia'], errors='raise')
    if reference_day.isna().any() or not reference_day.eq(reference_day.dt.normalize()).all():
        raise ValueError('DESSEM reference dates must be nonempty calendar dates')
    period = pd.to_numeric(work['num_patamar'], errors='raise')
    if not (period.between(1, 48) & period.eq(period.round())).all():
        raise ValueError('DESSEM num_patamar must be an integer from 1 to 48')
    local_start = reference_day + pd.to_timedelta((period - 1) * 30, unit='min')
    work['interval_start_utc'] = local_start.dt.tz_localize(
        source_timezone, ambiguous='raise', nonexistent='raise',
    ).dt.tz_convert('UTC')
    work['subsystem_id'] = work['cod_subsistema'].astype(str).str.strip().str.upper().map(SUBSYSTEM_MAP)
    if not work['subsystem_id'].isin(['N', 'NE', 'S', 'SE/CO']).all():
        raise ValueError('DESSEM contains an unknown subsystem')
    key = ['interval_start_utc', 'subsystem_id']
    if work.duplicated(key).any():
        raise ValueError('DESSEM contains duplicate subsystem/half-hour rows; select one version')

    for source_column in VALUE_COLUMNS:
        values = pd.to_numeric(work[source_column], errors='raise')
        if not (np.isfinite(values) & values.ge(0)).all():
            raise ValueError(f'DESSEM {source_column} must contain finite nonnegative MW')
        work[source_column] = values
    if not work['val_demanda'].gt(0).all():
        raise ValueError('DESSEM demand must be positive')
    work['interval_start_utc'] = work['interval_start_utc'].dt.floor('h')
    grouped = work.groupby(key, sort=True)
    if not grouped.size().eq(2).all():
        raise ValueError('DESSEM requires both half-hour periods for every hourly value')
    hourly = grouped[list(VALUE_COLUMNS)].mean().rename(columns=VALUE_COLUMNS).reset_index()
    hourly['source'] = SOURCE
    hourly['available_at_utc'] = captured.tz_convert('UTC')
    hourly['source_url'] = source_url
    hourly['snapshot_sha256'] = snapshot_sha256
    return hourly