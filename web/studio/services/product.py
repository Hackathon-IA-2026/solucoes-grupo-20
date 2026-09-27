from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from django.conf import settings

from motor_sin.common.io import read_table
from motor_sin.signals.real_signal import build_real_system_signal, enrich_signal_with_dessem
from motor_tarifa.customer.optimize import optimize_flexible_consumption, summarize_load_shift
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
MODEL_VALIDATION = ROOT / 'outputs/metrics/model_validation'
LOAD_HISTORY = ROOT / 'data/processed/demand/load_hourly.parquet'
E3_CLIMATE = ROOT / 'data/processed/climate/zone_climate_hourly_e3.parquet'
SUPPLY_HISTORY = ROOT / 'data/processed/generation/supply_by_subsystem_hourly.parquet'
DESSEM_SCHEDULE = ROOT / 'data/processed/generation/dessem_schedule_hourly.parquet'

RESIDENTIAL_APPLIANCES = (
    {'key': 'air_conditioner', 'name': 'Ar-condicionado', 'power_kw': 1.20, 'duration_hours': 3.0, 'usual_hours': (22, 23, 0, 1, 2, 3, 4, 5), 'guidance': 'Pré-resfrie o ambiente e reduza a potência nas horas mais caras.'},
    {'key': 'air_fryer', 'name': 'Air fryer', 'power_kw': 1.50, 'duration_hours': 0.5, 'usual_hours': (11, 12, 13, 18, 19, 20, 21), 'guidance': 'Antecipe ou atrase o preparo dentro da rotina da refeição.'},
    {'key': 'hair_dryer', 'name': 'Secador de cabelo', 'power_kw': 1.20, 'duration_hours': 0.25, 'usual_hours': (6, 7, 8, 18, 19, 20, 21), 'guidance': 'Concentre o uso curto em uma faixa de menor sinal.'},
    {'key': 'dishwasher', 'name': 'Lava-louças', 'power_kw': 1.20, 'duration_hours': 1.5, 'usual_hours': (20, 21, 22, 23, 0, 1, 2, 3, 4, 5), 'guidance': 'Use o início programado após o último uso da cozinha.'},
    {'key': 'ev_charging', 'name': 'Carregamento elétrico', 'power_kw': 7.40, 'duration_hours': 4.0, 'usual_hours': (21, 22, 23, 0, 1, 2, 3, 4, 5, 6), 'guidance': 'Programe o carregador para completar a carga antes da saída.'},
)


def _dataset(relative_path: str, local_path: Path) -> Path:
    return dataset_path(relative_path, local_path)


def _path_exists(relative_path: str, local_path: Path) -> bool:
    return _dataset(relative_path, local_path).exists()


def _dessem_schedule() -> pd.DataFrame:
    path = _dataset('data/processed/generation/dessem_schedule_hourly.parquet', DESSEM_SCHEDULE)
    return read_table(path) if path.exists() else pd.DataFrame()


def _contextual_predictions(region: str | None = None) -> tuple[pd.DataFrame, Path | None]:
    tags = {'N': 'n', 'NE': 'ne', 'S': 's', 'SE/CO': 'seco'}
    directory = _dataset('outputs/metrics/model_validation', MODEL_VALIDATION)
    candidates: list[tuple[float, Path]] = []
    if region in tags and directory.exists():
        for path in directory.glob(f'auto_e3_*_{tags[region]}_2023_2026_predictions.parquet'):
            metrics_path = path.with_name(path.name.replace('_predictions.parquet', '_metrics.csv'))
            score = float('inf')
            if metrics_path.exists():
                metrics = read_table(metrics_path)
                overall = metrics[
                    metrics.experiment.astype(str).eq('E3')
                    & metrics.segment.astype(str).eq('ALL')
                    & metrics.horizon.astype(str).eq('ALL')
                ]
                if len(overall):
                    score = float(overall.iloc[0].WAPE)
            candidates.append((score, path))
    legacy = _dataset('outputs/metrics/e3_real_pilot_predictions.parquet', E3_PREDICTIONS)
    if candidates:
        path = min(candidates, key=lambda item: item[0])[1]
    elif legacy.exists():
        path = legacy
    else:
        return pd.DataFrame(), None
    predictions = read_table(path)
    if 'experiment' in predictions.columns:
        predictions = predictions[predictions.experiment.astype(str).eq('E3')]
    if region:
        predictions = predictions[predictions.subsystem_id.astype(str).eq(str(region))]
    return predictions.copy(), path


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
    issue_local = issue_time_utc.tz_convert(DISPLAY_TZ) if issue_time_utc is not None else None
    selection_label = (
        f"Emissão {issue_local.strftime('%d/%m/%Y %Hh')} · horizonte até {last_local.strftime('%d/%m %Hh')}"
        if issue_local is not None else label
    )
    return {
        'key': key,
        'label': label,
        'selection_label': selection_label,
        'local_date': first_local.date().isoformat(),
        'local_start': first_local.isoformat(),
        'local_end': last_local.isoformat(),
        'local_end_label': last_local.strftime('%d/%m/%Y %Hh'),
        'issue_local': issue_local.isoformat() if issue_local is not None else None,
        'issue_local_date': issue_local.date().isoformat() if issue_local is not None else None,
        'issue_local_time': issue_local.strftime('%H:%M') if issue_local is not None else None,
        'issue_local_label': issue_local.strftime('%d/%m/%Y %Hh') if issue_local is not None else None,
        'timezone': DISPLAY_TIMEZONE,
        'source': source,
        'issue_time_utc': issue_time_utc.isoformat() if issue_time_utc is not None else None,
    }


