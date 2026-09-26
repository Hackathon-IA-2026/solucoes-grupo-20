from __future__ import annotations
import subprocess, sys
from pathlib import Path
from django.conf import settings
from web.studio.models import PipelineRun
from .stage_registry import STAGE_MAP


def launch_stage(stage_id:str, parameters:dict):
    if not settings.PREDICTA_ALLOW_PIPELINE_EXECUTION:
        raise PermissionError('Execução de pipeline está desabilitada neste ambiente.')
    stage=STAGE_MAP.get(stage_id)
    if not stage: raise KeyError(stage_id)
    run=PipelineRun.objects.create(stage_id=stage.id,stage_label=stage.title,parameters=parameters)
    log=Path(settings.PREDICTA_RUN_LOG_DIR)/f'{run.id}.log'
    run.log_path=str(log); run.save(update_fields=['log_path'])
    cmd=[sys.executable,'manage.py','run_pipeline_stage',str(run.id)]
    proc=subprocess.Popen(cmd,cwd=settings.PREDICTA_PROJECT_ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    run.pid=proc.pid; run.save(update_fields=['pid'])
    return run
