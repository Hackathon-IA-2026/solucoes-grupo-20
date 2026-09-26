from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from django.conf import settings

from motor_sin.common.io import read_table
from motor_sin.grid.index import coordinate_to_index
from .distribution import geojson_payload

ROOT = Path(settings.PREDICTA_PROJECT_ROOT)
DISPLAY_TZ = ZoneInfo('America/Sao_Paulo')

PLANTS_JSON = ROOT / 'configs/generation_assets_catalog.json'
LOAD_PATH = ROOT / 'data/processed/demand/load_hourly.parquet'
SUPPLY_PATH = ROOT / 'data/processed/generation/supply_by_subsystem_hourly.parquet'
CLIMATE_E3_PATH = ROOT / 'data/processed/climate/zone_climate_hourly_e3.parquet'
CLIMATE_E2_PATH = ROOT / 'data/processed/climate/zone_climate_hourly.parquet'
E3_DAILY_PATH = ROOT / 'data/processed/climate/e3_daily_context_all_regions.parquet'
E3_DAILY_FALLBACK = ROOT / 'data/processed/climate/e3_daily_context.parquet'
POINT_GLOB = 'e2_*_points.csv'

SUBSYSTEM_ALIASES = {
    'SECO': 'SE/CO',
    'SE/CO': 'SE/CO',
    'SUDESTE/CENTRO-OESTE': 'SE/CO',
    'SUL': 'S',
    'S': 'S',
    'NORDESTE': 'NE',
    'NE': 'NE',
    'NORTE': 'N',
    'N': 'N',
    'SIN': 'SIN',
}

EVENT_META = {
    'storm': {'label': 'Tempestade', 'color': '#7c3aed'},
    'wind': {'label': 'Vento', 'color': '#2563eb'},
    'rain': {'label': 'Chuva', 'color': '#0f766e'},
    'heat': {'label': 'Calor', 'color': '#dc2626'},
    'cold': {'label': 'Frio', 'color': '#0891b2'},
    'none': {'label': 'Sem evento', 'color': '#94a3b8'},
}


def canonical_subsystem(value: str | None) -> str:
    key = str(value or '').strip().upper()
    return SUBSYSTEM_ALIASES.get(key, key)


def _safe_read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return read_table(path)
    except Exception:
        return pd.DataFrame()


def _to_local_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors='coerce').dt.tz_convert(DISPLAY_TZ).dt.date


