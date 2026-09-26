from __future__ import annotations
import numpy as np

def bill_kwh(consumption_kwh,tariff_rs_kwh)->float:return float(np.sum(np.asarray(consumption_kwh,float)*np.asarray(tariff_rs_kwh,float)))
