import pandas as pd
import pytest
from motor_sin.sources.ons_balance import prepare_ons_balance, source_url


def frame():
 return pd.DataFrame({'id_subsistema':['SE'],'nom_subsistema':['SUDESTE/CENTRO-OESTE'],'din_instante':['2025-01-01 00:00:00'],'val_gerhidraulica':['1.234,5'],'val_gertermica':['100,0'],'val_gereolica':['20'],'val_gersolar':['0'],'val_carga':['2.000,5'],'val_intercambio':['-10,0']})

def test_timezone_must_be_explicit_for_naive_ons_timestamp():
 with pytest.raises(ValueError,match='refuses to guess'):
  prepare_ons_balance(frame(),source_timezone=None)

def test_ons_balance_normalizes_and_separates_load_supply():
 load,supply=prepare_ons_balance(frame(),source_timezone='UTC')
 assert load.iloc[0].subsystem_id=='SE/CO'
 assert load.iloc[0].load_mw==pytest.approx(2000.5)
 assert supply.iloc[0].generation_hydro_mw==pytest.approx(1234.5)
 assert supply.iloc[0].generation_total_mw==pytest.approx(1354.5)
 assert str(load.interval_start_utc.dtype)=='datetime64[ns, UTC]'

def test_source_url_is_versioned_by_year():
 assert source_url(2025).endswith('BALANCO_ENERGIA_SUBSISTEMA_2025.parquet')


def test_ons_balance_accepts_sin_aggregate_row():
 frame_sin = pd.DataFrame({
  'id_subsistema':['SIN'],
  'nom_subsistema':['SISTEMA INTERLIGADO NACIONAL'],
  'din_instante':['2025-01-01 00:00:00'],
  'val_gerhidraulica':[40778.712],
  'val_gertermica':[6835.338],
  'val_gereolica':[17662.519],
  'val_gersolar':[1.0],
  'val_carga':[65277.570],
  'val_intercambio':[0.0],
 })
 load,supply=prepare_ons_balance(frame_sin,source_timezone='America/Sao_Paulo')
 assert load.iloc[0].subsystem_id=='SIN'
 assert load.iloc[0].load_mw==pytest.approx(65277.570)
 assert str(load.interval_start_utc.dtype)=='datetime64[ns, UTC]'
 assert str(load.iloc[0].interval_start_utc)=='2025-01-01 03:00:00+00:00'
