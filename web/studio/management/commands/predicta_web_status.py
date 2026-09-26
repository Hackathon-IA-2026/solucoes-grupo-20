from django.core.management.base import BaseCommand
from web.studio.services.artifacts import all_artifact_statuses
from web.studio.services.model_registry import scan_model_families, active_model

class Command(BaseCommand):
    help='Show files/models detected by the Predicta web layer.'
    def handle(self,*args,**kwargs):
        self.stdout.write('Artifacts:')
        for a in all_artifact_statuses():
            self.stdout.write(f"  [{'OK' if a['exists'] else '--'}] {a['key']}: {a['path']}")
        self.stdout.write('\nModels:')
        for m in scan_model_families(): self.stdout.write(f"  {m['model_family_id']} {m['experiment']} {m['model_dir']}")
        self.stdout.write(f'\nActive: {active_model()}')
