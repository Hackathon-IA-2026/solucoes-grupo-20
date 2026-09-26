import pandas as pd,numpy as np
from motor_tarifa.base_tariff.parser import prepare_tariffs
from motor_tarifa.signal.calc import calculate_signal
from motor_tarifa.guardrails.core import ramp_limit

def test_tariff_unit_separation():
 raw=pd.DataFrame([{'distribuidora':'D','VlrTE':300,'VlrTUSD':400,'Unidade':'R$/MWh','Subgrupo':'B1'},{'distribuidora':'D','VlrTE':0,'VlrTUSD':20,'Unidade':'R$/kW','Subgrupo':'A4'}]);out,skip=prepare_tariffs(raw);assert len(out)==1 and len(skip)==1;assert abs(out.iloc[0].base_total_rs_kwh-.7)<1e-9

def test_signal_renormalizes_missing_supply_and_ramp():
 s,flags=calculate_signal(demand_pressure=1,supply_pressure=None,economic_signal=None,weights={'demand_pressure':.6,'supply_pressure':.4,'economic_signal':0});assert s==1 and 'SUPPLY_WEIGHT_RENORMALIZED' in flags
 vals,ap=ramp_limit([1,1.5],.1);assert abs(vals[1]-1.1)<1e-9 and ap[1]

def test_tariff_normalizes_nao_se_aplica_post_to_unique():
 raw=pd.DataFrame([{'SigAgente':'D','VlrTE':'300,00','VlrTUSD':'400,00','DscUnidadeTerciaria':'R$/MWh','DscSubGrupo':'B1','NomPostoTarifario':'Não se aplica','DatInicioVigencia':'01/01/2026','DatFimVigencia':'31/12/2026'}]);out,_=prepare_tariffs(raw);assert out.iloc[0].tariff_post=='UNIQUE'
