#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import xarray as xr

LAND_URLS = {
    'temperature': 'https://arco.datastores.ecmwf.int/cadl-arco-geo-007/arco/reanalysis_era5_land/sfc-2m-temperature/geoChunked.zarr',
    'precipitation': 'https://arco.datastores.ecmwf.int/cadl-arco-geo-009/arco/reanalysis_era5_land/sfc-pressure-precipitation/geoChunked.zarr',
    'wind': 'https://arco.datastores.ecmwf.int/cadl-arco-geo-008/arco/reanalysis_era5_land/sfc-wind/geoChunked.zarr',
    'radiation': 'https://arco.datastores.ecmwf.int/cadl-arco-geo-010/arco/reanalysis_era5_land/sfc-radiation-heat/geoChunked.zarr',
}
ERA5_SURFACE_URL = 'https://arco.datastores.ecmwf.int/cadl-arco-geo-002/arco/reanalysis_era5_single_levels/sfc/geoChunked.zarr'

ALIASES = {
    't2m': ('t2m', '2m_temperature', 'temperature_2m'),
    'd2m': ('d2m', '2m_dewpoint_temperature', 'dew_point_2m', 'dewpoint_2m'),
    'tp': ('tp', 'total_precipitation', 'precipitation'),
    'sp': ('sp', 'surface_pressure'),
    'u10': ('u10', '10m_u_component_of_wind'),
    'v10': ('v10', '10m_v_component_of_wind'),
    'ssrd': ('ssrd', 'surface_solar_radiation_downwards'),
    'gust': (
        'fg10', '10fg', 'i10fg', 'gust',
        '10m_wind_gust_since_previous_post_processing',
        '10m_wind_gust', 'wind_gusts_10m',
    ),
}

SUPPORTED_HOURLY = {
    'temperature_2m', 'dew_point_2m', 'relative_humidity_2m', 'precipitation',
    'surface_pressure', 'wind_speed_10m', 'wind_direction_10m',
    'wind_gusts_10m', 'shortwave_radiation',
}
SUPPORTED_DAILY = {
    'temperature_2m_max', 'temperature_2m_min', 'temperature_2m_mean',
    'precipitation_sum', 'wind_speed_10m_max', 'wind_gusts_10m_max',
    'shortwave_radiation_sum',
}


def load_cds_api_key() -> str:
    key = os.environ.get('CDSAPI_KEY', '').strip().strip('"').strip("'")
    if key:
        return key
    p = Path.home() / '.cdsapirc'
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines():
            m = re.match(r'^\s*key\s*:\s*(.+?)\s*$', line)
            if m:
                key = m.group(1).strip().strip('"').strip("'")
                if key:
                    return key
    raise RuntimeError('CDS API key ausente. Defina CDSAPI_KEY ou configure ~/.cdsapirc.')


def resolve_var(ds: xr.Dataset, logical: str) -> str:
    for name in ALIASES[logical]:
        if name in ds.data_vars:
            return name
    raise KeyError(f"ARCO: variável {logical!r} ausente; aliases={ALIASES[logical]}; disponíveis={list(ds.data_vars)}")


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(',') if x.strip()]


def parse_floats(value: str | None) -> list[float]:
    return [float(x) for x in split_csv(value)]


def rh_from_t_td(t_c: np.ndarray, td_c: np.ndarray) -> np.ndarray:
    # Magnus approximation over water; sufficient for the derived predictor.
    a = 17.625
    b = 243.04
    num = np.exp((a * td_c) / (b + td_c))
    den = np.exp((a * t_c) / (b + t_c))
    return np.clip(100.0 * num / den, 0.0, 100.0)


