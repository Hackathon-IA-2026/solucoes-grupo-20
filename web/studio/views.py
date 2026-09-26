from __future__ import annotations
import json
from datetime import date
from pathlib import Path
import pandas as pd
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from web.studio.models import PipelineRun
from .services.artifacts import all_artifact_statuses, preview_artifact
from .services.metrics import metrics_context
from .services.model_registry import scan_model_families, active_model, set_active_model
from .services.product import (
    DISPLAY_TIMEZONE,
    available_regions,
    effective_date_for,
    operational_status,
    profiles_for_location,
    replay_window,
    replay_windows,
    simulate_customer,
    simulation_available,
)
from .services.distribution import geojson_payload, distributor_catalog, distributor_info, tariff_profiles_for_cnpj
from .services.history import ons_history_context
from .services.features import preview_features, FEATURE_GROUPS
from .services.validation import validation_detail
from .services.runner import launch_stage
from .services.stage_registry import STAGE_MAP, stage_sections
from .services.territory import default_event_date, territory_summary
from motor_sin.climate.local_store import store_inventory

ROOT=Path(settings.PREDICTA_PROJECT_ROOT)


def _recent_runs(limit=8):return PipelineRun.objects.all()[:limit]


def _read_json_file(path:Path):
    if not path.exists():return None
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return None


def automation_page(request):
    report=_read_json_file(ROOT/'outputs/reports/full_automation.json')
    climate_store=store_inventory(ROOT/'data/climate_store')
    climate_store_coverage=_read_json_file(ROOT/'outputs/reports/climate_store_coverage.json')
    operational=_read_json_file(ROOT/'outputs/reports/operational_24h.json')
    weather=_read_json_file(ROOT/'outputs/reports/operational_weather_24h.json')
    registry=_read_json_file(ROOT/'models/demand/operational_registry.json')
    statuses={
        'load':(ROOT/'data/processed/demand/load_hourly.parquet').exists(),
        'tariffs':(ROOT/'data/processed/tariff/base_tariffs.parquet').exists(),
        'climate_e3':(ROOT/'data/processed/climate/zone_climate_hourly_e3.parquet').exists(),
        'registry':(ROOT/'models/demand/operational_registry.json').exists(),
        'operational_weather':(ROOT/'data/processed/climate/operational_zone_climate_24h.parquet').exists(),
        'system_signal':(ROOT/'outputs/contracts/system_signal_v1.parquet').exists(),
        'climate_store':bool(climate_store.get('total_files')),
    }
    op_rows=[{'region':z,**operational_status(z)} for z in ['N','NE','SE/CO','S']]
    registry_rows=[]
    if registry:
        for z in ['N','NE','SE/CO','S']:
            r=(registry.get('regions') or {}).get(z) or {}
            registry_rows.append({'region':z,**r})
    recent=PipelineRun.objects.filter(stage_id__in=['full_automation','refresh_operational','seed_climate_store','update_climate_store','verify_climate_store'])[:12]
    return render(request,'studio/automation.html',{'page':'automation','full_stage':STAGE_MAP['full_automation'],'refresh_stage':STAGE_MAP['refresh_operational'],'automation_report':report,'operational_report':operational,'weather_report':weather,'registry':registry,'registry_rows':registry_rows,'automation_statuses':statuses,'op_rows':op_rows,'recent_runs':recent,'climate_store':climate_store,'climate_store_coverage':climate_store_coverage})