def replay_windows(region: str | None = None) -> list[dict]:
    """List historical 24h windows available for the product replay selector."""
    windows: list[dict] = []
    schedule = _dessem_schedule()
    if schedule.empty:
        return windows
    coverage = schedule[['interval_start_utc', 'subsystem_id']].copy()
    coverage['interval_start_utc'] = pd.to_datetime(coverage['interval_start_utc'], utc=True)
    signal_path = _dataset('outputs/contracts/system_signal_v1.parquet', SIGNAL)
    p, predictions_path = _contextual_predictions(region)
    if predictions_path is not None and not p.empty:
        if {'issue_time_utc', 'interval_start_utc', 'subsystem_id'}.issubset(p.columns):
            p = p.copy()
            p['issue_time_utc'] = pd.to_datetime(p['issue_time_utc'], utc=True, errors='coerce')
            p['interval_start_utc'] = pd.to_datetime(p['interval_start_utc'], utc=True, errors='coerce')
            p = p.dropna(subset=['issue_time_utc', 'interval_start_utc'])
            p = p.merge(coverage, on=['interval_start_utc', 'subsystem_id'], how='inner', validate='many_to_one')
            for issue, g in p.groupby('issue_time_utc'):
                g = g.drop_duplicates(['interval_start_utc', 'subsystem_id'])
                if region:
                    ok = len(g) == 24 and g['interval_start_utc'].nunique() == 24 and g['interval_start_utc'].sort_values().diff().dropna().eq(pd.Timedelta(hours=1)).all()
                else:
                    counts = g.groupby('subsystem_id')['interval_start_utc'].nunique()
                    ok = bool(len(counts) and counts.max() >= 24)
                if not ok:
                    continue
                key = pd.Timestamp(issue).isoformat()
                windows.append(_window_descriptor(g.sort_values('interval_start_utc').head(24), key=key, source='CONTEXTUAL_CLIMATE_BACKTEST', issue_time_utc=pd.Timestamp(issue)))
    if not windows and signal_path.exists():
        s = read_table(signal_path)
        s = s[s['zone_type'].astype(str).eq('SUBSYSTEM')].copy()
        s['interval_start_utc'] = pd.to_datetime(s['interval_start_utc'], utc=True)
        s = s.merge(coverage.rename(columns={'subsystem_id': 'zone_id'}), on=['interval_start_utc', 'zone_id'], how='inner', validate='many_to_one')
        if region:
            s = s[s['zone_id'].astype(str).eq(str(region))]
        if len(s) >= 24 and s.sort_values('interval_start_utc').head(24)['interval_start_utc'].diff().dropna().eq(pd.Timedelta(hours=1)).all():
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


