from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import json
import pandas as pd
from django.conf import settings
from motor_sin.common.io import read_table

ROOT = Path(settings.PREDICTA_PROJECT_ROOT)

@dataclass(frozen=True)
class ArtifactSpec:
    key: str
    label: str
    path: str
    description: str
    stage: str
    category: str

ARTIFACTS = [
    ArtifactSpec('grid','Grade canônica 0,1°','data/processed/grid/brazil_grid_01deg.parquet','Índice espacial comum do projeto em EPSG:4326; não transforma carga agregada em dado por célula.','Fundação','Geoespacial'),
    ArtifactSpec('load','Carga ONS horária','data/processed/demand/load_hourly.parquet','Carga realizada normalizada por subsistema; é a variável-alvo do modelo.','Dados reais','ONS'),
    ArtifactSpec('supply','Oferta ONS observada','data/processed/generation/supply_by_subsystem_hourly.parquet','Geração observada por fonte/subsistema. É contexto físico e não é usada como geração futura.','Dados reais','ONS'),
    ArtifactSpec('climate_e2','Clima E2 por subsistema','data/processed/climate/zone_climate_hourly.parquet','Clima bruto horário agregado para o subsistema a partir de pontos representativos.','E2','Clima'),
    ArtifactSpec('climate_e3','Clima E3 enriquecido','data/processed/climate/zone_climate_hourly_e3.parquet','Clima E2 mais anomalias e eventos derivados do baseline de 10 anos.','E3','Clima'),
    ArtifactSpec('climate_operational','Clima operacional H01–H24','data/processed/climate/operational_zone_climate_24h.parquet','Previsão meteorológica disponível no issue time, com features compatíveis com o E3.','Operacional','Clima'),
    ArtifactSpec('climate_baseline','Baseline térmico E3','data/processed/climate/e3_temperature_baseline_monthly.parquet','Baseline 2015–2024 por ponto e mês para anomalias térmicas.','E3','Clima'),
    ArtifactSpec('e3_daily','Contexto diário E3','data/processed/climate/e3_daily_context.parquet','Anomalias e regras de eventos aplicadas a 2025 por ponto/dia.','E3','Clima'),
    ArtifactSpec('metrics_e1','Métricas E1/E0','outputs/metrics/real_pilot_metrics.csv','MAE, RMSE, WAPE e cobertura do backtest E0/E1.','Validação','Métricas'),
    ArtifactSpec('metrics_e3','Métricas E0–E3','outputs/metrics/e3_real_pilot_metrics.csv','Comparação final E0, E1, E2 e E3 no mesmo holdout.','Validação','Métricas'),
    ArtifactSpec('predictions_e3','Previsões held-out E3','outputs/metrics/e3_real_pilot_predictions.parquet','Previsões linha a linha por origem e horizonte, com realizado para auditoria.','Validação','Métricas'),
    ArtifactSpec('operational_forecast','Forecast operacional de demanda','data/processed/demand/operational_forecast_24h.parquet','H01–H24 por subsistema usando a família regional selecionada.','Operacional','Demanda'),
    ArtifactSpec('system_signal','system_signal_v1','outputs/contracts/system_signal_v1.parquet','Contrato de 24 horas entre Motor 1 e Motor 2.','Operacional','Contrato'),
    ArtifactSpec('distributor_catalog','Catálogo de distribuidoras','data/processed/tariff/distributor_catalog.csv','Áreas de concessão SIGEL/ANEEL relacionadas ao histórico tarifário por CNPJ.','Dados reais','Tarifa/Geo'),
    ArtifactSpec('distributor_geo','Áreas reais de concessão','data/processed/tariff/distributor_areas_wgs84.geojson','Polígonos reais das áreas de atuação, transformados para EPSG:4326 para uso no mapa web.','Dados reais','Geoespacial'),
    ArtifactSpec('base_tariffs','Tarifas-base ANEEL','data/processed/tariff/base_tariffs.parquet','TE + TUSD volumétricas normalizadas; componentes R$/kW permanecem separados.','Operacional','Tarifa'),
    ArtifactSpec('tariff_profiles','Perfis tarifários elegíveis','outputs/reports/tariff_profiles.csv','Perfis ANEEL válidos na data do sinal selecionado.','Operacional','Tarifa'),
    ArtifactSpec('tariff_v1','tariff_v1','outputs/contracts/tariff_v1.parquet','Tarifa dinâmica experimental por hora após guardrails.','Produto','Contrato'),
    ArtifactSpec('customer_hourly','Simulação horária do cliente','outputs/reports/customer_tariff_hourly.csv','Consumo do cliente + tarifa atual + tarifa dinâmica para as 24 horas.','Produto','Cliente'),
]


