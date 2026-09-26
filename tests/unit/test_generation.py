import pandas as pd
from motor_sin.generation.prepare import normalize_generation

def test_unknown_generation_type_preserved():
    raw=pd.DataFrame([{'din_instante':'2026-01-01T00:20:00Z','id_usina':'1','nom_usina':'X','nom_tipousina':'NovaFonte','id_subsistema':'SE','id_estado':'RJ','val_geracao':10}])
    out, unknown=normalize_generation(raw)
    assert out.iloc[0]['generation_type']=='NOVAFONTE'
    assert unknown==['NOVAFONTE']
    assert str(out.iloc[0]['interval_start_utc'])=='2026-01-01 00:00:00+00:00'
