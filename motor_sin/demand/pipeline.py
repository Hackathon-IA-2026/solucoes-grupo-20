from __future__ import annotations
from datetime import timedelta

from pathlib import Path
import numpy as np
import pandas as pd
from motor_sin.demand.features import build_supervised_features,feature_columns
from motor_sin.demand.model import fit_ridge_quantile,save_model,load_model,feature_contributions
from motor_sin.demand.metrics import regression_metrics
from motor_sin.calendar.br_calendar import calendar_feature_frame


def train_models(load:pd.DataFrame,zone_climate:pd.DataFrame|None,model_dir:str|Path,experiment:str='E3',*,calendar_timezone:str='America/Sao_Paulo')->pd.DataFrame:
    feats=build_supervised_features(load,zone_climate,calendar_timezone=calendar_timezone);records=[]
    for zone,g in feats.groupby('subsystem_id'):
        cols=feature_columns(g,experiment);model=fit_ridge_quantile(g,cols);path=Path(model_dir)/f'{zone.replace("/","_")}_{experiment}.json';save_model(model,path);records.append({'subsystem_id':zone,'experiment':experiment,'model_path':str(path),'n_rows':int(g.dropna(subset=cols+['load_mw']).shape[0]),'n_features':len(cols),'calendar_timezone':calendar_timezone})
    return pd.DataFrame(records)


def backtest_models(load:pd.DataFrame,zone_climate:pd.DataFrame|None,*,experiment:str='E3',test_hours:int=168,forecast_horizon:int=24,origin_step_hours:int=24,calendar_timezone:str='America/Sao_Paulo')->pd.DataFrame:
    # Keep the legacy API, but route evaluation through the same fixed-origin anti-leakage engine used by the real pilot.
    from motor_sin.demand.experiments import compare_experiments
    rows=[]
    zones=sorted(load['subsystem_id'].astype(str).unique())
    for zone in zones:
        metrics,_=compare_experiments(load,zone_climate,subsystem_id=zone,test_hours=test_hours,forecast_horizon=forecast_horizon,origin_step_hours=origin_step_hours,calendar_timezone=calendar_timezone)
        sel=metrics[(metrics['experiment'].eq(experiment)) & (metrics['segment'].eq('ALL')) & (metrics['horizon'].eq('ALL'))]
        if sel.empty: raise ValueError(f'experiment {experiment} unavailable for subsystem {zone}')
        r=sel.iloc[0].to_dict();r.update({'train_method':'fixed_origin_direct_multi_horizon_target_history','test_hours':test_hours,'forecast_horizon':forecast_horizon,'origin_step_hours':origin_step_hours,'calendar_timezone':calendar_timezone});rows.append(r)
    return pd.DataFrame(rows)


def _calendar_row(ts:pd.Timestamp,calendar_timezone:str)->dict:
 s=pd.Series([pd.Timestamp(ts)])
 return calendar_feature_frame(s,timezone=calendar_timezone).iloc[0].to_dict()


def forecast_24h(*,load_history:pd.DataFrame,future_zone_climate:pd.DataFrame,models_index:pd.DataFrame,issue_time:pd.Timestamp,horizon:int=24,experiment:str='E3',calendar_timezone:str='America/Sao_Paulo')->pd.DataFrame:
    issue=pd.Timestamp(issue_time)
    if issue.tzinfo is None: issue=issue.tz_localize('UTC')
    else: issue=issue.tz_convert('UTC')
    output=[]
    climate=future_zone_climate.copy();climate['interval_start_utc']=pd.to_datetime(climate['interval_start_utc'],utc=True,errors='raise')
    for zone in sorted(models_index.subsystem_id.unique()):
        model_path=models_index.loc[models_index.subsystem_id.eq(zone),'model_path'].iloc[0];model=load_model(model_path)
        hist=load_history[load_history.subsystem_id.eq(zone)].copy();hist['interval_start_utc']=pd.to_datetime(hist.interval_start_utc,utc=True);hist=hist[hist['interval_start_utc'].le(issue)].copy();series={ts:float(v) for ts,v in zip(hist.interval_start_utc,hist.load_mw)}
        if issue not in series:
            raise ValueError(f'load history for {zone} must contain the issue-time observation {issue} so lag_1h is available for the first forecast hour')
        for step in range(1,horizon+1):
            ts=issue+timedelta(hours=int(step))
            row={'interval_start_utc':ts,'subsystem_id':zone,**_calendar_row(ts,calendar_timezone)}
            for lag in [1,2,24,48,168]:
                prev=series.get(ts-timedelta(hours=int(lag)));row[f'lag_{lag}h']=prev
            cr=climate[(climate.subsystem_id==zone)&(climate.interval_start_utc==ts)]
            if not cr.empty:
                for c,v in cr.iloc[0].items():
                    if c not in {'interval_start_utc','subsystem_id','weighting_method'}:row[c]=v
            frame=pd.DataFrame([row]);missing=[c for c in model.features if c not in frame or pd.isna(frame.iloc[0].get(c))]
            if missing:raise ValueError(f'missing future feature(s) for {zone} {ts}: {missing}')
            p10,p50,p90=model.predict(frame);p50v=float(p50[0]);series[ts]=p50v;output.append({'issue_time_utc':issue,'interval_start_utc':ts,'horizon_hour':step,'subsystem_id':zone,'demand_p10_mw':float(p10[0]),'demand_p50_mw':p50v,'demand_p90_mw':float(p90[0]),'main_drivers_json':feature_contributions(model,frame.iloc[0]),'calendar_timezone':calendar_timezone})
    return pd.DataFrame(output)
