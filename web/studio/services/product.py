from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from django.conf import settings

from motor_sin.common.io import read_table
from motor_sin.signals.real_signal import build_real_system_signal
from motor_tarifa.customer.optimize import optimize_flexible_consumption
from motor_tarifa.customer.profiles import synthetic_daily_profile
from motor_tarifa.customer.result import build_customer_result
from motor_tarifa.pipeline import load_tariff_config, simulate_dynamic_tariff

from .distribution import (
    available_signal_regions,
    cnpj_digits,
    distributor_info,
    tariff_profiles_for_cnpj,
)
from .datasets import dataset_path, s3_configured

ROOT = Path(settings.PREDICTA_PROJECT_ROOT)
DISPLAY_TIMEZONE = 'America/Sao_Paulo'
DISPLAY_TZ = ZoneInfo(DISPLAY_TIMEZONE)
SIGNAL = ROOT / 'outputs/contracts/system_signal_v1.parquet'
TARIFFS = ROOT / 'data/processed/tariff/base_tariffs.parquet'
E3_PREDICTIONS = ROOT / 'outputs/metrics/e3_real_pilot_predictions.parquet'
LOAD_HISTORY = ROOT / 'data/processed/demand/load_hourly.parquet'
E3_CLIMATE = ROOT / 'data/processed/climate/zone_climate_hourly_e3.parquet'
SUPPLY_HISTORY = ROOT / 'data/processed/generation/supply_by_subsystem_hourly.parquet'


def _dataset(relative_path: str, local_path: Path) -> Path:
    return dataset_path(relative_path, local_path)


def _path_exists(relative_path: str, local_path: Path) -> bool:
    return _dataset(relative_path, local_path).exists()


def available_regions():
    return available_signal_regions()


def distributors():
    # Kept for backward compatibility; new product flow is CNPJ/map based.
    tariffs_path = _dataset('data/processed/tariff/base_tariffs.parquet', TARIFFS)
    if not tariffs_path.exists():
        return []
    df = read_table(tariffs_path)
    return sorted(df.distributor_id.dropna().astype(str).unique().tolist())


def profiles_for(distributor: str, region: str = 'SE/CO'):
    tariffs_path = _dataset('data/processed/tariff/base_tariffs.parquet', TARIFFS)
    if not tariffs_path.exists() or not distributor:
        return []
    df = read_table(tariffs_path)
    cnpj = ''
    if 'distributor_cnpj' in df.columns:
        m = df[df.distributor_id.astype(str).eq(distributor)]
        if len(m):
            cnpj = str(m.iloc[0].distributor_cnpj)
    return tariff_profiles_for_cnpj(cnpj, region) if cnpj else []


def profiles_for_location(cnpj: str, region: str, effective_date: date | None = None):
    return tariff_profiles_for_cnpj(cnpj, region, effective_date=effective_date)


def _quality_flags(frame: pd.DataFrame) -> set[str]:
    flags: set[str] = set()
    if 'quality_flags' not in frame.columns:
        return flags
    for raw in frame['quality_flags'].dropna().astype(str):
        try:
            value = json.loads(raw)
            if isinstance(value, list):
                flags.update(str(x) for x in value)
            else:
                flags.add(str(value))
        except Exception:
            flags.add(raw)
    return flags


def _window_descriptor(frame: pd.DataFrame, *, key: str, source: str, issue_time_utc: pd.Timestamp | None = None) -> dict:
    ts = pd.to_datetime(frame['interval_start_utc'], utc=True, errors='raise').sort_values()
    first_local = ts.iloc[0].tz_convert(DISPLAY_TZ)
    last_local = ts.iloc[-1].tz_convert(DISPLAY_TZ)
    same_day = first_local.date() == last_local.date()
    if same_day:
        label = f"{first_local.strftime('%d/%m/%Y')} · {first_local.strftime('%Hh')}–{last_local.strftime('%Hh')}"
    else:
        label = f"{first_local.strftime('%d/%m %Hh')} → {last_local.strftime('%d/%m/%Y %Hh')}"
    return {
        'key': key,
        'label': label,
        'local_date': first_local.date().isoformat(),
        'local_start': first_local.isoformat(),
        'local_end': last_local.isoformat(),
        'timezone': DISPLAY_TIMEZONE,
        'source': source,
        'issue_time_utc': issue_time_utc.isoformat() if issue_time_utc is not None else None,
    }


