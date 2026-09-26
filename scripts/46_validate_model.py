#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys, hashlib
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table, write_table, write_json
from motor_sin.demand.experiments import compare_experiments
from motor_sin.demand.availability import align_experiment_period



def main():
    p=argparse.ArgumentParser(description='Valida uma configuração de modelo (Ridge ou XGBoost) no backtest fixed-origin H01..H24.')
    p.add_argument('--experiment',choices=['E1','E2','E3'],default='E3')
    p.add_argument('--algorithm',choices=['ridge','xgboost'],default='ridge')
    p.add_argument('--load',default='data/processed/demand/load_hourly.parquet')
    p.add_argument('--climate')
    p.add_argument('--subsystem',default='SE/CO')
    p.add_argument('--history-start')
    p.add_argument('--history-end')
    p.add_argument('--test-hours',type=int,default=720)
    p.add_argument('--calibration-hours',type=int,default=720)
    p.add_argument('--forecast-horizon',type=int,default=24)
    p.add_argument('--origin-step-hours',type=int,default=24)
    p.add_argument('--calendar-timezone',default='America/Sao_Paulo')
    p.add_argument('--alpha',type=float,default=1.0)
    p.add_argument('--n-estimators',type=int,default=350)
    p.add_argument('--max-depth',type=int,default=6)
    p.add_argument('--learning-rate',type=float,default=0.05)
    p.add_argument('--subsample',type=float,default=0.9)
    p.add_argument('--colsample-bytree',type=float,default=0.9)
    p.add_argument('--output-prefix')
    a=p.parse_args()
    climate_path=a.climate
    if not climate_path:
        if a.experiment=='E2': climate_path='data/processed/climate/zone_climate_hourly.parquet'
        elif a.experiment=='E3': climate_path='data/processed/climate/zone_climate_hourly_e3.parquet'
    raw_load=read_table(a.load)
    raw_climate=read_table(climate_path) if climate_path else None
    load,climate,availability=align_experiment_period(
        raw_load,raw_climate,experiment=a.experiment,subsystem_id=a.subsystem,
        requested_start=a.history_start,requested_end=a.history_end,
    )
    load_start=availability.effective_start;load_end=availability.effective_end
    climate_start=availability.climate_start;climate_end=availability.climate_end
    print(json.dumps({'availability_window':availability.to_dict()},ensure_ascii=False,indent=2))
    if availability.adjusted_to_common_overlap:
        print('INFO: E2/E3 history was automatically clipped to the common ONS + climate coverage window.')
    xgb_params={'n_estimators':a.n_estimators,'max_depth':a.max_depth,'learning_rate':a.learning_rate,'subsample':a.subsample,'colsample_bytree':a.colsample_bytree}
    metrics,preds=compare_experiments(
        load,climate,subsystem_id=a.subsystem,test_hours=a.test_hours,forecast_horizon=a.forecast_horizon,
        origin_step_hours=a.origin_step_hours,calendar_timezone=a.calendar_timezone,calibration_hours=a.calibration_hours,
        alpha=a.alpha,algorithm=a.algorithm,xgb_params=xgb_params if a.algorithm=='xgboost' else None,
        experiments_override=[a.experiment],
    )
    config_for_id={'experiment':a.experiment,'algorithm':a.algorithm,'subsystem':a.subsystem,'history_start':a.history_start,'history_end':a.history_end,'test_hours':a.test_hours,'calibration_hours':a.calibration_hours,'alpha':a.alpha,'xgb_params':xgb_params if a.algorithm=='xgboost' else None}
    digest=hashlib.sha1(json.dumps(config_for_id,sort_keys=True,ensure_ascii=True).encode()).hexdigest()[:8]
    period=f'{a.history_start or "auto"}_{a.history_end or "latest"}'.replace('-','')
    slug=f'{a.experiment.lower()}_{a.algorithm.lower()}_{a.subsystem.replace("/","_").lower()}_{period}_{digest}'
    prefix=Path(a.output_prefix or f'outputs/metrics/model_validation/{slug}')
    metrics_path=prefix.with_name(prefix.name+'_metrics.csv');preds_path=prefix.with_name(prefix.name+'_predictions.parquet');report_path=Path('outputs/reports/model_validation')/f'{slug}.json'
    write_table(metrics,metrics_path);write_table(preds,preds_path)
    overall=metrics[(metrics.experiment.eq(a.experiment))&(metrics.segment.eq('ALL'))&(metrics.horizon.eq('ALL'))]
    row=overall.iloc[0].to_dict() if len(overall) else {}
    report={'validation_slug':slug,'experiment':a.experiment,'algorithm':a.algorithm,'subsystem_id':a.subsystem,'history_start_requested':a.history_start,'history_end_requested':a.history_end,'load_period_effective':{'start':load_start,'end':load_end,'rows':int(len(load))},'climate_period_effective':{'start':climate_start,'end':climate_end,'rows':int(len(climate)) if climate is not None else 0},'availability_window':availability.to_dict(),'test_hours':a.test_hours,'calibration_hours':a.calibration_hours,'metrics':{k:(None if pd.isna(v) else float(v) if isinstance(v,(int,float)) else v) for k,v in row.items()},'xgboost_params':xgb_params if a.algorithm=='xgboost' else None,'ridge_alpha':a.alpha if a.algorithm=='ridge' else None,'metrics_output':str(metrics_path),'predictions_output':str(preds_path)}
    write_json(report,report_path)
    show=metrics[(metrics.segment.eq('ALL'))&metrics.horizon.isin(['ALL','H01','H06','H12','H24'])]
    print(show.to_string(index=False));print(json.dumps(report,ensure_ascii=False,indent=2,default=str))

if __name__=='__main__': main()
