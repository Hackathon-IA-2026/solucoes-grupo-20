import numpy as np
import pandas as pd
from motor_sin.demand.real_gate import validate_real_pilot
from motor_sin.demand.experiments import compare_experiments,incremental_summary


def make_data(n=24*80):
 ts=pd.date_range('2025-01-01 03:00:00',periods=n,freq='h',tz='UTC')
 local=ts.tz_convert('America/Sao_Paulo');h=local.hour.to_numpy();temp=24+7*np.sin(2*np.pi*(h-14)/24);heat=(temp>30).astype(float);rng=np.random.default_rng(1)
 load=pd.DataFrame({'interval_start_utc':ts,'subsystem_id':'SE/CO','load_mw':30000+3000*np.sin(2*np.pi*(h-18)/24)+250*temp+1500*heat+rng.normal(0,120,n)})
 climate=pd.DataFrame({'interval_start_utc':ts,'subsystem_id':'SE/CO','temperature_2m_mean':temp,'precipitation_mean':0.1,'wind_speed_10m_mean':4.0,'solar_radiation_mean':np.maximum(0,500*np.sin(np.pi*(h-6)/12)),'temperature_anomaly_mean':temp-24,'temperature_percentile_p90':np.clip((temp-15)/20,0,1),'incident_cell_fraction':heat*.2,'incident_heat_fraction':heat*.2,'incident_cold_fraction':0.0,'incident_rain_fraction':0.0,'incident_wind_fraction':0.0,'incident_solar_deficit_fraction':0.0,'weather_mode':'PERFECT_WEATHER_BACKTEST'})
 return load,climate


def test_gate_and_fixed_origin_common_window():
 load,climate=make_data();g=validate_real_pilot(load,climate,subsystem_id='SE/CO',weather_mode='PERFECT_WEATHER_BACKTEST');assert g['ready']
 m,p=compare_experiments(load,climate,subsystem_id='SE/CO',test_hours=24*10,forecast_horizon=24,origin_step_hours=24,calendar_timezone='America/Sao_Paulo')
 assert {'E0_D1','E0_D7','E0_BLEND','E1','E2','E3'}.issubset(set(m.experiment))
 all_rows=m[(m.segment.eq('ALL')) & (m.horizon.eq('ALL'))]
 assert len(set(all_rows.n_rows))==1
 assert p['issue_time_utc'].nunique()==10
 assert set(p['horizon_hour'].unique())==set(range(1,25))
 assert (p['interval_start_utc'] > p['issue_time_utc']).all()
 assert incremental_summary(m)['baseline_reference']=='E1'


def test_fixed_origin_does_not_read_future_observed_load_for_single_origin():
 load,climate=make_data(n=24*35)
 m1,p1=compare_experiments(load,climate,subsystem_id='SE/CO',test_hours=24,forecast_horizon=24,origin_step_hours=24,calendar_timezone='America/Sao_Paulo')
 # Change every observed target after the issue time. With one 24h origin these values are evaluation targets only,
 # never lag inputs. Forecasts must remain byte-for-byte numerically equal.
 changed=load.copy();target_times=set(p1[p1.experiment.eq('E1')]['interval_start_utc'])
 changed.loc[changed.interval_start_utc.isin(target_times),'load_mw'] += 10000
 _,p2=compare_experiments(changed,climate,subsystem_id='SE/CO',test_hours=24,forecast_horizon=24,origin_step_hours=24,calendar_timezone='America/Sao_Paulo')
 a=p1[p1.experiment.eq('E1')].sort_values('horizon_hour')['p50_mw'].to_numpy()
 b=p2[p2.experiment.eq('E1')].sort_values('horizon_hour')['p50_mw'].to_numpy()
 assert np.allclose(a,b)


def test_operational_mode_requires_tagged_forecast():
 load,climate=make_data();climate['weather_mode']='PERFECT_WEATHER_BACKTEST';g=validate_real_pilot(load,climate,subsystem_id='SE/CO',weather_mode='OPERATIONAL_FORECAST');assert not g['ready']