def replay_windows(region: str | None = None) -> list[dict]:
    """List historical 24h windows available for the product replay selector."""
    windows: list[dict] = []
    predictions_path = _dataset('outputs/metrics/e3_real_pilot_predictions.parquet', E3_PREDICTIONS)
    signal_path = _dataset('outputs/contracts/system_signal_v1.parquet', SIGNAL)
    if predictions_path.exists():
        p = read_table(predictions_path)
        if {'issue_time_utc', 'interval_start_utc', 'subsystem_id'}.issubset(p.columns):
            if 'experiment' in p.columns:
                p = p[p['experiment'].astype(str).eq('E3')]
            if region:
                p = p[p['subsystem_id'].astype(str).eq(str(region))]
            p = p.copy()
            p['issue_time_utc'] = pd.to_datetime(p['issue_time_utc'], utc=True, errors='coerce')
            p['interval_start_utc'] = pd.to_datetime(p['interval_start_utc'], utc=True, errors='coerce')
            p = p.dropna(subset=['issue_time_utc', 'interval_start_utc'])
            for issue, g in p.groupby('issue_time_utc'):
                g = g.drop_duplicates(['interval_start_utc', 'subsystem_id'])
                if region:
                    ok = len(g) == 24 and g['interval_start_utc'].nunique() == 24
                else:
                    counts = g.groupby('subsystem_id')['interval_start_utc'].nunique()
                    ok = bool(len(counts) and counts.max() >= 24)
                if not ok:
                    continue
                key = pd.Timestamp(issue).isoformat()
                windows.append(_window_descriptor(g.sort_values('interval_start_utc').head(24), key=key, source='E3_BACKTEST', issue_time_utc=pd.Timestamp(issue)))
    if not windows and signal_path.exists():
        s = read_table(signal_path)
        s = s[s['zone_type'].astype(str).eq('SUBSYSTEM')].copy()
        if region:
            s = s[s['zone_id'].astype(str).eq(str(region))]
        if len(s) >= 24:
            windows.append(_window_descriptor(s.sort_values('interval_start_utc').head(24), key='CURRENT_SIGNAL_REPLAY', source='SYSTEM_SIGNAL_V1'))
    windows.sort(key=lambda x: x['local_start'])
    return windows


def replay_window(region: str, key: str | None) -> dict | None:
    windows = replay_windows(region)
    if not windows:
        return None
    if not key:
        return windows[-1]
    return next((w for w in windows if w['key'] == key), None)


def _load_current_signal(region: str) -> pd.DataFrame:
    signal_path = _dataset('outputs/contracts/system_signal_v1.parquet', SIGNAL)
    if not signal_path.exists():
        return pd.DataFrame()
    s = read_table(signal_path)
    s['interval_start_utc'] = pd.to_datetime(s['interval_start_utc'], utc=True, errors='raise')
    return s[(s['zone_type'].astype(str).eq('SUBSYSTEM')) & (s['zone_id'].astype(str).eq(str(region)))].sort_values('interval_start_utc').copy()


def operational_status(region: str) -> dict:
    """Describe whether system_signal_v1 is genuinely usable as a current 24h forecast."""
    z = _load_current_signal(region)
    if len(z) != 24:
        return {'available': False, 'reason': f'{region} não possui 24 horas operacionais publicadas em system_signal_v1.'}
    flags = _quality_flags(z)
    if 'PERFECT_WEATHER_BACKTEST_NOT_OPERATIONAL' in flags:
        return {
            'available': False,
            'reason': 'O sinal disponível usa clima observado de backtest (PERFECT_WEATHER_BACKTEST); não pode ser apresentado como previsão atual.',
        }
    now = pd.Timestamp.now(tz='UTC')
    first = z['interval_start_utc'].min()
    last = z['interval_start_utc'].max()
    if first > now + pd.Timedelta(hours=3) or first < now - pd.Timedelta(hours=3) or last < now + pd.Timedelta(hours=20):
        f = first.tz_convert(DISPLAY_TZ).strftime('%d/%m/%Y %Hh')
        l = last.tz_convert(DISPLAY_TZ).strftime('%d/%m/%Y %Hh')
        return {'available': False, 'reason': f'O system_signal_v1 cobre {f}–{l} ({DISPLAY_TIMEZONE}), não o horizonte operacional atual.'}
    desc = _window_descriptor(z, key='OPERATIONAL_CURRENT', source='SYSTEM_SIGNAL_V1_OPERATIONAL')
    return {'available': True, 'reason': 'Previsão operacional de 24h disponível.', **desc}


