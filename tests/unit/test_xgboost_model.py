import numpy as np
import pandas as pd
import pytest
from motor_sin.demand.model import fit_demand_model, save_model, load_model, feature_contributions


def test_xgboost_model_roundtrip(tmp_path):
    pytest.importorskip('xgboost')
    x=np.arange(120,dtype=float)
    df=pd.DataFrame({'f1':x,'f2':np.sin(x/8),'load_mw':1000+2*x+20*np.sin(x/8)})
    model=fit_demand_model(df,['f1','f2'],algorithm='xgboost',xgb_params={'n_estimators':30,'max_depth':3,'learning_rate':0.1,'n_jobs':1})
    before=model.predict_p50(df.tail(5))
    path=tmp_path/'model.json';save_model(model,path);loaded=load_model(path);after=loaded.predict_p50(df.tail(5))
    assert np.allclose(before,after,rtol=1e-6,atol=1e-6)
    drivers=feature_contributions(loaded,df.iloc[-1])
    assert drivers and set(drivers).issubset({'f1','f2'})
