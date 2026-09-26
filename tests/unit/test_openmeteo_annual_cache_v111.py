from __future__ import annotations

from urllib.error import HTTPError

import pandas as pd

from motor_sin.climate.batch_openmeteo import annual_date_windows, download_hourly_points_annual
from motor_sin.climate import batch_openmeteo
from motor_sin.climate import http_client


def test_annual_date_windows_split_partial_edges():
    assert annual_date_windows('2023-03-10','2025-02-04') == [
        (2023,'2023-03-10','2023-12-31'),
        (2024,'2024-01-01','2024-12-31'),
        (2025,'2025-01-01','2025-02-04'),
    ]


def test_hourly_annual_download_uses_year_partitions(monkeypatch, tmp_path):
    calls=[]
    def fake(points, *, start_date, end_date, raw_directory, progress_callback=None, **kwargs):
        calls.append((start_date,end_date,str(raw_directory)))
        if progress_callback:
            progress_callback({'phase':'year_fake','channel':'e2_hourly'})
        return pd.DataFrame([{
            'point_id':'p1','status':'cached','raw_file':str(tmp_path/'x.json'),
            'start_date':start_date,'end_date':end_date,
        }])
    monkeypatch.setattr(batch_openmeteo,'download_hourly_points_batched',fake)
    points=pd.DataFrame([{
        'point_id':'p1','name':'X','state':'SP','subsystem_id':'SE/CO',
        'latitude':-23.5,'longitude':-46.6,'timezone':'America/Sao_Paulo','weight':1.0,
    }])
    out=download_hourly_points_annual(
        points,start_date='2023-01-01',end_date='2024-03-01',raw_directory=tmp_path/'raw'
    )
    assert calls == [
        ('2023-01-01','2023-12-31',str(tmp_path/'raw'/'year=2023')),
        ('2024-01-01','2024-03-01',str(tmp_path/'raw'/'year=2024')),
    ]
    assert out['archive_year'].tolist()==[2023,2024]


def test_global_cooldown_after_three_consecutive_429(monkeypatch):
    sleeps=[]
    attempts={'n':0}
    class FakeResponse:
        status=200
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def read(self): return b'{"ok": true}'
    def fake_urlopen(request, timeout):
        attempts['n']+=1
        if attempts['n'] <= 3:
            raise HTTPError(request.full_url,429,'Too Many Requests',hdrs={},fp=None)
        return FakeResponse()
    monkeypatch.setattr(http_client,'urlopen',fake_urlopen)
    monkeypatch.setattr(http_client.time,'sleep',lambda seconds:sleeps.append(seconds))
    http_client.reset_rate_limit_state()
    status,payload=http_client.fetch_json_with_retry(
        'https://example.test/data',max_retries=5,base_backoff_seconds=1,
        cooldown_after_429=3,global_cooldown_seconds=30,max_backoff_seconds=10,
    )
    assert status==200 and payload['ok'] is True
    assert sleeps==[1,2,30]
    stats=http_client.rate_limit_stats()
    assert stats['total_429']==3
    assert stats['cooldowns']==1
    assert stats['consecutive_429']==0


