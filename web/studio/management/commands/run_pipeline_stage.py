from __future__ import annotations
import json, subprocess
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from web.studio.models import PipelineRun
from web.studio.services.stage_registry import build_command
from web.studio.services.model_registry import active_model

class Command(BaseCommand):
    help='Execute a whitelisted Predicta pipeline stage and persist its status/log.'

    def add_arguments(self, parser):
        parser.add_argument('run_id')

    def handle(self,*args,**opts):
        run=PipelineRun.objects.get(pk=opts['run_id'])
        log_path=Path(run.log_path)
        log_path.parent.mkdir(parents=True,exist_ok=True)
        run.status='RUNNING'; run.started_at=timezone.now(); run.save(update_fields=['status','started_at'])
        try:
            cmd=build_command(run.stage_id,run.parameters,active_model())
            run.command=cmd; run.save(update_fields=['command'])
            with log_path.open('w',encoding='utf-8',buffering=1) as fh:
                fh.write('Predicta Web Pipeline\n')
                fh.write('Stage: '+run.stage_label+'\n')
                fh.write('Command: '+json.dumps(cmd,ensure_ascii=False)+'\n\n')
                proc=subprocess.run(cmd,cwd=settings.PREDICTA_PROJECT_ROOT,stdout=fh,stderr=subprocess.STDOUT,text=True)
            run.return_code=proc.returncode
            run.status='SUCCESS' if proc.returncode==0 else 'FAILED'
            if proc.returncode!=0: run.error_message=f'Etapa terminou com código {proc.returncode}. Consulte o log.'
        except Exception as e:
            run.status='FAILED'; run.return_code=-1; run.error_message=str(e)
            with log_path.open('a',encoding='utf-8') as fh: fh.write('\nERROR: '+str(e)+'\n')
        run.finished_at=timezone.now(); run.save(update_fields=['status','return_code','error_message','finished_at'])
