from __future__ import annotations

from dataclasses import dataclass, field
import pandas as pd

WEATHER_MODES={'PERFECT_WEATHER_BACKTEST','OPERATIONAL_FORECAST'}


def _canon_zone(x:str)->str:
    x=str(x).strip().upper()
    return {'SE':'SE/CO','SECO':'SE/CO'}.get(x,x)


def validate_real_pilot(load:pd.DataFrame, zone_climate:pd.DataFrame|None, *, subsystem_id:str, weather_mode:str, start:str|None=None, end:str|None=None)->dict:
    blockers=[];warnings=[];checks={}
    zone=_canon_zone(subsystem_id);mode=weather_mode.upper()
    if mode not in WEATHER_MODES:blockers.append(f'unsupported weather_mode={weather_mode}')
    l=load.copy();required={'interval_start_utc','subsystem_id','load_mw'}
    miss=required-set(l.columns)
    if miss:blockers.append(f'load missing columns {sorted(miss)}');return {'ready':False,'blockers':blockers,'warnings':warnings,'checks':checks}
    l['interval_start_utc']=pd.to_datetime(l['interval_start_utc'],utc=True,errors='coerce');l['subsystem_id']=l['subsystem_id'].map(_canon_zone);l=l[l.subsystem_id.eq(zone)].sort_values('interval_start_utc')
    if start:l=l[l.interval_start_utc>=pd.Timestamp(start,tz='UTC') if pd.Timestamp(start).tzinfo is None else l.interval_start_utc>=pd.Timestamp(start).tz_convert('UTC')]
    if end:l=l[l.interval_start_utc<=pd.Timestamp(end,tz='UTC') if pd.Timestamp(end).tzinfo is None else l.interval_start_utc<=pd.Timestamp(end).tz_convert('UTC')]
    if l.empty:blockers.append(f'no load rows for subsystem {zone}')
    dup=int(l.duplicated(['interval_start_utc','subsystem_id']).sum());checks['load_duplicate_hours']=dup
    if dup:blockers.append(f'load has {dup} duplicate subsystem-hours')
    if len(l):
        expected=pd.date_range(l.interval_start_utc.min(),l.interval_start_utc.max(),freq='h',tz='UTC');missing=int(len(expected.difference(pd.DatetimeIndex(l.interval_start_utc))));checks['load_missing_hours']=missing
        checks['load_rows']=int(len(l));checks['load_start']=str(l.interval_start_utc.min());checks['load_end']=str(l.interval_start_utc.max())
        if missing:warnings.append(f'load has {missing} missing hourly timestamps inside selected period')
        if len(l)<24*60:warnings.append('pilot has less than ~60 days of load; E1-E3 validation will be weak')
    checks['load_negative_values']=int(pd.to_numeric(l.load_mw,errors='coerce').lt(0).sum()) if len(l) else 0
    if checks['load_negative_values']:blockers.append('load contains negative MW values')

    if zone_climate is None or zone_climate.empty:
        warnings.append('zone_climate not supplied: only E0/E1 can run; E2/E3 climate hypothesis is not testable yet')
    else:
        z=zone_climate.copy();r={'interval_start_utc','subsystem_id'};m=r-set(z.columns)
        if m:blockers.append(f'zone_climate missing columns {sorted(m)}')
        else:
            z['interval_start_utc']=pd.to_datetime(z['interval_start_utc'],utc=True,errors='coerce');z['subsystem_id']=z['subsystem_id'].map(_canon_zone);z=z[z.subsystem_id.eq(zone)]
            d=int(z.duplicated(['interval_start_utc','subsystem_id']).sum());checks['climate_duplicate_hours']=d
            if d:blockers.append(f'zone_climate has {d} duplicate subsystem-hours')
            raw_prefix=['temperature_2m_','precipitation_','wind_speed_','solar_radiation_'];has_raw=all(any(c.startswith(p) for c in z.columns) for p in raw_prefix);checks['climate_raw_feature_families_ok']=has_raw
            if not has_raw:blockers.append('zone_climate lacks one or more raw feature families: temperature, precipitation, wind, solar radiation')
            anomaly_or_percentile=any(('anomaly_' in c or 'percentile_' in c) for c in z.columns)
            incident_cols=[c for c in z.columns if c.startswith('incident_')]
            nonzero_incident=any(pd.to_numeric(z[c],errors='coerce').fillna(0).abs().gt(0).any() for c in incident_cols)
            has_enhanced=bool(anomaly_or_percentile or nonzero_incident);checks['climate_enhanced_features_present']=has_enhanced
            if not has_enhanced:warnings.append('no anomaly/percentile/incident features found: E3 will not represent the intended extreme-event layer')
            if len(l):
                overlap=l[['interval_start_utc']].merge(z[['interval_start_utc']].drop_duplicates(),on='interval_start_utc',how='inner');checks['climate_load_overlap_hours']=int(len(overlap))
                if len(overlap)<max(168,min(len(l),24*30)):blockers.append(f'insufficient climate/load overlap: {len(overlap)} hours')
            if mode=='OPERATIONAL_FORECAST':
                src=' '.join(str(x) for x in z.get('weather_mode',pd.Series(dtype=str)).dropna().unique()).upper()
                if 'OPERATIONAL_FORECAST' not in src:blockers.append('OPERATIONAL_FORECAST selected but zone_climate is not explicitly tagged weather_mode=OPERATIONAL_FORECAST')
            elif mode=='PERFECT_WEATHER_BACKTEST':
                warnings.append('PERFECT_WEATHER_BACKTEST measures climate upper-bound value; it is not an operational forecast evaluation')
    return {'ready':not blockers,'subsystem_id':zone,'weather_mode':mode,'blockers':blockers,'warnings':warnings,'checks':checks}
