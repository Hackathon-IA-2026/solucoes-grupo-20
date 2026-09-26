from __future__ import annotations
import numpy as np


def centered01(value:float)->float:return 2.0*(float(value)-0.5)

def calculate_signal(*,demand_pressure:float,supply_pressure:float|None,economic_signal:float|None,weights:dict[str,float])->tuple[float,list[str]]:
    vals={'demand_pressure':centered01(demand_pressure),'supply_pressure':None if supply_pressure is None else centered01(supply_pressure),'economic_signal':economic_signal}
    active=[(k,float(weights.get(k,0)),v) for k,v in vals.items() if v is not None and float(weights.get(k,0))>0]
    if not active:return 0.0,['NO_ACTIVE_SIGNAL_COMPONENTS']
    denom=sum(w for _,w,_ in active);signal=sum((w/denom)*float(v) for _,w,v in active)
    flags=[]
    if supply_pressure is None and float(weights.get('supply_pressure',0))>0:flags.append('SUPPLY_WEIGHT_RENORMALIZED')
    return float(np.clip(signal,-1,1)),flags
