from __future__ import annotations
import numpy as np

def regression_metrics(y,p50,p10=None,p90=None)->dict:
 y=np.asarray(y,float);p=np.asarray(p50,float);err=y-p;out={'MAE':float(np.mean(np.abs(err))),'RMSE':float(np.sqrt(np.mean(err**2))),'WAPE':float(np.sum(np.abs(err))/max(np.sum(np.abs(y)),1e-9))}
 if p10 is not None and p90 is not None:out['p10_p90_coverage']=float(np.mean((y>=np.asarray(p10))&(y<=np.asarray(p90))))
 return out
