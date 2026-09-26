from __future__ import annotations
import numpy as np


def floor_cap(values,min_value,max_value):
    arr=np.asarray(values,float);clipped=np.clip(arr,min_value,max_value);return clipped,arr<min_value,arr>max_value

def ramp_limit(values,delta_max):
    arr=np.asarray(values,float).copy();applied=np.zeros(len(arr),dtype=bool)
    for i in range(1,len(arr)):
        lo=arr[i-1]-delta_max;hi=arr[i-1]+delta_max;new=float(np.clip(arr[i],lo,hi));applied[i]=abs(new-arr[i])>1e-12;arr[i]=new
    return arr,applied

def neutralize(values,weights=None,target=1.0):
    arr=np.asarray(values,float);w=np.ones(len(arr)) if weights is None else np.asarray(weights,float);den=float(np.sum(w));avg=float(np.sum(w*arr)/den) if den else 1.0;factor=float(target/max(avg,1e-12));return arr*factor,factor
