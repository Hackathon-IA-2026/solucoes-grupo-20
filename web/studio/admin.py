from django.contrib import admin
from .models import PipelineRun, ProjectSetting

@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = ('stage_label','status','created_at','finished_at','return_code')
    list_filter = ('status','stage_id')
    search_fields = ('stage_label','stage_id')

admin.site.register(ProjectSetting)