def test_legacy_multiyear_hourly_raw_is_split_into_annual_cache(tmp_path):
    from motor_sin.climate.annual_cache import seed_annual_cache_from_legacy
    from motor_sin.climate.openmeteo import build_archive_parameters, OPENMETEO_ARCHIVE_URL
    from motor_sin.common.provenance import persist_immutable_raw_record, find_cached_raw_record

    legacy=tmp_path/'legacy_e2';annual=tmp_path/'annual_e2';legacy_e3=tmp_path/'legacy_e3';annual_e3=tmp_path/'annual_e3'
    params=build_archive_parameters(latitude=-23.5,longitude=-46.6,start_date='2023-12-31',end_date='2024-01-01',model='era5_seamless')
    payload={
        'latitude':-23.5,'longitude':-46.6,'utc_offset_seconds':0,'timezone':'GMT','elevation':10,
        'hourly_units':{'time':'iso8601','temperature_2m':'°C','dew_point_2m':'°C','precipitation':'mm','wind_speed_10m':'km/h','shortwave_radiation':'W/m²'},
        'hourly':{
            'time':['2023-12-31T23:00','2024-01-01T00:00'],
            'temperature_2m':[20,21],'dew_point_2m':[15,16],'precipitation':[0,1],
            'wind_speed_10m':[10,12],'shortwave_radiation':[0,0],
        },
    }
    external='era5_seamless:-23.5000:-46.6000:2023-12-31:2024-01-01'
    persist_immutable_raw_record(directory=legacy,source='open-meteo',source_service='historical',source_endpoint=OPENMETEO_ARCHIVE_URL,external_id=external,request_parameters=params,payload=payload,http_status=200)
    rep=seed_annual_cache_from_legacy(legacy_e2_directory=legacy,legacy_e3_directory=legacy_e3,annual_e2_directory=annual,annual_e3_directory=annual_e3)
    assert rep['e2']['created']==2
    p2023=build_archive_parameters(latitude=-23.5,longitude=-46.6,start_date='2023-12-31',end_date='2023-12-31',model='era5_seamless')
    e2023='era5_seamless:-23.5000:-46.6000:2023-12-31:2023-12-31'
    cached=find_cached_raw_record(directory=annual/'year=2023',source_service='historical',external_id=e2023,request_parameters=p2023)
    assert cached is not None
    assert cached[1]['payload']['hourly']['time']==['2023-12-31T23:00']


def test_persistent_429_becomes_deferred_not_raw_http_error(monkeypatch):
    sleeps=[]
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url,429,'Too Many Requests',hdrs={},fp=None)
    monkeypatch.setattr(http_client,'urlopen',fake_urlopen)
    monkeypatch.setattr(http_client.time,'sleep',lambda seconds:sleeps.append(seconds))
    http_client.reset_rate_limit_state()
    try:
        http_client.fetch_json_with_retry(
            'https://example.test/data',max_retries=1,base_backoff_seconds=1,
            cooldown_after_429=99,global_cooldown_seconds=30,max_backoff_seconds=2,
        )
    except http_client.OpenMeteoRateLimitDeferred as exc:
        assert exc.retry_after_seconds >= 900
        assert exc.stats['total_429'] == 2
    else:
        raise AssertionError('expected OpenMeteoRateLimitDeferred')
    assert sleeps == [1]


def test_archive_url_can_be_overridden_at_runtime(monkeypatch):
    from motor_sin.climate.openmeteo import get_openmeteo_archive_url
    monkeypatch.setenv('PREDICTA_OPENMETEO_ARCHIVE_URL','http://127.0.0.1:8080/v1/archive')
    assert get_openmeteo_archive_url() == 'http://127.0.0.1:8080/v1/archive'


def test_daily_batches_can_mix_timezones_in_one_request(monkeypatch, tmp_path):
    calls=[]
    def fake_fetch(url, **kwargs):
        calls.append(url)
        return 200,[{'daily':{'time':['2019-01-01']}},{'daily':{'time':['2019-01-01']}}]
    monkeypatch.setattr(batch_openmeteo,'fetch_json_with_retry',fake_fetch)
    monkeypatch.setattr(batch_openmeteo,'find_cached_raw_record',lambda **kwargs:None)
    counter={'n':0}
    def fake_persist(**kwargs):
        counter['n']+=1
        return tmp_path/f"p{counter['n']}.json",True,f'h{counter["n"]}'
    monkeypatch.setattr(batch_openmeteo,'persist_immutable_raw_record',fake_persist)
    points=pd.DataFrame([
        {'point_id':'p1','name':'A','state':'AM','subsystem_id':'N','latitude':-3.1,'longitude':-60.0,'timezone':'America/Manaus','weight':1.0},
        {'point_id':'p2','name':'B','state':'PA','subsystem_id':'N','latitude':-1.4,'longitude':-48.5,'timezone':'America/Belem','weight':1.0},
    ])
    rows=batch_openmeteo._daily_download_group(
        points,channel='baseline_temperature',model='era5_land',variables=('temperature_2m_max','temperature_2m_min'),
        start_date='2019-01-01',end_date='2019-12-31',raw_directory=tmp_path,timeout_seconds=30,batch_size=24,
        request_delay_seconds=0,max_retries=0,base_backoff_seconds=1,cooldown_after_429=3,global_cooldown_seconds=30,
    )
    assert len(calls)==1
    assert 'America%2FManaus%2CAmerica%2FBelem' in calls[0]
    assert len(rows)==2