def simulation_available(region: str, mode: str = 'replay', replay_key: str | None = None) -> bool:
    mode = str(mode or 'replay').lower()
    if mode == 'operational':
        return bool(operational_status(region).get('available'))
    return replay_window(region, replay_key) is not None


def effective_date_for(region: str, mode: str = 'replay', replay_key: str | None = None) -> date | None:
    mode = str(mode or 'replay').lower()
    if mode == 'operational':
        status = operational_status(region)
        if status.get('available') and status.get('local_date'):
            return date.fromisoformat(status['local_date'])
        return None
    w = replay_window(region, replay_key)
    return date.fromisoformat(w['local_date']) if w else None


def _signal_for_replay(region: str, replay_key: str | None) -> tuple[pd.DataFrame, dict]:
    w = replay_window(region, replay_key)
    if not w:
        raise ValueError(f'Não há janela histórica completa de 24h para {region}.')
    predictions_path = _dataset('outputs/metrics/e3_real_pilot_predictions.parquet', E3_PREDICTIONS)
    load_path = _dataset('data/processed/demand/load_hourly.parquet', LOAD_HISTORY)
    climate_path = _dataset('data/processed/climate/zone_climate_hourly_e3.parquet', E3_CLIMATE)
    supply_path = _dataset('data/processed/generation/supply_by_subsystem_hourly.parquet', SUPPLY_HISTORY)
    if w['source'] == 'E3_BACKTEST' and predictions_path.exists():
        if not load_path.exists():
            raise ValueError('Histórico de carga não encontrado; necessário para reconstruir D no replay.')
        p = read_table(predictions_path)
        if 'experiment' in p.columns:
            p = p[p['experiment'].astype(str).eq('E3')]
        p['issue_time_utc'] = pd.to_datetime(p['issue_time_utc'], utc=True, errors='raise')
        p['interval_start_utc'] = pd.to_datetime(p['interval_start_utc'], utc=True, errors='raise')
        issue = pd.Timestamp(w['key'])
        issue = issue.tz_localize('UTC') if issue.tzinfo is None else issue.tz_convert('UTC')
        forecast = p[(p['subsystem_id'].astype(str).eq(str(region))) & (p['issue_time_utc'].eq(issue))].copy()
        if len(forecast) != 24:
            raise ValueError(f'A janela selecionada possui {len(forecast)} horas E3; esperado 24.')
        climate = read_table(climate_path) if climate_path.exists() else None
        supply = read_table(supply_path) if supply_path.exists() else None
        signal = build_real_system_signal(
            forecast=forecast,
            load_history=read_table(load_path),
            climate_context=climate,
            run_id=f"web-replay-{issue.strftime('%Y%m%dT%H%MZ')}",
            calendar_timezone=DISPLAY_TIMEZONE,
            observed_supply_backtest=supply,
        )
        return signal, w
    z = _load_current_signal(region)
    if len(z) != 24:
        raise ValueError('system_signal_v1 de replay não possui 24 horas completas.')
    return z, w


def resolve_signal(region: str, mode: str = 'replay', replay_key: str | None = None) -> tuple[pd.DataFrame, dict]:
    mode = str(mode or 'replay').lower()
    if mode == 'operational':
        status = operational_status(region)
        if not status.get('available'):
            raise ValueError(status.get('reason') or 'Modo operacional indisponível.')
        return _load_current_signal(region), status
    if mode != 'replay':
        raise ValueError('Modo de simulação inválido; use replay ou operational.')
    return _signal_for_replay(region, replay_key)


def _extract_d_context(flags_raw) -> tuple[str, int | None]:
    try:
        flags = json.loads(flags_raw) if isinstance(flags_raw, str) else list(flags_raw or [])
    except Exception:
        flags = []
    method = next((str(x).replace('DEMAND_PERCENTILE_CONTEXT_', '') for x in flags if str(x).startswith('DEMAND_PERCENTILE_CONTEXT_')), 'HOUR_MONTH')
    n_raw = next((str(x).replace('DEMAND_PERCENTILE_REFERENCE_N_', '') for x in flags if str(x).startswith('DEMAND_PERCENTILE_REFERENCE_N_')), '')
    try:
        n = int(n_raw)
    except Exception:
        n = None
    return method, n


