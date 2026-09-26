from __future__ import annotations

from datetime import date,time
from zoneinfo import ZoneInfo
import pandas as pd

FIXED_HOLIDAYS={(1,1),(4,21),(5,1),(9,7),(10,12),(11,2),(11,15),(12,25)}


def _minutes(text:str)->int:
    h,m=[int(x) for x in str(text).split(':')[:2]];return h*60+m


def _day_type(ts:pd.Timestamp)->str:
    if (ts.month,ts.day) in FIXED_HOLIDAYS:return 'HOLIDAY'
    return 'WEEKEND' if ts.dayofweek>=5 else 'WEEKDAY'


def resolve_tariff_posts(timestamps:pd.Series,*,distributor_id:str,rules:pd.DataFrame,timezone_name:str='America/Sao_Paulo')->pd.DataFrame:
    utc=pd.to_datetime(timestamps,utc=True,errors='raise');local=utc.dt.tz_convert(ZoneInfo(timezone_name));rows=[]
    r=rules[rules.distributor_id.astype(str).eq(str(distributor_id))].copy()
    if r.empty:
        return pd.DataFrame({'interval_start_utc':utc,'tariff_post':'UNIQUE'})
    for u,l in zip(utc,local):
        dtype=_day_type(l);mins=l.hour*60+l.minute;current=l.date();match=None
        candidates=r[r.day_type.astype(str).str.upper().isin([dtype,'ALL'])]
        for rr in candidates.itertuples(index=False):
            vf=pd.to_datetime(rr.valid_from).date();vt=pd.to_datetime(rr.valid_to).date()
            if not(vf<=current<=vt):continue
            start=_minutes(rr.start_local_time);end=_minutes(rr.end_local_time)
            inside=(start<=mins<end) if end>start else (mins>=start or mins<end)
            if inside:match=str(rr.tariff_post);break
        if match is None:raise ValueError(f'no tariff-post rule for {distributor_id} at local time {l}')
        rows.append({'interval_start_utc':u,'tariff_post':match})
    return pd.DataFrame(rows)