def test_direct_multi_horizon_and_horizon_specific_calibration_metadata():
 load,climate=make_data(n=24*100)
 _,p=compare_experiments(load,climate,subsystem_id='SE/CO',test_hours=24*10,forecast_horizon=24,origin_step_hours=24,calendar_timezone='America/Sao_Paulo',calibration_hours=240)
 e1=p[p.experiment.eq('E1')]
 assert set(e1.model_strategy)=={'direct_multi_horizon_target_history'}
 assert set(e1.interval_calibration_method)=={'heldout_pretest_asymmetric_residual_quantiles'}
 assert e1.interval_calibration_rows.min()>=48
 assert e1.interval_calibration_coverage.between(0,1).all()
 assert (e1.p10_mw <= e1.p50_mw).all()
 assert (e1.p50_mw <= e1.p90_mw).all()
 # Direct strategy has one independently fitted model for every operational horizon.
 assert set(e1.horizon_hour.unique())==set(range(1,25))


def test_direct_h02_does_not_depend_on_h01_observed_target():
 load,climate=make_data(n=24*40)
 _,p1=compare_experiments(load,climate,subsystem_id='SE/CO',test_hours=24,forecast_horizon=24,origin_step_hours=24,calendar_timezone='America/Sao_Paulo',calibration_hours=168)
 e1=p1[p1.experiment.eq('E1')].sort_values('horizon_hour')
 h01_time=e1.loc[e1.horizon_hour.eq(1),'interval_start_utc'].iloc[0]
 changed=load.copy();changed.loc[changed.interval_start_utc.eq(h01_time),'load_mw'] += 50000
 _,p2=compare_experiments(changed,climate,subsystem_id='SE/CO',test_hours=24,forecast_horizon=24,origin_step_hours=24,calendar_timezone='America/Sao_Paulo',calibration_hours=168)
 a=e1.loc[e1.horizon_hour.eq(2),'p50_mw'].iloc[0]
 b=p2[(p2.experiment.eq('E1')) & (p2.horizon_hour.eq(2))]['p50_mw'].iloc[0]
 assert a==b


def test_target_history_features_are_aligned_to_target_and_known_at_issue():
 from motor_sin.demand.direct import build_direct_frame, direct_feature_columns
 n=24*20
 ts=pd.date_range('2025-01-01 03:00:00',periods=n,freq='h',tz='UTC')
 load=pd.DataFrame({'interval_start_utc':ts,'subsystem_id':'SE/CO','load_mw':np.arange(n,dtype=float)})
 frame=build_direct_frame(load,None,horizon_hour=12,calendar_timezone='America/Sao_Paulo')
 # Choose a row well after all historical windows exist.
 i=24*10
 issue=frame.iloc[i]['issue_time_utc'];target=frame.iloc[i]['interval_start_utc']
 lookup=dict(zip(ts,np.arange(n,dtype=float)))
 row=frame.iloc[i]
 assert row['target_lag_24h']==lookup[target-pd.Timedelta(hours=24)]
 assert row['target_lag_48h']==lookup[target-pd.Timedelta(hours=48)]
 assert row['target_lag_168h']==lookup[target-pd.Timedelta(hours=168)]
 assert target-pd.Timedelta(hours=24) <= issue
 assert np.isclose(row['mean_same_target_hour_3d'],np.mean([lookup[target-np.timedelta64(d, 'D')] for d in range(1,4)]))
 assert np.isclose(row['mean_same_target_hour_7d'],np.mean([lookup[target-np.timedelta64(d, 'D')] for d in range(1,8)]))
 cols=direct_feature_columns(frame,'E1')
 for c in ['target_lag_24h','target_lag_48h','target_lag_168h','mean_same_target_hour_3d','mean_same_target_hour_7d','target_hour_sin','target_hour_cos']:
  assert c in cols


def test_h24_target_lag_24_is_exactly_issue_load_not_future():
 from motor_sin.demand.direct import build_direct_prediction_row
 n=24*15
 ts=pd.date_range('2025-01-01 03:00:00',periods=n,freq='h',tz='UTC')
 vals=np.arange(n,dtype=float)
 lookup=dict(zip(ts,vals))
 issue=ts[-25];target=issue+pd.Timedelta(hours=24)
 row=build_direct_prediction_row(issue=issue,target=target,subsystem_id='SE/CO',actual_lookup=lookup,climate_lookup=None,calendar_timezone='America/Sao_Paulo').iloc[0]
 assert row['target_lag_24h']==lookup[issue]
 assert row['target_lag_48h']==lookup[issue-pd.Timedelta(hours=24)]
 assert row['mean_same_target_hour_7d']==np.mean([lookup[target-np.timedelta64(d, 'D')] for d in range(1,8)])
