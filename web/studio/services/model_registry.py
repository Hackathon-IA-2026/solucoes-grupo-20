from __future__ import annotations
from pathlib import Path
import json
from django.conf import settings
from web.studio.models import ProjectSetting

ROOT=Path(settings.PREDICTA_PROJECT_ROOT)


def scan_model_families():
    rows=[]
    base=ROOT/'models'/'demand'
    if not base.exists(): return rows
    for manifest in base.rglob('manifest.json'):
        try:
            data=json.loads(manifest.read_text(encoding='utf-8'))
            rows.append({
                'model_family_id':data.get('model_family_id',manifest.parent.name),
                'experiment':data.get('experiment','?'),
                'subsystem_id':data.get('subsystem_id','?'),
                'model_dir':str(manifest.parent.relative_to(ROOT)),
                'forecast_horizon_hours':data.get('forecast_horizon_hours'),
                'calibration_hours':data.get('calibration_hours'),
                'algorithm':data.get('algorithm','RidgeQuantileModel'),
                'algorithm_key':data.get('algorithm_key','ridge'),
                'algorithm_params':data.get('algorithm_params',{}),
                'feature_set_version':data.get('feature_set_version'),
                'load_history_start_utc':data.get('load_history_start_utc'),
                'load_history_end_utc':data.get('load_history_end_utc'),
                'weather_modes_seen':data.get('weather_modes_seen',[]),
                'deployment_status':data.get('deployment_status'),
                'requested_train_start':data.get('requested_train_start'),
                'requested_train_end':data.get('requested_train_end'),
                'models_count':len(data.get('models',[])),
                'manifest':data,
            })
        except Exception as e:
            rows.append({'model_family_id':manifest.parent.name,'experiment':'ERROR','subsystem_id':'?','model_dir':str(manifest.parent.relative_to(ROOT)),'error':str(e),'models_count':0})
    return sorted(rows,key=lambda r:(r.get('experiment',''),r.get('model_family_id','')))


def active_model():
    obj=ProjectSetting.objects.filter(key='active_model').first()
    return obj.value if obj else None


def set_active_model(payload:dict):
    obj,_=ProjectSetting.objects.update_or_create(key='active_model',defaults={'value':payload})
    return obj.value
