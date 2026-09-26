from __future__ import annotations
from pathlib import Path
import pandas as pd
from django.conf import settings
from motor_sin.common.io import read_table
from motor_sin.demand.direct import build_direct_frame, direct_feature_columns

ROOT=Path(settings.PREDICTA_PROJECT_ROOT)
LOAD=ROOT/'data/processed/demand/load_hourly.parquet'
CLIMATE={'E2':ROOT/'data/processed/climate/zone_climate_hourly.parquet','E3':ROOT/'data/processed/climate/zone_climate_hourly_e3.parquet'}

FEATURE_GROUPS=[
 {'name':'Estado no issue time','purpose':'Captura nível e tendência recente conhecidos no momento da emissão.','examples':['issue_lag_0h','issue_lag_1h','issue_lag_2h','issue_lag_24h','issue_lag_168h']},
 {'name':'Histórico do horário-alvo','purpose':'Mostra como a carga se comportou no mesmo horário que queremos prever.','examples':['target_lag_24h','target_lag_48h','target_lag_168h','mean_same_target_hour_3d','mean_same_target_hour_7d']},
 {'name':'Calendário do alvo','purpose':'Representa hora local, dia da semana, fim de semana, feriados e ciclicidade.','examples':['target_hour','target_day_of_week','target_weekend','target_hour_sin','target_hour_cos']},
 {'name':'Clima bruto (E2)','purpose':'Condições meteorológicas do horário-alvo: temperatura, precipitação, vento e radiação.','examples':['temperature_2m_mean','temperature_2m_p90','precipitation_mean','wind_speed_10m_mean','solar_radiation_mean']},
 {'name':'Contexto climático (E3)','purpose':'Diz se o clima é anômalo/extremo para o histórico regional em vez de usar apenas o valor absoluto.','examples':['temperature_anomaly_*','incident_heat_fraction','incident_cold_fraction','incident_rain_fraction','incident_wind_fraction']},
]

def preview_features(experiment='E3',subsystem='SE/CO',horizon=24,rows=20)->dict:
    exp=str(experiment).upper();h=int(horizon)
    if not LOAD.exists():return {'exists':False,'reason':'Carga ONS consolidada ainda não existe.'}
    load=read_table(LOAD);load=load[load.subsystem_id.astype(str).eq(subsystem)].copy()
    climate=None
    if exp in CLIMATE:
        p=CLIMATE[exp]
        if not p.exists():return {'exists':False,'reason':f'Dataset climático {exp} ainda não existe.'}
        climate=read_table(p);climate=climate[climate.subsystem_id.astype(str).eq(subsystem)].copy()
    frame=build_direct_frame(load,climate,horizon_hour=h,calendar_timezone='America/Sao_Paulo')
    features=direct_feature_columns(frame,exp)
    cols=['issue_time_utc','interval_start_utc','load_mw',*features]
    sample=frame[cols].dropna().tail(max(1,min(int(rows),100)))
    table=[]
    for row in sample.itertuples(index=False,name=None):
        vals=[]
        for v in row:
            if pd.isna(v):vals.append(None)
            elif isinstance(v,pd.Timestamp):vals.append(v.isoformat())
            elif hasattr(v,'item'):
                try:vals.append(v.item())
                except Exception:vals.append(str(v))
            else:vals.append(v)
        table.append(vals)
    return {'exists':True,'experiment':exp,'horizon':h,'feature_count':len(features),'features':features,'headers':cols,'table':table,'rows':len(sample)}