def dashboard(request):
    artifacts=all_artifact_statuses();metrics=metrics_context();models=scan_model_families();active=active_model();complete=sum(1 for a in artifacts if a['exists']);by_key={a['key']:a for a in artifacts}
    if not by_key.get('load',{}).get('exists'):next_action={'title':'Adicionar histórico ONS','text':'Escolha os anos em Dados e consolide a série antes de modelar.','url':'studio:data'}
    elif not by_key.get('climate_e3',{}).get('exists'):next_action={'title':'Completar features climáticas','text':'Construa E2/E3 na página Features para habilitar o experimento climático.','url':'studio:features'}
    elif not metrics.get('exists'):next_action={'title':'Validar uma configuração','text':'Compare Ridge/XGBoost e E1/E2/E3 no mesmo holdout.','url':'studio:modeling'}
    elif not models:next_action={'title':'Congelar modelo','text':'Depois de validar, treine/congele a configuração escolhida.','url':'studio:models'}
    elif not active:next_action={'title':'Selecionar modelo ativo','text':'Promova uma família congelada para inferência.','url':'studio:models'}
    elif not by_key.get('system_signal',{}).get('exists'):next_action={'title':'Gerar sinal operacional','text':'Execute inferência e publique system_signal_v1.','url':'studio:pipeline'}
    elif not by_key.get('base_tariffs',{}).get('exists'):next_action={'title':'Carregar mapa e tarifas','text':'Relacione áreas reais de concessão e tarifas ANEEL por CNPJ.','url':'studio:data'}
    else:next_action={'title':'Simular cliente','text':'Clique em uma área real de concessão e compare tarifa atual × Predicta.','url':'studio:product'}
    return render(request,'studio/dashboard.html',{'page':'dashboard','artifacts':artifacts,'artifact_complete':complete,'artifact_total':len(artifacts),'metrics':metrics,'models':models,'active_model':active,'recent_runs':_recent_runs(),'regions':[{'id':k,'available':v} for k,v in available_regions().items()],'next_action':next_action})


def pipeline(request):return render(request,'studio/pipeline.html',{'page':'pipeline','sections':stage_sections(),'recent_runs':_recent_runs(12)})

@require_POST
def run_stage(request,stage_id):
    stage=STAGE_MAP.get(stage_id)
    if not stage:raise Http404('Etapa inexistente')
    params={}
    for p in stage.params:params[p.name]='1' if p.kind=='checkbox' and request.POST.get(p.name) else ('0' if p.kind=='checkbox' else request.POST.get(p.name,p.default))
    try:
        run=launch_stage(stage_id,params);messages.success(request,f'Etapa “{stage.title}” iniciada. O log será atualizado em segundo plano.');return redirect('studio:run_detail',run_id=run.id)
    except Exception as e:messages.error(request,f'Não foi possível iniciar a etapa: {e}');return redirect(request.META.get('HTTP_REFERER') or 'studio:pipeline')


def run_detail(request,run_id):
    run=get_object_or_404(PipelineRun,pk=run_id);log=''
    if run.log_path and Path(run.log_path).exists():
        try:log=Path(run.log_path).read_text(encoding='utf-8',errors='replace')[-50000:]
        except Exception as e:log=f'Erro ao ler log: {e}'
    return render(request,'studio/run_detail.html',{'page':'pipeline','run':run,'stage':STAGE_MAP.get(run.stage_id),'log':log})


def run_status(request,run_id):
    run=get_object_or_404(PipelineRun,pk=run_id);log=''
    if run.log_path and Path(run.log_path).exists():log=Path(run.log_path).read_text(encoding='utf-8',errors='replace')[-30000:]
    return JsonResponse({'id':str(run.id),'status':run.status,'return_code':run.return_code,'finished_at':run.finished_at.isoformat() if run.finished_at else None,'error_message':run.error_message,'log':log})


def data_explorer(request):
    key=request.GET.get('dataset') or 'load';rows=request.GET.get('rows','30')
    try:preview=preview_artifact(key,int(rows))
    except (KeyError,ValueError):preview=preview_artifact('load',30);key='load'
    return render(request,'studio/data_explorer.html',{'page':'data','artifacts':all_artifact_statuses(),'selected_key':key,'preview':preview,'rows':rows,'history':ons_history_context(),'ons_stage':STAGE_MAP['sync_ons_history'],'tariff_stage':STAGE_MAP['prepare_tariff_geo']})


def features_page(request):
    exp=request.GET.get('experiment','E3').upper();sub=request.GET.get('subsystem','SE/CO');h=int(request.GET.get('horizon','24'))
    try:preview=preview_features(exp,sub,h,20)
    except Exception as e:preview={'exists':False,'reason':str(e)}
    return render(request,'studio/features.html',{'page':'features','feature_groups':FEATURE_GROUPS,'preview':preview,'experiment':exp,'subsystem':sub,'horizon':h,'e2_stages':[STAGE_MAP['download_e2'],STAGE_MAP['prepare_e2']],'e3_stages':[STAGE_MAP['download_e3'],STAGE_MAP['prepare_e3']]})


