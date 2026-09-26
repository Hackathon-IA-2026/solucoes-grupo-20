from __future__ import annotations
from pathlib import Path
import pandas as pd
from django.conf import settings
from motor_sin.common.io import read_table

ROOT=Path(settings.PREDICTA_PROJECT_ROOT)


def best_metrics_path():
    candidates=[ROOT/'outputs/metrics/e3_real_pilot_metrics.csv',ROOT/'outputs/metrics/real_pilot_metrics.csv']
    return next((p for p in candidates if p.exists()),None)


def metrics_context():
    p=best_metrics_path()
    if not p: return {'exists':False}
    df=read_table(p)
    overall=df[(df['segment']=='ALL')&(df['horizon']=='ALL')].copy()
    overall=overall.sort_values('WAPE')
    rows=[]
    for idx,(_,r) in enumerate(overall.iterrows()):
        rows.append({'experiment':r['experiment'],'MAE':float(r['MAE']),'RMSE':float(r['RMSE']),'WAPE':float(r['WAPE']),'WAPE_pct':float(r['WAPE'])*100,'coverage':None if pd.isna(r.get('p10_p90_coverage')) else float(r['p10_p90_coverage']),'coverage_pct':None if pd.isna(r.get('p10_p90_coverage')) else float(r['p10_p90_coverage'])*100,'has_coverage':not pd.isna(r.get('p10_p90_coverage')),'n_rows':int(r['n_rows']),'best_wape':idx==0})
    exps=[e for e in ['E0_BLEND','E1','E2','E3'] if e in set(df['experiment'])]
    horizon_labels=[f'H{i:02d}' for i in range(1,25)]
    series=[]
    for e in exps:
        s=df[(df.experiment==e)&(df.segment=='ALL')&df.horizon.isin(horizon_labels)].set_index('horizon').reindex(horizon_labels)
        series.append({'name':e,'values':[None if pd.isna(v) else float(v)*100 for v in s['WAPE'].tolist()]})
    return {'exists':True,'path':str(p.relative_to(ROOT)),'rows':rows,'horizon_labels':horizon_labels,'horizon_series':series,'raw':df}