def _residential_guidance(hourly: pd.DataFrame) -> list[dict]:
    work = hourly.copy()
    work['local_time'] = pd.to_datetime(work['interval_start_utc'], utc=True).dt.tz_convert(DISPLAY_TZ)
    work['hour'] = work['local_time'].dt.hour
    tariff = pd.to_numeric(work['dynamic_tariff_rs_kwh'], errors='raise')
    guidance = []
    for appliance in RESIDENTIAL_APPLIANCES:
        candidates = work[work['hour'].isin(appliance['usual_hours'])]
        if candidates.empty:
            candidates = work
        best = candidates.loc[candidates['dynamic_tariff_rs_kwh'].idxmin()]
        reference_rate = float(candidates['dynamic_tariff_rs_kwh'].max())
        best_rate = float(best['dynamic_tariff_rs_kwh'])
        energy_kwh = float(appliance['power_kw'] * appliance['duration_hours'])
        guidance.append({
            **appliance,
            'energy_kwh': energy_kwh,
            'recommended_time': best['local_time'].strftime('%d/%m às %Hh'),
            'estimated_saving_per_use_rs': max(0.0, energy_kwh * (reference_rate - best_rate)),
            'best_rate_rs_kwh': best_rate,
        })
    return guidance


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
    if 'DESSEM_REPLAY_NOT_ASOF' in flags:
        return {'available': False, 'reason': 'O DESSEM desta janela foi capturado depois da emissão da previsão; disponível somente como cenário retrospectivo.'}
    if not z['supply_pressure'].notna().all() or not all('DESSEM_SCHEDULE_COMPARISON_PROXY' in json.loads(raw) for raw in z['quality_flags']):
        return {'available': False, 'reason': 'A previsão operacional requer 24 horas de programação DESSEM válida.'}
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
        raise ValueError(f'Não há janela de 24h com previsão Predicta e DESSEM completos para {region}.')
    predictions, predictions_path = _contextual_predictions(region)
    load_path = _dataset('data/processed/demand/load_hourly.parquet', LOAD_HISTORY)
    climate_path = _dataset('data/processed/climate/zone_climate_hourly_e3.parquet', E3_CLIMATE)
    supply_path = _dataset('data/processed/generation/supply_by_subsystem_hourly.parquet', SUPPLY_HISTORY)
    if w['source'] in {'E3_BACKTEST', 'CONTEXTUAL_CLIMATE_BACKTEST'} and predictions_path is not None:
        if not load_path.exists():
            raise ValueError('Histórico de carga não encontrado; necessário para reconstruir D no replay.')
        p = predictions
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
            dessem_schedule=_dessem_schedule(),
            allow_dessem_replay=True,
            require_dessem=True,
        )
        return signal, w
    z = _load_current_signal(region)
    if len(z) != 24:
        raise ValueError('system_signal_v1 de replay não possui 24 horas completas.')
    issue_raw = json.loads(z['main_drivers_json'].iloc[0]).get('dessem', {}).get('forecast_issue_time_utc')
    return enrich_signal_with_dessem(
        z, _dessem_schedule(), issue_time_utc=pd.Timestamp(issue_raw) if issue_raw else None,
        allow_replay=True, required=True,
    ), w


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
    optimization_objective: str = 'cost',
    portfolio_customers: int = 1000,
    participation_pct: float = 100.0,
):
    if isinstance(portfolio_customers, bool) or not isinstance(portfolio_customers, int) or not 1 <= portfolio_customers <= 1_000_000:
        raise ValueError('A carteira simulada deve ter entre 1 e 1.000.000 clientes inteiros.')
    if not np.isfinite(participation_pct) or not 0 <= participation_pct <= 100:
        raise ValueError('A adesão deve ficar entre 0% e 100%.')
    tariffs_path = _dataset('data/processed/tariff/base_tariffs.parquet', TARIFFS)
    if not tariffs_path.exists():
        raise ValueError('Tarifas processadas ainda não existem; prepare GeoJSON + tarifas ANEEL na etapa Dados.')
    signal, window = resolve_signal(region, mode, replay_key)
    tariffs = read_table(tariffs_path)
    z = signal[(signal.zone_type.astype(str) == 'SUBSYSTEM') & (signal.zone_id.astype(str) == region)].copy()
    if len(z) != 24:
        raise ValueError(f'Região {region} não possui exatamente 24 horas de sinal para a janela escolhida.')
    dessem = [json.loads(raw).get('dessem', {}) for raw in z['main_drivers_json']]
    if not all('programmed_load_mw' in record for record in dessem):
        raise ValueError('DESSEM obrigatório: a janela não contém a programação oficial completa.')
    z['dessem_programmed_load_mw'] = [record['programmed_load_mw'] for record in dessem]
    z['dessem_relative_gap_pct'] = [record['relative_gap_pct'] for record in dessem]

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
        objective=optimization_objective,
    )
    optimized = consumption[['interval_start_utc']].copy()
    optimized['optimized_consumption_kwh'] = optimized_values
    optimized['consumer_optimized_consumption_kwh'] = optimized_values

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
    result['projection'] = {
        'days': 30.4375,
        'method': 'REPEAT_SELECTED_24H_AVERAGE_MONTH',
        'is_forecast': False,
    }
    result['dessem'] = {
        'source': 'ONS_DESSEM_BALANCO_GERAL',
        'hours': len(dessem),
        'retrospective': any(record['mode'] == 'RETROSPECTIVE_SCENARIO' for record in dessem),
        'captured_at_utc': max(record['available_at_utc'] for record in dessem),
        'snapshot_sha256': sorted({record['snapshot_sha256'] for record in dessem}),
        'source_urls': sorted({record['source_url'] for record in dessem}),
    }
    result['simulation_scope_pt'] = 'Comparação experimental de 24h com TE+TUSD volumétricas; não é previsão integral de fatura regulada.'

    hourly = out.merge(consumption[['interval_start_utc', 'consumption_kwh']], on='interval_start_utc', how='left')
    hourly = hourly.merge(optimized, on='interval_start_utc', how='left')
    hourly = hourly.merge(
        z[['interval_start_utc', 'demand_p50_mw', 'dessem_programmed_load_mw', 'dessem_relative_gap_pct', 'quality_flags']],
        on='interval_start_utc',
        how='left',
        validate='one_to_one',
        suffixes=('_tariff', ''),
    )

    # Realized ONS load is only available for replay windows; operational hours stay null.
    obs_path = _dataset('data/processed/demand/load_hourly.parquet', LOAD_HISTORY)
    if obs_path.exists():
        obs = read_table(obs_path)
        obs = obs[obs['subsystem_id'].astype(str).eq(str(region))][['interval_start_utc', 'load_mw']].copy()
        obs['interval_start_utc'] = pd.to_datetime(obs['interval_start_utc'], utc=True, errors='coerce')
        obs = obs.dropna(subset=['interval_start_utc']).drop_duplicates('interval_start_utc')
        hourly = hourly.merge(
            obs.rename(columns={'load_mw': 'actual_load_mw'}),
            on='interval_start_utc', how='left', validate='one_to_one',
        )
    else:
        hourly['actual_load_mw'] = np.nan

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
        'potential_savings_month_rs': potential_savings * result['projection']['days'],
        'method': ('MINIMIZE_VARIANCE_WITH_ENERGY_PEAK_AND_COST_CONSTRAINTS' if optimization_objective == 'flatten'
                   else 'SHIFT_FLEXIBLE_ENERGY_TO_CHEAPEST_HOURS_WITH_HEADROOM'),
        'load_shape': summarize_load_shift(hourly.consumption_kwh, hourly.optimized_consumption_kwh),
        'is_illustrative': True,
    }
    result['consumer'] = {
        **optimization_meta,
        'current_cost_24h_rs': original_dynamic,
        'optimized_cost_24h_rs': optimized_dynamic,
        'savings_24h_rs': potential_savings,
        'savings_month_rs': potential_savings * result['projection']['days'],
        'savings_pct': 100.0 * potential_savings / original_dynamic if original_dynamic else 0.0,
        'guidance': _residential_guidance(hourly),
        'is_illustrative': True,
    }
    participating = int(np.floor(portfolio_customers * participation_pct / 100 + 0.5))
    portfolio_before = hourly.consumption_kwh.to_numpy(float) * portfolio_customers
    portfolio_after = (
        hourly.consumption_kwh.to_numpy(float) * (portfolio_customers - participating)
        + hourly.optimized_consumption_kwh.to_numpy(float) * participating
    )
    shape = summarize_load_shift(portfolio_before, portfolio_after)
    hourly['portfolio_before_mw'] = portfolio_before / 1000
    hourly['portfolio_after_mw'] = portfolio_after / 1000
    result['portfolio'] = {
        'customer_count': portfolio_customers,
        'participating_customers': participating,
        'participation_pct': 100 * participating / portfolio_customers,
        'requested_participation_pct': float(participation_pct),
        'customer_savings_24h_rs': potential_savings * participating,
        'customer_savings_month_rs': potential_savings * participating * result['projection']['days'],
        'savings_scope': 'PARTICIPATING_CONSUMERS_NOT_DISTRIBUTOR_PROFIT',
        'peak_before_mw': shape['peak_before_kw'] / 1000,
        'peak_after_mw': shape['peak_after_kw'] / 1000,
        'peak_reduction_mw': (shape['peak_before_kw'] - shape['peak_after_kw']) / 1000,
        'energy_before_mwh': shape['energy_before_kwh'] / 1000,
        'energy_after_mwh': shape['energy_after_kwh'] / 1000,
        'load_shape': shape,
        'profile_assumption': 'IDENTICAL_SYNTHETIC_HOURLY_CUSTOMER_PROFILES',
        'scope': 'SIMULATED_PORTFOLIO_NOT_TOTAL_DISTRIBUTOR_LOAD',
        'is_illustrative': True,
    }
    return result, hourly