def simulate_customer(
    *,
    region: str,
    cnpj: str,
    distributor: str,
    profile: str,
    monthly_kwh: float,
    customer_type: str,
    mode: str = 'replay',
    replay_key: str | None = None,
    flexible_fraction: float = 0.20,
):
    tariffs_path = _dataset('data/processed/tariff/base_tariffs.parquet', TARIFFS)
    if not tariffs_path.exists():
        raise ValueError('Tarifas processadas ainda não existem; prepare GeoJSON + tarifas ANEEL na etapa Dados.')
    signal, window = resolve_signal(region, mode, replay_key)
    tariffs = read_table(tariffs_path)
    z = signal[(signal.zone_type.astype(str) == 'SUBSYSTEM') & (signal.zone_id.astype(str) == region)].copy()
    if len(z) != 24:
        raise ValueError(f'Região {region} não possui exatamente 24 horas de sinal para a janela escolhida.')

    # Validate the selected tariff agent still belongs to the clicked concession CNPJ.
    if 'distributor_cnpj' in tariffs.columns:
        valid = tariffs[
            tariffs.distributor_cnpj.astype(str).str.replace(r'\D', '', regex=True).str.zfill(14).eq(cnpj_digits(cnpj))
        ]
        if distributor not in set(valid.distributor_id.astype(str)):
            raise ValueError('O perfil selecionado não pertence à área de concessão clicada.')

    ts = z.interval_start_utc
    daily = float(monthly_kwh) / 30.4375
    consumption = synthetic_daily_profile(daily, customer_type, ts, timezone_name=DISPLAY_TIMEZONE)
    out, sim = simulate_dynamic_tariff(
        system_signal=signal,
        base_tariffs=tariffs,
        distributor_id=distributor,
        profile_id=profile,
        subsystem_id=region,
        config=load_tariff_config(),
        run_id='web-customer-mvp',
        post_rules=None,
        consumption_ref_kwh=consumption.consumption_kwh.to_numpy(float),
    )

    optimized_values, optimization_meta = optimize_flexible_consumption(
        consumption.consumption_kwh.to_numpy(float),
        out.dynamic_tariff_rs_kwh.to_numpy(float),
        flexible_fraction=float(flexible_fraction),
    )
    optimized = consumption[['interval_start_utc']].copy()
    optimized['optimized_consumption_kwh'] = optimized_values

    info = distributor_info(cnpj) or {}
    meta = {
        'distributor_id': distributor,
        'distributor_cnpj': cnpj_digits(cnpj),
        'concession_sigla': info.get('sigla'),
        'concession_name': info.get('razao_social'),
        'tariff_profile_id': profile,
        'subsystem_id': region,
        'customer_type': customer_type,
        'profile_source': str(consumption.profile_source.iloc[0]),
        'daily_consumption_kwh': float(consumption.consumption_kwh.sum()),
    }
    result = build_customer_result(tariff=out, consumption=consumption, simulation_report=sim, customer_meta=meta)
    result['concession'] = info
    result['simulation_mode'] = str(mode or 'replay').lower()
    result['display_timezone'] = DISPLAY_TIMEZONE
    result['window'] = window
    result['simulation_scope_pt'] = 'Comparação experimental de 24h com TE+TUSD volumétricas; não é previsão integral de fatura regulada.'

    hourly = out.merge(consumption[['interval_start_utc', 'consumption_kwh']], on='interval_start_utc', how='left')
    hourly = hourly.merge(optimized, on='interval_start_utc', how='left')
    hourly = hourly.merge(
        z[['interval_start_utc', 'demand_p50_mw', 'quality_flags']],
        on='interval_start_utc',
        how='left',
        validate='one_to_one',
    )

    original_dynamic = float((hourly['consumption_kwh'] * hourly['dynamic_tariff_rs_kwh']).sum())
    optimized_dynamic = float((hourly['optimized_consumption_kwh'] * hourly['dynamic_tariff_rs_kwh']).sum())
    potential_savings = original_dynamic - optimized_dynamic
    result['optimization'] = {
        **optimization_meta,
        'flexible_percent': 100.0 * float(optimization_meta.get('flexible_fraction', 0.0)),
        'original_dynamic_cost_24h_rs': original_dynamic,
        'optimized_dynamic_cost_24h_rs': optimized_dynamic,
        'potential_savings_24h_rs': potential_savings,
        'potential_savings_pct': (100.0 * potential_savings / original_dynamic) if original_dynamic else 0.0,
        'potential_savings_month_rs': potential_savings * 30.4375,
        'method': 'SHIFT_FLEXIBLE_ENERGY_TO_CHEAPEST_HOURS_WITH_HEADROOM',
        'is_illustrative': True,
    }
    return result, hourly
