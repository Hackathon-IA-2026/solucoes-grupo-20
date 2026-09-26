#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import write_table


def main():
    n=24*120
    ts=pd.date_range('2025-01-01',periods=n,freq='h',tz='UTC')
    t=np.arange(n);hour=ts.hour.to_numpy();dow=ts.dayofweek.to_numpy()
    temp=25+6*np.sin(2*np.pi*(hour-14)/24)+2*np.sin(2*np.pi*t/(24*30))
    heat=(temp>31).astype(float)
    load=32000+3000*np.sin(2*np.pi*(hour-18)/24)+800*(dow<5)+160*temp+1200*heat+300*np.sin(2*np.pi*t/(24*7))
    rng=np.random.default_rng(42);load=load+rng.normal(0,220,n)
    raw=pd.DataFrame({
        'id_subsistema':'SE','nom_subsistema':'SUDESTE/CENTRO-OESTE','din_instante':ts.tz_localize(None).astype(str),
        'val_gerhidraulica':18000+500*np.sin(t/50),'val_gertermica':5000,'val_gereolica':1200,'val_gersolar':np.maximum(0,2500*np.sin(np.pi*(hour-6)/12)),
        'val_carga':load,'val_intercambio':0,
    })
    Path('tests/fixtures').mkdir(parents=True,exist_ok=True);raw.to_csv('tests/fixtures/ons_balance_source_shaped.csv',index=False)
    zone=pd.DataFrame({'interval_start_utc':ts,'subsystem_id':'SE/CO','temperature_2m_mean':temp,'temperature_2m_median':temp,'temperature_2m_p90':temp+1,'temperature_2m_max':temp+2,
        'precipitation_mean':np.maximum(0,rng.gamma(0.4,0.7,n)-0.2),'precipitation_p90':0.5,'wind_speed_10m_mean':4+np.sin(t/19),'wind_speed_10m_p90':6,'solar_radiation_mean':np.maximum(0,500*np.sin(np.pi*(hour-6)/12)),'solar_radiation_p90':600,
        'temperature_anomaly_mean':temp-25,'temperature_percentile_p90':np.clip((temp-18)/18,0,1),'incident_cell_fraction':heat*.2,'incident_heat_fraction':heat*.2,'incident_cold_fraction':0.0,'incident_rain_fraction':0.0,'incident_wind_fraction':0.0,'incident_solar_deficit_fraction':0.0,'weather_mode':'PERFECT_WEATHER_BACKTEST'})
    zone.to_csv('tests/fixtures/zone_climate_source_shaped.csv',index=False)
    tariff=pd.DataFrame([{'DatGeracaoConjuntoDados':'2026-09-18','DscREH':'REH 0000','SigAgente':'DIST TESTE','NumCNPJDistribuidora':'00000000000000','DatInicioVigencia':'01/01/2026','DatFimVigencia':'31/12/2026','DscBaseTarifaria':'Aplicacao','DscSubGrupo':'B1','DscModalidadeTarifaria':'Convencional','DscClasse':'Residencial','DscSubClasse':'Residencial','DscDetalhe':'Não se aplica','NomPostoTarifario':'Não se aplica','DscUnidadeTerciaria':'R$/MWh','SigAgenteAcessante':'','VlrTUSD':'430,50','VlrTE':'280,25'},
                         {'DatGeracaoConjuntoDados':'2026-09-18','DscREH':'REH 0000','SigAgente':'DIST TESTE','NumCNPJDistribuidora':'00000000000000','DatInicioVigencia':'01/01/2026','DatFimVigencia':'31/12/2026','DscBaseTarifaria':'Aplicacao','DscSubGrupo':'A4','DscModalidadeTarifaria':'Verde','DscClasse':'Comercial','DscSubClasse':'Comercial','DscDetalhe':'Demanda','NomPostoTarifario':'Não se aplica','DscUnidadeTerciaria':'R$/kW','SigAgenteAcessante':'','VlrTUSD':'32,10','VlrTE':'0'}])
    tariff.to_csv('tests/fixtures/aneel_tariff_source_shaped.csv',index=False)
    print('generated source-shaped fixtures')
if __name__=='__main__':main()
