from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from motor_sin.grid.index import coordinate_to_index
from motor_sin.climate.e2_pilot import aggregate_pilot_zone_climate, load_pilot_points
from motor_sin.climate.e3_snapshot import build_e3_hourly_zone_context, merge_e2_with_e3_context
from motor_sin.climate.openmeteo_snapshot_anomaly import load_snapshot_rules
from motor_sin.climate.http_client import fetch_json_with_retry

FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'
HOURLY_VARS = ['temperature_2m','dew_point_2m','precipitation','wind_speed_10m','shortwave_radiation']
DAILY_VARS = ['temperature_2m_max','temperature_2m_min','precipitation_sum','wind_gusts_10m_max','weather_code']
RAW_TO_CANONICAL = {
    'temperature_2m':'temperature_2m',
    'dew_point_2m':'dewpoint_2m',
    'precipitation':'precipitation',
    'wind_speed_10m':'wind_speed_10m',
    'shortwave_radiation':'solar_radiation',
}


def fetch_forecast_batch(points: pd.DataFrame, *, timezone_name: str, timeout_seconds: int = 60, batch_size: int = 12, max_retries: int = 10, backoff_seconds: float = 10.0) -> list[tuple[pd.Series, dict]]:
    rows=[]
    for start in range(0,len(points),max(1,int(batch_size))):
        batch=points.iloc[start:start+max(1,int(batch_size))]
        params={
            'latitude': ','.join(f'{float(x):.5f}' for x in batch.latitude),
            'longitude': ','.join(f'{float(x):.5f}' for x in batch.longitude),
            'hourly': ','.join(HOURLY_VARS), 'daily': ','.join(DAILY_VARS),
            'timezone': timezone_name, 'forecast_days': 4, 'past_days': 2,
            'temperature_unit':'celsius','wind_speed_unit':'kmh','precipitation_unit':'mm','timeformat':'iso8601',
        }
        url=f'{FORECAST_URL}?{urlencode(params)}'
        _,payload=fetch_json_with_retry(url,timeout_seconds=timeout_seconds,max_retries=max_retries,base_backoff_seconds=backoff_seconds,user_agent='predicta-hackathon/1.11')
        payloads=[payload] if isinstance(payload,dict) and len(batch)==1 else payload
        if not isinstance(payloads,list) or len(payloads)!=len(batch):raise ValueError('Open-Meteo forecast multi-location response shape mismatch')
        for (_,point),item in zip(batch.iterrows(),payloads):
            if not isinstance(item,dict) or item.get('error') is True:raise RuntimeError(f'Open-Meteo forecast failed: {item}')
            rows.append((point,item))
    return rows


def fetch_forecast_point(*, latitude: float, longitude: float, timezone_name: str, timeout_seconds: int = 60) -> dict:
    point=pd.DataFrame([{'latitude':latitude,'longitude':longitude}])
    return fetch_forecast_batch(point,timezone_name=timezone_name,timeout_seconds=timeout_seconds,batch_size=1)[0][1]


def _hourly_frame(payload: dict, point: pd.Series) -> pd.DataFrame:
    hourly = payload.get('hourly') or {}
    times = hourly.get('time') or []
    tz = ZoneInfo(str(point['timezone']))
    n = len(times)
    if not n:
        raise ValueError(f'forecast returned no hourly rows for {point["point_id"]}')
    cell_id = coordinate_to_index(float(point['latitude']), float(point['longitude'])).cell_id
    records=[]
    for i,t in enumerate(times):
        local = pd.Timestamp(t)
        local = local.tz_localize(tz) if local.tzinfo is None else local.tz_convert(tz)
        rec={
            'interval_start_utc':local.tz_convert('UTC'),'cell_id':cell_id,
            'source':'open-meteo','source_service':'forecast','source_model':'best_match',
            'source_grid_latitude':float(payload.get('latitude',point['latitude'])),
            'source_grid_longitude':float(payload.get('longitude',point['longitude'])),
            'source_elevation':payload.get('elevation'),'raw_record_id':None,'raw_payload_hash':None,'raw_file':'operational_api',
        }
        for raw,canonical in RAW_TO_CANONICAL.items():
            vals=hourly.get(raw) or [None]*n
            v=vals[i]
            if v is not None and canonical=='wind_speed_10m': v=float(v)/3.6
            rec[canonical]=v
        records.append(rec)
    return pd.DataFrame(records)


def _daily_frame(payload: dict, point: pd.Series) -> pd.DataFrame:
    daily=payload.get('daily') or {}; times=daily.get('time') or []
    cell_id=coordinate_to_index(float(point['latitude']),float(point['longitude'])).cell_id
    rows=[]
    for i,d in enumerate(times):
        row={'point_id':str(point['point_id']),'cell_id':cell_id,'date_local':str(d),'timezone':str(point['timezone']),
             'name':str(point['name']),'state':str(point['state']),'subsystem_id':str(point['subsystem_id']),'weight':float(point['weight'])}
        for c in DAILY_VARS:
            vals=daily.get(c) or [None]*len(times);row[c]=vals[i]
        rows.append(row)
    return pd.DataFrame(rows)


