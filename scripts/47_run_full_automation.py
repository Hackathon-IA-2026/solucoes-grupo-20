#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys,time
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import read_table,write_table,write_json

REGIONS={'N':'n','NE':'ne','SE/CO':'seco','S':'s'}
ALGORITHMS=('ridge','xgboost')

class ClimateRateLimitWaiting(RuntimeError):
    pass

def run(cmd:list[str],label:str,steps:list[dict]):
    print(f'\n=== {label} ===\n$ '+' '.join(cmd),flush=True);t=time.time();proc=subprocess.run(cmd,text=True)
    item={'label':label,'command':cmd,'return_code':proc.returncode,'seconds':round(time.time()-t,2)};steps.append(item)
    if proc.returncode!=0:raise RuntimeError(f'{label} failed with code {proc.returncode}')


def run_resumable_rate_limited(cmd:list[str],label:str,steps:list[dict],*,wait_seconds:float,max_cycles:int):
    # Exit code 75 means the immutable climate checkpoint is safe but the provider
    # has no rate-limit capacity right now. Resume the exact same command later.
    cycle=0
    while True:
        print(f'\n=== {label} ===\n$ '+' '.join(cmd),flush=True);t=time.time();proc=subprocess.run(cmd,text=True)
        item={'label':label,'command':cmd,'return_code':proc.returncode,'seconds':round(time.time()-t,2),'defer_cycle':cycle};steps.append(item)
        if proc.returncode==0:return
        if proc.returncode!=75:raise RuntimeError(f'{label} failed with code {proc.returncode}')
        cycle+=1
        if cycle>int(max_cycles):
            raise ClimateRateLimitWaiting(f'{label} is waiting for Open-Meteo rate-limit capacity after {max_cycles} deferred cycles; rerun later and cache will resume')
        wait=max(float(wait_seconds),60.0)
        print(f'PREDICTA_RATE_LIMIT_WAIT: checkpoint preserved; sleeping {wait:.0f}s before automatic resume ({cycle}/{max_cycles})',flush=True)
        time.sleep(wait)

def py(script,*args):return [sys.executable,f'scripts/{script}',*[str(x) for x in args]]

def combine(paths:list[tuple[str,Path]],output:Path,add_region:bool=False):
    frames=[]
    for region,p in paths:
        df=read_table(p)
        if add_region and 'subsystem_id' not in df.columns:df['subsystem_id']=region
        frames.append(df)
    out=pd.concat(frames,ignore_index=True)
    keys=[c for c in ['subsystem_id','target_year','interval_start_utc','cell_id','month','metric','point_id','date_local'] if c in out.columns]
    if keys:out=out.sort_values(keys).reset_index(drop=True)
    write_table(out,output);return len(out)

def overall_wape(path:Path,experiment='E3')->float:
    df=pd.read_csv(path);g=df[(df['experiment'].astype(str).eq(experiment))&(df['segment'].astype(str).eq('ALL'))&(df['horizon'].astype(str).eq('ALL'))]
    if g.empty:raise ValueError(f'overall WAPE not found in {path}')
    col='wape' if 'wape' in g.columns else 'WAPE';return float(g.iloc[0][col])

