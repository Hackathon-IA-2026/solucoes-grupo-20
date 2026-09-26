import numpy as np,pandas as pd
from motor_sin.demand.prepare import prepare_load
from motor_sin.demand.features import build_supervised_features,feature_columns
from motor_sin.demand.model import fit_ridge_quantile

def test_load_half_hour_to_hour_and_no_future_lag():
 raw=pd.DataFrame({'din_referenciautc':['2026-01-01T00:00Z','2026-01-01T00:30Z','2026-01-01T01:00Z','2026-01-01T01:30Z'],'id_subsistema':['SE']*4,'val_carga':[100,120,130,150]})
 out=prepare_load(raw);assert out.iloc[0].load_mw==110;assert out.iloc[0].subsystem_id=='SE/CO'

def test_ridge_quantiles_order():
 n=250;ts=pd.date_range('2026-01-01',periods=n,freq='h',tz='UTC');load=100+10*np.sin(np.arange(n)/24*2*np.pi)+np.arange(n)*.01;df=pd.DataFrame({'interval_start_utc':ts,'subsystem_id':'S','load_mw':load});f=build_supervised_features(df);cols=feature_columns(f,'E1');m=fit_ridge_quantile(f,cols);valid=f.dropna(subset=cols).tail(10);p10,p50,p90=m.predict(valid);assert np.all(p10<=p50);assert np.all(p50<=p90)