def _fmt_num(value: float | int | None, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return '—'
    return f'{float(value):,.{digits}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _pearson(x: pd.Series, y: pd.Series) -> float | None:
    pair = pd.DataFrame({'x': pd.to_numeric(x, errors='coerce'), 'y': pd.to_numeric(y, errors='coerce')}).dropna()
    if len(pair) < 3:
        return None
    val = pair['x'].corr(pair['y'])
    if pd.isna(val):
        return None
    return float(val)


def _haversine_km(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    r = 6371.0
    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * r * np.arcsin(np.sqrt(a))


def load_plants() -> pd.DataFrame:
    if not PLANTS_JSON.exists():
        return pd.DataFrame()
    payload = json.loads(PLANTS_JSON.read_text(encoding='utf-8'))
    plants = pd.DataFrame(payload.get('usinas', []))
    if plants.empty:
        return plants
    plants = plants.rename(columns={
        'nome_siga': 'plant_name',
        'nome_ons': 'plant_name_ons',
        'fonte_nome': 'source_name',
        'fonte': 'source_key',
        'capacidade_instalada_mw': 'capacity_mw',
        'geracao_media_mw': 'generation_avg_mw',
        'localizacao_tipo': 'location_type',
        'confianca': 'confidence',
    })
    plants['subsystem_id'] = plants['subsistema'].map(canonical_subsystem)
    plants['uf'] = plants['uf'].astype(str).str[:2]
    plants['capacity_mw'] = pd.to_numeric(plants['capacity_mw'], errors='coerce')
    plants['generation_avg_mw'] = pd.to_numeric(plants['generation_avg_mw'], errors='coerce')
    plants['latitude'] = pd.to_numeric(plants['latitude'], errors='coerce')
    plants['longitude'] = pd.to_numeric(plants['longitude'], errors='coerce')
    plants = plants.dropna(subset=['latitude', 'longitude'])
    plants['cell_id']=[coordinate_to_index(float(a),float(b)).cell_id for a,b in zip(plants['latitude'],plants['longitude'])]
    return plants


def load_points(subsystem_id: str | None = None) -> pd.DataFrame:
    rows = []
    grid_files = sorted((ROOT / 'data/processed/grid').glob('climate_points_*_01deg.csv'))
    source_files = grid_files if grid_files else sorted((ROOT / 'configs').glob(POINT_GLOB))
    for path in source_files:
        try:
            part = pd.read_csv(path)
        except Exception:
            continue
        rows.append(part)
    if not rows:
        return pd.DataFrame(columns=['point_id', 'name', 'state', 'subsystem_id', 'latitude', 'longitude', 'timezone', 'weight'])
    # Alguns artefatos de grade climática (ex.: climate_points_*_01deg.csv)
    # usam cell_id em vez de point_id. O loader da interface não deve assumir
    # que todo CSV encontrado é um artefato territorial já normalizado.
    if not rows:
        return pd.DataFrame(columns=['point_id'])

    normalized_rows = []
    for frame in rows:
        if frame is None:
            continue
        frame = frame.copy()

        if 'point_id' not in frame.columns:
            if 'cell_id' in frame.columns:
                # Grade canônica 0,1° / ARCO: a célula é o identificador estável.
                frame['point_id'] = frame['cell_id'].astype(str)
            elif frame.empty:
                continue
            else:
                # CSV sem identificador territorial reconhecível: não deve
                # derrubar a página nem contaminar o conjunto de pontos.
                continue

        normalized_rows.append(frame)

    if not normalized_rows:
        return pd.DataFrame(columns=['point_id'])

    df = pd.concat(normalized_rows, ignore_index=True, sort=False)

    if df.empty:
        return df

    df = df.drop_duplicates('point_id')
    # Compatibilidade entre artefatos territoriais legados e a grade
    # climática canônica usada pelo ERA5-Land ARCO.
    #
    # Os climate_points_*_01deg.csv têm cell_id/latitude/longitude e podem
    # não carregar subsystem_id, pois o subsistema já é conhecido pelo
    # argumento desta função. Não devemos derrubar a interface por isso.
    if 'subsystem_id' not in df.columns:
        df['subsystem_id'] = canonical_subsystem(subsystem_id)
    else:
        df['subsystem_id'] = df['subsystem_id'].map(canonical_subsystem)
        # Se algum artefato trouxe subsystem_id vazio, o contexto da chamada
        # é a fonte autoritativa para completar o valor.
        df['subsystem_id'] = df['subsystem_id'].fillna(
            canonical_subsystem(subsystem_id)
        )
    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
    if 'cell_id' not in df.columns:
        df['cell_id']=[coordinate_to_index(float(a),float(b)).cell_id if pd.notna(a) and pd.notna(b) else None for a,b in zip(df['latitude'],df['longitude'])]
    if subsystem_id:
        df = df[df['subsystem_id'].eq(canonical_subsystem(subsystem_id))]
    return df.dropna(subset=['latitude', 'longitude'])

def _daily_context() -> pd.DataFrame:
    path = E3_DAILY_PATH if E3_DAILY_PATH.exists() else E3_DAILY_FALLBACK
    return _safe_read(path)


def available_event_dates(subsystem_id: str | None = None) -> list[date]:
    ctx = _daily_context()
    if ctx.empty or 'date_local' not in ctx.columns:
        return []
    if subsystem_id and 'subsystem_id' in ctx.columns:
        ctx['subsystem_id'] = ctx['subsystem_id'].map(canonical_subsystem)
        ctx = ctx[ctx['subsystem_id'].eq(canonical_subsystem(subsystem_id))]
    dates = pd.to_datetime(ctx['date_local'], errors='coerce').dt.date.dropna().drop_duplicates().sort_values()
    return dates.tolist()


def default_event_date(subsystem_id: str | None = None) -> date | None:
    dates = available_event_dates(subsystem_id)
    return dates[-1] if dates else None


def _classify_event(row: pd.Series) -> str:
    if bool(row.get('storm_candidate', False)):
        return 'storm'
    if bool(row.get('wind_event', False)) or bool(row.get('strong_wind_day', False)) or bool(row.get('severe_wind_day', False)) or bool(row.get('extreme_wind_day', False)):
        return 'wind'
    if bool(row.get('rain_event', False)) or bool(row.get('heavy_rain_day', False)) or bool(row.get('extreme_rain_day', False)):
        return 'rain'
    if bool(row.get('heat_event', False)) or bool(row.get('extreme_heat_day', False)) or bool(row.get('unusually_hot_day', False)) or bool(row.get('heat_wave_candidate', False)):
        return 'heat'
    if bool(row.get('cold_event', False)) or bool(row.get('extreme_cold_day', False)) or bool(row.get('unusually_cold_day', False)) or bool(row.get('cold_wave_candidate', False)):
        return 'cold'
    return 'none'


def event_points_for_date(subsystem_id: str, selected_date: date | None) -> pd.DataFrame:
    points = load_points(subsystem_id)
    if points.empty:
        return []
    ctx = _daily_context()
    if points.empty or ctx.empty:
        return pd.DataFrame()
    ctx['subsystem_id'] = ctx['subsystem_id'].map(canonical_subsystem)
    ctx = ctx[ctx['subsystem_id'].eq(canonical_subsystem(subsystem_id))].copy()
    ctx['date_local'] = pd.to_datetime(ctx['date_local'], errors='coerce').dt.date
    if selected_date:
        ctx = ctx[ctx['date_local'].eq(selected_date)]
    if ctx.empty:
        return pd.DataFrame()
    merged = points.merge(ctx, on=['point_id', 'subsystem_id'], how='inner', suffixes=('', '_ctx'))
    if merged.empty:
        return merged
    merged['event_type'] = merged.apply(_classify_event, axis=1)
    merged['event_label'] = merged['event_type'].map(lambda x: EVENT_META.get(x, EVENT_META['none'])['label'])
    merged['event_color'] = merged['event_type'].map(lambda x: EVENT_META.get(x, EVENT_META['none'])['color'])
    merged['has_event'] = merged['event_type'].ne('none')
    merged['severity_score'] = (
        merged['event_type'].map({'storm': 5, 'wind': 4, 'rain': 3, 'heat': 2, 'cold': 1, 'none': 0}).astype(float)
        + pd.to_numeric(merged.get('temperature_max_anomaly_c'), errors='coerce').fillna(0).clip(lower=0) * 0.1
        + pd.to_numeric(merged.get('precipitation_sum'), errors='coerce').fillna(0) * 0.01
        + pd.to_numeric(merged.get('wind_gusts_10m_max'), errors='coerce').fillna(0) * 0.005
    )
    return merged.sort_values(['has_event', 'severity_score'], ascending=[False, False]).reset_index(drop=True)


def plant_exposure_for_date(subsystem_id: str, selected_date: date | None, max_distance_km: float = 300.0) -> pd.DataFrame:
    plants = load_plants()
    plants = plants[plants['subsystem_id'].eq(canonical_subsystem(subsystem_id))].copy()
    events = event_points_for_date(subsystem_id, selected_date)
    if plants.empty:
        return plants
    if events.empty or not events['has_event'].any():
        plants['near_event'] = False
        plants['nearest_event_type'] = 'none'
        plants['nearest_event_label'] = EVENT_META['none']['label']
        plants['distance_to_event_km'] = np.nan
        return plants.sort_values(['capacity_mw', 'generation_avg_mw'], ascending=False).reset_index(drop=True)
    active = events[events['has_event']].copy()
    exact_pos = {str(cell): pos for pos, cell in enumerate(active['cell_id'].astype(str).tolist())} if 'cell_id' in active.columns else {}
    plant_coords = plants[['latitude', 'longitude']].to_numpy(dtype=float)
    event_coords = active[['latitude', 'longitude']].to_numpy(dtype=float)
    nearest_ix = []; nearest_dist = []
    for _, plant in plants.iterrows():
        if str(plant.get('cell_id')) in exact_pos:
            nearest_ix.append(int(exact_pos[str(plant.get('cell_id'))])); nearest_dist.append(0.0); continue
        lat=float(plant['latitude']);lon=float(plant['longitude']);d=_haversine_km(np.full(len(event_coords),lat),np.full(len(event_coords),lon),event_coords[:,0],event_coords[:,1]);j=int(np.nanargmin(d));nearest_ix.append(j);nearest_dist.append(float(d[j]))
    plants['distance_to_event_km'] = nearest_dist
    plants['near_event'] = plants['distance_to_event_km'].le(float(max_distance_km))
    nearest = active.iloc[nearest_ix].reset_index(drop=True)
    plants['nearest_event_type'] = nearest['event_type'].values
    plants['nearest_event_label'] = nearest['event_label'].values
    plants['nearest_event_point'] = nearest['name'].values
    plants['event_color'] = nearest['event_color'].values
    plants['exposure_method'] = np.where(plants['distance_to_event_km'].eq(0), 'EXACT_01DEG_CELL', 'NEAREST_ACTIVE_GRID_CELL')
    return plants.sort_values(['near_event', 'capacity_mw', 'generation_avg_mw'], ascending=[False, False, False]).reset_index(drop=True)


def _merged_hourly(subsystem_id: str) -> pd.DataFrame:
    load = _safe_read(LOAD_PATH)
    climate = _safe_read(CLIMATE_E3_PATH)
    if climate.empty:
        climate = _safe_read(CLIMATE_E2_PATH)
    supply = _safe_read(SUPPLY_PATH)
    zone = canonical_subsystem(subsystem_id)
    if load.empty:
        return pd.DataFrame()
    load['subsystem_id'] = load['subsystem_id'].map(canonical_subsystem)
    load['interval_start_utc'] = pd.to_datetime(load['interval_start_utc'], utc=True, errors='coerce')
    load = load[load['subsystem_id'].eq(zone)][['interval_start_utc', 'subsystem_id', 'load_mw']].copy()
    out = load
    if not supply.empty:
        supply['subsystem_id'] = supply['subsystem_id'].map(canonical_subsystem)
        supply['interval_start_utc'] = pd.to_datetime(supply['interval_start_utc'], utc=True, errors='coerce')
        keep = [c for c in ['interval_start_utc', 'subsystem_id', 'generation_total_mw', 'generation_hydro_mw', 'generation_thermal_mw', 'generation_wind_mw', 'generation_solar_mw'] if c in supply.columns]
        out = out.merge(supply[supply['subsystem_id'].eq(zone)][keep], on=['interval_start_utc', 'subsystem_id'], how='left')
    if not climate.empty:
        climate['subsystem_id'] = climate['subsystem_id'].map(canonical_subsystem)
        climate['interval_start_utc'] = pd.to_datetime(climate['interval_start_utc'], utc=True, errors='coerce')
        keep = [c for c in climate.columns if c in {'interval_start_utc', 'subsystem_id', 'temperature_2m_mean', 'temperature_2m_p90', 'precipitation_mean', 'wind_speed_10m_mean', 'solar_radiation_mean', 'incident_cell_fraction', 'incident_heat_fraction', 'incident_cold_fraction', 'incident_rain_fraction', 'incident_wind_fraction', 'incident_solar_deficit_fraction', 'temperature_max_anomaly_c_mean', 'temperature_min_anomaly_c_mean', 'incident_event_any_fraction', 'incident_storm_fraction'}]
        out = out.merge(climate[climate['subsystem_id'].eq(zone)][keep], on=['interval_start_utc', 'subsystem_id'], how='left')
    out['local_date'] = _to_local_date(out['interval_start_utc'])
    out['local_hour'] = pd.to_datetime(out['interval_start_utc'], utc=True, errors='coerce').dt.tz_convert(DISPLAY_TZ).dt.hour
    return out.sort_values('interval_start_utc').reset_index(drop=True)


def territory_summary(subsystem_id: str, selected_date: date | None) -> dict[str, Any]:
    merged = _merged_hourly(subsystem_id)
    events = event_points_for_date(subsystem_id, selected_date)
    plants = plant_exposure_for_date(subsystem_id, selected_date)
    day = merged[merged['local_date'].eq(selected_date)].copy() if (selected_date and not merged.empty) else pd.DataFrame()

    summary = {
        'subsystem_id': canonical_subsystem(subsystem_id),
        'selected_date': selected_date.isoformat() if selected_date else '',
        'has_hourly_data': not merged.empty,
        'has_events': not events.empty,
        'has_plants': not plants.empty,
        'plant_count': int(len(plants)) if not plants.empty else 0,
        'active_event_points': int(events['has_event'].sum()) if not events.empty else 0,
        'plants_near_events': int(plants['near_event'].sum()) if not plants.empty and 'near_event' in plants else 0,
        'capacity_near_events_mw': float(plants.loc[plants['near_event'], 'capacity_mw'].sum()) if not plants.empty and 'near_event' in plants else 0.0,
        'avg_load_mw': float(day['load_mw'].mean()) if not day.empty else None,
        'peak_load_mw': float(day['load_mw'].max()) if not day.empty else None,
        'avg_generation_mw': float(day['generation_total_mw'].mean()) if not day.empty and 'generation_total_mw' in day else None,
    }

    correlations = []
    pairs = [
        ('load_mw', 'temperature_2m_mean', 'Demanda × temperatura média', 'Carga tende a subir/baixar com temperatura absoluta.'),
        ('load_mw', 'incident_heat_fraction', 'Demanda × evento de calor', 'Mede associação entre horas mais quentes/extremas e carga.'),
        ('load_mw', 'incident_rain_fraction', 'Demanda × evento de chuva', 'Ajuda a ver sensibilidade da carga a chuva forte/contínua.'),
        ('generation_hydro_mw', 'incident_rain_fraction', 'Hídrica × evento de chuva', 'Relação de curto prazo entre chuva regional e geração hídrica observada.'),
        ('generation_wind_mw', 'incident_wind_fraction', 'Eólica × evento de vento', 'Relação entre vento regional e geração eólica observada.'),
        ('generation_solar_mw', 'incident_solar_deficit_fraction', 'Solar × déficit solar', 'Relação entre horas com menor disponibilidade solar e geração fotovoltaica.'),
        ('generation_total_mw', 'load_mw', 'Geração total × demanda', 'Contexto físico entre oferta observada e carga no subsistema.'),
    ]
    if not merged.empty:
        for left, right, title, explanation in pairs:
            if left in merged.columns and right in merged.columns:
                val = _pearson(merged[left], merged[right])
                if val is not None:
                    correlations.append({
                        'title': title,
                        'left': left,
                        'right': right,
                        'value': val,
                        'explanation': explanation,
                        'strength': 'forte' if abs(val) >= 0.6 else 'moderada' if abs(val) >= 0.3 else 'fraca',
                        'direction': 'positiva' if val >= 0 else 'negativa',
                    })
    event_impacts = []
    if not merged.empty:
        for event_col, label in [
            ('incident_heat_fraction', 'horas com calor extremo/anômalo'),
            ('incident_rain_fraction', 'horas com chuva forte/extrema'),
            ('incident_wind_fraction', 'horas com vento forte'),
        ]:
            if event_col not in merged.columns:
                continue
            evt = pd.to_numeric(merged[event_col], errors='coerce').fillna(0)
            on = merged[evt.gt(0)]
            off = merged[evt.le(0)]
            if on.empty or off.empty:
                continue
            event_impacts.append({
                'label': label,
                'hours': int(len(on)),
                'load_delta_pct': _delta_pct(on.get('load_mw'), off.get('load_mw')),
                'generation_delta_pct': _delta_pct(on.get('generation_total_mw'), off.get('generation_total_mw')) if 'generation_total_mw' in merged else None,
                'wind_delta_pct': _delta_pct(on.get('generation_wind_mw'), off.get('generation_wind_mw')) if 'generation_wind_mw' in merged else None,
                'solar_delta_pct': _delta_pct(on.get('generation_solar_mw'), off.get('generation_solar_mw')) if 'generation_solar_mw' in merged else None,
                'hydro_delta_pct': _delta_pct(on.get('generation_hydro_mw'), off.get('generation_hydro_mw')) if 'generation_hydro_mw' in merged else None,
            })

    timeline = []
    if not day.empty:
        for _, row in day.iterrows():
            local = pd.Timestamp(row['interval_start_utc']).tz_convert(DISPLAY_TZ)
            event_intensity = max(
                float(pd.to_numeric(pd.Series([row.get('incident_heat_fraction')]), errors='coerce').fillna(0).iloc[0]),
                float(pd.to_numeric(pd.Series([row.get('incident_rain_fraction')]), errors='coerce').fillna(0).iloc[0]),
                float(pd.to_numeric(pd.Series([row.get('incident_wind_fraction')]), errors='coerce').fillna(0).iloc[0]),
                float(pd.to_numeric(pd.Series([row.get('incident_storm_fraction')]), errors='coerce').fillna(0).iloc[0]) if 'incident_storm_fraction' in row else 0.0,
            )
            timeline.append({
                'time': local.strftime('%Hh'),
                'local_iso': local.isoformat(),
                'load_mw': float(row['load_mw']) if pd.notna(row.get('load_mw')) else None,
                'generation_total_mw': float(row['generation_total_mw']) if 'generation_total_mw' in row and pd.notna(row.get('generation_total_mw')) else None,
                'generation_wind_mw': float(row['generation_wind_mw']) if 'generation_wind_mw' in row and pd.notna(row.get('generation_wind_mw')) else None,
                'generation_solar_mw': float(row['generation_solar_mw']) if 'generation_solar_mw' in row and pd.notna(row.get('generation_solar_mw')) else None,
                'temperature_2m_mean': float(row['temperature_2m_mean']) if 'temperature_2m_mean' in row and pd.notna(row.get('temperature_2m_mean')) else None,
                'event_intensity': event_intensity,
                'incident_heat_fraction': float(row['incident_heat_fraction']) if 'incident_heat_fraction' in row and pd.notna(row.get('incident_heat_fraction')) else 0.0,
                'incident_rain_fraction': float(row['incident_rain_fraction']) if 'incident_rain_fraction' in row and pd.notna(row.get('incident_rain_fraction')) else 0.0,
                'incident_wind_fraction': float(row['incident_wind_fraction']) if 'incident_wind_fraction' in row and pd.notna(row.get('incident_wind_fraction')) else 0.0,
            })

    source_mix = []
    if not plants.empty:
        grp = plants.groupby('source_name', as_index=False).agg(plant_count=('plant_name', 'size'), capacity_mw=('capacity_mw', 'sum'), generation_avg_mw=('generation_avg_mw', 'sum'))
        if 'near_event' in plants:
            near = plants[plants['near_event']].groupby('source_name', as_index=False).agg(capacity_near_event_mw=('capacity_mw', 'sum'))
            grp = grp.merge(near, on='source_name', how='left')
        grp['capacity_near_event_mw'] = grp['capacity_near_event_mw'].fillna(0.0)
        source_mix = grp.sort_values('capacity_mw', ascending=False).to_dict(orient='records')

    top_plants = []
    if not plants.empty:
        keep_cols = [c for c in ['plant_name', 'uf', 'source_name', 'capacity_mw', 'generation_avg_mw', 'near_event', 'nearest_event_label', 'nearest_event_point', 'distance_to_event_km', 'latitude', 'longitude'] if c in plants.columns]
        top_plants = plants[keep_cols].head(15).to_dict(orient='records')

    base_geo = geojson_payload()
    region_features = []
    for feat in base_geo.get('features', []):
        props = feat.get('properties', {})
        if canonical_subsystem(props.get('subsystem_id')).upper() == canonical_subsystem(subsystem_id).upper():
            region_features.append(feat)
    map_payload = {
        'subsystem_id': canonical_subsystem(subsystem_id),
        'selected_date': selected_date.isoformat() if selected_date else '',
        'features': region_features,
        'plants': [
            {
                'name': str(r.get('plant_name') or ''),
                'uf': str(r.get('uf') or ''),
                'source': str(r.get('source_name') or ''),
                'capacity_mw': None if pd.isna(r.get('capacity_mw')) else float(r.get('capacity_mw')),
                'generation_avg_mw': None if pd.isna(r.get('generation_avg_mw')) else float(r.get('generation_avg_mw')),
                'latitude': float(r.get('latitude')),
                'longitude': float(r.get('longitude')),
                'near_event': bool(r.get('near_event', False)),
                'event_label': str(r.get('nearest_event_label') or ''),
                'event_point': str(r.get('nearest_event_point') or ''),
                'distance_to_event_km': None if pd.isna(r.get('distance_to_event_km')) else float(r.get('distance_to_event_km')),
                'color': '#dc2626' if bool(r.get('near_event', False)) else '#334155',
            }
            for _, r in plants.head(180).iterrows()
        ],
        'events': [
            {
                'name': str(r.get('name') or ''),
                'state': str(r.get('state') or ''),
                'latitude': float(r.get('latitude')),
                'longitude': float(r.get('longitude')),
                'event_type': str(r.get('event_type') or 'none'),
                'event_label': str(r.get('event_label') or ''),
                'has_event': bool(r.get('has_event', False)),
                'temperature_max_anomaly_c': None if pd.isna(r.get('temperature_max_anomaly_c')) else float(r.get('temperature_max_anomaly_c')),
                'precipitation_sum': None if pd.isna(r.get('precipitation_sum')) else float(r.get('precipitation_sum')),
                'wind_gusts_10m_max': None if pd.isna(r.get('wind_gusts_10m_max')) else float(r.get('wind_gusts_10m_max')),
                'color': str(r.get('event_color') or '#94a3b8'),
            }
            for _, r in events.iterrows()
        ],
    }

    return {
        'subsystem_id': canonical_subsystem(subsystem_id),
        'selected_date': selected_date,
        'available_dates': available_event_dates(subsystem_id),
        'summary': summary,
        'correlations': correlations,
        'event_impacts': event_impacts,
        'timeline': timeline,
        'source_mix': source_mix,
        'top_plants': top_plants,
        'map_payload': map_payload,
        'notes': _notes(merged, events, plants),
    }


def _delta_pct(on: pd.Series | None, off: pd.Series | None) -> float | None:
    if on is None or off is None:
        return None
    on = pd.to_numeric(on, errors='coerce').dropna()
    off = pd.to_numeric(off, errors='coerce').dropna()
    if on.empty or off.empty:
        return None
    base = float(off.mean())
    if not np.isfinite(base) or abs(base) < 1e-9:
        return None
    return float((float(on.mean()) / base - 1.0) * 100.0)


def _notes(merged: pd.DataFrame, events: pd.DataFrame, plants: pd.DataFrame) -> list[str]:
    notes = [
        'Correlação não implica causalidade; os números servem como diagnóstico exploratório do MVP.',
        'A exposição de usinas a eventos usa pontos climáticos representativos do subsistema e distância aproximada; é um proxy espacial, não uma análise elétrica/meteorológica oficial.',
    ]
    if merged.empty:
        notes.append('Ainda não há série horária suficiente de carga/geração/clima para calcular relações quantitativas.')
    if events.empty:
        notes.append('Os eventos climáticos só aparecem depois de materializar o contexto E3 diário para a região.')
    if plants.empty:
        notes.append('As localizações de usinas dependem do catálogo georreferenciado configurado no projeto.')
    return notes
