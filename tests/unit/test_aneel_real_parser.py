import pandas as pd
import pytest
from motor_tarifa.base_tariff.parser import prepare_tariffs


def test_current_aneel_columns_and_decimal_comma():
 df=pd.DataFrame([
 {'SigAgente':'LIGHT','DatInicioVigencia':'01/01/2026','DatFimVigencia':'31/12/2026','DscBaseTarifaria':'Aplicacao','DscSubGrupo':'B1','DscModalidadeTarifaria':'Convencional','DscClasse':'Residencial','DscSubClasse':'Residencial','DscDetalhe':'Não se aplica','NomPostoTarifario':'Não se aplica','DscUnidadeTerciaria':'R$/MWh','VlrTUSD':'430,50','VlrTE':'280,25'},
 {'SigAgente':'LIGHT','DatInicioVigencia':'01/01/2026','DatFimVigencia':'31/12/2026','DscBaseTarifaria':'Aplicacao','DscSubGrupo':'A4','DscModalidadeTarifaria':'Verde','DscClasse':'Comercial','DscSubClasse':'Comercial','DscDetalhe':'Demanda','NomPostoTarifario':'Não se aplica','DscUnidadeTerciaria':'R$/kW','VlrTUSD':'32,10','VlrTE':'0'}])
 out,skip=prepare_tariffs(df)
 assert len(out)==1 and len(skip)==1
 assert out.iloc[0].base_total_rs_kwh==pytest.approx(0.71075)
 assert 'B1' in out.iloc[0].tariff_profile_id
 assert out.iloc[0].valid_from=='2026-01-01'