def _score_daily_forecast(daily: pd.DataFrame, baseline: pd.DataFrame, rules: dict) -> pd.DataFrame:
    work=daily.copy();work['month']=pd.to_datetime(work['date_local']).dt.month
    base=baseline.copy()
    maxb=base[base.metric.eq('temperature_2m_max')].rename(columns={c:f'max_{c}' for c in ['mean','p05','p10','p90','p95']})
    minb=base[base.metric.eq('temperature_2m_min')].rename(columns={c:f'min_{c}' for c in ['mean','p05','p10','p90','p95']})
    cols=['cell_id','month','max_mean','max_p05','max_p10','max_p90','max_p95']
    work=work.merge(maxb[cols],on=['cell_id','month'],how='left',validate='many_to_one')
    cols=['cell_id','month','min_mean','min_p05','min_p10','min_p90','min_p95']
    work=work.merge(minb[cols],on=['cell_id','month'],how='left',validate='many_to_one')
    if work[['max_mean','max_p90','max_p95','min_mean','min_p05','min_p10','min_p90']].isna().any().any():
        raise ValueError('operational forecast baseline missing cell/month thresholds')
    tmax=pd.to_numeric(work['temperature_2m_max'],errors='coerce');tmin=pd.to_numeric(work['temperature_2m_min'],errors='coerce')
    work['temperature_max_anomaly_c']=tmax-work['max_mean'];work['temperature_min_anomaly_c']=tmin-work['min_mean']
    te=rules['temperature_events']
    work['extreme_heat_day']=tmax.ge(work['max_p95']) & work['temperature_max_anomaly_c'].ge(float(te['extreme_heat_day']['anomaly_threshold_c']))
    hot=tmax.ge(work['max_p90']);work['unusually_hot_day']=hot & ~work['extreme_heat_day']
    heat_pred=hot & work['temperature_max_anomaly_c'].ge(float(te['heat_wave_candidate']['anomaly_threshold_c']))
    work['extreme_cold_day']=tmin.le(work['min_p05']) & work['temperature_min_anomaly_c'].le(float(te['extreme_cold_day']['anomaly_threshold_c']))
    cold=tmin.le(work['min_p10']);work['unusually_cold_day']=cold & ~work['extreme_cold_day']
    cold_pred=cold & work['temperature_min_anomaly_c'].le(float(te['cold_wave_candidate']['anomaly_threshold_c']))
    work['heat_wave_candidate']=False;work['cold_wave_candidate']=False
    for _,idx in work.groupby('point_id').groups.items():
        idx=list(idx);h=heat_pred.loc[idx].astype(int).rolling(int(te['heat_wave_candidate']['minimum_consecutive_days']),min_periods=int(te['heat_wave_candidate']['minimum_consecutive_days'])).sum()
        c=cold_pred.loc[idx].astype(int).rolling(int(te['cold_wave_candidate']['minimum_consecutive_days']),min_periods=int(te['cold_wave_candidate']['minimum_consecutive_days'])).sum()
        work.loc[idx,'heat_wave_candidate']=h.eq(int(te['heat_wave_candidate']['minimum_consecutive_days'])).to_numpy()
        work.loc[idx,'cold_wave_candidate']=c.eq(int(te['cold_wave_candidate']['minimum_consecutive_days'])).to_numpy()
    work['warm_night_evidence']=tmin.ge(work['min_p90'])
    pr=rules['precipitation_events'];prec=pd.to_numeric(work['precipitation_sum'],errors='coerce')
    work['extreme_rain_day']=prec.ge(float(pr['extreme_rain_day']['threshold']));work['heavy_rain_day']=prec.ge(float(pr['heavy_rain_day']['threshold'])) & ~work['extreme_rain_day']
    wr=rules['wind_events'];gust=pd.to_numeric(work['wind_gusts_10m_max'],errors='coerce')
    work['extreme_wind_day']=gust.ge(float(wr['extreme_wind_day']['threshold']));work['severe_wind_day']=gust.ge(float(wr['severe_wind_day']['threshold'])) & ~work['extreme_wind_day'];work['strong_wind_day']=gust.ge(float(wr['strong_wind_day']['threshold'])) & ~work['severe_wind_day'] & ~work['extreme_wind_day']
    sr=rules['storm_events']['storm_candidate'];codes=pd.to_numeric(work.get('weather_code'),errors='coerce')
    work['storm_candidate']=codes.isin(sr.get('forecast_weather_codes',[])) | (prec.ge(float(sr['minimum_precipitation_mm'])) & gust.ge(float(sr['minimum_wind_gust_kmh'])))
    work['heat_event']=work[['unusually_hot_day','extreme_heat_day','heat_wave_candidate']].any(axis=1);work['cold_event']=work[['unusually_cold_day','extreme_cold_day','cold_wave_candidate']].any(axis=1)
    work['rain_event']=work[['heavy_rain_day','extreme_rain_day']].any(axis=1);work['wind_event']=work[['strong_wind_day','severe_wind_day','extreme_wind_day']].any(axis=1);work['event_any']=work[['heat_event','cold_event','rain_event','wind_event','storm_candidate']].any(axis=1)
    work['rules_version']=str(rules['rules_version']);work['baseline_version']=str(rules['temperature_baseline']['baseline_version']);work['baseline_year_start']=int(base['baseline_year_start'].min());work['baseline_year_end']=int(base['baseline_year_end'].max());work['baseline_grouping']='calendar_month';work['baseline_scientific_status']='operational_baseline_not_official_climatological_normal';work['storm_simultaneity_confirmed']=False
    return work


