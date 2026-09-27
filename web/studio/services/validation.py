from __future__ import annotations
from pathlib import Path
import json
import pandas as pd
from django.conf import settings
from motor_sin.common.io import read_table

ROOT=Path(settings.PREDICTA_PROJECT_ROOT)
VAL_DIR=ROOT/'outputs/metrics/model_validation'
REP_DIR=ROOT/'outputs/reports/model_validation'
REGIONS=('N','NE','S','SE/CO')
DESSEM_PATH=ROOT/'data/processed/generation/dessem_schedule_hourly.parquet'


def _region_from_slug(slug:str)->str|None:
    normalized=f'_{slug.lower().replace("-","_")}_'
    for token,region in (('_se_co_','SE/CO'),('_seco_','SE/CO'),('_ne_','NE'),('_n_','N'),('_s_','S')):
        if token in normalized:return region
    return None


def _contextual_comparisons(runs:list[dict])->list[dict]:
    comparisons=[]
    for region in REGIONS:
        candidates=[r for r in runs if r.get('region')==region and r.get('comparison_group')=='auto_2023_2026' and r.get('experiment')=='E3']
        if not candidates:continue
        forecast=min(candidates,key=lambda r:r['WAPE'])
        dessem=_dessem_benchmark(forecast)
        comparisons.append({'region':region,'forecast':forecast,'dessem':dessem})
    return comparisons


def _dessem_benchmark(run:dict)->dict|None:
    predictions_path=run.get('predictions_path')
    if not predictions_path or not DESSEM_PATH.exists():return None
    path=ROOT/predictions_path
    if not path.exists():return None
    predictions=read_table(path)
    predictions=predictions[predictions.experiment.astype(str).eq(run['experiment'])].copy()
    schedule=read_table(DESSEM_PATH)
    for frame in (predictions,schedule):
        frame['interval_start_utc']=pd.to_datetime(frame['interval_start_utc'],utc=True,errors='coerce')
    schedule=schedule[schedule.subsystem_id.astype(str).eq(run['region'])]
    aligned=predictions.merge(
        schedule[['interval_start_utc','subsystem_id','programmed_load_mw','available_at_utc']],
        on=['interval_start_utc','subsystem_id'],how='inner',
    ).dropna(subset=['actual_mw','p50_mw','programmed_load_mw'])
    denominator=aligned.actual_mw.abs().sum()
    if aligned.empty or not denominator:return None
    predicta_wape=(aligned.actual_mw-aligned.p50_mw).abs().sum()/denominator
    dessem_wape=(aligned.actual_mw-aligned.programmed_load_mw).abs().sum()/denominator
    available=pd.to_datetime(aligned.available_at_utc,utc=True,errors='coerce')
    return {
        'predicta_wape_pct':100*predicta_wape,'dessem_wape_pct':100*dessem_wape,
        'gain_pct':100*(1-predicta_wape/dessem_wape) if dessem_wape else None,
        'rows':len(aligned),'total_rows':len(predictions),'coverage_pct':100*len(aligned)/len(predictions),
        'start':aligned.interval_start_utc.min(),'end':aligned.interval_start_utc.max(),
        'retrospective':bool((available>aligned.interval_start_utc).any()),
    }


