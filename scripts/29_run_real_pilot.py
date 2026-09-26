#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table,write_json
from motor_sin.demand.real_gate import validate_real_pilot
from motor_sin.demand.experiments import compare_experiments,incremental_summary


def main():
 p=argparse.ArgumentParser(description='Piloto real E0/E1/E2/E3 com direct multi-horizon H01-H24, histórico do horário-alvo e intervalos calibrados por horizonte.')
 p.add_argument('--load',required=True)
 p.add_argument('--climate')
 p.add_argument('--subsystem',default='SE/CO')
 p.add_argument('--weather-mode',choices=['PERFECT_WEATHER_BACKTEST','OPERATIONAL_FORECAST'],default='PERFECT_WEATHER_BACKTEST')
 p.add_argument('--test-hours',type=int,default=720,help='Tamanho da janela final de avaliação. Ex.: 720 = 30 dias.')
 p.add_argument('--forecast-horizon',type=int,default=24,help='Horizonte emitido em cada origem. MVP: 24h.')
 p.add_argument('--origin-step-hours',type=int,default=24,help='Distância entre origens de previsão. Default: uma origem por dia.')
 p.add_argument('--calendar-timezone',default='America/Sao_Paulo',help='Fuso civil usado apenas para hora/dia/feriados; armazenamento e joins permanecem UTC.')
 p.add_argument('--calibration-hours',type=int,default=720,help='Bloco cronológico pré-teste usado para calibrar p10/p90 separadamente por horizonte. Default: 720h.')
 p.add_argument('--start');p.add_argument('--end')
 p.add_argument('--metrics-output',default='outputs/metrics/real_pilot_metrics.csv')
 p.add_argument('--predictions-output',default='outputs/metrics/real_pilot_predictions.parquet')
 p.add_argument('--report-output',default='outputs/reports/real_pilot_summary.json')
 a=p.parse_args();load=read_table(a.load);climate=read_table(a.climate) if a.climate else None
 gate=validate_real_pilot(load,climate,subsystem_id=a.subsystem,weather_mode=a.weather_mode,start=a.start,end=a.end)
 if not gate['ready']:
  write_json(gate,'outputs/reports/real_data_gate.json');print(json.dumps(gate,indent=2,ensure_ascii=False));raise SystemExit(2)
 # Optional date filter applied after gate using canonical UTC timestamps.
 load=load.copy();load['interval_start_utc']=pd.to_datetime(load['interval_start_utc'],utc=True,errors='raise')
 if a.start:
  start=pd.Timestamp(a.start);start=start.tz_localize('UTC') if start.tzinfo is None else start.tz_convert('UTC');load=load[load.interval_start_utc>=start]
 if a.end:
  end=pd.Timestamp(a.end);end=end.tz_localize('UTC') if end.tzinfo is None else end.tz_convert('UTC');load=load[load.interval_start_utc<=end]
 if climate is not None:
  climate=climate.copy();climate['interval_start_utc']=pd.to_datetime(climate['interval_start_utc'],utc=True,errors='raise')
  if a.start: climate=climate[climate.interval_start_utc>=start]
  if a.end: climate=climate[climate.interval_start_utc<=end]
 metrics,preds=compare_experiments(
  load,climate,subsystem_id=a.subsystem,test_hours=a.test_hours,
  forecast_horizon=a.forecast_horizon,origin_step_hours=a.origin_step_hours,
  calendar_timezone=a.calendar_timezone,calibration_hours=a.calibration_hours,
 )
 write_table(metrics,a.metrics_output);write_table(preds,a.predictions_output)
 direct=preds[preds['model_strategy'].astype(str).str.startswith('direct_multi_horizon')].copy() if 'model_strategy' in preds else pd.DataFrame()
 cal_audit={}
 if len(direct):
  one=direct.drop_duplicates(['experiment','horizon_hour'])
  e1=one[one['experiment'].eq('E1')]
  if len(e1):
   cal_audit={
    'method':str(e1['interval_calibration_method'].iloc[0]),
    'requested_hours':a.calibration_hours,
    'effective_rows_min':int(e1['interval_calibration_rows'].min()),
    'effective_rows_max':int(e1['interval_calibration_rows'].max()),
    'empirical_coverage_mean':float(e1['interval_calibration_coverage'].mean()),
    'empirical_coverage_min':float(e1['interval_calibration_coverage'].min()),
    'empirical_coverage_max':float(e1['interval_calibration_coverage'].max()),
   }
 summary={
  'gate':gate,
  'backtest':{
   'method':'fixed_origin_direct_multi_horizon_target_history',
   'forecast_horizon_hours':a.forecast_horizon,
   'origin_step_hours':a.origin_step_hours,
   'calendar_timezone':a.calendar_timezone,
   'calibration_hours':a.calibration_hours,
   'interval_calibration':'held-out chronological pre-test residual quantiles, independently per H01..H24',
   'n_origins':int(preds['issue_time_utc'].nunique()),
   'anti_leakage':'Each H01..H24 model uses issue-time state plus target-relative historical load that is guaranteed to be at or before issue time. No forecast horizon consumes another horizon prediction or observed future load.',
   'feature_set_version':'v1.1.4_target_history',
  },
  'interval_calibration_audit':cal_audit,
  'comparison':incremental_summary(metrics),
  'interpretation_rule':'Negative WAPE change means lower error than E1. Do not claim climate improvement unless measured on held-out fixed-origin forecasts.',
  'metrics_output':a.metrics_output,'predictions_output':a.predictions_output,
 }
 write_json(summary,a.report_output)
 # Console focuses on aggregate and salient horizons; full H01..H24 remains in CSV.
 show=metrics[(metrics['segment'].eq('ALL')) & (metrics['horizon'].isin(['ALL','H01','H06','H12','H24']))]
 print(show.to_string(index=False));print(json.dumps(summary['comparison'],indent=2,ensure_ascii=False))
if __name__=='__main__':main()
