import json
from pathlib import Path

import numpy as np
import pandas as pd

from contracts.validators.core import validate_dataframe
from motor_sin.demand.inference import forecast_frozen_direct_family
from motor_sin.demand.registry import freeze_direct_model_family
from motor_sin.signals.real_signal import build_real_system_signal
from motor_tarifa.base_tariff.parser import prepare_tariffs
from motor_tarifa.customer.profiles import synthetic_daily_profile
from motor_tarifa.pipeline import load_tariff_config, simulate_dynamic_tariff


def _series(n=620):
    ts=pd.date_range('2025-01-01T00:00:00Z',periods=n,freq='h')
    hour=ts.hour.to_numpy();dow=ts.dayofweek.to_numpy()
    load=40000+4500*np.sin(2*np.pi*(hour-8)/24)+1000*(dow<5)+np.linspace(0,700,n)
    l=pd.DataFrame({'interval_start_utc':ts,'subsystem_id':'SE/CO','load_mw':load})
    temp=25+6*np.sin(2*np.pi*(hour-14)/24)
    z=pd.DataFrame({
        'interval_start_utc':ts,'subsystem_id':'SE/CO','weather_mode':'PERFECT_WEATHER_BACKTEST',
        'temperature_2m_mean':temp,'temperature_2m_p90':temp+2,
        'dewpoint_2m_mean':temp-5,'precipitation_mean':np.maximum(0,np.sin(np.arange(n)/30)),
        'wind_speed_10m_mean':3+np.sin(np.arange(n)/17),'solar_radiation_mean':np.maximum(0,500*np.sin(np.pi*(hour-6)/12)),
        'temperature_anomaly_mean':np.sin(np.arange(n)/100),
        'incident_heat_fraction':(temp>29).astype(float)*0.25,
        'incident_cell_fraction':(temp>29).astype(float)*0.25,
    })
    return l,z


def test_freeze_then_infer_without_retraining(tmp_path):
    load,climate=_series()
    model_dir=tmp_path/'models'
    manifest=freeze_direct_model_family(load,climate,subsystem_id='SE/CO',horizon=2,calibration_hours=48,output_dir=model_dir,model_family_id='TEST_FAMILY')
    assert len(manifest['models'])==2
    issue=load.interval_start_utc.iloc[-3]
    out=forecast_frozen_direct_family(load_history=load,future_zone_climate=climate,model_dir=model_dir,issue_time=issue,horizon=2,allow_perfect_weather=True)
    assert len(out)==2 and out.model_family_id.eq('TEST_FAMILY').all()
    assert (out.demand_p10_mw<=out.demand_p50_mw).all() and (out.demand_p50_mw<=out.demand_p90_mw).all()


def test_build_real_system_signal_contract():
    load,climate=_series(400)
    issue=load.interval_start_utc.iloc[-25]
    future=load.iloc[-24:].copy()
    forecast=pd.DataFrame({
        'issue_time_utc':issue,'interval_start_utc':future.interval_start_utc,'subsystem_id':'SE/CO',
        'demand_p10_mw':future.load_mw*0.97,'demand_p50_mw':future.load_mw,'demand_p90_mw':future.load_mw*1.03,
        'main_drivers_json':'{}',
    })
    ctx=climate[climate.interval_start_utc.isin(future.interval_start_utc)].copy()
    out=build_real_system_signal(forecast=forecast,load_history=load,climate_context=ctx,run_id='r1')
    vr=validate_dataframe(out,'system_signal_v1',expected_hours=24)
    assert vr.valid, vr.errors
    assert out.supply_pressure.isna().all()
    assert out.demand_percentile.between(0,1).all()


def test_aneel_unique_post_and_customer_tariff():
    raw=pd.DataFrame([{
        'SigAgente':'DIST TESTE','DatInicioVigencia':'01/01/2026','DatFimVigencia':'31/12/2026','DscBaseTarifaria':'Aplicacao',
        'DscSubGrupo':'B1','DscModalidadeTarifaria':'Convencional','DscClasse':'Residencial','DscSubClasse':'Residencial','DscDetalhe':'Não se aplica',
        'NomPostoTarifario':'Não se aplica','DscUnidadeTerciaria':'R$/MWh','VlrTUSD':'430,50','VlrTE':'280,25'
    }])
    base,skip=prepare_tariffs(raw)
    assert base.iloc[0].tariff_post=='UNIQUE' and skip.empty
    ts=pd.date_range('2026-06-01T03:00:00Z',periods=24,freq='h')
    signal=pd.DataFrame({
        'schema_version':'system_signal_v1','run_id':'r','interval_start_utc':ts,'zone_type':'SUBSYSTEM','zone_id':'SE/CO',
        'demand_p10_mw':100,'demand_p50_mw':110,'demand_p90_mw':120,'demand_percentile':np.linspace(.2,.9,24),
        'supply_pressure':None,'climate_exposure':0.1,'generation_by_type_json':'{}','main_drivers_json':'{}','data_freshness_ok':True,'quality_flags':'[]'
    })
    cons=synthetic_daily_profile(10,'residential',signal.interval_start_utc)
    out,rep=simulate_dynamic_tariff(system_signal=signal,base_tariffs=base,distributor_id='DIST TESTE',profile_id=base.iloc[0].tariff_profile_id,subsystem_id='SE/CO',config=load_tariff_config(),run_id='t',consumption_ref_kwh=cons.consumption_kwh.to_numpy())
    assert len(out)==24 and rep['reference_bill_rs']>0
    assert validate_dataframe(out,'tariff_v1',expected_hours=24).valid