def artifact_path(spec: ArtifactSpec) -> Path:
    return ROOT / spec.path


def artifact_status(spec: ArtifactSpec) -> dict:
    p = artifact_path(spec)
    out = {'key':spec.key,'label':spec.label,'path':spec.path,'exists':p.exists(),'description':spec.description,'stage':spec.stage,'category':spec.category}
    if p.exists():
        stat = p.stat(); out.update({'bytes':stat.st_size,'modified':stat.st_mtime})
        try:
            if p.suffix.lower() in {'.csv','.parquet'}:
                df=read_table(p)
                out['rows']=int(len(df)); out['columns']=int(len(df.columns))
            elif p.suffix.lower()=='.json':
                payload=json.loads(p.read_text(encoding='utf-8')); out['rows']=len(payload) if isinstance(payload,list) else None
        except Exception as e:
            out['inspect_error']=str(e)
    return out


def all_artifact_statuses():
    return [artifact_status(a) for a in ARTIFACTS]


def get_artifact(key:str)->ArtifactSpec|None:
    return next((a for a in ARTIFACTS if a.key==key),None)


def _serialize_value(v):
    if pd.isna(v): return None
    if isinstance(v,pd.Timestamp): return v.isoformat()
    if hasattr(v,'item'):
        try: return v.item()
        except Exception: pass
    return str(v) if not isinstance(v,(str,int,float,bool)) else v


def preview_artifact(key:str, rows:int=30) -> dict:
    spec=get_artifact(key)
    if not spec: raise KeyError(key)
    p=artifact_path(spec)
    if not p.exists(): return {'spec':spec,'exists':False}
    if p.suffix.lower() not in {'.csv','.parquet'}:
        return {'spec':spec,'exists':True,'text':p.read_text(encoding='utf-8')[:20000]}
    df=read_table(p)
    head=df.head(max(1,min(int(rows),200))).copy()
    columns=[{'name':c,'dtype':str(df[c].dtype),'missing':int(df[c].isna().sum())} for c in df.columns]
    table=[[ _serialize_value(v) for v in row ] for row in head.itertuples(index=False,name=None)]
    numeric=df.select_dtypes(include='number')
    stats=[]
    if len(numeric.columns):
        desc=numeric.describe().T.reset_index().rename(columns={'index':'column'})
        for _,r in desc.iterrows():
            d={k:_serialize_value(v) for k,v in r.to_dict().items()}
            d['p25']=d.pop('25%',None); d['p50']=d.pop('50%',None); d['p75']=d.pop('75%',None)
            stats.append(d)
    chart=None
    time_candidates=[c for c in ['interval_start_utc','din_instante','issue_time_utc'] if c in df.columns]
    if time_candidates and len(numeric.columns):
        x=time_candidates[0]; y=next((c for c in numeric.columns if c not in {'horizon_hour'}),numeric.columns[0])
        sample=df[[x,y]].dropna().tail(168)
        chart={'x':[str(v) for v in sample[x].tolist()],'y':[float(v) for v in sample[y].tolist()],'y_label':y}
    return {'spec':spec,'exists':True,'row_count':int(len(df)),'column_count':int(len(df.columns)),'columns':columns,'headers':list(head.columns),'table':table,'stats':stats,'chart':chart}
