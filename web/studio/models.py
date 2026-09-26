import uuid
from django.db import models


class PipelineRun(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pendente'),
        ('RUNNING', 'Executando'),
        ('SUCCESS', 'Concluído'),
        ('FAILED', 'Falhou'),
        ('CANCELLED', 'Cancelado'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stage_id = models.CharField(max_length=80)
    stage_label = models.CharField(max_length=180)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='PENDING')
    parameters = models.JSONField(default=dict, blank=True)
    command = models.JSONField(default=list, blank=True)
    log_path = models.CharField(max_length=500, blank=True)
    pid = models.IntegerField(null=True, blank=True)
    return_code = models.IntegerField(null=True, blank=True)
    output_summary = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.stage_label} — {self.status}'


class ProjectSetting(models.Model):
    key = models.CharField(max_length=120, unique=True)
    value = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key
