from pathlib import Path
import json
from django.conf import settings
from .models import ProjectSetting


def project_context(request):
    active = ProjectSetting.objects.filter(key='active_model').first()
    registry_path=Path(settings.PREDICTA_PROJECT_ROOT)/'models/demand/operational_registry.json'
    registry=None
    if registry_path.exists():
        try:registry=json.loads(registry_path.read_text(encoding='utf-8'))
        except Exception:registry=None
    return {
        'project_name': 'Predicta',
        'project_root': str(settings.PREDICTA_PROJECT_ROOT),
        'active_model_global': active.value if active else None,
        'operational_registry_global': registry,
        'pipeline_execution_enabled': settings.PREDICTA_ALLOW_PIPELINE_EXECUTION,
    }