def territory_page(request):
    region=(request.POST.get('region') if request.method=='POST' else request.GET.get('region','SE/CO')) or 'SE/CO'
    selected_raw=(request.POST.get('event_date') if request.method=='POST' else request.GET.get('event_date','')).strip()
    selected=None
    if selected_raw:
        try:selected=date.fromisoformat(selected_raw)
        except ValueError:selected=None
    if selected is None:selected=default_event_date(region)
    territory=territory_summary(region,selected)
    return render(request,'studio/territory.html',{'page':'territory','territory':territory,'selected_region':region,'selected_event_date':selected.isoformat() if selected else '', 'regions':[{'id':k,'available':v} for k,v in available_regions().items()]})


def modeling_page(request):
    return render(request,'studio/modeling.html',{'page':'modeling','validate_stage':STAGE_MAP['validate_model'],'train_stage':STAGE_MAP['train_model'],'history':ons_history_context(),'recent_runs':_recent_runs(10)})


def validation_page(request):
    slug=request.GET.get('run');return render(request,'studio/validation.html',{'page':'validation','validation':validation_detail(slug),'pilot_metrics':metrics_context()})


def experiments(request):
    # Backward-compatible route: the old "Experimentos" page is now the validation workspace.
    return validation_page(request)


def models_page(request):
    # Validation metrics live in the Validation workspace. Do not attach a legacy
    # Ridge E3 WAPE to an XGBoost family just because the experiment name matches.
    models=scan_model_families()
    return render(request,'studio/models.html',{'page':'models','models':models,'active_model':active_model(),'train_stage':STAGE_MAP['train_model'],'metrics':metrics_context()})

@require_POST
def activate_model(request):
    model_dir=request.POST.get('model_dir','');family=request.POST.get('model_family_id','');match=next((m for m in scan_model_families() if m['model_dir']==model_dir and m['model_family_id']==family),None)
    if not match:messages.error(request,'Família de modelo não encontrada no repositório.')
    else:
        payload={k:match.get(k) for k in ['model_family_id','experiment','subsystem_id','model_dir','forecast_horizon_hours','deployment_status','algorithm','algorithm_key']};set_active_model(payload);messages.success(request,f"Modelo ativo alterado para {family} ({match.get('experiment')} / {match.get('algorithm')}).")
    return redirect('studio:models')