def main():
    p=argparse.ArgumentParser(description='One-click Predicta automation: ONS multi-year, 0.1-degree climate grid, rolling baselines, Ridge+XGBoost all regions and optional operational H01-H24.')
    p.add_argument('--start-year',type=int,default=2023);p.add_argument('--end-year',type=int,default=2026)
    p.add_argument('--history-start');p.add_argument('--history-end');p.add_argument('--test-hours',type=int,default=720);p.add_argument('--calibration-hours',type=int,default=720)
    p.add_argument('--alpha',type=float,default=1.0);p.add_argument('--n-estimators',type=int,default=350);p.add_argument('--max-depth',type=int,default=6);p.add_argument('--learning-rate',type=float,default=0.05);p.add_argument('--subsample',type=float,default=0.9);p.add_argument('--colsample-bytree',type=float,default=0.9)
    p.add_argument('--climate-grid-mode',choices=['adaptive','full'],default='adaptive');p.add_argument('--climate-stride-cells',type=int,default=20)
    p.add_argument('--climate-batch-size',type=int,default=6);p.add_argument('--climate-daily-batch-size',type=int,default=24);p.add_argument('--climate-archive-url',default='');p.add_argument('--climate-history-mode',choices=['local-first','local-only'],default='local-first');p.add_argument('--climate-historical-backend',choices=['auto','arco','openmeteo','openmeteo-fallback-arco'],default='auto',help='Historical climate backend. auto/arco use ARCO for cache gaps; Open-Meteo remains for operational forecast.');p.add_argument('--climate-store-root',default='data/climate_store');p.add_argument('--climate-request-delay',type=float,default=2.0);p.add_argument('--climate-max-retries',type=int,default=10);p.add_argument('--climate-backoff',type=float,default=10.0);p.add_argument('--climate-cooldown-after-429',type=int,default=3);p.add_argument('--climate-cooldown-seconds',type=float,default=90.0);p.add_argument('--climate-timeout',type=int,default=120);p.add_argument('--climate-defer-wait-seconds',type=float,default=900.0);p.add_argument('--climate-defer-cycles',type=int,default=8)
    p.add_argument('--skip-tests',action='store_true');p.add_argument('--skip-operational',action='store_true');p.add_argument('--operational-issue',default='auto');p.add_argument('--max-load-staleness-hours',type=float,default=3.0)
    p.add_argument('--report',default='outputs/reports/full_automation.json');a=p.parse_args()
    if a.end_year<a.start_year:raise SystemExit('end-year must be >= start-year')
    Path(a.report).parent.mkdir(parents=True,exist_ok=True);steps=[];started=pd.Timestamp.now(tz='UTC')
    report={'status':'RUNNING','started_at_utc':started.isoformat(),'config':vars(a),'regions':{},'steps':steps,'climate_policy':{'target_years':'derived automatically from ONS/training range','rolling_baseline':'Y-10..Y-1 for every target year','grid_resolution_deg':0.1,'grid_mode':a.climate_grid_mode,'rate_limit':{'batch_size_hourly':a.climate_batch_size,'batch_size_daily':a.climate_daily_batch_size,'request_delay_seconds':a.climate_request_delay,'max_retries':a.climate_max_retries,'base_backoff_seconds':a.climate_backoff,'cooldown_after_429':a.climate_cooldown_after_429,'cooldown_seconds':a.climate_cooldown_seconds},'climate_store':a.climate_store_root,'history_mode':a.climate_history_mode,'historical_backend':a.climate_historical_backend,'historical_source_policy':'AUTO/ARCO: ERA5-Land ARCO 0.1° for core variables + ERA5 ARCO 0.25° for gust; Open-Meteo reserved for operational forecast','annual_cache':'persistent local store; selected backend only fills missing ranges','resume':'checkpoint per batch + point/date-range immutable cache'}}
    def save():write_json(report,a.report)
    save()
    try:
        if not a.skip_tests:
            run([sys.executable,'-m','pytest','-q'],'Gate 0 · testes científicos',steps);save()
            run([sys.executable,'manage.py','check'],'Gate 0 · Django system check',steps);save()
            run([sys.executable,'manage.py','test','web.studio'],'Gate 0 · testes da interface web',steps);save()
        run(py('00_bootstrap_phase0.py','--require-parquet'),'Gate 0 · contratos v1',steps);save()
        run(py('01_build_grid.py','--brazil-only','--output','data/processed/grid/brazil_grid_01deg.parquet'),'Grade espacial Brasil 0,1°',steps);save()
        run(py('52_build_climate_grid_points.py','--mode',a.climate_grid_mode,'--stride-cells',a.climate_stride_cells),'Grade climática ativa 0,1° + células de usinas',steps);save()
        run(py('55_manage_climate_store.py','seed-existing','--store-root',a.climate_store_root,'--annual-archive-root','data/raw/climate/annual_archive'),'Climate Store · reaproveitar caches históricos já baixados',steps);save()
        run(py('45_sync_ons_history.py','--start-year',a.start_year,'--end-year',a.end_year,'--source-timezone','America/Sao_Paulo','--refresh-end-year'),'Histórico ONS multi-ano',steps);save()
        run(py('44_prepare_tariff_geography.py'),'Tarifas ANEEL + áreas de concessão',steps);save()

        e2_paths=[];e3_paths=[];baseline_paths=[];daily_paths=[]
        for region,tag in REGIONS.items():
            regdir=Path(f'data/processed/climate/regions/{tag}');regdir.mkdir(parents=True,exist_ok=True)
            points=f'data/processed/grid/climate_points_{tag}_01deg.csv';legacy_e2=f'data/raw/climate/e2_openmeteo_grid/{tag}/{a.start_year}_{a.end_year}';legacy_e3=f'data/raw/climate/e3_openmeteo_grid/{tag}/{a.start_year}_{a.end_year}';raw_e2=f'{a.climate_store_root}/{tag}/hourly';manifest_e2=f'outputs/reports/climate/{tag}_e2_download_{a.start_year}_{a.end_year}.json';zone_e2=regdir/'zone_climate_hourly.parquet'
            raw_e3=f'{a.climate_store_root}/{tag}/daily';manifest_e3=f'outputs/reports/climate/{tag}_e3_download_{a.start_year}_{a.end_year}.json'
            download_report=f'outputs/reports/climate/{tag}_multiyear_download_{a.start_year}_{a.end_year}.json';checkpoint=f'outputs/reports/climate/{tag}_annual_download_checkpoint.json'
            # Enforce the canonical-grid invariant before historical materialization.
            # Duplicated cell_id definitions create duplicate cell/hour observations
            # downstream even when every provider request succeeds. Quarantine only
            # caches belonging to discarded duplicate point definitions.
            run(py('63_repair_duplicate_climate_cells.py','--points',points,'--grid','data/processed/grid/brazil_grid_01deg.parquet','--hourly-dir',raw_e2,'--daily-dir',raw_e3,'--quarantine-root',f'data/climate_store_quarantine/{tag}','--report',f'outputs/reports/climate/{tag}_cell_collision_repair.json'),f'{region} · validar unicidade da grade climática',steps);save()
            climate_cmd=py('53_download_multiyear_grid_climate.py','--load','data/processed/demand/load_hourly.parquet','--points',points,'--subsystem',region,'--start-year',a.start_year,'--end-year',a.end_year,'--e2-raw-dir',raw_e2,'--e2-manifest',manifest_e2,'--e3-raw-dir',raw_e3,'--e3-manifest',manifest_e3,'--legacy-e2-raw-dir',legacy_e2,'--legacy-e3-raw-dir',legacy_e3,'--history-mode',a.climate_history_mode,'--history-backend',a.climate_historical_backend,'--batch-size',a.climate_batch_size,'--daily-batch-size',a.climate_daily_batch_size,'--request-delay',a.climate_request_delay,'--max-retries',a.climate_max_retries,'--backoff',a.climate_backoff,'--cooldown-after-429',a.climate_cooldown_after_429,'--cooldown-seconds',a.climate_cooldown_seconds,'--timeout',a.climate_timeout,'--checkpoint',checkpoint,'--report',download_report)
            if a.climate_archive_url: climate_cmd += ['--archive-url',a.climate_archive_url]
            if a.climate_history_mode=='local-only':
                run(climate_cmd,f'{region} · clima multi-ano 0,1° · LOCAL ONLY',steps);save()
            elif a.climate_historical_backend=='openmeteo':
                # Legacy explicit mode: keep the old defer/resume behaviour.
                run_resumable_rate_limited(climate_cmd,f'{region} · clima multi-ano 0,1° · OPEN-METEO LEGACY',steps,wait_seconds=a.climate_defer_wait_seconds,max_cycles=a.climate_defer_cycles);save()
            else:
                # AUTO/ARCO is ARCO-first. openmeteo-fallback-arco handles the
                # 429 -> ARCO switch inside script 53 and returns 0 when complete.
                label_backend='ARCO AUTO' if a.climate_historical_backend in {'auto','arco'} else 'OPEN-METEO → ARCO FALLBACK'
                run(climate_cmd,f'{region} · clima multi-ano 0,1° · {label_backend}',steps);save()
            run(py('32_prepare_e2_zone_climate.py','--raw-dir',raw_e2,'--manifest',manifest_e2,'--replace-run','--run-id',f'e2-grid-{tag}-{a.start_year}-{a.end_year}','--subsystem',region,'--points',points,'--output-root',f'data/processed/climate/regions/{tag}/climate_hourly','--zone-output',zone_e2,'--report',f'outputs/reports/climate/{tag}_e2_prepare_{a.start_year}_{a.end_year}.json'),f'{region} · features E2 multi-ano',steps);save()
            baseline=regdir/'e3_temperature_baseline_monthly.parquet';daily=regdir/'e3_daily_context.parquet';hourly=regdir/'e3_zone_context_hourly.parquet';zone_e3=regdir/'zone_climate_hourly_e3.parquet'
            run(py('54_prepare_multiyear_e3.py','--manifest',manifest_e3,'--points',points,'--subsystem',region,'--e2-climate',zone_e2,'--start-year',a.start_year,'--end-year',a.end_year,'--baseline-output',baseline,'--daily-output',daily,'--hourly-output',hourly,'--zone-output',zone_e3,'--report',f'outputs/reports/climate/{tag}_e3_prepare_{a.start_year}_{a.end_year}.json'),f'{region} · rolling baselines + eventos E3 multi-ano',steps);save()
            e2_paths.append((region,zone_e2));e3_paths.append((region,zone_e3));baseline_paths.append((region,baseline));daily_paths.append((region,daily));report['regions'][region]={'points':points,'e2':str(zone_e2),'e3':str(zone_e3),'baseline':str(baseline),'download_report':download_report,'download_checkpoint':checkpoint};save()

        Path('data/processed/climate').mkdir(parents=True,exist_ok=True)
        report['combined_climate_rows']={'e2':combine(e2_paths,Path('data/processed/climate/zone_climate_hourly.parquet')),'e3':combine(e3_paths,Path('data/processed/climate/zone_climate_hourly_e3.parquet')),'baseline':combine(baseline_paths,Path('data/processed/climate/e3_temperature_baseline_monthly_all_regions.parquet'),add_region=True),'daily':combine(daily_paths,Path('data/processed/climate/e3_daily_context_all_regions.parquet'),add_region=True)};save()

        candidates={};registry={'version':'1.1','experiment':'E3','selection_metric':'WAPE','generated_at_utc':pd.Timestamp.now(tz='UTC').isoformat(),'training_years':[a.start_year,a.end_year],'climate_grid_resolution_deg':0.1,'regions':{}}
        for region,tag in REGIONS.items():
            candidates[region]=[]
            for algo in ALGORITHMS:
                prefix=Path(f'outputs/metrics/model_validation/auto_e3_{algo}_{tag}_{a.start_year}_{a.end_year}');prefix.parent.mkdir(parents=True,exist_ok=True)
                cmd=py('46_validate_model.py','--experiment','E3','--algorithm',algo,'--subsystem',region,'--test-hours',a.test_hours,'--calibration-hours',a.calibration_hours,'--alpha',a.alpha,'--output-prefix',prefix)
                if a.history_start:cmd+=['--history-start',a.history_start]
                if a.history_end:cmd+=['--history-end',a.history_end]
                if algo=='xgboost':cmd+=['--n-estimators',a.n_estimators,'--max-depth',a.max_depth,'--learning-rate',a.learning_rate,'--subsample',a.subsample,'--colsample-bytree',a.colsample_bytree]
                run(cmd,f'{region} · validar E3 {algo}',steps);metrics=prefix.with_name(prefix.name+'_metrics.csv');wape=overall_wape(metrics)
                model_dir=f'models/demand/e3_{algo}_{tag}_auto';family=f'E3_{algo.upper()}_{tag.upper()}_AUTO';train_report=f'outputs/reports/model_training/{tag}_{algo}.json'
                cmd=py('43_train_model_family.py','--experiment','E3','--algorithm',algo,'--subsystem',region,'--calibration-hours',a.calibration_hours,'--alpha',a.alpha,'--model-dir',model_dir,'--model-family-id',family,'--report',train_report)
                if a.history_start:cmd+=['--train-start',a.history_start]
                if a.history_end:cmd+=['--train-end',a.history_end]
                if algo=='xgboost':cmd+=['--n-estimators',a.n_estimators,'--max-depth',a.max_depth,'--learning-rate',a.learning_rate,'--subsample',a.subsample,'--colsample-bytree',a.colsample_bytree]
                run(cmd,f'{region} · congelar E3 {algo}',steps);candidates[region].append({'algorithm':algo,'wape':wape,'model_dir':model_dir,'model_family_id':family,'metrics_path':str(metrics),'training_report':train_report})
            winner=min(candidates[region],key=lambda x:x['wape']);registry['regions'][region]={**winner,'candidates':candidates[region]};report['regions'][region]['models']=candidates[region];report['regions'][region]['selected']=winner;save()
        Path('models/demand').mkdir(parents=True,exist_ok=True);write_json(registry,'models/demand/operational_registry.json');report['operational_registry']='models/demand/operational_registry.json';save()

        operational_ready=False
        if not a.skip_operational:
            try:
                if a.operational_issue=='auto':
                    current_load=read_table('data/processed/demand/load_hourly.parquet');current_load['interval_start_utc']=pd.to_datetime(current_load['interval_start_utc'],utc=True,errors='raise');current_load['subsystem_id']=current_load['subsystem_id'].astype(str).str.upper().replace({'SE':'SE/CO','SECO':'SE/CO'});common=min(current_load[current_load.subsystem_id.eq(z)].interval_start_utc.max() for z in REGIONS);operational_year=int(common.tz_convert('America/Sao_Paulo').year)
                else:
                    issue=pd.Timestamp(a.operational_issue);issue=issue.tz_localize('UTC') if issue.tzinfo is None else issue.tz_convert('UTC');operational_year=int(issue.tz_convert('America/Sao_Paulo').year)
                run(py('51_prepare_operational_baselines.py','--target-year',operational_year,'--store-root',a.climate_store_root,'--history-mode','local-only','--batch-size',a.climate_batch_size,'--request-delay',a.climate_request_delay,'--max-retries',a.climate_max_retries,'--backoff',a.climate_backoff,'--cooldown-after-429',a.climate_cooldown_after_429,'--cooldown-seconds',a.climate_cooldown_seconds),'Operacional · baseline climático local do ano corrente',steps);save()
                run(py('48_build_operational_weather.py','--issue-time',a.operational_issue),'Operacional · previsão meteorológica H01–H24 em células 0,1°',steps);save()
                run(py('49_run_operational_24h.py','--issue-time',a.operational_issue,'--max-staleness-hours',a.max_load_staleness_hours),'Operacional · demanda + system_signal_v1',steps);save();report['operational_report']='outputs/reports/operational_24h.json';report['operational_status']='READY';operational_ready=True
            except Exception as op_exc:
                report['operational_status']='BLOCKED';report['operational_error']=str(op_exc);print(f'\nOPERATIONAL_BLOCKED: {op_exc}\n',flush=True);save()
        else:report['operational_status']='SKIPPED'
        report['status']='SUCCESS' if operational_ready or a.skip_operational else 'SUCCESS_WITH_OPERATIONAL_BLOCKED';report['finished_at_utc']=pd.Timestamp.now(tz='UTC').isoformat();save();print('\nAUTOMATION_SUCCESS\n'+json.dumps(report,ensure_ascii=False,indent=2,default=str))
    except ClimateRateLimitWaiting as exc:
        report['status']='WAITING_RATE_LIMIT';report['error']=str(exc);report['finished_at_utc']=pd.Timestamp.now(tz='UTC').isoformat();save();print('\nAUTOMATION_WAITING_RATE_LIMIT: '+str(exc),flush=True);raise SystemExit(75)
    except Exception as exc:
        report['status']='FAILED';report['error']=str(exc);report['finished_at_utc']=pd.Timestamp.now(tz='UTC').isoformat();save();raise
if __name__=='__main__':main()
