import uuid
from django.db import migrations, models

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name='PipelineRun',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('stage_id', models.CharField(max_length=80)),
                ('stage_label', models.CharField(max_length=180)),
                ('status', models.CharField(choices=[('PENDING','Pendente'),('RUNNING','Executando'),('SUCCESS','Concluído'),('FAILED','Falhou'),('CANCELLED','Cancelado')], default='PENDING', max_length=16)),
                ('parameters', models.JSONField(blank=True, default=dict)),
                ('command', models.JSONField(blank=True, default=list)),
                ('log_path', models.CharField(blank=True, max_length=500)),
                ('pid', models.IntegerField(blank=True, null=True)),
                ('return_code', models.IntegerField(blank=True, null=True)),
                ('output_summary', models.JSONField(blank=True, default=dict)),
                ('error_message', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={'ordering':['-created_at']},
        ),
        migrations.CreateModel(
            name='ProjectSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=120, unique=True)),
                ('value', models.JSONField(blank=True, default=dict)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