def product(request):
    result=None;hourly=[];error=None;catalog=distributor_catalog();options=[]
    if not catalog.empty:
        for _,r in catalog.sort_values(['uf','sigla']).iterrows():options.append({'cnpj':str(r.cnpj_digits),'sigla':str(r.sigla),'name':str(r.razao_social),'uf':str(r.uf),'region':str(r.subsystem_id)})

    selected_cnpj=request.POST.get('cnpj','') if request.method=='POST' else request.GET.get('cnpj','')
    selected_region=request.POST.get('region','') if request.method=='POST' else request.GET.get('region','SE/CO')
    mode=request.POST.get('simulation_mode','replay') if request.method=='POST' else request.GET.get('simulation_mode','replay')
    mode=mode if mode in {'replay','operational'} else 'replay'
    windows=replay_windows(selected_region or None)
    selected_replay=request.POST.get('replay_issue','') if request.method=='POST' else request.GET.get('replay_issue','')
    if mode=='replay' and not selected_replay and windows:selected_replay=windows[-1]['key']
    op_status=operational_status(selected_region or 'SE/CO')

    selected_distributor=request.POST.get('distributor','') if request.method=='POST' else ''
    selected_profile=request.POST.get('profile','') if request.method=='POST' else ''
    monthly_kwh=request.POST.get('monthly_kwh','300') if request.method=='POST' else '300'
    customer_type=request.POST.get('customer_type','residential') if request.method=='POST' else 'residential'
    flexible_pct=request.POST.get('flexible_pct','20') if request.method=='POST' else '20'
    info=distributor_info(selected_cnpj) if selected_cnpj else None
    if info and not selected_region:selected_region=str(info.get('subsystem_id') or '')

    effective=effective_date_for(selected_region,mode,selected_replay) if selected_region else None
    profiles=profiles_for_location(selected_cnpj,selected_region,effective) if selected_cnpj and selected_region else []
    selected_window=replay_window(selected_region,selected_replay) if mode=='replay' and selected_region else None

    if request.method=='POST':
        try:
            if mode=='operational' and not op_status.get('available'):raise ValueError(op_status.get('reason') or 'Modo operacional indisponível.')
            if not selected_cnpj:raise ValueError('Selecione uma área de concessão no mapa ou na busca.')
            if not selected_region:raise ValueError('Não foi possível associar a área ao subsistema do MVP.')
            if not selected_distributor:raise ValueError('Selecione um perfil tarifário; ele define o agente tarifário vigente.')
            if not selected_profile:raise ValueError('Selecione um perfil tarifário.')
            flex=float(flexible_pct)/100.0
            if not 0<=flex<=0.80:raise ValueError('Carga flexível deve ficar entre 0% e 80%.')
            result,frame=simulate_customer(region=selected_region,cnpj=selected_cnpj,distributor=selected_distributor,profile=selected_profile,monthly_kwh=float(monthly_kwh),customer_type=customer_type,mode=mode,replay_key=selected_replay,flexible_fraction=flex)
            for _,r in frame.iterrows():
                local=pd.Timestamp(r['interval_start_utc']).tz_convert(DISPLAY_TIMEZONE)
                flags=r.get('quality_flags','[]')
                context='HOUR_MONTH';reference_n=None
                try:
                    parsed=json.loads(flags) if isinstance(flags,str) else list(flags or [])
                    context=next((str(x).replace('DEMAND_PERCENTILE_CONTEXT_','') for x in parsed if str(x).startswith('DEMAND_PERCENTILE_CONTEXT_')),context)
                    n=next((str(x).replace('DEMAND_PERCENTILE_REFERENCE_N_','') for x in parsed if str(x).startswith('DEMAND_PERCENTILE_REFERENCE_N_')),None)
                    reference_n=int(n) if n is not None else None
                except Exception:pass
                hourly.append({'time':local.strftime('%d/%m %Hh'),'local_iso':local.isoformat(),'base':float(r['base_total_rs_kwh']),'dynamic':float(r['dynamic_tariff_rs_kwh']),'consumption':float(r['consumption_kwh']),'optimized_consumption':float(r['optimized_consumption_kwh']),'multiplier':float(r['final_multiplier']),'demand_pressure':float(r['demand_pressure']),'demand_mw':float(r['demand_p50_mw']),'demand_context':context,'demand_reference_n':reference_n,'delta_pct':100*(float(r['dynamic_tariff_rs_kwh'])/float(r['base_total_rs_kwh'])-1) if float(r['base_total_rs_kwh']) else 0})
        except Exception as e:error=str(e)

    return render(request,'studio/product.html',{
        'page':'product','regions':[{'id':k,'available':v} for k,v in available_regions().items()],'distributor_options':options,'profiles':profiles,'result':result,'hourly':hourly,'error':error,
        'selected_region':selected_region,'selected_cnpj':selected_cnpj,'selected_distributor':selected_distributor,'selected_profile':selected_profile,'selected_info':info,'monthly_kwh':monthly_kwh,'customer_type':customer_type,
        'active_model':active_model(),'tariffs_ready':(ROOT/'data/processed/tariff/base_tariffs.parquet').exists(),'simulation_mode':mode,'replay_windows':windows,'selected_replay':selected_replay,'selected_window':selected_window,
        'operational_status':op_status,'display_timezone':DISPLAY_TIMEZONE,'effective_date':effective.isoformat() if effective else '', 'flexible_pct':flexible_pct,
    })


def api_profiles(request):
    cnpj=request.GET.get('cnpj','');region=request.GET.get('region','');mode=request.GET.get('mode','replay');replay_key=request.GET.get('replay_issue') or None
    effective_raw=request.GET.get('effective_date','');effective=None
    if effective_raw:
        try:effective=date.fromisoformat(effective_raw)
        except ValueError:effective=None
    if effective is None and region:effective=effective_date_for(region,mode,replay_key)
    return JsonResponse({'profiles':tariff_profiles_for_cnpj(cnpj,region or None,effective_date=effective),'distributor':distributor_info(cnpj),'signal_available':simulation_available(region,mode,replay_key) if region else False,'effective_date':effective.isoformat() if effective else None,'display_timezone':DISPLAY_TIMEZONE})


def api_distribution_areas(request):return JsonResponse(geojson_payload())

def api_distributor_info(request):
    cnpj=request.GET.get('cnpj','');return JsonResponse({'distributor':distributor_info(cnpj),'profiles':tariff_profiles_for_cnpj(cnpj,request.GET.get('region') or None)})