def validation_runs()->list[dict]:
    rows=[]
    if not VAL_DIR.exists():return rows
    for p in sorted(VAL_DIR.glob('*_metrics.csv'),key=lambda x:x.stat().st_mtime,reverse=True):
        try:
            df=read_table(p);model=df[~df.experiment.astype(str).str.startswith('E0_')]
            overall=model[(model.segment=='ALL')&(model.horizon=='ALL')]
            if overall.empty:continue
            r=overall.iloc[0];slug=p.name[:-12] if p.name.endswith('_metrics.csv') else p.stem
            pred=p.with_name(p.name.replace('_metrics.csv','_predictions.parquet'))
            report_path=REP_DIR/f'{slug}.json';report={}
            if report_path.exists():
                try:report=json.loads(report_path.read_text(encoding='utf-8'))
                except Exception:report={}
            rows.append({'slug':slug,'path':str(p.relative_to(ROOT)),'predictions_path':str(pred.relative_to(ROOT)) if pred.exists() else None,'region':report.get('subsystem') or _region_from_slug(slug),'comparison_group':'auto_2023_2026' if slug.startswith('auto_e') and slug.endswith('_2023_2026') else 'other','experiment':str(r.experiment),'algorithm':str(r.get('algorithm','ridge')),'MAE':float(r.MAE),'RMSE':float(r.RMSE),'WAPE':float(r.WAPE),'WAPE_pct':float(r.WAPE)*100,'coverage':None if pd.isna(r.p10_p90_coverage) else float(r.p10_p90_coverage),'coverage_pct':None if pd.isna(r.p10_p90_coverage) else float(r.p10_p90_coverage)*100,'n_rows':int(r.n_rows),'modified':p.stat().st_mtime,'history_start':report.get('history_start_requested'),'history_end':report.get('history_end_requested'),'load_period_effective':report.get('load_period_effective'),'climate_period_effective':report.get('climate_period_effective'),'params':report.get('xgboost_params') or ({'alpha':report.get('ridge_alpha')} if report.get('ridge_alpha') is not None else {}),'test_hours':report.get('test_hours') or 720,'calibration_hours':report.get('calibration_hours')})
        except Exception as e:rows.append({'slug':p.stem,'path':str(p.relative_to(ROOT)),'error':str(e)})
    good=[r for r in rows if 'WAPE' in r]
    if good:
        best=min(r['WAPE'] for r in good)
        for r in good:r['best']=abs(r['WAPE']-best)<1e-12
    return rows


def validation_detail(region:str|None=None)->dict:
    runs=validation_runs();good=[r for r in runs if 'WAPE' in r]
    if not good:return {'exists':False,'runs':runs}
    comparisons=_contextual_comparisons(good)
    default=comparisons[0]['forecast'] if comparisons else good[0]
    selected=next((item['forecast'] for item in comparisons if item['region']==region),default)
    metrics=read_table(ROOT/selected['path'])
    model=metrics[metrics.experiment.eq(selected['experiment'])]
    labels=[f'H{i:02d}' for i in range(1,25)];h=model[(model.segment=='ALL')&model.horizon.isin(labels)].set_index('horizon').reindex(labels)
    horizon={'labels':labels,'wape':[None if pd.isna(v) else float(v)*100 for v in h.WAPE.tolist()],'mae':[None if pd.isna(v) else float(v) for v in h.MAE.tolist()]}
    actual_chart=None
    if selected.get('predictions_path'):
        p=ROOT/selected['predictions_path']
        if p.exists():
            preds=read_table(p);preds=preds[preds.experiment.eq(selected['experiment'])].sort_values(['issue_time_utc','horizon_hour'])
            # To avoid plotting overlapping origins, use the last complete origin.
            if len(preds):
                last=preds.issue_time_utc.max();g=preds[preds.issue_time_utc.eq(last)].sort_values('horizon_hour')
                dessem=[]
                if DESSEM_PATH.exists():
                    schedule=read_table(DESSEM_PATH)
                    schedule['interval_start_utc']=pd.to_datetime(schedule.interval_start_utc,utc=True,errors='coerce')
                    lookup=schedule[schedule.subsystem_id.astype(str).eq(selected['region'])].set_index('interval_start_utc').programmed_load_mw
                    dessem=[None if pd.isna(value) else float(value) for value in pd.to_datetime(g.interval_start_utc,utc=True).map(lookup)]
                actual_chart={'labels':[pd.Timestamp(x).strftime('%d/%m %Hh') for x in g.interval_start_utc],'actual':[float(x) for x in g.actual_mw],'predicted':[float(x) for x in g.p50_mw],'dessem':dessem,'p10':[float(x) for x in g.p10_mw],'p90':[float(x) for x in g.p90_mw],'issue_time':str(last)}
    return {'exists':True,'comparisons':comparisons,'selected':selected,'horizon':horizon,'actual_chart':actual_chart}
