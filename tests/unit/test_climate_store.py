from __future__ import annotations
from pathlib import Path
from motor_sin.climate.local_store import find_local_records,contiguous_ranges,seed_store_from_annual_archive
from motor_sin.climate.openmeteo import build_archive_parameters
from motor_sin.common.provenance import persist_immutable_raw_record

def _hourly_payload(start,end):
    import pandas as pd
    idx=pd.date_range(start,end+' 23:00:00',freq='h');n=len(idx)
    return {'latitude':-15.8,'longitude':-47.9,'hourly_units':{'time':'iso8601','temperature_2m':'°C','dew_point_2m':'°C','precipitation':'mm','wind_speed_10m':'m/s','shortwave_radiation':'W/m²'},'hourly':{'time':[x.strftime('%Y-%m-%dT%H:%M') for x in idx],'temperature_2m':[20.0]*n,'dew_point_2m':[15.0]*n,'precipitation':[0.0]*n,'wind_speed_10m':[3.0]*n,'shortwave_radiation':[0.0]*n}}
def test_local_store_finds_only_new_date_delta(tmp_path:Path):
    params=build_archive_parameters(latitude=-15.8,longitude=-47.9,start_date='2026-01-01',end_date='2026-01-05',model='era5_seamless');persist_immutable_raw_record(directory=tmp_path,source='open-meteo',source_service='historical',source_endpoint='local-test',external_id='era5_seamless:-15.8000:-47.9000:2026-01-01:2026-01-05',request_parameters=params,payload=_hourly_payload('2026-01-01','2026-01-05'),http_status=200)
    desired=build_archive_parameters(latitude=-15.8,longitude=-47.9,start_date='2026-01-01',end_date='2026-01-08',model='era5_seamless');records,missing=find_local_records(directory=tmp_path,source_service='historical',request_parameters=desired,block_name='hourly',start_date='2026-01-01',end_date='2026-01-08');assert len(records)==1;assert missing==[('2026-01-06','2026-01-08')]
def test_local_store_full_window_has_no_gap(tmp_path:Path):
    params=build_archive_parameters(latitude=-15.8,longitude=-47.9,start_date='2025-01-01',end_date='2025-01-03',model='era5_seamless');persist_immutable_raw_record(directory=tmp_path,source='open-meteo',source_service='historical',source_endpoint='local-test',external_id='x',request_parameters=params,payload=_hourly_payload('2025-01-01','2025-01-03'),http_status=200);records,missing=find_local_records(directory=tmp_path,source_service='historical',request_parameters=params,block_name='hourly',start_date='2025-01-01',end_date='2025-01-03');assert len(records)==1;assert not missing
def test_contiguous_ranges():
    from datetime import date
    assert contiguous_ranges([date(2026,1,1),date(2026,1,2),date(2026,1,4)])==[('2026-01-01','2026-01-02'),('2026-01-04','2026-01-04')]
def test_seed_store_reuses_existing_cache(tmp_path:Path):
    source=tmp_path/'annual'/'n'/'hourly'/'year=2025';source.mkdir(parents=True);(source/'sample.json').write_text('{"ok":true}\n');target=tmp_path/'store';report=seed_store_from_annual_archive(annual_archive_root=tmp_path/'annual',store_root=target);assert report['created']==1;assert (target/'n'/'hourly'/'year=2025'/'sample.json').exists()
def test_hourly_local_only_never_requests_network_when_gap_exists(tmp_path:Path):
    import pandas as pd,pytest
    from motor_sin.climate.batch_openmeteo import download_hourly_points_batched
    from motor_sin.climate.local_store import LocalClimateStoreGap
    point=pd.DataFrame([{'point_id':'P1','name':'P1','state':'DF','subsystem_id':'SE/CO','latitude':-15.8,'longitude':-47.9,'timezone':'America/Sao_Paulo','weight':1.0}]);params=build_archive_parameters(latitude=-15.8,longitude=-47.9,start_date='2026-01-01',end_date='2026-01-02',model='era5_seamless');persist_immutable_raw_record(directory=tmp_path,source='open-meteo',source_service='historical',source_endpoint='local-test',external_id='x',request_parameters=params,payload=_hourly_payload('2026-01-01','2026-01-02'),http_status=200)
    with pytest.raises(LocalClimateStoreGap) as exc:download_hourly_points_batched(point,start_date='2026-01-01',end_date='2026-01-04',raw_directory=tmp_path,model='era5_seamless',allow_network=False)
    assert exc.value.gaps[0]['start_date']=='2026-01-03';assert exc.value.gaps[0]['end_date']=='2026-01-04'