def wind_direction_deg(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    # Meteorological direction FROM which the wind blows.
    return (270.0 - np.degrees(np.arctan2(v, u))) % 360.0


class ArcoAdapter:
    def __init__(self) -> None:
        self.key = load_cds_api_key()
        self.datasets: dict[str, xr.Dataset] = {}

    def _open(self, group: str) -> xr.Dataset:
        if group in self.datasets:
            return self.datasets[group]
        url = ERA5_SURFACE_URL if group == 'era5' else LAND_URLS[group]
        ds = xr.open_zarr(
            url,
            consolidated=True,
            storage_options={'headers': {'Authorization': f'Bearer {self.key}'}},
        )
        self.datasets[group] = ds
        return ds

    def _select(self, group: str, logical: str, lats: list[float], lons: list[float], utc_start: pd.Timestamp, utc_end: pd.Timestamp) -> xr.DataArray:
        ds = self._open(group)
        name = resolve_var(ds, logical)
        p = np.arange(len(lats))
        lat_idx = xr.DataArray(np.asarray(lats, dtype=float), dims='point', coords={'point': p})
        lon_idx = xr.DataArray(np.asarray(lons, dtype=float), dims='point', coords={'point': p})
        return (
            ds[name]
            .sel(latitude=lat_idx, longitude=lon_idx, method='nearest')
            .sel(time=slice(utc_start.tz_localize(None).to_datetime64(), utc_end.tz_localize(None).to_datetime64()))
            .transpose('time', 'point')
            .load()
        )

    def fetch(self, *, lats: list[float], lons: list[float], start_date: str, end_date: str, timezone_names: list[str] | str, hourly: list[str], daily: list[str], windspeed_unit: str) -> list[dict]:
        if len(lats) != len(lons) or not lats:
            raise ValueError('latitude/longitude inválidos ou com tamanhos diferentes')
        unknown_h = sorted(set(hourly) - SUPPORTED_HOURLY)
        unknown_d = sorted(set(daily) - SUPPORTED_DAILY)
        if unknown_h or unknown_d:
            raise ValueError(f'variáveis não suportadas pelo adaptador ARCO: hourly={unknown_h}, daily={unknown_d}')

        # Open-Meteo accepts either one timezone for the whole batch or one
        # timezone per coordinate. batch_openmeteo sends the latter. Never
        # feed the comma-separated list to ZoneInfo as a single key.
        if isinstance(timezone_names, str):
            tz_names = split_csv(timezone_names) or ['GMT']
        else:
            tz_names = [str(x).strip() for x in timezone_names if str(x).strip()] or ['GMT']
        if len(tz_names) == 1:
            tz_names = tz_names * len(lats)
        elif len(tz_names) != len(lats):
            raise ValueError(
                f'timezone count must be 1 or match points: timezones={len(tz_names)} points={len(lats)}'
            )

        normalized_tz_names: list[str] = []
        tzs: list[ZoneInfo] = []
        local_windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []
        for raw_name in tz_names:
            name = raw_name or 'GMT'
            if name.lower() in {'gmt', 'utc', 'auto'}:
                name = 'UTC'
            tz = ZoneInfo(name)
            local_start_i = pd.Timestamp(start_date).tz_localize(tz)
            local_end_i = (pd.Timestamp(end_date) + pd.Timedelta(days=1)).tz_localize(tz)
            normalized_tz_names.append(name)
            tzs.append(tz)
            local_windows.append((local_start_i, local_end_i))

        # Fetch one common UTC envelope covering every point-local window.
        utc_start = min(x[0].tz_convert('UTC') for x in local_windows)
        utc_end = max(x[1].tz_convert('UTC') for x in local_windows) - pd.Timedelta(hours=1)

        need_t = bool(set(hourly) & {'temperature_2m', 'relative_humidity_2m'}) or bool(set(daily) & {'temperature_2m_max', 'temperature_2m_min', 'temperature_2m_mean'})
        need_td = bool(set(hourly) & {'dew_point_2m', 'relative_humidity_2m'})
        need_p = 'surface_pressure' in hourly
        need_tp = 'precipitation' in hourly or 'precipitation_sum' in daily
        need_wind = bool(set(hourly) & {'wind_speed_10m', 'wind_direction_10m'}) or 'wind_speed_10m_max' in daily
        need_gust = 'wind_gusts_10m' in hourly or 'wind_gusts_10m_max' in daily
        need_rad = 'shortwave_radiation' in hourly or 'shortwave_radiation_sum' in daily

        arrays: dict[str, xr.DataArray] = {}
        if need_t:
            arrays['t2m'] = self._select('temperature', 't2m', lats, lons, utc_start, utc_end)
        if need_td:
            arrays['d2m'] = self._select('temperature', 'd2m', lats, lons, utc_start, utc_end)
        if need_p:
            arrays['sp'] = self._select('precipitation', 'sp', lats, lons, utc_start, utc_end)
        if need_tp:
            arrays['tp'] = self._select('precipitation', 'tp', lats, lons, utc_start, utc_end)
        if need_wind:
            arrays['u10'] = self._select('wind', 'u10', lats, lons, utc_start, utc_end)
            arrays['v10'] = self._select('wind', 'v10', lats, lons, utc_start, utc_end)
        if need_rad:
            arrays['ssrd'] = self._select('radiation', 'ssrd', lats, lons, utc_start, utc_end)
        if need_gust:
            # ERA5-Land ARCO does not expose gust in its current subset. Use the
            # official ERA5 single-level ARCO gust (0.25°), sampled nearest to
            # each Predicta 0.1° cell. This is explicit and never silently
            # substitutes sustained wind speed for gust.
            arrays['gust'] = self._select('era5', 'gust', lats, lons, utc_start, utc_end)

        if not arrays:
            raise ValueError('requisição sem variáveis hourly/daily')

        results: list[dict] = []
        for i, (lat, lon) in enumerate(zip(lats, lons)):
            tz = tzs[i]
            tz_name = normalized_tz_names[i]
            local_start, local_end_exclusive = local_windows[i]
            frame: pd.DataFrame | None = None
            for name, arr in arrays.items():
                idx = pd.DatetimeIndex(arr['time'].values).tz_localize('UTC')
                s = pd.Series(np.asarray(arr.values[:, i], dtype=float), index=idx, name=name)
                frame = s.to_frame() if frame is None else frame.join(s, how='outer')
            assert frame is not None
            frame = frame.sort_index()
            local_idx = frame.index.tz_convert(tz)
            mask = (local_idx >= local_start) & (local_idx < local_end_exclusive)
            frame = frame.loc[mask].copy()
            local_idx = frame.index.tz_convert(tz)
            if frame.empty:
                raise RuntimeError(f'ARCO não retornou dados para {lat},{lon} em {start_date}..{end_date}')

            if 't2m' in frame:
                frame['temperature_2m'] = frame['t2m'] - 273.15
            if 'd2m' in frame:
                frame['dew_point_2m'] = frame['d2m'] - 273.15
            if 'temperature_2m' in frame and 'dew_point_2m' in frame:
                frame['relative_humidity_2m'] = rh_from_t_td(frame['temperature_2m'].to_numpy(), frame['dew_point_2m'].to_numpy())
            if 'tp' in frame:
                frame['precipitation'] = np.maximum(frame['tp'].to_numpy(dtype=float) * 1000.0, 0.0)
            if 'sp' in frame:
                frame['surface_pressure'] = frame['sp'].to_numpy(dtype=float) / 100.0  # hPa
            if 'u10' in frame and 'v10' in frame:
                u = frame['u10'].to_numpy(dtype=float)
                v = frame['v10'].to_numpy(dtype=float)
                speed_ms = np.sqrt(u*u + v*v)
                frame['wind_speed_10m'] = speed_ms * (3.6 if windspeed_unit != 'ms' else 1.0)
                frame['wind_direction_10m'] = wind_direction_deg(u, v)
            if 'gust' in frame:
                gust = frame['gust'].to_numpy(dtype=float)
                frame['wind_gusts_10m'] = gust * (3.6 if windspeed_unit != 'ms' else 1.0)
            if 'ssrd' in frame:
                # Hourly accumulated J/m² -> mean W/m² over the hour.
                frame['shortwave_radiation'] = np.maximum(frame['ssrd'].to_numpy(dtype=float) / 3600.0, 0.0)
                frame['_ssrd_j_m2'] = np.maximum(frame['ssrd'].to_numpy(dtype=float), 0.0)

            utc_offset_seconds = int(local_idx[0].utcoffset().total_seconds()) if len(local_idx) else 0
            result = {
                'latitude': float(lat),
                'longitude': float(lon),
                'generationtime_ms': 0.0,
                'utc_offset_seconds': utc_offset_seconds,
                'timezone': tz_name,
                'timezone_abbreviation': local_idx[0].tzname() if len(local_idx) else 'UTC',
            }

            if hourly:
                result['hourly_units'] = {}
                h = {'time': [x.strftime('%Y-%m-%dT%H:%M') for x in local_idx]}
                for var in hourly:
                    if var not in frame.columns:
                        raise ValueError(f'variável horária {var} não pôde ser derivada')
                    h[var] = [None if pd.isna(v) else float(v) for v in frame[var].to_numpy()]
                    result['hourly_units'][var] = {
                        'temperature_2m': '°C', 'dew_point_2m': '°C', 'relative_humidity_2m': '%',
                        'precipitation': 'mm', 'surface_pressure': 'hPa',
                        'wind_speed_10m': 'm/s' if windspeed_unit == 'ms' else 'km/h',
                        'wind_direction_10m': '°', 'wind_gusts_10m': 'm/s' if windspeed_unit == 'ms' else 'km/h',
                        'shortwave_radiation': 'W/m²',
                    }[var]
                result['hourly'] = h

            if daily:
                tmp = frame.copy()
                tmp['_date'] = [x.date().isoformat() for x in local_idx]
                groups = tmp.groupby('_date', sort=True)
                d = {'time': list(groups.size().index)}
                result['daily_units'] = {}
                for var in daily:
                    if var == 'temperature_2m_max':
                        vals = groups['temperature_2m'].max()
                        unit = '°C'
                    elif var == 'temperature_2m_min':
                        vals = groups['temperature_2m'].min()
                        unit = '°C'
                    elif var == 'temperature_2m_mean':
                        vals = groups['temperature_2m'].mean()
                        unit = '°C'
                    elif var == 'precipitation_sum':
                        vals = groups['precipitation'].sum(min_count=1)
                        unit = 'mm'
                    elif var == 'wind_speed_10m_max':
                        vals = groups['wind_speed_10m'].max()
                        unit = 'm/s' if windspeed_unit == 'ms' else 'km/h'
                    elif var == 'wind_gusts_10m_max':
                        vals = groups['wind_gusts_10m'].max()
                        unit = 'm/s' if windspeed_unit == 'ms' else 'km/h'
                    elif var == 'shortwave_radiation_sum':
                        vals = groups['_ssrd_j_m2'].sum(min_count=1) / 1_000_000.0
                        unit = 'MJ/m²'
                    else:
                        raise ValueError(f'variável diária não suportada: {var}')
                    d[var] = [None if pd.isna(v) else float(v) for v in vals.to_numpy()]
                    result['daily_units'][var] = unit
                result['daily'] = d

            result['_predicta_provenance'] = {
                'historical_backend': 'ARCO',
                'core_source': 'ERA5-Land ARCO 0.1°',
                'gust_source': 'ERA5 single-level ARCO 0.25° nearest-neighbour' if need_gust else None,
            }
            results.append(result)
        return results


ADAPTER: ArcoAdapter | None = None


class Handler(BaseHTTPRequestHandler):
    server_version = 'PredictaARCOProxy/1.0'

    def log_message(self, fmt: str, *args) -> None:
        print('ARCO_PROXY ' + (fmt % args), flush=True)

    def _json(self, status: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        global ADAPTER
        parsed = urlparse(self.path)
        if parsed.path == '/healthz':
            self._json(200, {'status': 'ok', 'backend': 'arco'})
            return
        if parsed.path not in {'/v1/archive', '/archive'}:
            self._json(404, {'error': True, 'reason': 'not found'})
            return
        try:
            q = parse_qs(parsed.query)
            first = lambda k, default='': q.get(k, [default])[0]
            many = lambda k: [item for raw in q.get(k, []) for item in split_csv(raw)]
            lats = [float(x) for x in many('latitude')]
            lons = [float(x) for x in many('longitude')]
            start_date = first('start_date')
            end_date = first('end_date')
            if not start_date or not end_date:
                raise ValueError('start_date/end_date obrigatórios')
            hourly = many('hourly')
            daily = many('daily')
            timezone_names = many('timezone') or ['GMT']
            windspeed_unit = first('wind_speed_unit', first('windspeed_unit', 'kmh'))
            if ADAPTER is None:
                ADAPTER = ArcoAdapter()
            t0 = time.time()
            results = ADAPTER.fetch(
                lats=lats, lons=lons, start_date=start_date, end_date=end_date,
                timezone_names=timezone_names, hourly=hourly, daily=daily,
                windspeed_unit=windspeed_unit,
            )
            print(
                f'ARCO_PROXY_OK points={len(results)} dates={start_date}..{end_date} '
                f'hourly={hourly} daily={daily} seconds={time.time()-t0:.2f}',
                flush=True,
            )
            self._json(200, results if len(results) > 1 else results[0])
        except Exception as exc:
            print(f'ARCO_PROXY_ERROR {type(exc).__name__}: {exc}', flush=True)
            self._json(500, {'error': True, 'reason': f'{type(exc).__name__}: {exc}'})


def main() -> None:
    p = argparse.ArgumentParser(description='Local Open-Meteo-compatible historical endpoint backed by ECMWF ARCO.')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8765)
    a = p.parse_args()
    # Fail early if credentials are missing.
    load_cds_api_key()
    server = HTTPServer((a.host, a.port), Handler)
    print(f'PREDICTA_ARCO_PROXY_READY http://{a.host}:{a.port}/v1/archive', flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
