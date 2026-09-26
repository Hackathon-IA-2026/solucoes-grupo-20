import pandas as pd
from motor_tarifa.base_tariff.parser import prepare_tariffs


def test_tariff_parser_preserves_cnpj_and_human_profile_label():
    raw=pd.DataFrame([{
        'SigAgente':'ENEL RJ','NumCNPJDistribuidora':'33.050.071/0001-58','VlrTE':'329,38','VlrTUSD':'731,72',
        'DscUnidadeTerciaria':'MWh','DscSubGrupo':'B1','DscModalidadeTarifaria':'Convencional','DscClasse':'Residencial',
        'DscSubClasse':'Residencial','DscDetalhe':'Não se aplica','DscBaseTarifaria':'Tarifa de Aplicação',
        'NomPostoTarifario':'Não se aplica','DatInicioVigencia':'15/03/2026','DatFimVigencia':'14/03/2027'
    }])
    out,skip=prepare_tariffs(raw)
    assert not len(skip)
    assert out.iloc[0].distributor_cnpj=='33050071000158'
    assert out.iloc[0].tariff_post=='UNIQUE'
    assert 'B1' in out.iloc[0].profile_label
    assert abs(out.iloc[0].base_total_rs_kwh-1.06110)<1e-8

from motor_tarifa.pipeline import _select_tariff


def test_select_tariff_collapses_only_identical_economic_duplicates():
    rows=[{
        'distributor_id':'ENEL RJ','tariff_profile_id':'B1|Convencional|Residencial|Tarifa de Aplicação',
        'tariff_post':'UNIQUE','base_te_rs_kwh':0.32938,'base_tusd_rs_kwh':0.73172,'base_total_rs_kwh':1.06110,
        'valid_from':'2026-03-15','valid_to':'2027-03-14','source':'ANEEL','extra':'A'
    },{
        'distributor_id':'ENEL RJ','tariff_profile_id':'B1|Convencional|Residencial|Tarifa de Aplicação',
        'tariff_post':'UNIQUE','base_te_rs_kwh':0.32938,'base_tusd_rs_kwh':0.73172,'base_total_rs_kwh':1.06110,
        'valid_from':'2026-03-15','valid_to':'2027-03-14','source':'ANEEL','extra':'B'
    }]
    base=pd.DataFrame(rows)
    r=_select_tariff(base,'ENEL RJ',rows[0]['tariff_profile_id'],'UNIQUE',pd.Timestamp('2026-09-19T12:00:00Z'))
    assert abs(float(r.base_total_rs_kwh)-1.06110)<1e-8


def test_select_tariff_rejects_conflicting_economic_duplicates():
    rows=[{
        'distributor_id':'ENEL RJ','tariff_profile_id':'P','tariff_post':'UNIQUE',
        'base_te_rs_kwh':0.3,'base_tusd_rs_kwh':0.7,'base_total_rs_kwh':1.0,
        'valid_from':'2026-01-01','valid_to':'2026-12-31'
    },{
        'distributor_id':'ENEL RJ','tariff_profile_id':'P','tariff_post':'UNIQUE',
        'base_te_rs_kwh':0.4,'base_tusd_rs_kwh':0.7,'base_total_rs_kwh':1.1,
        'valid_from':'2026-01-01','valid_to':'2026-12-31'
    }]
    import pytest
    with pytest.raises(ValueError,match='must be unique'):
        _select_tariff(pd.DataFrame(rows),'ENEL RJ','P','UNIQUE',pd.Timestamp('2026-09-19T12:00:00Z'))


def test_tariff_parser_keeps_iso_aneel_dates_without_day_month_swap():
    raw=pd.DataFrame([{
        'SigAgente':'ENEL RJ','NumCNPJDistribuidora':'33050071000158','VlrTE':'329.38','VlrTUSD':'731.72',
        'DscUnidadeTerciaria':'MWh','DscSubGrupo':'B1','DscModalidadeTarifaria':'Convencional','DscClasse':'Residencial',
        'DscSubClasse':'Residencial','DscDetalhe':'Não se aplica','DscBaseTarifaria':'Tarifa de Aplicação',
        'NomPostoTarifario':'Não se aplica','DatInicioVigencia':'2026-03-15','DatFimVigencia':'2027-03-14'
    }])
    out,_=prepare_tariffs(raw)
    assert out.iloc[0].valid_from=='2026-03-15'
    assert out.iloc[0].valid_to=='2027-03-14'