def build_operational_zone_forecast(*, points_path: str|Path, subsystem_id: str, baseline_path: str|Path, issue_time_utc: pd.Timestamp, historical_template_path: str|Path|None=None, rules_path: str|Path='configs/openmeteo_event_rules_snapshot_2026-08-08.2.json', timeout_seconds: int=60) -> tuple[pd.DataFrame,dict]:
    points=load_pilot_points(points_path,subsystem_id=subsystem_id);baseline=pd.read_parquet(baseline_path);rules=load_snapshot_rules(rules_path)
    hourly_parts=[];daily_parts=[]
    for timezone_name,g in points.groupby('timezone',sort=True):
        for p,payload in fetch_forecast_batch(g,timezone_name=str(timezone_name),timeout_seconds=timeout_seconds,batch_size=20):
            hourly_parts.append(_hourly_frame(payload,p));daily_parts.append(_daily_frame(payload,p))
    hourly=pd.concat(hourly_parts,ignore_index=True);daily=pd.concat(daily_parts,ignore_index=True)
    issue=pd.Timestamp(issue_time_utc);issue=issue.tz_localize('UTC') if issue.tzinfo is None else issue.tz_convert('UTC')
    targets=pd.date_range(issue+timedelta(hours=1),periods=24,freq='h',tz='UTC')
    hourly=hourly[hourly['interval_start_utc'].isin(targets)].copy()
    if hourly['interval_start_utc'].nunique()!=24:raise ValueError(f'Open-Meteo operational forecast does not cover all 24 target hours after issue {issue}')
    regional_hourly=hourly
    spatial_method='GRID_01DEG_ACTIVE_CELLS_OPERATIONAL' if 'point_role' in points.columns else 'MVP_REPRESENTATIVE_POINTS_UNIFORM_OPERATIONAL'
    if 'point_role' in points.columns:
        regional=points[points['point_role'].astype(str).str.contains('regional_grid',regex=False)].copy()
        allowed={coordinate_to_index(float(r.latitude),float(r.longitude)).cell_id for r in regional.itertuples(index=False)}
        if allowed:regional_hourly=hourly[hourly['cell_id'].astype(str).isin(allowed)].copy()
    e2=aggregate_pilot_zone_climate(regional_hourly,subsystem_id=subsystem_id,spatial_method=spatial_method)
    e2=e2[e2['interval_start_utc'].isin(targets)].copy();e2['weather_mode']='OPERATIONAL_FORECAST';e2['climate_source_model']='open_meteo_forecast_best_match'
    daily_scored=_score_daily_forecast(daily,baseline,rules)
    hourly_ctx=build_e3_hourly_zone_context(daily_scored,points,pd.DataFrame({'interval_start_utc':targets}),subsystem_id=subsystem_id)
    out=merge_e2_with_e3_context(e2,hourly_ctx);out['weather_mode']='OPERATIONAL_FORECAST';out['forecast_issued_at_utc']=issue;out['climate_spatial_method']=spatial_method
    if historical_template_path and Path(historical_template_path).exists():
        template=pd.read_parquet(historical_template_path,nrows=None) if False else pd.read_parquet(historical_template_path)
        feature_like=[c for c in template.columns if any(c.startswith(v) for v in ['temperature_2m_','dewpoint_2m_','precipitation_','wind_speed_','solar_radiation_']) or 'anomaly_' in c or 'percentile_' in c or c.startswith('incident_')]
        for c in feature_like:
            if c not in out.columns:
                if any(c.startswith(v) for v in ['temperature_2m_','dewpoint_2m_','precipitation_','wind_speed_','solar_radiation_']):raise ValueError(f'operational forecast missing required raw climate feature {c}')
                out[c]=0.0
        missing_null=[c for c in feature_like if c in out and pd.to_numeric(out[c],errors='coerce').isna().any()]
        if missing_null:raise ValueError(f'operational climate has null model features: {missing_null[:10]}')
    report={'subsystem_id':subsystem_id,'issue_time_utc':issue.isoformat(),'rows':int(len(out)),'target_start_utc':targets[0].isoformat(),'target_end_utc':targets[-1].isoformat(),'weather_mode':'OPERATIONAL_FORECAST','point_count':int(len(points)),'baseline_path':str(baseline_path)}
    return out.sort_values('interval_start_utc').reset_index(drop=True),report
